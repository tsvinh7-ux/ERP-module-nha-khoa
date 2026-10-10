from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    dmag_health_department = fields.Char(
        'Cơ quan quản lý (dòng đầu đơn thuốc)',
        help='Ví dụ: SỞ Y TẾ THÀNH PHỐ HỒ CHÍ MINH – in ở góc trái đầu đơn thuốc theo TT 26/2025/TT-BYT.')
    dmag_rx_allow_controlled = fields.Boolean(
        'Cho phép kê đơn thuốc gây nghiện / hướng thần (N, H)',
        help='Phòng khám nha khoa thông thường không kê đơn "N" / "H". Chỉ bật khi cơ sở đủ điều kiện; '
             'bác sĩ còn phải được đánh dấu "Được kê đơn N/H".')
    dmag_rx_allow_90_days = fields.Boolean(
        'Cho phép kê tối đa 90 ngày cho bệnh mạn tính',
        help='TT 26/2025: tối đa 30 ngày/thuốc; riêng danh mục bệnh mạn tính (Phụ lục VII) được tối đa 90 ngày. '
             'Mặc định tắt.')
