import logging
from datetime import timedelta

import requests

from odoo import _, fields, models
from odoo.modules import module as odoo_module
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

ZALO_OAUTH_URL = 'https://oauth.zaloapp.com/v4/oa/access_token'
ZNS_SEND_URL = 'https://business.openapi.zalo.me/message/template'
SECRET_GROUPS = 'base.group_system,dmag_dental_base.group_dmag_director'


class ResCompany(models.Model):
    _inherit = 'res.company'

    dmag_zns_mode = fields.Selection([
        ('mock', 'Giả lập (không gửi thật – dùng thử / kiểm thử)'),
        ('live', 'Gửi trực tiếp qua Zalo Business API'),
        ('bizapps', 'Ủy quyền cho module Zalo ZNS của Bizapps'),
    ], string='Chế độ gửi ZNS', default='mock', required=True)
    dmag_zalo_oa_id = fields.Char('Zalo OA ID')
    dmag_zalo_app_id = fields.Char('Zalo App ID', groups=SECRET_GROUPS)
    dmag_zalo_app_secret = fields.Char('Zalo App Secret (secret_key)', groups=SECRET_GROUPS)
    dmag_zalo_access_token = fields.Char('Access token OA', groups=SECRET_GROUPS, copy=False)
    dmag_zalo_refresh_token = fields.Char('Refresh token OA', groups=SECRET_GROUPS, copy=False)
    dmag_zalo_token_expiry = fields.Datetime('Access token hết hạn lúc', groups=SECRET_GROUPS, copy=False)
    dmag_zalo_webhook_secret = fields.Char(
        'OA Secret Key (xác thực webhook)', groups=SECRET_GROUPS, copy=False,
        help='Khóa bí mật của OA dùng tính chữ ký X-ZEvent-Signature. Để trống = không xác thực chữ ký.')
    dmag_zalo_webhook_key = fields.Char(
        'Mã định danh webhook', copy=False, groups=SECRET_GROUPS,
        help='Dùng đường dẫn /dmag/zalo/webhook/<mã> khi có nhiều phòng khám / nhiều OA.')
    dmag_zns_dev_mode = fields.Boolean(
        'Chế độ development của ZNS', help='Gửi kèm "mode": "development" (chỉ gửi đến quản trị viên OA, không tính phí).')
    dmag_zns_bizapps_method = fields.Char(
        'Hàm gửi của Bizapps', default='send_zns_template',
        help='Tên hàm trên model biz.zalo.zns được gọi ở chế độ Bizapps (cần xác nhận với Bizapps).')
    dmag_zns_quiet_start = fields.Float('Giờ yên lặng từ', default=21.0)
    dmag_zns_quiet_end = fields.Float('Giờ yên lặng đến', default=7.0)
    dmag_zns_max_retry = fields.Integer('Số lần thử lại tối đa', default=3)

    # ------------------------------------------------------------------ OAuth v4
    def _dmag_zalo_get_access_token(self):
        """Access token còn hạn (tự làm mới bằng refresh token nếu sắp hết hạn)."""
        self.ensure_one()
        company = self.sudo()
        expiry = company.dmag_zalo_token_expiry
        if not company.dmag_zalo_access_token or (
                expiry and expiry <= fields.Datetime.now() + timedelta(minutes=5)):
            company._dmag_zalo_refresh_token()
        if not company.dmag_zalo_access_token:
            raise UserError(_('Chưa cấu hình access token Zalo OA cho phòng khám %s.', company.name))
        return company.dmag_zalo_access_token

    def _dmag_zalo_refresh_token(self):
        """Làm mới access token qua Zalo OAuth v4.

        POST https://oauth.zaloapp.com/v4/oa/access_token
        header ``secret_key``; body (form) ``refresh_token``, ``app_id``, ``grant_type=refresh_token``.
        Refresh token chỉ dùng một lần – lưu lại refresh token mới trả về.
        """
        self.ensure_one()
        company = self.sudo()
        if not (company.dmag_zalo_refresh_token and company.dmag_zalo_app_id and company.dmag_zalo_app_secret):
            raise UserError(_('Thiếu App ID / App Secret / Refresh token Zalo để làm mới access token.'))
        try:
            response = requests.post(ZALO_OAUTH_URL, headers={
                'secret_key': company.dmag_zalo_app_secret,
                'Content-Type': 'application/x-www-form-urlencoded',
            }, data={
                'refresh_token': company.dmag_zalo_refresh_token,
                'app_id': company.dmag_zalo_app_id,
                'grant_type': 'refresh_token',
            }, timeout=20)
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise UserError(_('Không làm mới được token Zalo: %s', exc)) from exc
        if not data.get('access_token'):
            raise UserError(_('Zalo từ chối làm mới token: %s',
                              data.get('error_description') or data.get('error_name') or data))
        try:
            expires_in = int(data.get('expires_in') or 90000)
        except (TypeError, ValueError):
            expires_in = 90000
        company.write({
            'dmag_zalo_access_token': data['access_token'],
            'dmag_zalo_refresh_token': data.get('refresh_token') or company.dmag_zalo_refresh_token,
            'dmag_zalo_token_expiry': fields.Datetime.now() + timedelta(seconds=expires_in),
        })
        _logger.info('Zalo OA access token refreshed for company %s', company.id)
        return True

    def action_dmag_zalo_refresh_token(self):
        for company in self:
            company._dmag_zalo_refresh_token()
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'type': 'success', 'message': _('Đã làm mới access token Zalo OA.')},
        }

    def _cron_dmag_zalo_refresh_tokens(self):
        companies = self.sudo().search([('dmag_zns_mode', '=', 'live'), ('dmag_zalo_refresh_token', '!=', False)])
        for company in companies:
            expiry = company.dmag_zalo_token_expiry
            if expiry and expiry > fields.Datetime.now() + timedelta(hours=2):
                continue
            try:
                company._dmag_zalo_refresh_token()
                if not getattr(odoo_module, 'current_test', False):
                    self.env.cr.commit()  # refresh token chỉ dùng 1 lần – lưu ngay  # pylint: disable=invalid-commit
            except UserError as exc:
                _logger.warning('Zalo token refresh failed for company %s: %s', company.id, exc)
