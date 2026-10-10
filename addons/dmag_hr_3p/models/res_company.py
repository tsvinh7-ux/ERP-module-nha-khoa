from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    dmag_p2_standard_score = fields.Float(
        'Điểm năng lực chuẩn (hệ số P2 = 1)', default=3.0,
        help='Hệ số P2 = điểm năng lực bình quân có trọng số / điểm chuẩn. Ví dụ điểm 3/5 → hệ số 1,0.')
    dmag_kpi_cap = fields.Float(
        'Trần % hoàn thành KPI', default=120.0,
        help='Mỗi KPI được tính tối đa bao nhiêu % mục tiêu khi cộng vào P3.')
    dmag_okr_success = fields.Float(
        'Ngưỡng OKR thành công (%)', default=70.0,
        help='Theo OKR mẫu DMAG: đạt ~70% là thành công → nhận đủ thưởng OKR.')
