import re
from urllib.parse import urlencode

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

DEFAULT_TZ = 'Asia/Ho_Chi_Minh'
WEBHOOK_PATH = '/dmag/sepay/webhook'


class DmagSepayConfig(models.Model):
    """Cấu hình thu tiền chuyển khoản qua SePay – mỗi phòng khám (công ty) một bản ghi."""
    _name = 'dmag.sepay.config'
    _description = 'Cấu hình SePay'
    _rec_name = 'company_id'

    company_id = fields.Many2one('res.company', string='Phòng khám', required=True,
                                 default=lambda self: self.env.company, ondelete='cascade')
    enabled = fields.Boolean('Bật thu tiền qua SePay', default=True)
    demo_mode = fields.Boolean(
        'Chế độ demo – cho phép giả lập chuyển khoản',
        help='Chỉ dùng khi chạy thử: màn hình thu tiền có nút "Giả lập khách chuyển khoản" – hệ thống tự tạo '
             'một webhook SePay giống thật để thử toàn bộ luồng (gạch nợ, hóa đơn, thông báo). TẮT khi vận hành thật.')
    bank_code = fields.Char('Ngân hàng (mã ngắn SePay)', required=True,
                            help='Tên viết tắt ngân hàng theo danh sách của SePay, '
                                 'ví dụ: MBBank, Vietcombank, ACB, TPBank, BIDV, VietinBank.')
    account_number = fields.Char('Số tài khoản', required=True,
                                 help='Số tài khoản nhận tiền (hoặc tài khoản ảo VA) đã liên kết SePay.')
    account_name = fields.Char('Chủ tài khoản', required=True)
    api_key = fields.Char('API Key webhook', copy=False,
                          groups='dmag_dental_base.group_dmag_director,base.group_system',
                          help='Khóa API khai báo ở SePay (Webhooks → Kiểu chứng thực: API Key). '
                               'SePay gửi header "Authorization: Apikey <khóa>".')
    code_prefix = fields.Char('Tiền tố mã thanh toán', required=True, default='DMAG',
                              help='Mã thanh toán = tiền tố + 8 ký tự ngẫu nhiên, nằm trong nội dung chuyển khoản. '
                                   'Nên trùng với "Cấu trúc mã thanh toán" khai báo trong SePay.')
    amount_tolerance = fields.Monetary('Dung sai số tiền', currency_field='currency_id', default=0.0,
                                       help='Chênh lệch tối đa vẫn coi yêu cầu là "Đã thanh toán đủ".')
    request_validity = fields.Integer('Hiệu lực mã QR (phút)', default=60,
                                      help='Quá hạn thì yêu cầu chuyển "Hết hạn"; tiền về muộn vẫn được '
                                           'đối trừ nếu lượt khám còn nợ.')
    qr_base_url = fields.Char('Địa chỉ tạo ảnh QR', required=True, default='https://qr.sepay.vn/img')
    qr_template = fields.Selection([
        ('compact', 'Gọn (compact)'),
        ('qronly', 'Chỉ mã QR'),
        ('', 'Mặc định'),
    ], string='Mẫu ảnh QR', default='compact')
    timezone = fields.Char('Múi giờ giao dịch', default=DEFAULT_TZ, required=True,
                           help='Múi giờ của trường transactionDate SePay gửi.')
    currency_id = fields.Many2one(related='company_id.currency_id')
    webhook_url = fields.Char('URL webhook khai báo ở SePay', compute='_compute_webhook_url')

    _sql_constraints = [
        ('company_uniq', 'unique(company_id)', 'Mỗi phòng khám chỉ có một cấu hình SePay.'),
    ]

    def _compute_webhook_url(self):
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        for config in self:
            config.webhook_url = base.rstrip('/') + WEBHOOK_PATH

    @api.constrains('code_prefix')
    def _check_prefix(self):
        for config in self:
            if not re.fullmatch(r'[A-Za-z0-9]{2,10}', config.code_prefix or ''):
                raise ValidationError(_('Tiền tố mã thanh toán chỉ gồm 2–10 chữ cái / chữ số, không dấu, không khoảng trắng.'))

    @api.constrains('timezone')
    def _check_timezone(self):
        for config in self:
            if config.timezone not in pytz.all_timezones_set:
                raise ValidationError(_('Múi giờ không hợp lệ: %s', config.timezone))

    @api.model
    def _get_for_company(self, company, raise_if_missing=True):
        config = self.sudo().search([('company_id', '=', company.id), ('enabled', '=', True)], limit=1)
        if not config and raise_if_missing:
            raise UserError(_('Phòng khám %s chưa cấu hình / chưa bật thu tiền qua SePay '
                              '(Nha khoa → Cấu hình → SePay).', company.name))
        return config

    def _build_qr_url(self, amount, content):
        self.ensure_one()
        params = {
            'acc': self.account_number or '',
            'bank': self.bank_code or '',
            'amount': int(round(amount or 0)),
            'des': content or '',
        }
        if self.qr_template:
            params['template'] = self.qr_template
        return '%s?%s' % (self.qr_base_url, urlencode(params))

    def _code_regex(self):
        self.ensure_one()
        return re.compile(re.escape(self.code_prefix.upper()) + r'[A-Z0-9]{8}')

    def _localize(self, dt_str):
        """'YYYY-MM-DD HH:MM:SS' giờ địa phương (SePay) → datetime UTC naive."""
        self.ensure_one()
        if not dt_str:
            return False
        try:
            local = fields.Datetime.to_datetime(str(dt_str)[:19])
        except ValueError:
            return False
        tz = pytz.timezone(self.timezone or DEFAULT_TZ)
        return tz.localize(local).astimezone(pytz.utc).replace(tzinfo=None)
