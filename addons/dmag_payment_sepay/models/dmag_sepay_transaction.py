import hmac
import json
import logging
import re

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import float_compare, float_is_zero

from odoo.addons.dmag_dental_base.models.dmag_access import check_director, is_director, is_manager, is_workflow

from .dmag_payment_log import company_today
from .dmag_payment_request import BUS_CHANNEL, BUS_TYPE

_logger = logging.getLogger(__name__)

ACCOUNTANT_GROUP = 'account.group_account_invoice'


def can_reconcile(env):
    """Đối soát thủ công: Quản lý, Giám đốc hoặc kế toán."""
    return is_manager(env) or env.user.has_group(ACCOUNTANT_GROUP)


class DmagSepayTransaction(models.Model):
    """Giao dịch ngân hàng SePay báo về qua webhook – lưu nguyên payload, không xóa."""
    _name = 'dmag.sepay.transaction'
    _description = 'Giao dịch SePay'
    _inherit = ['mail.thread']
    _order = 'id desc'
    _rec_name = 'display_label'

    sepay_id = fields.Char('Mã giao dịch SePay', index=True, readonly=True)
    company_id = fields.Many2one('res.company', string='Phòng khám', required=True, index=True, readonly=True)
    display_label = fields.Char(compute='_compute_display_label')
    gateway = fields.Char('Ngân hàng', readonly=True)
    transaction_date = fields.Datetime('Thời điểm giao dịch', readonly=True)
    local_date = fields.Date('Ngày giao dịch', index=True, readonly=True)
    account_number = fields.Char('Số tài khoản', readonly=True)
    sub_account = fields.Char('Tài khoản phụ (VA)', readonly=True)
    transfer_type = fields.Selection([('in', 'Tiền vào'), ('out', 'Tiền ra')], string='Loại', readonly=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    amount = fields.Monetary('Số tiền', currency_field='currency_id', readonly=True)
    applied_amount = fields.Monetary('Đã gạch nợ', currency_field='currency_id', readonly=True, tracking=True)
    unapplied_amount = fields.Monetary('Chưa gạch nợ', compute='_compute_unapplied', store=True,
                                       currency_field='currency_id')
    accumulated = fields.Monetary('Số dư lũy kế', currency_field='currency_id', readonly=True)
    code = fields.Char('Mã thanh toán (SePay)', readonly=True)
    parsed_code = fields.Char('Mã nhận diện', readonly=True)
    content = fields.Text('Nội dung chuyển khoản', readonly=True)
    reference_code = fields.Char('Mã tham chiếu ngân hàng', readonly=True)
    description = fields.Text('Mô tả (SMS / ngân hàng)', readonly=True)
    raw_payload = fields.Text('Payload gốc (JSON)', readonly=True)
    request_id = fields.Many2one('dmag.payment.request', string='Yêu cầu thanh toán', readonly=True, index=True)
    visit_id = fields.Many2one('dmag.dental.visit', string='Lượt khám', readonly=True, index=True)
    patient_id = fields.Many2one(related='visit_id.patient_id', string='Bệnh nhân')
    payment_ids = fields.Many2many('account.payment', string='Chứng từ thanh toán', readonly=True,
                                   groups='account.group_account_invoice')
    state = fields.Selection([
        ('new', 'Mới nhận'),
        ('matched', 'Đã gạch nợ'),
        ('unmatched', 'Chờ xử lý'),
        ('duplicate', 'Trùng lặp'),
        ('ignored', 'Bỏ qua'),
    ], string='Trạng thái', default='new', required=True, index=True, readonly=True, tracking=True)
    needs_review = fields.Boolean('Cần xử lý', readonly=True, index=True,
                                  help='Giao dịch chưa khớp, khớp một phần, trả thừa hoặc lỗi khi gạch nợ.')
    message = fields.Text('Kết quả xử lý', readonly=True)
    matched_by_id = fields.Many2one('res.users', string='Người đối soát', readonly=True)
    matched_date = fields.Datetime('Thời điểm đối soát', readonly=True)
    closing_id = fields.Many2one('dmag.cash.closing', string='Biên bản chốt két', readonly=True, index=True)

    def init(self):
        # Idempotency: mỗi id SePay chỉ có một bản ghi "gốc"; các lần gửi lại lưu trạng thái duplicate.
        self.env.cr.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS dmag_sepay_transaction_sepay_id_uniq
            ON dmag_sepay_transaction (sepay_id) WHERE state != 'duplicate' AND sepay_id IS NOT NULL
        """)

    @api.depends('sepay_id', 'amount', 'state')
    def _compute_display_label(self):
        for tx in self:
            tx.display_label = 'SePay #%s – %s' % (tx.sepay_id or tx.id, tx.amount)

    @api.depends('amount', 'applied_amount', 'transfer_type')
    def _compute_unapplied(self):
        for tx in self:
            tx.unapplied_amount = max(tx.amount - tx.applied_amount, 0.0) if tx.transfer_type == 'in' else 0.0

    # ------------------------------------------------------------------ protection
    def write(self, vals):
        if not (is_workflow(self.env) or is_director(self.env)):
            raise AccessError(_('Giao dịch ngân hàng không sửa được. Dùng "Đối soát thủ công" '
                                '(Quản lý / Kế toán) hoặc liên hệ Giám đốc.'))
        return super().write(vals)

    def unlink(self):
        check_director(self.env, _('Giao dịch ngân hàng là chứng cứ đối soát – chỉ Giám đốc / Quản lý cấp cao được xóa.'))
        return super().unlink()

    def _wf_write(self, vals):
        return self.with_context(dmag_workflow=True).write(vals)

    # ------------------------------------------------------------------ webhook entry point
    @api.model
    def _sepay_authenticate(self, auth_header, payload):
        """Trả về cấu hình SePay có API key khớp header (so sánh thời gian hằng), hoặc rỗng."""
        Config = self.env['dmag.sepay.config'].sudo()
        token = (auth_header or '').strip()
        parts = token.split(None, 1)
        if len(parts) == 2 and parts[0].lower() in ('apikey', 'bearer'):
            token = parts[1].strip()
            # Một số thư viện gửi "Bearer Apikey <key>"
            sub = token.split(None, 1)
            if len(sub) == 2 and sub[0].lower() == 'apikey':
                token = sub[1].strip()
        if not token:
            return Config
        matched = Config
        for config in Config.search([('enabled', '=', True)]):
            key = config.api_key or ''
            if key and hmac.compare_digest(key.encode(), token.encode()):
                matched |= config
        if len(matched) > 1 and isinstance(payload, dict):
            acc = str(payload.get('accountNumber') or '')
            sub_acc = str(payload.get('subAccount') or '')
            exact = matched.filtered(lambda c: c.account_number in (acc, sub_acc))
            matched = exact or matched
        return matched[:1]

    @api.model
    def _sepay_handle_webhook(self, auth_header, payload):
        """Xử lý một webhook SePay. Trả về (mã HTTP, dict phản hồi JSON).

        Phải chạy với quyền hệ thống (controller gọi bằng env superuser).
        """
        config = self._sepay_authenticate(auth_header, payload)
        if not config:
            _logger.warning('SePay webhook: sai / thiếu API key')
            return 401, {'success': False, 'message': 'Unauthorized'}
        if not isinstance(payload, dict):
            return 400, {'success': False, 'message': 'Invalid payload'}
        company = config.company_id
        self = self.sudo().with_company(company)
        sepay_id = payload.get('id')
        sepay_id = str(sepay_id) if sepay_id not in (None, '') else False
        vals = self._sepay_prepare_vals(config, payload, sepay_id)
        if sepay_id:
            original = self.search([('sepay_id', '=', sepay_id), ('state', '!=', 'duplicate')], limit=1)
            if original:
                vals.update(state='duplicate', message=_('Trùng giao dịch SePay #%(id)s đã nhận (bản ghi %(rec)s) – bỏ qua.',
                                                         id=sepay_id, rec=original.id))
                self.create(vals)
                return 200, {'success': True, 'message': 'duplicate'}
        tx = self.create(vals)
        tx._sepay_process(config)
        return 200, {'success': True}

    @api.model
    def _sepay_prepare_vals(self, config, payload, sepay_id):
        def num(key):
            try:
                return float(payload.get(key) or 0.0)
            except (TypeError, ValueError):
                return 0.0
        tx_date = config._localize(payload.get('transactionDate')) or fields.Datetime.now()
        transfer_type = str(payload.get('transferType') or '').lower()
        return {
            'sepay_id': sepay_id,
            'company_id': config.company_id.id,
            'gateway': payload.get('gateway'),
            'transaction_date': tx_date,
            'local_date': company_today(config.company_id, tx_date),
            'account_number': payload.get('accountNumber'),
            'sub_account': payload.get('subAccount'),
            'transfer_type': transfer_type if transfer_type in ('in', 'out') else False,
            'amount': num('transferAmount'),
            'accumulated': num('accumulated'),
            'code': payload.get('code'),
            'content': payload.get('content'),
            'reference_code': payload.get('referenceCode'),
            'description': payload.get('description'),
            'raw_payload': json.dumps(payload, ensure_ascii=False, indent=1, default=str),
        }

    def _sepay_candidate_codes(self, config):
        self.ensure_one()
        regex = config._code_regex()
        found = []
        if self.code:
            found += regex.findall(str(self.code).upper())
        for text in (self.content or '', self.description or ''):
            upper = text.upper()
            found += regex.findall(upper)
            # Ngân hàng có thể chèn dấu cách / ký tự lạ vào giữa mã
            found += regex.findall(re.sub(r'[^A-Z0-9]', '', upper))
        return list(dict.fromkeys(found))

    def _sepay_process(self, config):
        self.ensure_one()
        if self.transfer_type != 'in':
            self._wf_write({'state': 'ignored', 'message': _('Giao dịch tiền ra (transferType = %s) – bỏ qua.', self.transfer_type)})
            return
        if float_is_zero(self.amount, precision_rounding=self.currency_id.rounding or 1.0) or self.amount < 0:
            self._wf_write({'state': 'ignored', 'message': _('Số tiền không hợp lệ – bỏ qua.')})
            return
        codes = self._sepay_candidate_codes(config)
        request = self.env['dmag.payment.request']
        if codes:
            request = request.search([('name', 'in', codes), ('company_id', '=', self.company_id.id)],
                                     order='id desc', limit=1)
        self._wf_write({'parsed_code': request.name or (codes[0] if codes else False)})
        if not request:
            self._mark_unmatched(_('Không tìm thấy mã thanh toán hợp lệ trong nội dung chuyển khoản.'))
            return
        self._apply_to_visit(request.visit_id, request, source='sepay', tolerance=config.amount_tolerance)

    def _mark_unmatched(self, message):
        self._wf_write({'state': 'unmatched', 'needs_review': True, 'message': message})
        self._notify_unmatched()

    def _notify_unmatched(self):
        Bus = self.env['bus.bus'].sudo()
        for tx in self:
            Bus._sendone((tx.company_id, BUS_CHANNEL), BUS_TYPE, {
                'event': 'unmatched',
                'transaction_id': tx.id,
                'transaction_amount': tx.amount,
                'message': tx.message,
                'request_id': tx.request_id.id or False,
                'visit_id': tx.visit_id.id or False,
            })

    def _apply_to_visit(self, visit, request=None, amount=None, source='sepay', tolerance=0.0):
        """Gạch nợ lượt khám bằng tiền của giao dịch (tối đa số còn phải thu). Chạy quyền hệ thống."""
        self.ensure_one()
        request = request or self.env['dmag.payment.request']
        available = self.unapplied_amount if amount is None else min(amount, self.unapplied_amount)
        rounding = self.currency_id.rounding or 1.0
        vals = {'request_id': request.id or self.request_id.id, 'visit_id': visit.id}
        if float_is_zero(available, precision_rounding=rounding):
            self._wf_write(dict(vals, state='unmatched', needs_review=True,
                                message=_('Giao dịch không còn số tiền chưa gạch nợ.')))
            return False
        visit_su = visit.sudo().with_company(visit.company_id).with_context(dmag_payment_source=source,
                                                                           dmag_sepay_transaction_id=self.id)
        visit_su.invalidate_recordset(['amount_due', 'payment_status'])
        due = visit_su.amount_due
        if float_compare(due, 0.0, precision_rounding=rounding) <= 0:
            self._wf_write(dict(vals, state='unmatched', needs_review=True,
                                message=_('Lượt khám %s đã thanh toán đủ – khoản tiền này có thể là trả thừa / '
                                          'chuyển nhầm, cần xử lý thủ công.', visit.name)))
            self._notify_unmatched()
            return False
        pay = min(available, due)
        try:
            with self.env.cr.savepoint():
                payment_ids = visit_su.register_payment('transfer', pay, reference=request.name or self.parsed_code
                                                        or self.reference_code or self.sepay_id)
        except (UserError, AccessError) as exc:
            self.env.invalidate_all()
            _logger.warning('SePay: gạch nợ lỗi cho giao dịch %s: %s', self.id, exc)
            self._wf_write(dict(vals, state='unmatched', needs_review=True,
                                message=_('Lỗi khi gạch nợ lượt khám %(visit)s: %(err)s', visit=visit.name, err=exc)))
            self._notify_unmatched()
            return False
        applied = self.applied_amount + pay
        notes = [_('Gạch nợ %(amount)s cho lượt khám %(visit)s.', amount=pay, visit=visit.name)]
        leftover = self.amount - applied
        review = False
        if float_compare(leftover, tolerance or 0.0, precision_rounding=rounding) > 0:
            review = True
            notes.append(_('Còn thừa %s chưa gạch nợ – cần xử lý (hoàn tiền / gạch cho lượt khám khác).', leftover))
        if request:
            request._register_received(pay, tolerance)
            if request.state == 'partial':
                notes.append(_('Khách chuyển thiếu: yêu cầu %(code)s còn %(res)s.', code=request.name, res=request.residual))
        self._wf_write(dict(vals, state='matched', needs_review=review, applied_amount=applied,
                            payment_ids=[(4, pid) for pid in payment_ids], message='\n'.join(notes),
                            matched_date=fields.Datetime.now(),
                            matched_by_id=self.env.uid if source == 'manual_match' else False))
        visit.sudo().message_post(body=_('SePay: nhận chuyển khoản %(amount)s (mã %(code)s, GD #%(id)s).',
                                         amount=self.amount, code=request.name or self.parsed_code or '-',
                                         id=self.sepay_id or self.id))
        if request:
            request._notify_bus(self, event='received')
        else:
            self.env['bus.bus'].sudo()._sendone((visit.company_id, BUS_CHANNEL), BUS_TYPE, {
                'event': 'received', 'transaction_id': self.id, 'transaction_amount': self.amount,
                'message': self.message, 'request_id': False, 'visit_id': visit.id,
                'visit_payment_status': visit_su.payment_status, 'visit_amount_due': visit_su.amount_due,
            })
        return True

    # ------------------------------------------------------------------ UI actions
    def action_open_match_wizard(self):
        self.ensure_one()
        if not can_reconcile(self.env):
            raise AccessError(_('Chỉ Quản lý, Giám đốc hoặc Kế toán được đối soát thủ công.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Đối soát thủ công'),
            'res_model': 'dmag.sepay.match.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_transaction_id': self.id},
        }

    def action_ignore(self):
        if not can_reconcile(self.env):
            raise AccessError(_('Chỉ Quản lý, Giám đốc hoặc Kế toán được đánh dấu bỏ qua giao dịch.'))
        for tx in self:
            if tx.state == 'matched' and not tx.needs_review:
                continue
            tx._wf_write({
                'state': 'ignored' if tx.state != 'matched' else 'matched',
                'needs_review': False,
                'message': (tx.message or '') + '\n' + _('Đánh dấu đã xử lý ngoài hệ thống bởi %s.', self.env.user.name),
                'matched_by_id': self.env.uid,
                'matched_date': fields.Datetime.now(),
            })
        return True
