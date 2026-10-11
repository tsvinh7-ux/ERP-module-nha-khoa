from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    # AI-07 – trợ lý Zalo OA
    dmag_ai_zalo_enabled = fields.Boolean(
        'Trợ lý AI nhận tin Zalo OA', default=True,
        help='Tin khách nhắn vào OA (webhook user_send_text) được chuyển cho trợ lý AI-07.')
    dmag_ai_zalo_reply_mode = fields.Selection([
        ('approve', 'Nhân viên duyệt trước khi gửi'),
        ('auto', 'Tự động trả lời 24/7'),
    ], string='Gửi câu trả lời của trợ lý qua Zalo', default='approve', required=True,
        help='"Tự động": trợ lý trả lời ngay trong hội thoại khách chủ động nhắn (giờ hành chính lẫn ngoài giờ). '
             '"Duyệt": câu trả lời nằm chờ ở Hộp thư trợ lý, nhân viên bấm Gửi.')
    dmag_ai_clinic_hours = fields.Char('Giờ làm việc (trợ lý trả lời khách)',
                                       default='Thứ 2 – Chủ nhật: 8:00 – 20:00 (nghỉ trưa 12:00 – 13:00 vẫn nhận khách hẹn trước)')
    dmag_ai_parking_info = fields.Char('Gửi xe', default='Có chỗ gửi xe máy miễn phí trước phòng khám; ô tô gửi bãi lân cận.')
    dmag_ai_payment_info = fields.Char('Thanh toán', default='Tiền mặt, chuyển khoản (quét QR), thẻ; hỗ trợ trả góp 0% cho niềng răng / implant.')
    dmag_ai_preparation_info = fields.Text(
        'Chuẩn bị trước khi khám',
        default='Mang theo CCCD; đơn thuốc đang dùng (nếu có); phim X-quang cũ (nếu có). '
                'Ăn nhẹ trước khi đến nếu làm thủ thuật. Đến sớm 10 phút để làm hồ sơ.')
    # AI-08 / AI-11
    dmag_ai_noshow_threshold = fields.Float('Ngưỡng cảnh báo không đến', default=0.35,
                                            help='Lịch hẹn có xác suất không đến ≥ ngưỡng hiện huy hiệu trên bảng điều phối.')
    dmag_ai_chair_target = fields.Float('Mục tiêu công suất ghế', default=0.75,
                                        help='Gợi ý xếp lịch ưu tiên khung giờ / ghế đang dưới mục tiêu này.')
    # AI-18
    dmag_ai_followup_enabled = fields.Boolean('Tự tạo câu hỏi theo dõi sau thủ thuật', default=True)
