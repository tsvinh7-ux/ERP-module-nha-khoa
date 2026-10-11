from odoo import _, fields, models

from odoo.addons.dmag_dental_base.models.dmag_access import check_director


class ResCompany(models.Model):
    _inherit = 'res.company'

    # AI-07 – trợ lý Zalo OA
    dmag_ai_zalo_enabled = fields.Boolean(
        'Trợ lý AI nhận tin Zalo OA', default=True,
        help='Tin khách nhắn vào OA (webhook user_send_text) được chuyển cho trợ lý AI-07.')
    dmag_ai_zalo_reply_mode = fields.Selection([
        ('approve', 'Nhân viên duyệt mọi câu'),
        ('script', 'Tự động theo kịch bản đã duyệt (khuyến nghị)'),
        ('auto', 'Tự động hoàn toàn (chỉ Giám đốc bật)'),
    ], string='Trợ lý Zalo trả lời khách', default='script', required=True,
        help='"Theo kịch bản": trợ lý chỉ tự gửi khi tin của khách khớp một kịch bản Giám đốc đã duyệt (độ tin cậy ≥ '
             'ngưỡng) – câu trả lời là mẫu đã duyệt điền dữ liệu thật; còn lại soạn nháp chờ nhân viên duyệt. '
             '"Duyệt mọi câu": mọi câu trả lời nằm chờ ở Hộp thư trợ lý. "Tự động hoàn toàn": AI tự trả lời mọi câu '
             '(trong khuôn khổ quy tắc an toàn) – chỉ Giám đốc bật.')
    dmag_ai_script_threshold = fields.Float(
        'Ngưỡng tin cậy tự gửi theo kịch bản', default=0.6,
        help='Tin của khách khớp kịch bản với độ tin cậy từ ngưỡng này trở lên mới được tự gửi.')
    dmag_ai_escalation_ack = fields.Char(
        'Tin báo đã nhận khi chuyển nhân viên',
        default='Dạ em đã nhận câu hỏi của anh/chị, nhân viên tư vấn sẽ trả lời trong ít phút ạ.',
        help='Mẫu cố định tự gửi một lần khi câu hỏi chưa có kịch bản được chuyển nhân viên duyệt. Để trống = không gửi.')
    dmag_ai_clinic_hours = fields.Char(
        'Ghi chú thêm về giờ làm việc',
        help='Giờ làm việc trợ lý báo khách lấy từ Nha khoa › Cấu hình › Phòng khám › Lịch làm việc; '
             'ô này chỉ để ghi chú thêm (ví dụ: "Ngoài giờ vui lòng gọi hotline").')
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

    def write(self, vals):
        if vals.get('dmag_ai_zalo_reply_mode') == 'auto':
            check_director(self.env, _('Chỉ Giám đốc được bật "Tự động hoàn toàn" cho trợ lý Zalo.'))
        return super().write(vals)
