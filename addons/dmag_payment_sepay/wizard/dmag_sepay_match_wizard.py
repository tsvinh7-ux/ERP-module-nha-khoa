from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from ..models.dmag_sepay_transaction import can_reconcile


class DmagSepayMatchWizard(models.TransientModel):
    """Đối soát thủ công giao dịch SePay chưa khớp: chọn lượt khám / yêu cầu → gạch nợ."""
    _name = 'dmag.sepay.match.wizard'
    _description = 'Đối soát thủ công giao dịch SePay'

    transaction_id = fields.Many2one('dmag.sepay.transaction', string='Giao dịch', required=True, readonly=True)
    company_id = fields.Many2one(related='transaction_id.company_id')
    currency_id = fields.Many2one(related='transaction_id.currency_id')
    content = fields.Text(related='transaction_id.content')
    unapplied_amount = fields.Monetary(related='transaction_id.unapplied_amount', string='Chưa gạch nợ')
    request_id = fields.Many2one('dmag.payment.request', string='Yêu cầu thanh toán',
                                 domain="[('company_id', '=', company_id), ('state', 'in', ('pending', 'partial', 'expired'))]")
    visit_id = fields.Many2one('dmag.dental.visit', string='Lượt khám',
                               domain="[('company_id', '=', company_id)]")
    visit_amount_due = fields.Monetary(related='visit_id.amount_due', string='Lượt khám còn phải thu')
    amount = fields.Monetary('Số tiền gạch nợ', required=True)
    note = fields.Char('Ghi chú')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        tx = self.env['dmag.sepay.transaction'].browse(res.get('transaction_id'))
        if tx:
            res.setdefault('amount', tx.unapplied_amount)
            if tx.request_id:
                res.setdefault('request_id', tx.request_id.id)
                res.setdefault('visit_id', tx.request_id.visit_id.id)
            elif tx.visit_id:
                res.setdefault('visit_id', tx.visit_id.id)
        return res

    @api.onchange('request_id')
    def _onchange_request_id(self):
        if self.request_id:
            self.visit_id = self.request_id.visit_id

    def action_apply(self):
        self.ensure_one()
        if not can_reconcile(self.env):
            raise AccessError(_('Chỉ Quản lý, Giám đốc hoặc Kế toán được đối soát thủ công.'))
        tx = self.transaction_id.sudo()
        if tx.state in ('duplicate', 'ignored'):
            raise UserError(_('Không đối soát được giao dịch trùng lặp / đã bỏ qua.'))
        visit = self.request_id.visit_id or self.visit_id
        if not visit:
            raise UserError(_('Chọn lượt khám hoặc yêu cầu thanh toán.'))
        if visit.company_id != tx.company_id:
            raise UserError(_('Lượt khám thuộc phòng khám khác giao dịch.'))
        if self.amount <= 0 or self.amount > tx.unapplied_amount + 0.5:
            raise UserError(_('Số tiền gạch nợ không hợp lệ (giao dịch còn %s chưa gạch).', tx.unapplied_amount))
        tx = tx.with_context(dmag_payment_user_id=self.env.uid)
        ok = tx._apply_to_visit(visit, self.request_id.sudo(), amount=self.amount, source='manual_match')
        if not ok:
            raise UserError(tx.message or _('Không gạch nợ được.'))
        tx.with_context(dmag_workflow=True).write({'matched_by_id': self.env.uid})
        tx.message_post(body=_('Đối soát thủ công bởi %(user)s → lượt khám %(visit)s. %(note)s',
                               user=self.env.user.name, visit=visit.name, note=self.note or ''))
        return {'type': 'ir.actions.act_window_close'}
