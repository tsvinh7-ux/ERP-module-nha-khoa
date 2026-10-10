import secrets
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import float_compare

from odoo.addons.dmag_dental_base.models.dmag_access import check_director, is_director, is_workflow

CODE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
CODE_LENGTH = 8
# Trường nhân viên được sửa sau khi tạo (mọi trường khác: quy trình hệ thống / Giám đốc)
STAFF_EDITABLE = {'note'}
BUS_CHANNEL = 'dmag_payment'
BUS_TYPE = 'dmag_payment/update'


class DmagPaymentRequest(models.Model):
    """Yêu cầu thanh toán chuyển khoản (VietQR động qua SePay) cho một lượt khám."""
    _name = 'dmag.payment.request'
    _description = 'Yêu cầu thanh toán'
    _inherit = ['mail.thread']
    _order = 'create_date desc, id desc'

    name = fields.Char('Mã thanh toán', required=True, copy=False, readonly=True, index=True,
                       help='Nằm trong nội dung chuyển khoản; SePay đọc mã này để gạch nợ tự động.')
    company_id = fields.Many2one('res.company', string='Phòng khám', required=True, index=True,
                                 default=lambda self: self.env.company)
    visit_id = fields.Many2one('dmag.dental.visit', string='Lượt khám', required=True, index=True,
                               ondelete='restrict')
    patient_id = fields.Many2one(related='visit_id.patient_id', string='Bệnh nhân', store=True)
    invoice_ids = fields.Many2many('account.move', string='Hóa đơn', copy=False,
                                   groups='account.group_account_invoice')
    currency_id = fields.Many2one(related='company_id.currency_id')
    amount = fields.Monetary('Số tiền yêu cầu', required=True, tracking=True, currency_field='currency_id')
    paid_amount = fields.Monetary('Đã nhận', currency_field='currency_id', copy=False, tracking=True)
    residual = fields.Monetary('Còn thiếu', compute='_compute_residual', currency_field='currency_id')
    state = fields.Selection([
        ('pending', 'Chờ thanh toán'),
        ('partial', 'Thanh toán một phần'),
        ('paid', 'Đã thanh toán'),
        ('expired', 'Hết hạn'),
        ('cancelled', 'Đã hủy'),
    ], string='Trạng thái', default='pending', required=True, tracking=True, index=True, copy=False)
    expiry = fields.Datetime('Hết hạn lúc')
    transfer_content = fields.Char('Nội dung chuyển khoản', compute='_compute_qr')
    qr_url = fields.Char('Ảnh QR', compute='_compute_qr')
    transaction_ids = fields.One2many('dmag.sepay.transaction', 'request_id', string='Giao dịch SePay')
    note = fields.Char('Ghi chú')

    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'Mã thanh toán phải là duy nhất.'),
        ('amount_positive', 'CHECK(amount > 0)', 'Số tiền yêu cầu phải lớn hơn 0.'),
    ]

    @api.depends('amount', 'paid_amount')
    def _compute_residual(self):
        for req in self:
            req.residual = max(req.amount - req.paid_amount, 0.0)

    @api.depends('name', 'amount', 'paid_amount', 'company_id')
    def _compute_qr(self):
        Config = self.env['dmag.sepay.config']
        for req in self:
            req.transfer_content = req.name
            config = Config._get_for_company(req.company_id, raise_if_missing=False) if req.company_id else Config
            req.qr_url = config._build_qr_url(req.residual or req.amount, req.name) if config and req.name else False

    # ------------------------------------------------------------------ CRUD
    @api.model
    def _generate_code(self, company):
        config = self.env['dmag.sepay.config']._get_for_company(company)
        prefix = config.code_prefix.upper()
        for _attempt in range(20):
            code = prefix + ''.join(secrets.choice(CODE_ALPHABET) for _i in range(CODE_LENGTH))
            if not self.sudo().with_context(active_test=False).search_count([('name', '=', code)]):
                return code
        raise UserError(_('Không sinh được mã thanh toán duy nhất, vui lòng thử lại.'))

    @api.model_create_multi
    def create(self, vals_list):
        Visit = self.env['dmag.dental.visit']
        for vals in vals_list:
            visit = Visit.browse(vals.get('visit_id'))
            if not visit.exists():
                raise UserError(_('Yêu cầu thanh toán phải gắn với một lượt khám.'))
            vals['company_id'] = visit.company_id.id
            config = self.env['dmag.sepay.config']._get_for_company(visit.company_id)
            vals.setdefault('expiry', fields.Datetime.now() + timedelta(minutes=config.request_validity or 60))
            vals['name'] = self._generate_code(visit.company_id)
            if not vals.get('invoice_ids'):
                vals['invoice_ids'] = [(6, 0, visit._get_open_invoices().ids)]
            if not (is_director(self.env) or is_workflow(self.env)):
                due = visit.amount_due
                if not vals.get('amount'):
                    vals['amount'] = due
                rounding = visit.currency_id.rounding or 1.0
                if float_compare(vals['amount'], due, precision_rounding=rounding) > 0:
                    raise AccessError(_('Số tiền yêu cầu (%(amount)s) vượt số phải thu của lượt khám (%(due)s). '
                                        'Chỉ Giám đốc / Quản lý cấp cao được điều chỉnh.',
                                        amount=vals['amount'], due=due))
                vals.pop('paid_amount', None)
                vals.pop('state', None)
        return super().create(vals_list)

    def write(self, vals):
        if not (is_workflow(self.env) or is_director(self.env)) and set(vals) - STAFF_EDITABLE:
            raise AccessError(_('Yêu cầu thanh toán đã phát hành không sửa được (số tiền, trạng thái…). '
                                'Hãy hủy và tạo yêu cầu mới, hoặc liên hệ Giám đốc / Quản lý cấp cao.'))
        return super().write(vals)

    def unlink(self):
        check_director(self.env, _('Chỉ Giám đốc / Quản lý cấp cao được xóa yêu cầu thanh toán.'))
        if self.mapped('transaction_ids'):
            raise UserError(_('Không xóa được yêu cầu đã có giao dịch ngân hàng – hãy hủy.'))
        return super().unlink()

    # ------------------------------------------------------------------ actions
    def action_cancel(self):
        for req in self:
            if req.state in ('paid', 'cancelled'):
                continue
            if req.paid_amount and not is_director(self.env):
                raise AccessError(_('Yêu cầu %s đã nhận tiền – chỉ Giám đốc / Quản lý cấp cao được hủy.', req.name))
            req.with_context(dmag_workflow=True).write({'state': 'cancelled'})
            req.message_post(body=_('Hủy yêu cầu thanh toán bởi %s.', self.env.user.name))
        return True

    @api.model
    def _cron_expire(self):
        expired = self.sudo().search([('state', '=', 'pending'), ('expiry', '<', fields.Datetime.now())])
        expired.with_context(dmag_workflow=True).write({'state': 'expired'})
        return True

    def _register_received(self, amount, tolerance=0.0):
        """Cộng tiền đã nhận và cập nhật trạng thái (chạy trong quy trình webhook / đối soát)."""
        for req in self:
            paid = req.paid_amount + amount
            rounding = req.currency_id.rounding or 1.0
            full = float_compare(paid + (tolerance or 0.0), req.amount, precision_rounding=rounding) >= 0
            req.with_context(dmag_workflow=True).write({
                'paid_amount': paid,
                'state': 'paid' if full else 'partial',
            })

    # ------------------------------------------------------------------ UI API
    def _qr_dict(self):
        self.ensure_one()
        config = self.env['dmag.sepay.config']._get_for_company(self.company_id)
        return {
            'request_id': self.id,
            'code': self.name,
            'amount': self.residual or self.amount,
            'qr_url': self.qr_url,
            'bank': config.bank_code,
            'account_number': config.account_number,
            'account_name': config.account_name,
            'content': self.transfer_content,
            'expiry': fields.Datetime.to_string(self.expiry) if self.expiry else False,
            'state': self.state,
            'demo': bool(config.demo_mode),
        }

    def action_simulate_transfer(self, amount=False):
        """Chế độ demo: tạo webhook SePay giả lập đúng định dạng thật cho yêu cầu này (thử toàn bộ luồng)."""
        self.ensure_one()
        config = self.env['dmag.sepay.config'].sudo()._get_for_company(self.company_id)
        if not config.demo_mode:
            raise UserError(_('Chỉ giả lập chuyển khoản được khi bật "Chế độ demo" trong cấu hình SePay.'))
        if self.state not in ('pending', 'partial'):
            raise UserError(_('Yêu cầu thanh toán %s không còn chờ thu.', self.name))
        if not config.api_key:
            config.api_key = secrets.token_urlsafe(24)
        now = fields.Datetime.context_timestamp(self.with_context(tz=config.timezone), fields.Datetime.now())
        payload = {
            'id': 'DEMO-%s-%s' % (self.id, secrets.token_hex(4)),
            'gateway': config.bank_code,
            'transactionDate': now.strftime('%Y-%m-%d %H:%M:%S'),
            'accountNumber': config.account_number,
            'subAccount': None,
            'code': None,
            'content': '%s CHUYEN TIEN KHAM RANG (DEMO)' % (self.transfer_content or self.name),
            'transferType': 'in',
            'description': 'Giả lập chuyển khoản – chế độ demo',
            'transferAmount': amount or self.residual or self.amount,
            'accumulated': 0,
            'referenceCode': 'DEMO%s' % secrets.token_hex(3).upper(),
        }
        status, res = self.env['dmag.sepay.transaction'].sudo()._sepay_handle_webhook('Apikey %s' % config.api_key, payload)
        if status != 200:
            raise UserError(_('Giả lập thất bại: %s', res.get('message')))
        return self.get_status()

    def get_status(self):
        """Trạng thái hiện tại (cùng cấu trúc với thông báo bus) – để màn hình lễ tân hỏi lại khi cần."""
        self.ensure_one()
        visit = self.visit_id
        visit.invalidate_recordset(['amount_due', 'payment_status'])
        return {
            'request_id': self.id,
            'code': self.name,
            'state': self.state,
            'amount': self.amount,
            'paid_amount': self.paid_amount,
            'residual': self.residual,
            'visit_id': visit.id,
            'visit_payment_status': visit.payment_status,
            'visit_amount_due': visit.amount_due,
        }

    def _notify_bus(self, transaction=None, event='received'):
        """Gửi thông báo tới màn hình lễ tân: kênh (res.company, 'dmag_payment'), loại 'dmag_payment/update'."""
        Bus = self.env['bus.bus'].sudo()
        for req in self:
            payload = req.get_status()
            payload.update({
                'event': event,
                'transaction_id': transaction.id if transaction else False,
                'transaction_amount': transaction.amount if transaction else 0.0,
                'message': transaction.message if transaction else '',
            })
            Bus._sendone((req.company_id, BUS_CHANNEL), BUS_TYPE, payload)
