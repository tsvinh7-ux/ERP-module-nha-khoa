from odoo import _, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    warranty_card_ids = fields.One2many('dmag.warranty.card', 'patient_id', string='Thẻ bảo hành')
    warranty_card_count = fields.Integer(compute='_compute_warranty_card_count')

    def _compute_warranty_card_count(self):
        data = self.env['dmag.warranty.card']._read_group(
            [('patient_id', 'in', self.ids)], ['patient_id'], ['__count'])
        counts = {partner.id: count for partner, count in data}
        for partner in self:
            partner.warranty_card_count = counts.get(partner.id, 0)

    def action_open_warranty_cards(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Thẻ bảo hành'),
            'res_model': 'dmag.warranty.card',
            'view_mode': 'tree,form',
            'domain': [('patient_id', '=', self.id)],
            'context': {'create': False},
        }
