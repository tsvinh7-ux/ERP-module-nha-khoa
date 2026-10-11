from odoo import fields, models

SOURCES = [
    ('local', 'Tại chỗ (LOCAL)'),
    ('api_vn', 'API trong nước (FPT.AI / Viettel AI)'),
    ('api_llm', 'Mô hình ngôn ngữ qua API (Claude)'),
    ('hybrid', 'Kết hợp'),
]
MODELS = [
    ('claude-opus-5-5', 'Claude Opus 5.5 (mạnh nhất – mặc định)'),
    ('claude-sonnet-5-5', 'Claude Sonnet 5.5 (cân bằng)'),
    ('claude-haiku-5-5', 'Claude Haiku 5.5 (rẻ, nhanh)'),
]


class DmagAiFeature(models.Model):
    """Danh mục tính năng AI – mỗi tính năng bật/tắt và chọn mô hình riêng (AI-00 … AI-19)."""
    _name = 'dmag.ai.feature'
    _description = 'Tính năng AI'
    _order = 'code'

    code = fields.Char('Mã', required=True)
    name = fields.Char('Tính năng', required=True)
    description = fields.Text('Mô tả')
    audience = fields.Selection([
        ('platform', 'Nền tảng'), ('doctor', 'Bác sĩ'), ('front', 'Lễ tân / CSKH'),
        ('manager', 'Quản lý / Giám đốc'), ('patient', 'Khách hàng'),
    ], string='Đối tượng')
    source = fields.Selection(SOURCES, string='Nguồn AI', required=True, default='api_llm')
    model = fields.Selection(MODELS, string='Mô hình Claude', default='claude-opus-5-5')
    effort = fields.Selection([('low', 'Thấp'), ('medium', 'Vừa'), ('high', 'Cao')], string='Mức suy luận',
                              default='medium')
    active = fields.Boolean('Bật', default=True)
    sends_patient_data = fields.Boolean('Có dữ liệu bệnh nhân',
                                        help='Cần đồng ý xử lý bằng AI của bệnh nhân; dữ liệu được ẩn danh trước khi gửi.')
    log_count = fields.Integer('Số lần dùng', compute='_compute_stats')
    cost_month_vnd = fields.Float('Chi phí tháng này (đ)', compute='_compute_stats')

    _sql_constraints = [('code_uniq', 'unique(code)', 'Mã tính năng AI đã tồn tại.')]

    def _compute_stats(self):
        Log = self.env['dmag.ai.log'].sudo()
        month_start = fields.Date.context_today(self).replace(day=1)
        for feature in self:
            logs = Log.search([('feature_id', '=', feature.id)])
            feature.log_count = len(logs)
            feature.cost_month_vnd = sum(logs.filtered(lambda l: l.create_date.date() >= month_start).mapped('cost_vnd'))
