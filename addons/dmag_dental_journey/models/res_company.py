from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    dmag_cskh_user_id = fields.Many2one('res.users', string='Nhân viên CSKH mặc định',
                                        help='Nhận việc gọi CSKH tự động (không đến, hỏi thăm +24h, nhắc tái khám).')
    dmag_cskh_lead_user_id = fields.Many2one('res.users', string='Trưởng CSKH',
                                             help='Nhận phiếu phàn nàn khi khách chấm NPS ≤ 6.')
    dmag_google_review_url = fields.Char('Link đánh giá Google',
                                         help='Mời khách chấm NPS 9–10 đánh giá phòng khám trên Google.')
    dmag_painless_video_url = fields.Char('Video "quy trình không đau"',
                                          help='Gửi kèm tin nhắc lịch D-1 cho ca thủ thuật.')
    dmag_health_declaration_url = fields.Char('Link khai báo sức khỏe trước khi đến',
                                              help='Gửi kèm tin nhắc lịch trước 2 giờ.')
    dmag_referral_message = fields.Char(
        'Lời mời giới thiệu', default='Giới thiệu người thân đến khám – cả hai cùng nhận ưu đãi chăm sóc răng miệng.')
