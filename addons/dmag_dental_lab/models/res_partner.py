from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_dental_lab = fields.Boolean('Là labo nha khoa', index=True,
                                   help='Đối tác gia công phục hình (labo). Phiếu labo chỉ chọn được đối tác này.')
    dmag_lab_lead_days = fields.Integer('Thời gian gia công chuẩn (ngày)', default=7,
                                        help='Dùng gợi ý ngày hẹn trả khi gửi phiếu labo.')
