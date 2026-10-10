from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    dental_plan_id = fields.Many2one('dmag.treatment.plan', string='Kế hoạch điều trị', readonly=True, copy=False)
    dental_visit_id = fields.Many2one('dmag.dental.visit', string='Lượt khám', readonly=True, copy=False)
