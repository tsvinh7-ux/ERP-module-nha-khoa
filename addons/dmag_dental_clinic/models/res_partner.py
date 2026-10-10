from odoo import _, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    dental_visit_ids = fields.One2many('dmag.dental.visit', 'patient_id', string='Lượt khám')
    dental_visit_count = fields.Integer(compute='_compute_dental_counts', string='Số lượt khám')
    dental_plan_count = fields.Integer(compute='_compute_dental_counts', string='Số kế hoạch')
    last_visit_date = fields.Datetime(compute='_compute_dental_counts', string='Lần khám gần nhất')

    def _dmag_has_medical_records(self):
        self.ensure_one()
        return bool(self.env['dmag.dental.visit'].sudo().search_count(
            [('patient_id', '=', self.id), ('state', 'in', ('in_chair', 'done'))], limit=1))

    def _compute_dental_counts(self):
        Visit = self.env['dmag.dental.visit']
        Plan = self.env['dmag.treatment.plan']
        for partner in self:
            if not partner.id or not partner.is_patient:
                partner.dental_visit_count = partner.dental_plan_count = 0
                partner.last_visit_date = False
                continue
            partner.dental_visit_count = Visit.search_count([('patient_id', '=', partner.id)])
            partner.dental_plan_count = Plan.search_count([('patient_id', '=', partner.id)])
            last = Visit.search([('patient_id', '=', partner.id), ('state', '=', 'done')],
                                order='scheduled_start desc', limit=1)
            partner.last_visit_date = last.scheduled_start

    def action_open_dental_visits(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Lượt khám – %s', self.name),
            'res_model': 'dmag.dental.visit',
            'view_mode': 'tree,form,calendar',
            'domain': [('patient_id', '=', self.id)],
            'context': {'default_patient_id': self.id},
        }

    def action_open_dental_plans(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Kế hoạch điều trị – %s', self.name),
            'res_model': 'dmag.treatment.plan',
            'view_mode': 'tree,form',
            'domain': [('patient_id', '=', self.id)],
            'context': {'default_patient_id': self.id},
        }

    def action_open_dental_chart(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sơ đồ răng – %s', self.name),
            'res_model': 'dmag.dental.chart.entry',
            'view_mode': 'tree,form',
            'domain': [('patient_id', '=', self.id)],
            'context': {'default_patient_id': self.id, 'search_default_group_tooth': 1},
        }
