from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class DmagDentalPractitioner(models.Model):
    _inherit = 'dmag.dental.practitioner'

    mysign_user_id = fields.Char(
        'Tài khoản MySign', tracking=True,
        help='Mã người dùng MySign của bác sĩ (thường là số CCCD / định danh đăng ký với Viettel-CA).')
    mysign_credential_id = fields.Char('Credential ID MySign', readonly=True, copy=False)
    mysign_cert_subject = fields.Char('Chủ thể chứng thư số', readonly=True, copy=False)
    mysign_cert_serial = fields.Char('Số serial chứng thư số', tracking=True, copy=False)
    mysign_cert_valid_to = fields.Datetime('Chứng thư số hiệu lực đến', tracking=True, copy=False)
    mysign_cert_state = fields.Selection([
        ('missing', 'Chưa khai báo'),
        ('valid', 'Còn hiệu lực'),
        ('expiring', 'Sắp hết hạn (< 30 ngày)'),
        ('expired', 'Đã hết hạn'),
    ], string='Tình trạng chứng thư số', compute='_compute_mysign_cert_state')
    mysign_cert_warning = fields.Char('Cảnh báo chứng thư số', compute='_compute_mysign_cert_state')

    @api.depends('mysign_cert_valid_to', 'mysign_user_id')
    def _compute_mysign_cert_state(self):
        now = fields.Datetime.now()
        for practitioner in self:
            valid_to = practitioner.mysign_cert_valid_to
            practitioner.mysign_cert_warning = False
            if not valid_to:
                practitioner.mysign_cert_state = 'missing'
            elif valid_to < now:
                practitioner.mysign_cert_state = 'expired'
                practitioner.mysign_cert_warning = _('Chứng thư số MySign đã hết hạn – không ký được bệnh án.')
            elif valid_to < now + timedelta(days=30):
                practitioner.mysign_cert_state = 'expiring'
                practitioner.mysign_cert_warning = _('Chứng thư số MySign sắp hết hạn – liên hệ Viettel-CA gia hạn.')
            else:
                practitioner.mysign_cert_state = 'valid'

    def action_fetch_mysign_certificate(self):
        """Lấy thông tin chứng thư từ nhà cung cấp ký số của phòng khám."""
        for practitioner in self:
            provider = self.env['dmag.esign.provider']._dmag_get_provider(practitioner.company_id)
            if not provider:
                raise UserError(_('Phòng khám chưa cấu hình nhà cung cấp ký số.'))
            provider._esign_fetch_certificate(practitioner)
        return True
