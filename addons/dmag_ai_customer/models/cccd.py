"""AI-10 – Đọc chuỗi mã QR trên CCCD gắn chip (tại chỗ, không gửi dữ liệu đi đâu).

Định dạng QR mặt trước CCCD gắn chip (Bộ Công an)::

    <số CCCD 12 số>|<số CMND cũ 9 số hoặc trống>|<họ và tên>|<ngày sinh ddmmyyyy>|<giới tính>|<nơi thường trú>|<ngày cấp ddmmyyyy>

Một số thẻ có thêm trường ở cuối (họ tên cha/mẹ…) – bỏ qua. Bản JS tương đương:
``static/src/patches/cccd_parser.js`` (dùng trong hộp thoại "Bệnh nhân mới").
"""
import re
from datetime import date

from odoo import _, api, models
from odoo.exceptions import UserError

# Chuỗi mẫu cho demo – số định danh GIẢ (không thuộc về ai), đúng định dạng.
SAMPLE_QR = ('079190001234|025123456|Nguyễn Thị Minh Anh|15081990|Nữ|'
             '123 Nguyễn Thị Minh Khai, Phường Bến Thành, Quận 1, TP. Hồ Chí Minh|20042021')


def _parse_ddmmyyyy(value):
    value = (value or '').strip()
    if not re.fullmatch(r'\d{8}', value):
        return False
    try:
        return date(int(value[4:]), int(value[2:4]), int(value[:2]))
    except ValueError:
        return False


def parse_cccd_qr(raw):
    """Trả về dict ``citizen_id, old_id, name, birthdate (date), gender ('male'/'female'/False), address,
    issue_date (date)``; ném ``ValueError`` (thông báo tiếng Việt) nếu không đúng định dạng."""
    text = (raw or '').strip().replace('\r', '').replace('\n', '')
    parts = [p.strip() for p in text.split('|')]
    if len(parts) < 6:
        raise ValueError('Không phải mã QR CCCD (cần ít nhất 6 trường, ngăn cách bằng dấu |).')
    citizen_id, old_id, name, birth, sex, address = parts[:6]
    issue = parts[6] if len(parts) > 6 else ''
    if not re.fullmatch(r'\d{12}', citizen_id):
        raise ValueError('Số CCCD phải gồm 12 chữ số.')
    if old_id and not re.fullmatch(r'\d{9}|\d{12}', old_id):
        old_id = ''
    if not name:
        raise ValueError('Mã QR thiếu họ tên.')
    birthdate = _parse_ddmmyyyy(birth)
    if birth and not birthdate:
        raise ValueError('Ngày sinh trong mã QR không hợp lệ (ddmmyyyy).')
    sex_folded = sex.lower()
    gender = 'male' if sex_folded in ('nam', 'male', 'm') else 'female' if sex_folded in ('nữ', 'nu', 'female', 'f') else False
    return {
        'citizen_id': citizen_id,
        'old_id': old_id,
        'name': ' '.join(name.split()),
        'birthdate': birthdate,
        'gender': gender,
        'address': ' '.join(address.split()),
        'issue_date': _parse_ddmmyyyy(issue),
    }


class DmagAiCccd(models.AbstractModel):
    _name = 'dmag.ai.cccd'
    _description = 'Đọc mã QR CCCD (AI-10, tại chỗ)'

    @api.model
    def parse_qr(self, raw):
        if not self.env['dmag.ai'].is_feature_active('AI-10'):
            raise UserError(_('Tính năng "Nhập bệnh nhân từ CCCD" đang tắt.'))
        try:
            data = parse_cccd_qr(raw)
        except ValueError as e:
            raise UserError(str(e)) from e
        for key in ('birthdate', 'issue_date'):
            data[key] = data[key].isoformat() if data[key] else False
        existing = self.env['res.partner'].search([('citizen_id', '=', data['citizen_id'])], limit=1)
        data['existing'] = {'id': existing.id, 'name': existing.name, 'code': existing.patient_code or ''} \
            if existing else False
        return data

    @api.model
    def sample_qr(self):
        return SAMPLE_QR
