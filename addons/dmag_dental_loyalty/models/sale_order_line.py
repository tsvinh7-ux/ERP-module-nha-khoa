from odoo import fields, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    dmag_loyalty_visit_id = fields.Many2one('dmag.dental.visit', string='Ưu đãi cho lượt khám',
                                            readonly=True, copy=False, index=True)
    dmag_voucher_id = fields.Many2one('dmag.loyalty.voucher', string='Voucher', readonly=True, copy=False)
