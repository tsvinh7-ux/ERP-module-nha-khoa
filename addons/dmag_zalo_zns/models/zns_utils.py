"""Tiện ích ZNS: chuẩn hóa số điện thoại, tính tham số mẫu, giờ yên lặng."""
import re
from datetime import datetime, time, timedelta

import pytz

from odoo import fields, models

DEFAULT_TZ = 'Asia/Ho_Chi_Minh'


def normalize_phone(phone):
    """Chuẩn hóa số di động Việt Nam về dạng ZNS ``84xxxxxxxxx``.

    Trả về False nếu không hợp lệ.
    """
    if not phone:
        return False
    digits = re.sub(r'\D', '', str(phone))
    if digits.startswith('0084'):
        digits = digits[2:]
    if digits.startswith('84') and len(digits) in (11, 12):
        pass
    elif digits.startswith('0') and len(digits) in (10, 11):
        digits = '84' + digits[1:]
    elif len(digits) == 9:
        digits = '84' + digits
    else:
        return False
    return digits if len(digits) in (11, 12) else False


def get_tz(env, partner=None):
    name = (partner and partner.tz) or env.user.tz or DEFAULT_TZ
    try:
        return pytz.timezone(name)
    except pytz.UnknownTimeZoneError:
        return pytz.timezone(DEFAULT_TZ)


def to_local(env, value, partner=None):
    """Datetime UTC (naive) → giờ địa phương (naive)."""
    if not value:
        return value
    if isinstance(value, datetime):
        return pytz.utc.localize(value).astimezone(get_tz(env, partner)).replace(tzinfo=None)
    return value


def float_to_time(value):
    hours = int(value) % 24
    minutes = int(round((value - int(value)) * 60)) % 60
    return time(hours, minutes)


def quiet_until(env, company, now=None):
    """Nếu ``now`` nằm trong giờ yên lặng của phòng khám → trả về thời điểm (UTC naive) được gửi lại;
    ngược lại trả về False."""
    now = now or fields.Datetime.now()
    start = company.dmag_zns_quiet_start
    end = company.dmag_zns_quiet_end
    if start == end:
        return False
    tz = get_tz(env)
    local = pytz.utc.localize(now).astimezone(tz)
    hour = local.hour + local.minute / 60.0
    if start > end:  # qua nửa đêm: 21h → 7h
        in_quiet = hour >= start or hour < end
    else:
        in_quiet = start <= hour < end
    if not in_quiet:
        return False
    resume_date = local.date()
    if start > end and hour >= start:
        resume_date += timedelta(days=1)
    resume = tz.localize(datetime.combine(resume_date, float_to_time(end)))
    return resume.astimezone(pytz.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------- expressions
def _format_number(value):
    return '{:,.0f}'.format(value or 0).replace(',', '.')


FILTERS = {
    'time': lambda env, v, p: to_local(env, v, p).strftime('%H:%M') if isinstance(v, datetime) else v,
    'date': lambda env, v, p: (to_local(env, v, p) if isinstance(v, datetime) else v).strftime('%d/%m/%Y')
    if v else '',
    'datetime': lambda env, v, p: to_local(env, v, p).strftime('%H:%M %d/%m/%Y') if isinstance(v, datetime) else v,
    'upper': lambda env, v, p: str(v).upper(),
    'lower': lambda env, v, p: str(v).lower(),
    'title': lambda env, v, p: str(v).title(),
    'money': lambda env, v, p: _format_number(v),
    'int': lambda env, v, p: str(int(v or 0)),
    'first': lambda env, v, p: v[:1] if isinstance(v, models.BaseModel) else v,
    'join': lambda env, v, p: ', '.join(v.mapped('display_name')) if isinstance(v, models.BaseModel) else v,
    'firstname': lambda env, v, p: str(v).split()[-1] if v else '',
}


class ExpressionError(Exception):
    pass


def eval_expression(env, expression, variables, partner=None):
    """Tính một biểu thức tham số ZNS (không dùng eval).

    Cú pháp: ``đường_dẫn[|bộ_lọc...]`` – ví dụ ``patient.name``, ``visit.scheduled_start|time``,
    ``visit.doctor_id.name``, ``company.name``. Chuỗi cố định đặt trong nháy: ``'Nha khoa DMAG'``.
    Nhiều phương án dự phòng: ``visit.doctor_id.name || 'bác sĩ'``.
    """
    for alternative in [a.strip() for a in (expression or '').split('||')]:
        value = _eval_single(env, alternative, variables, partner)
        if value not in (False, None, ''):
            return value
    return ''


def _eval_single(env, expression, variables, partner):
    if not expression:
        return ''
    if len(expression) >= 2 and expression[0] == expression[-1] and expression[0] in '\'"':
        return expression[1:-1]
    parts = [p.strip() for p in expression.split('|')]
    path, filters = parts[0], parts[1:]
    names = path.split('.')
    if names[0] not in variables:
        raise ExpressionError('Biến "%s" không có (dùng: %s)' % (names[0], ', '.join(sorted(variables))))
    value = variables[names[0]]
    for name in names[1:]:
        if value in (None, False):
            return ''
        if isinstance(value, models.BaseModel):
            if name.startswith('_') or (name not in value._fields and name != 'display_name'):
                raise ExpressionError('Trường "%s" không có trên %s' % (name, value._name))
            value = value[:1][name] if value else ''
        elif isinstance(value, dict):
            value = value.get(name, '')
        else:
            raise ExpressionError('Không truy cập được "%s"' % name)
    for flt in filters:
        if flt not in FILTERS:
            raise ExpressionError('Bộ lọc "%s" không hỗ trợ (dùng: %s)' % (flt, ', '.join(sorted(FILTERS))))
        if value in (None, False, ''):
            return ''
        value = FILTERS[flt](env, value, partner)
    if isinstance(value, models.BaseModel):
        value = ', '.join(value.mapped('display_name'))
    elif isinstance(value, datetime):
        value = to_local(env, value, partner).strftime('%H:%M %d/%m/%Y')
    elif hasattr(value, 'strftime'):
        value = value.strftime('%d/%m/%Y')
    elif isinstance(value, float) and value.is_integer():
        value = int(value)
    if value is False or value is None:
        return ''
    return str(value)
