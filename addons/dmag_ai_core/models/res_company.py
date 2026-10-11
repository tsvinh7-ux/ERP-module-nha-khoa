from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    dmag_ai_mode = fields.Selection([
        ('simulate', 'Giả lập (demo – không gọi AI thật, không tốn phí)'),
        ('live', 'Claude API (AI thật – tính phí theo token)'),
    ], string='Chế độ AI', default='simulate', required=True)
    dmag_ai_api_key = fields.Char('Khóa API Claude', groups='dmag_dental_base.group_dmag_director,base.group_system',
                                  copy=False, help='Lấy tại console.anthropic.com → API Keys. Chỉ Giám đốc thấy.')
    dmag_ai_key_set = fields.Boolean('Đã có khóa API', compute='_compute_dmag_ai_key_set')
    dmag_ai_monthly_budget = fields.Float('Trần chi phí AI / tháng (đ)', default=5000000.0,
                                          help='Vượt trần → các tính năng AI tạm dừng tới đầu tháng sau.')
    dmag_ai_usd_rate = fields.Float('Tỷ giá USD → đ (ước tính chi phí)', default=26000.0)
    dmag_ai_require_consent = fields.Boolean('Bắt buộc bệnh nhân đồng ý xử lý bằng AI', default=True)
    dmag_ai_zdr = fields.Boolean('Đã ký thỏa thuận không lưu dữ liệu (ZDR)',
                                 help='Ghi nhận pháp lý: nhà cung cấp API không lưu nội dung gửi đi.')

    def _compute_dmag_ai_key_set(self):
        for company in self:
            company.dmag_ai_key_set = bool(company.sudo().dmag_ai_api_key)
