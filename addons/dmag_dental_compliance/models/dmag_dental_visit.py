from odoo import fields, models


class DmagDentalVisit(models.Model):
    _inherit = 'dmag.dental.visit'

    sterilization_batch_ids = fields.Many2many(
        'dmag.sterilization.batch', 'dmag_visit_sterilization_rel', 'visit_id', 'batch_id',
        string='Mẻ tiệt khuẩn dụng cụ', domain=[('state', '=', 'released')],
        help='Truy vết dụng cụ: mẻ hấp đã dùng cho lượt khám (TT 16/2018/TT-BYT về kiểm soát nhiễm khuẩn).')
