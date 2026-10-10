from odoo import _, fields, models


class DmagDentalVisit(models.Model):
    _inherit = 'dmag.dental.visit'

    lab_order_ids = fields.One2many('dmag.lab.order', 'visit_id', string='Phiếu labo')
    lab_order_count = fields.Integer(compute='_compute_lab_order_count')

    def _compute_lab_order_count(self):
        for visit in self:
            visit.lab_order_count = len(visit.lab_order_ids)

    def action_open_lab_orders(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Phiếu labo'),
            'res_model': 'dmag.lab.order',
            'view_mode': 'tree,form',
            'domain': [('visit_id', '=', self.id)],
            'context': {'default_visit_id': self.id, 'default_patient_id': self.patient_id.id},
        }
