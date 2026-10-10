from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare


class DmagDentalVisit(models.Model):
    _inherit = 'dmag.dental.visit'

    payment_request_ids = fields.One2many('dmag.payment.request', 'visit_id', string='Yêu cầu thanh toán')
    payment_log_ids = fields.One2many('dmag.payment.log', 'visit_id', string='Nhật ký thu tiền')

    def register_payment(self, method, amount=False, reference=False):
        """Ghi thêm nhật ký thu tiền (phương thức, số tiền, người thu) để chốt két."""
        payment_ids = super().register_payment(method, amount=amount, reference=reference)
        payments = self.env['account.payment'].sudo().browse(payment_ids)
        ctx = self.env.context
        self.env['dmag.payment.log'].sudo().create({
            'visit_id': self.id,
            'company_id': self.company_id.id,
            'method': method,
            'amount': sum(payments.mapped('amount')) or amount or 0.0,
            'reference': reference or self.name,
            'source': ctx.get('dmag_payment_source') or 'counter',
            'user_id': ctx.get('dmag_payment_user_id') or self.env.uid,
            'payment_ids': [(6, 0, payments.ids)],
            'sepay_transaction_id': ctx.get('dmag_sepay_transaction_id') or False,
        })
        return payment_ids

    def get_payment_qr(self, amount=False):
        """Tạo (hoặc dùng lại) yêu cầu thanh toán VietQR cho số còn phải thu của lượt khám.

        :param amount: tùy chọn – thu trước một phần (≤ số phải thu). Mặc định: toàn bộ ``amount_due``.
        :return: dict {request_id, code, amount, qr_url, bank, account_number, account_name,
                 content, expiry, state}
        """
        self.ensure_one()
        config = self.env['dmag.sepay.config']._get_for_company(self.company_id)
        if self.payment_status == 'to_invoice':
            self._create_and_post_invoices()
            self.invalidate_recordset(['amount_due', 'payment_status'])
        due = self.amount_due
        rounding = self.currency_id.rounding or 1.0
        if float_compare(due, 0.0, precision_rounding=rounding) <= 0:
            raise UserError(_('Lượt khám %s không còn khoản phải thu.', self.name))
        target = amount or due
        Request = self.env['dmag.payment.request']
        pending = Request.search([('visit_id', '=', self.id), ('state', '=', 'pending')])
        now = fields.Datetime.now()
        reuse = pending.filtered(lambda r: (not r.expiry or r.expiry > now)
                                 and float_compare(r.amount, target, precision_rounding=rounding) == 0)[:1]
        (pending - reuse).with_context(dmag_workflow=True).write({'state': 'cancelled'})
        if not reuse:
            reuse = Request.create({'visit_id': self.id, 'amount': target})
            self.message_post(body=_('Tạo mã thanh toán %(code)s – %(amount)s (VietQR / SePay, %(bank)s).',
                                     code=reuse.name, amount=target, bank=config.bank_code))
        return reuse._qr_dict()

    def action_payment_qr(self):
        """Nút trên form lượt khám: mở yêu cầu thanh toán có ảnh QR."""
        self.ensure_one()
        data = self.get_payment_qr()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'dmag.payment.request',
            'res_id': data['request_id'],
            'view_mode': 'form',
            'target': 'new',
            'name': _('Mã QR thanh toán'),
        }
