"""Liên thông Hệ thống thông tin quốc gia về quản lý kê đơn thuốc (donthuocquocgia.vn).

Căn cứ: QĐ 808/QĐ-BYT (2022), TT 26/2025/TT-BYT. Đường dẫn API và tên trường JSON cấu hình được /
gom trong một phương thức (``_rx_national_payload``) để chỉnh khi Bộ Y tế cập nhật tài liệu.
**Cần xác nhận với tài liệu API bản mới nhất trước khi bật chế độ "Thật".**
"""
import json
import logging
import time
import uuid
from datetime import timedelta

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

SECRET_KEYS = {'password', 'mat_khau', 'token', 'access_token'}
OUTPATIENT = 1      # hinh_thuc_dieu_tri: ngoại trú – CẦN XÁC NHẬN mã giá trị
GENDER_CODES = {'male': 1, 'female': 0, 'other': 2}  # CẦN XÁC NHẬN


def _mask(data):
    if isinstance(data, dict):
        return {k: ('***' if k in SECRET_KEYS else _mask(v)) for k, v in data.items()}
    if isinstance(data, list):
        return [_mask(v) for v in data]
    return data


class DmagRxNationalConfig(models.Model):
    _name = 'dmag.rx.national.config'
    _description = 'Cấu hình liên thông đơn thuốc quốc gia'
    _rec_name = 'company_id'

    company_id = fields.Many2one('res.company', string='Phòng khám', required=True,
                                 default=lambda self: self.env.company, ondelete='cascade')
    enabled = fields.Boolean('Bật liên thông', help='Tắt: đơn đã phát hành nằm trong hàng đợi, '
                                                    'tự gửi khi bật lại.')
    mode = fields.Selection([
        ('mock', 'Giả lập (thử nghiệm / demo)'),
        ('live', 'Kết nối thật'),
    ], string='Chế độ', required=True, default='mock')
    mock_fail = fields.Boolean('Giả lập lỗi gửi đơn', help='Chỉ dùng ở chế độ giả lập để thử luồng lỗi / gửi lại.')
    base_url = fields.Char('Địa chỉ API', required=True, default='https://api.donthuocquocgia.vn')
    path_login_facility = fields.Char('Đường dẫn đăng nhập cơ sở', required=True,
                                      default='/api/auth/dang-nhap-co-so')
    path_login_doctor = fields.Char('Đường dẫn đăng nhập bác sĩ', required=True,
                                    default='/api/auth/dang-nhap-bac-si')
    path_send = fields.Char('Đường dẫn gửi đơn thuốc', required=True, default='/api/v1/gui-don-thuoc')
    path_cancel = fields.Char('Đường dẫn hủy đơn thuốc', default='/api/v1/huy-don-thuoc')
    facility_link_code = fields.Char('Mã liên thông cơ sở')
    facility_password = fields.Char('Mật khẩu liên thông cơ sở', groups='dmag_dental_base.group_dmag_director')
    facility_token = fields.Char('Token cơ sở', copy=False, groups='base.group_system')
    facility_token_expiry = fields.Datetime('Token cơ sở hết hạn', copy=False, groups='base.group_system')
    token_validity_days = fields.Integer('Hiệu lực token (ngày)', default=7)
    timeout = fields.Integer('Thời gian chờ (giây)', default=20)
    max_attempts = fields.Integer('Số lần gửi tối đa (hàng đợi)', default=10)
    log_ids = fields.One2many('dmag.rx.send.log', 'config_id', string='Nhật ký')

    _sql_constraints = [
        ('company_uniq', 'unique(company_id)', 'Mỗi phòng khám chỉ có một cấu hình liên thông đơn thuốc.'),
    ]

    @api.model
    def _get_for_company(self, company):
        return self.sudo().search([('company_id', '=', company.id)], limit=1)

    # ------------------------------------------------------------------ transport
    def _call(self, operation, path, payload, token=None, prescription=None):
        """POST JSON, ghi nhật ký. Trả về (ok, data, error)."""
        self.ensure_one()
        url = (self.base_url or '').rstrip('/') + '/' + (path or '').lstrip('/')
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        if token:
            headers['Authorization'] = f'Bearer {token}'
        started = time.monotonic()
        status, data, error = 0, {}, False
        try:
            if self.mode == 'mock':
                status, data = self._mock_response(operation, payload)
            else:
                response = requests.post(url, data=json.dumps(payload), headers=headers,
                                         timeout=self.timeout or 20)
                status = response.status_code
                try:
                    data = response.json()
                except ValueError:
                    data = {'raw': response.text[:2000]}
        except requests.RequestException as exc:
            error = _('Không kết nối được Hệ thống đơn thuốc quốc gia: %s', exc)
        ok, parse_error = self._parse_response(status, data) if not error else (False, error)
        error = error or parse_error
        self.env['dmag.rx.send.log'].sudo().create({
            'config_id': self.id,
            'company_id': self.company_id.id,
            'prescription_id': prescription.id if prescription else False,
            'operation': operation,
            'url': url,
            'request_body': json.dumps(_mask(payload), ensure_ascii=False, indent=1, default=str),
            'status_code': status,
            'response_body': json.dumps(_mask(data), ensure_ascii=False, indent=1, default=str)[:20000],
            'success': ok,
            'error_message': error or False,
            'duration_ms': int((time.monotonic() - started) * 1000),
        })
        return ok, data, error

    @api.model
    def _parse_response(self, status, data):
        """Đánh giá phản hồi – CẦN XÁC NHẬN cấu trúc phản hồi chính thức."""
        if not 200 <= (status or 0) < 300:
            message = (isinstance(data, dict) and (data.get('message') or data.get('error'))) or ''
            return False, _('HTTP %(status)s: %(msg)s', status=status, msg=message or json.dumps(data)[:500])
        if isinstance(data, dict) and (data.get('success') is False or data.get('error')):
            return False, str(data.get('message') or data.get('error'))
        return True, False

    @api.model
    def _extract_token(self, data):
        if not isinstance(data, dict):
            return False
        inner = data.get('data') if isinstance(data.get('data'), dict) else {}
        return data.get('token') or data.get('access_token') or inner.get('token') or inner.get('access_token')

    def _mock_response(self, operation, payload):
        if operation in ('login_facility', 'login_doctor'):
            return 200, {'success': True, 'token': f'mock-{operation}-{uuid.uuid4().hex[:12]}'}
        if self.mock_fail:
            return 400, {'success': False, 'message': _('Giả lập lỗi: dữ liệu đơn thuốc không hợp lệ.')}
        return 200, {'success': True, 'ma_don_thuoc': payload.get('ma_don_thuoc'),
                     'message': 'Giả lập: đã nhận đơn thuốc.'}

    # ------------------------------------------------------------------ authentication
    def _token_valid(self, expiry):
        return expiry and expiry > fields.Datetime.now() + timedelta(minutes=5)

    def _get_facility_token(self):
        self.ensure_one()
        config = self.sudo()
        if config.facility_token and self._token_valid(config.facility_token_expiry):
            return config.facility_token, False
        if config.mode == 'live' and (not config.facility_link_code or not config.facility_password):
            return False, _('Chưa khai báo mã liên thông / mật khẩu của cơ sở.')
        payload = {'ma_lien_thong_co_so_kham_chua_benh': config.facility_link_code,
                   'password': config.facility_password}
        ok, data, error = config._call('login_facility', config.path_login_facility, payload)
        token = ok and self._extract_token(data)
        if not token:
            return False, error or _('Đăng nhập cơ sở không trả về token.')
        config.write({'facility_token': token,
                      'facility_token_expiry': fields.Datetime.now() + timedelta(days=config.token_validity_days or 7)})
        return token, False

    def _get_doctor_token(self, practitioner):
        self.ensure_one()
        config = self.sudo()
        doctor = practitioner.sudo()
        if doctor.rx_token and self._token_valid(doctor.rx_token_expiry):
            return doctor.rx_token, False
        if config.mode == 'live' and (not doctor.rx_link_code or not doctor.rx_link_password):
            return False, _('Bác sĩ %s chưa khai báo mã liên thông / mật khẩu đơn thuốc quốc gia.', doctor.name)
        facility_token, error = config._get_facility_token()
        if error:
            return False, error
        payload = {'ma_lien_thong_co_so_kham_chua_benh': config.facility_link_code,
                   'ma_lien_thong_bac_si': doctor.rx_link_code,
                   'password': doctor.rx_link_password}
        ok, data, error = config._call('login_doctor', config.path_login_doctor, payload, token=facility_token)
        token = ok and self._extract_token(data)
        if not token:
            return False, error or _('Đăng nhập bác sĩ không trả về token.')
        doctor.write({'rx_token': token,
                      'rx_token_expiry': fields.Datetime.now() + timedelta(days=config.token_validity_days or 7)})
        return token, False

    # ------------------------------------------------------------------ payload
    @api.model
    def _rx_national_payload(self, rx):
        """ÁNH XẠ DUY NHẤT đơn thuốc → JSON "gui-don-thuoc" (QĐ 808/QĐ-BYT).

        Tên trường lấy theo tài liệu hướng dẫn kết nối; mọi chỉnh sửa khi BYT cập nhật
        chỉ cần sửa tại đây. Các giá trị mã hóa (giới tính, hình thức điều trị) CẦN XÁC NHẬN.
        """
        def d(value, fmt='%Y-%m-%d'):
            return value.strftime(fmt) if value else ''

        local_date = fields.Datetime.context_timestamp(rx, rx.date) if rx.date else False
        guardian = rx.companion_name or (rx.patient_id.guardian_id.name if rx.patient_id.guardian_id else '')
        return {
            'ma_don_thuoc': rx.name,
            'loai_don_thuoc': rx.rx_type,
            'hinh_thuc_dieu_tri': OUTPATIENT,
            'ho_ten_benh_nhan': rx.patient_name or '',
            'ngay_sinh_benh_nhan': d(rx.patient_birthdate, '%d/%m/%Y'),
            'can_nang': rx.weight or None,
            'gioi_tinh': GENDER_CODES.get(rx.patient_gender, 2),
            'ma_so_the_bao_hiem_y_te': rx.patient_bhyt or '',
            'thong_tin_nguoi_giam_ho': guardian or '',
            'dia_chi': rx.patient_address or '',
            'chan_doan': [{'ma_chan_doan': diag.code, 'ten_chan_doan': diag.name}
                          for diag in rx.diagnosis_ids] or [{'ma_chan_doan': '', 'ten_chan_doan': rx.diagnosis_text or ''}],
            'luu_y': rx.diagnosis_text or '',
            'hinh_thuc': 1 if not rx.replaced_id else 2,  # 1: kê mới, 2: thay thế – CẦN XÁC NHẬN
            'loi_dan': rx.advice or '',
            'so_dien_thoai_nguoi_kham_benh': rx.patient_phone or '',
            'ngay_tai_kham': d(rx.re_exam_date),
            'ngay_gio_ke_don': d(local_date, '%Y-%m-%d %H:%M:%S'),
            'thong_tin_don_thuoc': [{
                'ma_thuoc': line.drug_id.national_code or '',
                'biet_duoc': line.drug_id.brand_name or '',
                'ten_thuoc': line.drug_id.name,
                'don_vi_tinh': line.unit or line.drug_id.unit or '',
                'cach_dung': line.usage or '',
                'so_luong': line.quantity,
            } for line in rx.line_ids],
        }

    # ------------------------------------------------------------------ operations
    def _send_prescription(self, rx):
        """Gửi một đơn. Trả về (ok, error)."""
        self.ensure_one()
        config = self.sudo()
        rx = rx.sudo()
        token, error = config._get_doctor_token(rx.doctor_id)
        if error:
            config._log_failure('send', error, rx)
            return False, error
        ok, _data, error = config._call('send', config.path_send, config._rx_national_payload(rx),
                                        token=token, prescription=rx)
        if not ok and str(error).startswith('HTTP 401'):  # token hết hạn phía máy chủ → đăng nhập lại lần sau
            rx.doctor_id.sudo().write({'rx_token': False, 'rx_token_expiry': False})
        return ok, error

    def _cancel_prescription(self, rx):
        self.ensure_one()
        config = self.sudo()
        if not config.path_cancel:
            return False, _('Chưa cấu hình đường dẫn hủy đơn.')
        token, error = config._get_doctor_token(rx.doctor_id)
        if error:
            config._log_failure('cancel', error, rx)
            return False, error
        ok, _data, error = config._call('cancel', config.path_cancel, {'ma_don_thuoc': rx.name},
                                        token=token, prescription=rx)
        return ok, error

    def _log_failure(self, operation, error, rx=None):
        self.env['dmag.rx.send.log'].sudo().create({
            'config_id': self.id, 'company_id': self.company_id.id,
            'prescription_id': rx.id if rx else False, 'operation': operation,
            'success': False, 'error_message': error,
        })

    def action_test_connection(self):
        self.ensure_one()
        token, error = self._get_facility_token()
        if error:
            raise UserError(error)
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'type': 'success', 'title': _('Liên thông đơn thuốc'),
                           'message': _('Đăng nhập cơ sở thành công.')}}

    def action_clear_tokens(self):
        self.sudo().write({'facility_token': False, 'facility_token_expiry': False})
        doctors = self.env['dmag.dental.practitioner'].sudo().search([('company_id', 'in', self.company_id.ids)])
        doctors.write({'rx_token': False, 'rx_token_expiry': False})
        return True


class DmagRxSendLog(models.Model):
    _name = 'dmag.rx.send.log'
    _description = 'Nhật ký liên thông đơn thuốc'
    _order = 'id desc'
    _rec_name = 'operation'

    config_id = fields.Many2one('dmag.rx.national.config', ondelete='cascade', index=True)
    company_id = fields.Many2one('res.company', string='Phòng khám', index=True)
    prescription_id = fields.Many2one('dmag.prescription', string='Đơn thuốc', ondelete='set null', index=True)
    operation = fields.Selection([
        ('login_facility', 'Đăng nhập cơ sở'),
        ('login_doctor', 'Đăng nhập bác sĩ'),
        ('send', 'Gửi đơn thuốc'),
        ('cancel', 'Hủy đơn thuốc'),
    ], string='Thao tác', required=True)
    url = fields.Char('Địa chỉ')
    request_body = fields.Text('Dữ liệu gửi (đã che mật khẩu)')
    status_code = fields.Integer('Mã HTTP')
    response_body = fields.Text('Phản hồi')
    success = fields.Boolean('Thành công')
    error_message = fields.Text('Lỗi')
    duration_ms = fields.Integer('Thời gian (ms)')
