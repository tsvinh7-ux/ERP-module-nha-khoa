from odoo import fields, models


class StockLocation(models.Model):
    _inherit = 'stock.location'

    dmag_is_clinical_consumption = fields.Boolean('Tiêu hao lâm sàng (nha khoa)')


class StockPickingType(models.Model):
    _inherit = 'stock.picking.type'

    dmag_is_clinical_consumption = fields.Boolean('Tiêu hao lâm sàng (nha khoa)')


class StockLot(models.Model):
    _inherit = 'stock.lot'

    dmag_patient_id = fields.Many2one('res.partner', string='Bệnh nhân (đã dùng)', readonly=True, index=True,
                                      help='Truy xuất: serial implant / lô vật liệu đã dùng cho bệnh nhân nào.')
    dmag_procedure_id = fields.Many2one('dmag.dental.procedure', string='Thủ thuật', readonly=True)
    dmag_used_date = fields.Datetime('Ngày sử dụng', readonly=True)
