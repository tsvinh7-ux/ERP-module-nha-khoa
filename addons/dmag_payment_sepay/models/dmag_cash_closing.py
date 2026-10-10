from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import float_is_zero

from odoo.addons.dmag_dental_base.models.dmag_access import check_director, is_director, is_manager, is_workflow

from .dmag_payment_log import company_today

# Trường nhân viên được nhập ở từng bước (mọi thay đổi khác do nút quy trình / Giám đốc)
EDITABLE_BY_STATE = {
    'draft': {'cash_opening', 'cash_counted', 'card_slip_total', 'note', 'shift', 'date', 'diff_reason'},
    'counted': {'diff_reason', 'note'},
}


class DmagCashClosing(models.Model):
    """Chốt két 4 bước: (1) số liệu hệ thống → (2) lễ tân kiểm đếm & ký → (3) thu ngân ký nhận,
    quản lý xác nhận → (4) khóa sổ. Sau xác nhận chỉ Giám đốc được sửa."""
    _name = 'dmag.cash.closing'
    _description = 'Chốt két'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'

    name = fields.Char('Số biên bản', required=True, copy=False, readonly=True, default='/')
    company_id = fields.Many2one('res.company', string='Phòng khám', required=True, index=True,
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    date = fields.Date('Ngày', required=True, default=lambda self: company_today(self.env.company), tracking=True)
    shift = fields.Selection([
        ('morning', 'Ca sáng'),
        ('afternoon', 'Ca chiều'),
        ('evening', 'Ca tối'),
        ('full', 'Cả ngày'),
    ], string='Ca', required=True, default='full', tracking=True)
    state = fields.Selection([
        ('draft', '1. Số liệu hệ thống'),
        ('counted', '2. Đã kiểm đếm'),
        ('confirmed', '3. Đã xác nhận'),
        ('locked', '4. Đã khóa sổ'),
    ], string='Trạng thái', default='draft', required=True, tracking=True, index=True, copy=False)

    log_ids = fields.One2many('dmag.payment.log', 'closing_id', string='Khoản thu trong ca', readonly=True)
    transaction_ids = fields.One2many('dmag.sepay.transaction', 'closing_id', string='Giao dịch SePay', readonly=True)

    system_cash = fields.Monetary('Hệ thống: tiền mặt', compute='_compute_totals', store=True)
    system_transfer = fields.Monetary('Hệ thống: chuyển khoản', compute='_compute_totals', store=True)
    system_card = fields.Monetary('Hệ thống: thẻ', compute='_compute_totals', store=True)
    system_total = fields.Monetary('Hệ thống: tổng thu', compute='_compute_totals', store=True)
    bank_sepay_total = fields.Monetary('Ngân hàng (SePay) báo có', compute='_compute_totals', store=True)

    cash_opening = fields.Monetary('Tiền đầu ca', tracking=True)
    cash_counted = fields.Monetary('Tiền mặt kiểm đếm thực tế', tracking=True)
    card_slip_total = fields.Monetary('Tổng hóa đơn POS / máy quẹt thẻ', tracking=True)
    cash_expected = fields.Monetary('Tiền mặt phải có', compute='_compute_diffs', store=True)
    cash_diff = fields.Monetary('Chênh lệch tiền mặt', compute='_compute_diffs', store=True)
    card_diff = fields.Monetary('Chênh lệch thẻ', compute='_compute_diffs', store=True)
    bank_diff = fields.Monetary('Chênh lệch chuyển khoản', compute='_compute_diffs', store=True,
                                help='Ngân hàng (SePay) báo có – chuyển khoản ghi nhận trên hệ thống. '
                                     'Khác 0: còn giao dịch chưa gạch nợ hoặc thu chuyển khoản không qua SePay.')
    has_difference = fields.Boolean('Có chênh lệch', compute='_compute_diffs', store=True)
    diff_reason = fields.Text('Giải trình chênh lệch', tracking=True)
    note = fields.Text('Ghi chú')

    receptionist_sign_uid = fields.Many2one('res.users', string='Lễ tân bàn giao', readonly=True, copy=False)
    receptionist_sign_date = fields.Datetime('Lễ tân ký lúc', readonly=True, copy=False)
    cashier_sign_uid = fields.Many2one('res.users', string='Thu ngân / thủ quỹ nhận', readonly=True, copy=False)
    cashier_sign_date = fields.Datetime('Thu ngân ký lúc', readonly=True, copy=False)
    confirm_uid = fields.Many2one('res.users', string='Quản lý xác nhận', readonly=True, copy=False)
    confirm_date = fields.Datetime('Xác nhận lúc', readonly=True, copy=False)
    lock_uid = fields.Many2one('res.users', string='Người khóa sổ', readonly=True, copy=False)
    lock_date = fields.Datetime('Khóa sổ lúc', readonly=True, copy=False)

    _sql_constraints = [
        ('company_date_shift_uniq', 'unique(company_id, date, shift)', 'Mỗi ca trong ngày chỉ có một biên bản chốt két.'),
    ]

    # ------------------------------------------------------------------ compute
    @api.depends('log_ids.amount', 'log_ids.method', 'transaction_ids.amount', 'transaction_ids.state')
    def _compute_totals(self):
        for closing in self:
            logs = closing.sudo().log_ids
            closing.system_cash = sum(logs.filtered(lambda l: l.method == 'cash').mapped('amount'))
            closing.system_transfer = sum(logs.filtered(lambda l: l.method == 'transfer').mapped('amount'))
            closing.system_card = sum(logs.filtered(lambda l: l.method == 'card').mapped('amount'))
            closing.system_total = closing.system_cash + closing.system_transfer + closing.system_card
            closing.bank_sepay_total = sum(closing.sudo().transaction_ids.filtered(
                lambda t: t.transfer_type == 'in' and t.state not in ('duplicate', 'ignored')).mapped('amount'))

    @api.depends('system_cash', 'system_transfer', 'system_card', 'bank_sepay_total',
                 'cash_opening', 'cash_counted', 'card_slip_total')
    def _compute_diffs(self):
        for closing in self:
            rounding = closing.currency_id.rounding or 1.0
            closing.cash_expected = closing.cash_opening + closing.system_cash
            closing.cash_diff = closing.cash_counted - closing.cash_expected
            closing.card_diff = closing.card_slip_total - closing.system_card
            closing.bank_diff = closing.bank_sepay_total - closing.system_transfer
            closing.has_difference = any(not float_is_zero(d, precision_rounding=rounding)
                                         for d in (closing.cash_diff, closing.card_diff, closing.bank_diff))

    # ------------------------------------------------------------------ CRUD
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                seq = self.env['ir.sequence'].sudo()
                if vals.get('company_id'):
                    seq = seq.with_company(vals['company_id'])
                vals['name'] = seq.next_by_code('dmag.cash.closing') or '/'
        closings = super().create(vals_list)
        closings.action_refresh()
        return closings

    def write(self, vals):
        if not (is_workflow(self.env) or is_director(self.env)):
            for closing in self:
                allowed = EDITABLE_BY_STATE.get(closing.state, set())
                if closing.state == 'counted' and not is_manager(self.env):
                    allowed = {'note'}
                if set(vals) - allowed:
                    raise AccessError(_('Biên bản %(name)s đang ở bước "%(state)s" – không sửa được. '
                                        'Chỉ Giám đốc / Quản lý cấp cao được sửa biên bản đã ký / xác nhận.',
                                        name=closing.name,
                                        state=dict(self._fields['state'].selection)[closing.state]))
        return super().write(vals)

    def unlink(self):
        check_director(self.env, _('Chỉ Giám đốc / Quản lý cấp cao được xóa biên bản chốt két.'))
        return super().unlink()

    def _wf_write(self, vals):
        return self.with_context(dmag_workflow=True).write(vals)

    # ------------------------------------------------------------------ step 1: system figures
    def action_refresh(self):
        """Gom các khoản thu & giao dịch SePay trong ngày chưa thuộc biên bản nào (ca trước đã chốt)."""
        Log = self.env['dmag.payment.log'].sudo()
        Tx = self.env['dmag.sepay.transaction'].sudo()
        for closing in self:
            if closing.state != 'draft':
                raise UserError(_('Chỉ cập nhật số liệu khi biên bản đang ở bước 1.'))
            logs = Log.search([('company_id', '=', closing.company_id.id), ('local_date', '=', closing.date),
                               ('closing_id', '=', False)])
            txs = Tx.search([('company_id', '=', closing.company_id.id), ('local_date', '=', closing.date),
                             ('closing_id', '=', False), ('transfer_type', '=', 'in'),
                             ('state', 'not in', ('duplicate', 'ignored'))])
            logs.with_context(dmag_workflow=True).write({'closing_id': closing.id})
            txs.with_context(dmag_workflow=True).write({'closing_id': closing.id})
        return True

    # ------------------------------------------------------------------ step 2: receptionist hand-over
    def action_sign_receptionist(self):
        for closing in self:
            if closing.state != 'draft':
                raise UserError(_('Biên bản %s không ở bước kiểm đếm.', closing.name))
            closing.action_refresh()
            closing._wf_write({
                'state': 'counted',
                'receptionist_sign_uid': self.env.uid,
                'receptionist_sign_date': fields.Datetime.now(),
            })
            closing.message_post(body=_('Lễ tân %(user)s ký bàn giao: tiền mặt đếm được %(cash)s, '
                                        'phiếu thẻ %(card)s.', user=self.env.user.name,
                                        cash=closing.cash_counted, card=closing.card_slip_total))
        return True

    # ------------------------------------------------------------------ step 3: cashier + manager
    def action_sign_cashier(self):
        for closing in self:
            if closing.state != 'counted':
                raise UserError(_('Lễ tân cần kiểm đếm và ký bàn giao trước.'))
            if closing.receptionist_sign_uid.id == self.env.uid and not is_director(self.env):
                raise UserError(_('Người nhận bàn giao phải khác người bàn giao.'))
            closing._wf_write({'cashier_sign_uid': self.env.uid, 'cashier_sign_date': fields.Datetime.now()})
            closing.message_post(body=_('Thu ngân / thủ quỹ %s ký nhận bàn giao.', self.env.user.name))
        return True

    def action_confirm(self):
        if not is_manager(self.env):
            raise AccessError(_('Chỉ Quản lý phòng khám trở lên được xác nhận chốt két.'))
        for closing in self:
            if closing.state != 'counted':
                raise UserError(_('Biên bản %s chưa qua bước kiểm đếm.', closing.name))
            if not (closing.receptionist_sign_uid and closing.cashier_sign_uid):
                raise UserError(_('Cần đủ chữ ký bàn giao của lễ tân và thu ngân trước khi xác nhận.'))
            if closing.has_difference and not (closing.diff_reason or '').strip():
                raise UserError(_('Có chênh lệch – nhập "Giải trình chênh lệch" trước khi xác nhận.'))
            closing._wf_write({'state': 'confirmed', 'confirm_uid': self.env.uid,
                               'confirm_date': fields.Datetime.now()})
        return True

    # ------------------------------------------------------------------ step 4: lock
    def action_lock(self):
        if not is_manager(self.env):
            raise AccessError(_('Chỉ Quản lý phòng khám trở lên được khóa sổ.'))
        for closing in self:
            if closing.state != 'confirmed':
                raise UserError(_('Biên bản %s chưa được xác nhận.', closing.name))
            closing._wf_write({'state': 'locked', 'lock_uid': self.env.uid, 'lock_date': fields.Datetime.now()})
        return True

    def action_reopen(self):
        check_director(self.env, _('Chỉ Giám đốc / Quản lý cấp cao được mở lại biên bản chốt két.'))
        for closing in self:
            closing._wf_write({
                'state': 'draft',
                'receptionist_sign_uid': False, 'receptionist_sign_date': False,
                'cashier_sign_uid': False, 'cashier_sign_date': False,
                'confirm_uid': False, 'confirm_date': False,
                'lock_uid': False, 'lock_date': False,
            })
            closing.message_post(body=_('Giám đốc %s mở lại biên bản – các chữ ký đã bị hủy.', self.env.user.name))
        return True

    def action_print(self):
        return self.env.ref('dmag_payment_sepay.action_report_dmag_cash_closing').report_action(self)
