from odoo import fields, models


class DmagDentalProcedure(models.Model):
    _inherit = 'dmag.dental.procedure'

    warranty_card_ids = fields.One2many('dmag.warranty.card', 'procedure_id', string='Thẻ bảo hành')

    def action_done(self):
        todo = self.filtered(lambda p: p.state == 'draft')
        res = super().action_done()
        todo.filtered(lambda p: p.state == 'done')._dmag_create_warranty_cards()
        return res

    def _dmag_create_warranty_cards(self):
        Card = self.env['dmag.warranty.card'].sudo()
        cards = Card.browse()
        for proc in self:
            if proc.product_id.warranty_months > 0 and not proc.warranty_card_ids:
                cards |= Card.create(Card._prepare_from_procedure(proc))
        return cards
