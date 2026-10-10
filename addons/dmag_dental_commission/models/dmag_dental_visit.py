import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class DmagTreatmentPlan(models.Model):
    _inherit = 'dmag.treatment.plan'

    dmag_consultant_id = fields.Many2one('res.users', string='Tư vấn viên', tracking=True)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    dmag_telesale_id = fields.Many2one('res.users', string='Telesale phụ trách')


class DmagDentalVisit(models.Model):
    _inherit = 'dmag.dental.visit'

    dmag_receptionist_id = fields.Many2one('res.users', string='Lễ tân tiếp đón', copy=False,
                                           help='Tự ghi người check-in; dùng cho hoa hồng chốt dịch vụ.')
    dmag_consultant_id = fields.Many2one('res.users', string='Tư vấn viên', copy=False)
    dmag_telesale_id = fields.Many2one('res.users', string='Telesale', copy=False)
    dmag_commission_ids = fields.One2many('dmag.commission.line', 'visit_id', string='Hoa hồng')
    dmag_commission_total = fields.Monetary('Tổng hoa hồng', compute='_compute_dmag_commission_total')

    def _compute_dmag_commission_total(self):
        for visit in self:
            visit.dmag_commission_total = sum(
                visit.sudo().dmag_commission_ids.filtered(lambda l: l.state == 'valid').mapped('amount'))

    def _dmag_journey_event(self, event):
        res = super()._dmag_journey_event(event)
        if event == 'arrived':
            for visit in self.filtered(lambda v: not v.dmag_receptionist_id):
                visit._workflow_write({'dmag_receptionist_id': self.env.uid})
        elif event == 'paid':
            self._dmag_compute_commissions()
        return res

    def action_dmag_recompute_commission(self):
        self._dmag_compute_commissions()
        return True

    # ------------------------------------------------------------------ engine
    def _dmag_compute_commissions(self):
        """Đồng bộ hoa hồng với tiền thực thu – idempotent.

        Với mỗi thủ thuật đã hoàn tất và mỗi người hưởng: số phải hưởng (theo phần đã thu) trừ
        tổng các dòng hợp lệ đã ghi = chênh lệch → sinh dòng dương / âm. Gọi lại nhiều lần không
        sinh trùng; hóa đơn bị đảo → phần thu giảm → dòng âm.
        """
        Line = self.env['dmag.commission.line'].sudo().with_context(dmag_workflow=True)
        Rule = self.env['dmag.commission.rule']
        today = fields.Date.context_today(self)
        for visit in self.sudo():
            procedures = visit.procedure_ids.filtered(lambda p: p.state == 'done' and p.sale_line_id)
            for proc in procedures:
                existing = Line.search([('procedure_id', '=', proc.id)])
                fuse = proc._dmag_ethics_fuse()
                if fuse:
                    to_void = existing.filtered(lambda l: l.state == 'valid')
                    if to_void:
                        to_void.write({'state': 'void', 'void_reason': fuse})
                        visit.message_post(body=_('Hủy hoa hồng thủ thuật %(proc)s – cầu chì y đức: %(reason)s',
                                                  proc=proc.display_name, reason=fuse))
                    elif not existing:
                        visit.message_post(body=_('Không tính hoa hồng thủ thuật %(proc)s – cầu chì y đức: %(reason)s',
                                                  proc=proc.display_name, reason=fuse))
                        _logger.info('Commission fuse on procedure %s: %s', proc.id, fuse)
                    continue
                ratio, taxinc = proc._dmag_collected_ratio()
                for role, ben in proc._dmag_beneficiaries().items():
                    rule = Rule._find_rule(visit.company_id, role, proc.product_id, today)
                    if not rule:
                        continue
                    mine = existing.filtered(lambda l: l.state == 'valid' and l.role == role
                                             and l.user_id == ben['user'] and l.partner_id == ben['partner']
                                             and l.practitioner_id == ben['practitioner'])
                    base, rate, amount = proc._dmag_commission_amount(rule, ratio, taxinc, ben, today)
                    currency = visit.company_id.currency_id
                    delta = currency.round(amount - sum(mine.mapped('amount')))
                    if currency.is_zero(delta):
                        continue
                    Line.create({
                        'name': _('%(role)s – %(proc)s', role=dict(Line._fields['role'].selection)[role],
                                  proc=proc.display_name),
                        'company_id': visit.company_id.id,
                        'date': today,
                        'visit_id': visit.id,
                        'procedure_id': proc.id,
                        'patient_id': visit.patient_id.id,
                        'product_id': proc.product_id.id,
                        'role': role,
                        'rule_id': rule.id,
                        'user_id': ben['user'].id,
                        'practitioner_id': ben['practitioner'].id,
                        'partner_id': ben['partner'].id,
                        'employee_id': ben['employee'].id,
                        'base_amount': currency.round(base - sum(mine.mapped('base_amount'))),
                        'rate': rate,
                        'amount': delta,
                        'kind': 'accrual' if delta > 0 else 'reversal',
                    })
        return True


