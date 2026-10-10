import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .zns_utils import ExpressionError, eval_expression

JOURNEY_EVENTS = [
    ('booked', 'Đặt lịch'),
    ('confirmed', 'Xác nhận lịch'),
    ('reminder', 'Nhắc lịch'),
    ('arrived', 'Check-in'),
    ('in_chair', 'Lên ghế'),
    ('done', 'Hoàn tất lượt khám'),
    ('cancelled', 'Hủy lịch'),
    ('no_show', 'Không đến'),
    ('signed', 'Ký bệnh án'),
    ('paid', 'Thanh toán'),
    ('nps', 'Khảo sát NPS'),
    ('recall', 'Nhắc tái khám'),
    ('birthday', 'Sinh nhật'),
    ('warranty', 'Bảo hành'),
    ('other', 'Khác'),
]


class DmagZnsTemplate(models.Model):
    """Mẫu ZNS đã đăng ký và được Zalo duyệt (template_id do Zalo cấp)."""
    _name = 'dmag.zns.template'
    _description = 'Mẫu tin Zalo ZNS'
    _order = 'sequence, id'

    name = fields.Char('Tên mẫu', required=True, translate=False)
    code = fields.Char('Mã nội bộ', required=True, index=True,
                       help='Khóa dùng trong code / luật hành trình, ví dụ booking_confirm.')
    sequence = fields.Integer(default=10)
    template_id = fields.Char('Template ID (Zalo)',
                              help='Mã mẫu do Zalo cấp sau khi duyệt. Bắt buộc ở chế độ gửi thật.')
    journey_event = fields.Selection(JOURNEY_EVENTS, string='Điểm chạm hành trình')
    transactional = fields.Boolean(
        'Tin giao dịch (gửi cả giờ yên lặng)',
        help='Tin giao dịch (xác nhận đặt lịch, chào mừng check-in…) được gửi ngay cả trong giờ yên lặng 21h–7h.')
    param_ids = fields.One2many('dmag.zns.template.param', 'template_id', string='Tham số', copy=True)
    preview_text = fields.Text('Nội dung mẫu (xem trước)',
                               help='Nội dung đã đăng ký với Zalo, tham số dạng <customer_name> hoặc {customer_name}.')
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Phòng khám', index=True,
                                 help='Để trống = dùng chung mọi phòng khám.')
    message_count = fields.Integer('Số tin', compute='_compute_message_count')
    note = fields.Text('Ghi chú')

    _sql_constraints = [
        ('code_company_uniq', 'unique(code, company_id)', 'Mã mẫu ZNS đã tồn tại cho phòng khám này.'),
    ]

    def _compute_message_count(self):
        data = self.env['dmag.zns.message'].sudo()._read_group(
            [('template_id', 'in', self.ids)], ['template_id'], ['__count'])
        counts = {tmpl.id: count for tmpl, count in data}
        for tmpl in self:
            tmpl.message_count = counts.get(tmpl.id, 0)

    @api.model
    def _dmag_get(self, key, company=None):
        """Tìm mẫu theo mã nội bộ (ưu tiên mẫu riêng của phòng khám), hoặc trả lại bản ghi truyền vào."""
        if isinstance(key, models.BaseModel):
            return key
        company = company or self.env.company
        if isinstance(key, int):
            return self.browse(key).exists()
        templates = self.sudo().search([('code', '=', key), ('company_id', 'in', (company.id, False))])
        return templates.sorted(lambda t: (not t.company_id, t.sequence))[:1]

    def _build_params(self, variables, partner=None, overrides=None):
        """Tính template_data từ bảng ánh xạ tham số."""
        self.ensure_one()
        data = {}
        for param in self.param_ids:
            try:
                value = eval_expression(self.env, param.expression, variables, partner)
            except ExpressionError as exc:
                raise UserError(_('Mẫu ZNS "%(tmpl)s", tham số %(param)s: %(err)s',
                                  tmpl=self.name, param=param.name, err=exc)) from exc
            if not value and param.default_value:
                value = param.default_value
            if param.max_length and len(value) > param.max_length:
                value = value[:param.max_length]
            data[param.name] = value
        for key, value in (overrides or {}).items():
            data[key] = '' if value in (None, False) else str(value)
        return data

    def _render_preview(self, data):
        self.ensure_one()
        text = self.preview_text or ''

        def repl(match):
            return str(data.get(match.group(1), match.group(0)))
        return re.sub(r'[<{]\s*(\w+)\s*[>}]', repl, text)

    def action_open_messages(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Tin ZNS – %s', self.name),
            'res_model': 'dmag.zns.message',
            'view_mode': 'tree,form',
            'domain': [('template_id', '=', self.id)],
        }


class DmagZnsTemplateParam(models.Model):
    _name = 'dmag.zns.template.param'
    _description = 'Tham số mẫu ZNS'
    _order = 'sequence, id'

    template_id = fields.Many2one('dmag.zns.template', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    name = fields.Char('Tham số Zalo', required=True, help='Tên tham số đúng như mẫu đã đăng ký, ví dụ customer_name.')
    expression = fields.Char(
        'Lấy giá trị từ', required=True,
        help="Đường dẫn trường + bộ lọc: patient.name, visit.scheduled_start|time, visit.scheduled_start|date, "
             "visit.doctor_id.name || 'bác sĩ', company.name, 'chuỗi cố định'. Bộ lọc: time, date, datetime, "
             "upper, lower, title, money, int, first, join, firstname.")
    default_value = fields.Char('Giá trị mặc định')
    max_length = fields.Integer('Độ dài tối đa', default=100,
                                help='Theo giới hạn kiểu tham số Zalo đã duyệt (0 = không cắt).')

    @api.constrains('name')
    def _check_name(self):
        for param in self:
            if not re.fullmatch(r'[A-Za-z0-9_]+', param.name or ''):
                raise ValidationError(_('Tên tham số ZNS chỉ gồm chữ không dấu, số và dấu gạch dưới.'))
