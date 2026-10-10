from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    dmag_health_authority = fields.Char(
        'Cơ quan quản lý (Sở Y tế)', default='SỞ Y TẾ',
        help='In ở góc trái tiêu đề bệnh án, ví dụ: SỞ Y TẾ THÀNH PHỐ HÀ NỘI.')
    dmag_record_retention_years = fields.Integer(
        'Thời hạn lưu trữ bệnh án ngoại trú (năm)', default=10,
        help='Số năm lưu trữ hồ sơ bệnh án ngoại trú, tính từ ngày kết thúc lượt khám. '
             'Mặc định 10 năm theo quy định cũ (TT 53/2017/TT-BYT). '
             'CẦN XÁC MINH lại theo Thông tư 33/2025/TT-BYT trước khi vận hành. '
             'Trước hạn này không ai (kể cả Giám đốc) xóa được bệnh án.')