class DmagDentalProcedure(models.Model):
    _inherit = 'dmag.dental.procedure'

    def _dmag_ethics_fuse(self):
        """Lý do hủy hoa hồng (cầu chì y đức) hoặc False."""
        self.ensure_one()
        plan = self.plan_line_id.plan_id
        if plan and plan.second_opinion_required and not plan.second_opinion_by_id:
            return _('Kế hoạch %s cần bác sĩ thứ hai duyệt chỉ định nhưng chưa có.', plan.name)
        if not plan and self.product_id.requires_second_opinion:
            return _('Dịch vụ %s cần bác sĩ thứ hai duyệt chỉ định nhưng thực hiện ngoài kế hoạch đã duyệt.',
                     self.product_id.name)
        visit = self.visit_id
        if 'dmag_complaint' in visit._fields and visit.dmag_complaint:
            return _('Lượt khám %s có phàn nàn của bệnh nhân.', visit.name)
        return False

    @staticmethod
    def _dmag_paid_ratio(move):
        """Tỷ lệ hóa đơn đã được thanh toán bằng tiền (không tính phần đối trừ với hóa đơn điều chỉnh)."""
        if not move.amount_total:
            return 0.0
        receivables = move.line_ids.filtered(lambda l: l.account_id.account_type == 'asset_receivable')
        if move.move_type == 'out_invoice':
            paid = sum(p.amount for p in receivables.matched_credit_ids
                       if p.credit_move_id.move_id.move_type == 'entry')
            return min(paid / move.amount_total, 1.0)
        # Hóa đơn điều chỉnh giảm: phần không đối trừ với hóa đơn chưa thu là tiền phải trả lại khách
        offset = sum(p.amount for p in receivables.matched_debit_ids
                     if p.debit_move_id.move_id.move_type == 'out_invoice')
        return max(0.0, 1.0 - offset / move.amount_total)

    def _dmag_collected_ratio(self):
        """(tỷ lệ đã thu của thủ thuật 0–1, giá trị thủ thuật gồm thuế)."""
        self.ensure_one()
        sale_line = self.sale_line_id.sudo()
        unit_taxinc = sale_line.price_reduce_taxinc
        delivered = unit_taxinc * sale_line.qty_delivered
        collected = 0.0
        for inv_line in sale_line.invoice_lines.filtered(lambda l: l.move_id.state == 'posted'):
            move = inv_line.move_id
            if move.move_type == 'out_invoice':
                collected += inv_line.price_total * self._dmag_paid_ratio(move)
            elif move.move_type == 'out_refund':
                collected -= inv_line.price_total * self._dmag_paid_ratio(move)
        ratio = max(0.0, min(1.0, collected / delivered)) if delivered else 0.0
        return ratio, unit_taxinc * self.quantity

    def _dmag_beneficiaries(self):
        self.ensure_one()
        visit = self.visit_id
        Users = self.env['res.users']
        Practitioner = self.env['dmag.dental.practitioner']
        Partner = self.env['res.partner']

        def ben(user=Users, practitioner=Practitioner, partner=Partner):
            user = user or practitioner.user_id
            employee = practitioner.sudo().employee_id or user.sudo().employee_ids[:1]
            return {'user': user, 'practitioner': practitioner, 'partner': partner or Partner,
                    'employee': employee}

        result = {}
        if self.doctor_id:
            result['doctor'] = ben(practitioner=self.doctor_id)
        if self.assistant_id:
            result['assistant'] = ben(practitioner=self.assistant_id)
        consultant = self.plan_line_id.plan_id.dmag_consultant_id or visit.dmag_consultant_id
        if consultant:
            result['consultant'] = ben(user=consultant)
        if visit.dmag_receptionist_id:
            result['receptionist'] = ben(user=visit.dmag_receptionist_id)
        telesale = visit.dmag_telesale_id or visit.patient_id.dmag_telesale_id
        if telesale:
            result['telesale'] = ben(user=telesale)
        referrer = visit.patient_id.referrer_id
        if referrer:
            result['referrer'] = ben(user=referrer.user_ids[:1], partner=referrer)
        return result

    def _dmag_commission_amount(self, rule, ratio, taxinc, ben, date):
        """(cơ sở, tỷ lệ %, số tiền phải hưởng lũy kế) cho thủ thuật này."""
        self.ensure_one()
        if rule.basis == 'fixed':
            base = self.quantity * ratio
            return base, 0.0, rule.fixed_amount * base
        if rule.basis == 'revenue':
            base = self.amount * ratio
            return base, rule.rate, base * rule.rate / 100.0
        base = taxinc * ratio
        rate = rule.rate
        if rule.basis == 'tiered':
            month_start = date.replace(day=1)
            others = self.env['dmag.commission.line'].sudo().search([
                ('rule_id', '=', rule.id), ('state', '=', 'valid'), ('date', '>=', month_start),
                ('procedure_id', '!=', self.id),
                ('user_id', '=', ben['user'].id), ('partner_id', '=', ben['partner'].id)])
            rate = rule._tier_rate(sum(others.mapped('base_amount')) + base)
        return base, rate, base * rate / 100.0
