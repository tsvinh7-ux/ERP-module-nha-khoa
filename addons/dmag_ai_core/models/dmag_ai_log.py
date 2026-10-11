from odoo import _, api, fields, models
from odoo.exceptions import AccessError


class DmagAiLog(models.Model):
    """Nhật ký mỗi lần gọi AI – truy vết (ai, khi nào, tính năng gì, cho hồ sơ nào) và chi phí. Không sửa, không xóa."""
    _name = 'dmag.ai.log'
    _description = 'Nhật ký AI'
    _order = 'id desc'

    feature_id = fields.Many2one('dmag.ai.feature', string='Tính năng', required=True, ondelete='restrict', index=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)
    user_id = fields.Many2one('res.users', string='Người dùng', default=lambda self: self.env.user, readonly=True)
    mode = fields.Selection([('simulate', 'Giả lập'), ('live', 'Claude API')], string='Chế độ', required=True)
    model = fields.Char('Mô hình')
    status = fields.Selection([
        ('ok', 'Thành công'), ('error', 'Lỗi'), ('refusal', 'AI từ chối'), ('budget', 'Vượt trần ngân sách'),
    ], string='Kết quả', required=True, default='ok')
    res_model = fields.Char('Đối tượng')
    res_id = fields.Integer('ID đối tượng')
    patient_id = fields.Many2one('res.partner', string='Bệnh nhân', index=True)
    input_tokens = fields.Integer('Token vào')
    output_tokens = fields.Integer('Token ra')
    cache_read_tokens = fields.Integer('Token đọc bộ nhớ đệm')
    tool_calls = fields.Integer('Số lần gọi công cụ')
    cost_usd = fields.Float('Chi phí (USD)', digits=(10, 5))
    cost_vnd = fields.Float('Chi phí (đ)', digits=(12, 0))
    estimated_cost_vnd = fields.Float('Chi phí nếu chạy thật (đ)', digits=(12, 0),
                                      help='Chế độ giả lập: ước tính theo độ dài nội dung và giá công bố.')
    duration_ms = fields.Integer('Thời gian (ms)')
    pseudonymized = fields.Integer('Số thông tin đã ẩn danh')
    request_preview = fields.Text('Nội dung gửi (đã ẩn danh, rút gọn)')
    response_preview = fields.Text('Kết quả (rút gọn)')
    error = fields.Text('Lỗi')
    request_id = fields.Char('Mã yêu cầu API')

    @api.model_create_multi
    def create(self, vals_list):
        return super(DmagAiLog, self.sudo()).create(vals_list)

    def write(self, vals):
        if not self.env.su:
            raise AccessError(_('Nhật ký AI không được sửa.'))
        return super().write(vals)

    def unlink(self):
        if not self.env.su:
            raise AccessError(_('Nhật ký AI không được xóa.'))
        return super().unlink()
