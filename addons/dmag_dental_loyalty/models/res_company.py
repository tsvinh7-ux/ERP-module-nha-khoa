from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    dmag_loyalty_amount_per_point = fields.Monetary(
        'Số tiền thực thu cho 1 điểm', default=10000.0, currency_field='currency_id',
        help='Ví dụ 10.000 ₫ thực thu = 1 điểm. Tính trên tiền đã thu (không tính công nợ).')
    dmag_loyalty_recall_points = fields.Integer('Điểm tái khám đúng hẹn', default=50)
    dmag_loyalty_recall_tolerance = fields.Integer(
        'Sai lệch cho phép khi tái khám (ngày)', default=14,
        help='Tái khám trong khoảng ± số ngày này quanh ngày hẹn tái khám được tính là đúng hẹn.')
    dmag_loyalty_referrer_points = fields.Integer('Điểm cho người giới thiệu', default=200)
    dmag_loyalty_referee_points = fields.Integer('Điểm cho người được giới thiệu', default=100)
    dmag_loyalty_survey_points = fields.Integer('Điểm hoàn thành khảo sát', default=20)
    dmag_loyalty_point_value = fields.Monetary(
        'Giá trị quy đổi 1 điểm', default=1000.0, currency_field='currency_id',
        help='Khi đổi điểm lấy voucher: giá trị voucher = số điểm × giá trị này.')
    dmag_loyalty_min_redeem = fields.Integer('Số điểm tối thiểu mỗi lần đổi', default=100)
    dmag_loyalty_approval_points = fields.Integer(
        'Đổi trên số điểm này cần Quản lý duyệt', default=1000)
    dmag_loyalty_voucher_days = fields.Integer(
        'Hạn dùng voucher mặc định (ngày)', default=90,
        help='Tối thiểu 7 ngày – cầu chì y đức: không có ưu đãi "chỉ hôm nay".')
    dmag_loyalty_family_pool = fields.Boolean(
        'Ví gia đình: dùng chung hạng và điểm', default=True,
        help='Bệnh nhân trong cùng nhóm gia đình được xét hạng theo tổng thực thu / gắn bó '
             'của cả nhà và dùng chung số dư điểm.')
