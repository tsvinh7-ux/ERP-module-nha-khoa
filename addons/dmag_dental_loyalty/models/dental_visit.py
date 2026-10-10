from dateutil.relativedelta import relativedelta

from odoo import _, fields, models
from odoo.exceptions import UserError


class DmagDentalVisit(models.Model):
    _inherit = 'dmag.dental.visit'

    dmag_voucher_ids = fields.One2many('dmag.loyalty.voucher', 'used_visit_id', string='Voucher đã áp')
    dmag_care_usage_ids = fields.One2many('dmag.care.usage', 'visit_id', string='Quyền lợi gói đã dùng')
    dmag_patient_tier_id = fields.Many2one(related='patient_id.dmag_tier_id', string='Hạng thành viên')

    # ------------------------------------------------------------------ journey hook
    def _dmag_journey_event(self, event):
        res = super()._dmag_journey_event(event)
        if event == 'paid':
            for visit in self:
                visit._dmag_loyalty_on_paid()
        elif event == 'done':
            for visit in self:
                visit._dmag_loyalty_award_recall()
        return res

    def _dmag_loyalty_on_paid(self):
        """Tích điểm theo thực thu (mỗi khoản thu một lần), thưởng giới thiệu, xét lại hạng."""
        self.ensure_one()
        patient = self.patient_id
        patient._dmag_loyalty_earn_from_invoices(self.sudo().invoice_ids, source=self)
        self._dmag_loyalty_award_referral()
        patient._dmag_loyalty_recompute()
        referrer = patient.sudo().referrer_id
        if referrer.is_patient:
            referrer._dmag_loyalty_recompute()

    def _dmag_loyalty_award_referral(self):
        """Giới thiệu 2 chiều: lượt khám đầu tiên của khách được giới thiệu đã thanh toán đủ
        → người giới thiệu và người được giới thiệu cùng được thưởng, mỗi bên đúng 1 lần."""
        self.ensure_one()
        patient = self.patient_id.sudo()
        referrer = patient.referrer_id
        if not referrer or referrer == patient or self.payment_status != 'paid':
            return
        company = self.company_id
        Ledger = self.env['dmag.loyalty.ledger']
        Ledger._dmag_earn(referrer, 'referral', company.dmag_loyalty_referrer_points, source=patient,
                          key='referral_referrer:%s' % patient.id, company=company,
                          note=_('Giới thiệu thành công: %s', patient.name))
        Ledger._dmag_earn(patient, 'referral', company.dmag_loyalty_referee_points, source=referrer,
                          key='referral_referee:%s' % patient.id, company=company,
                          note=_('Được giới thiệu bởi: %s', referrer.name))

    def _dmag_loyalty_recall_due(self):
        """Ngày hẹn tái khám suy ra từ lượt hoàn tất trước (dịch vụ có chu kỳ tái khám)."""
        self.ensure_one()
        previous = self.sudo().search([
            ('patient_id', '=', self.patient_id.id), ('state', '=', 'done'), ('id', '!=', self.id),
            ('scheduled_start', '<', self.scheduled_start)], order='scheduled_start desc', limit=1)
        if not previous:
            return False
        months = [m for m in previous.procedure_ids.mapped('product_id.recall_months') if m]
        if not months:
            return False
        base = (previous.done_time or previous.scheduled_start).date()
        return base + relativedelta(months=min(months))

    def _dmag_loyalty_award_recall(self):
        self.ensure_one()
        due = self._dmag_loyalty_recall_due()
        if not due:
            return
        company = self.company_id
        actual = (self.checkin_time or self.scheduled_start).date()
        if abs((actual - due).days) <= company.dmag_loyalty_recall_tolerance:
            self.env['dmag.loyalty.ledger']._dmag_earn(
                self.patient_id, 'recall', company.dmag_loyalty_recall_points, source=self,
                key='recall:%s' % self.id, company=company,
                note=_('Tái khám đúng hẹn (%s)', due.strftime('%d/%m/%Y')))

    # ------------------------------------------------------------------ billing
    def _get_lines_to_invoice(self):
        lines = super()._get_lines_to_invoice()
        if not self._origin.id:
            return lines
        extra = self.env['sale.order.line'].sudo().search([('dmag_loyalty_visit_id', '=', self._origin.id)])
        return lines | extra.filtered(lambda l: l.qty_to_invoice and l.state == 'sale')

    def _dmag_amount_to_invoice(self):
        self.ensure_one()
        lines = self._get_lines_to_invoice()
        return sum(line.price_reduce_taxinc * line.qty_to_invoice for line in lines)

    # ------------------------------------------------------------------ voucher
    def dmag_apply_voucher(self, code):
        """Áp voucher vào lượt khám: thêm dòng giảm giá vào đơn bán của lượt (quyền hệ thống).

        Áp trước khi lập hóa đơn. Voucher dùng một lần.
        """
        self.ensure_one()
        code = (code or '').strip().upper()
        Voucher = self.env['dmag.loyalty.voucher'].sudo()
        voucher = Voucher.search([('name', '=', code)], limit=1)
        if not voucher:
            raise UserError(_('Không tìm thấy voucher %s.', code))
        # Khóa dòng voucher để hai quầy không áp trùng cùng lúc
        self.env.cr.execute('SELECT id FROM dmag_loyalty_voucher WHERE id = %s FOR UPDATE NOWAIT', [voucher.id])
        voucher.invalidate_recordset(['state'])
        voucher._check_usable_for(self.patient_id, self.company_id)
        if self.state in ('cancel', 'no_show'):
            raise UserError(_('Lượt khám đã hủy.'))
        lines = self.sudo()._get_lines_to_invoice().filtered(lambda l: not l.dmag_voucher_id)
        base = sum(line.price_reduce_taxinc * line.qty_to_invoice for line in lines)
        base = min(base, self._dmag_amount_to_invoice())
        if base <= 0:
            raise UserError(_('Lượt khám chưa có dịch vụ chờ thanh toán – hãy áp voucher trước khi lập hóa đơn.'))
        amount = voucher._compute_discount_amount(base)
        order = lines[:1].order_id
        product = self.env.ref('dmag_dental_loyalty.product_loyalty_discount')
        line = self.env['sale.order.line'].sudo().create({
            'order_id': order.id,
            'product_id': product.id,
            'name': _('Ưu đãi thành viên – voucher %s', voucher.name),
            'product_uom_qty': 1,
            'price_unit': -amount,
            'tax_id': [(6, 0, lines[:1].tax_id.ids)],
            'dmag_loyalty_visit_id': self.id,
            'dmag_voucher_id': voucher.id,
        })
        voucher.with_context(dmag_workflow=True).write({
            'state': 'used', 'used_visit_id': self.id, 'used_date': fields.Datetime.now(),
            'used_amount': amount, 'sale_line_id': line.id,
        })
        self.message_post(body=_('Áp voucher %(code)s: giảm %(amount)s – người thực hiện: %(user)s',
                                 code=voucher.name, amount=amount, user=self.env.user.name))
        return {'voucher': voucher.name, 'amount': amount, 'amount_due': self._dmag_amount_to_invoice()}

    # ------------------------------------------------------------------ care plan
    def dmag_use_care_entitlement(self, procedure_id):
        """Dùng quyền lợi gói chăm sóc cho một thủ thuật: thủ thuật về 0 đồng, trừ quyền lợi."""
        self.ensure_one()
        proc = self.env['dmag.dental.procedure'].browse(procedure_id).exists()
        if not proc or proc.visit_id != self:
            raise UserError(_('Thủ thuật không thuộc lượt khám này.'))
        if proc.plan_line_id:
            raise UserError(_('Thủ thuật thuộc kế hoạch điều trị (hợp đồng) – không dùng quyền lợi gói.'))
        if self.env['dmag.care.usage'].sudo().search_count([('procedure_id', '=', proc.id)]):
            raise UserError(_('Thủ thuật này đã dùng quyền lợi gói.'))
        sale_line = proc.sudo().sale_line_id
        if sale_line and sale_line.qty_invoiced:
            raise UserError(_('Thủ thuật đã lập hóa đơn – không áp quyền lợi gói được nữa.'))
        subs = self.env['dmag.care.subscription'].sudo().search([
            ('partner_id', '=', self.patient_id.id), ('state', '=', 'active'),
            ('company_id', '=', self.company_id.id)], order='end_date asc')
        entitlement = subs._find_entitlement(proc.product_id, proc.quantity)
        if not entitlement:
            raise UserError(_('Bệnh nhân không còn quyền lợi gói cho dịch vụ "%s".', proc.product_id.name))
        original = proc.price_unit
        usage = self.env['dmag.care.usage'].sudo().create({
            'entitlement_id': entitlement.id,
            'visit_id': self.id,
            'procedure_id': proc.id,
            'quantity': proc.quantity,
            'original_price': original,
        })
        proc.with_context(dmag_workflow=True).sudo().write({'price_unit': 0.0, 'discount': 0.0})
        if sale_line:
            sale_line.write({'price_unit': 0.0, 'discount': 0.0,
                             'name': sale_line.name + _(' (quyền lợi gói %s)', entitlement.subscription_id.name)})
        self.message_post(body=_('Dùng quyền lợi gói %(sub)s cho %(svc)s (giá gốc %(price)s) – người thực hiện: %(user)s',
                                 sub=entitlement.subscription_id.name, svc=proc.product_id.name,
                                 price=original, user=self.env.user.name))
        return {'usage_id': usage.id, 'remaining': entitlement.qty_remaining}

    def action_open_dmag_loyalty_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Ưu đãi thành viên'),
            'res_model': 'dmag.loyalty.visit.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_visit_id': self.id},
        }

    def get_visit_workspace(self):
        res = super().get_visit_workspace()
        patient = self.patient_id.sudo()
        res['loyalty'] = {
            'tier': patient.dmag_tier_id._tier_dict() if patient.dmag_tier_id else False,
            'points': patient._dmag_points_balance(),
        }
        return res
