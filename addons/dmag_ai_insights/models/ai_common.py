"""Tiện ích dùng chung cho AI-13…AI-16: kỳ báo cáo theo lời nói tiếng Việt, chuẩn hóa chuỗi, định dạng số."""
import unicodedata
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo.addons.dmag_dental_goals.models.dmag_goal_dashboard import fmt_value
from odoo.addons.dmag_dental_goals.models.dmag_goal_metrics import METRICS, period_bounds

PERIODS = {
    'today': 'Hôm nay',
    'this_week': 'Tuần này',
    'last_week': 'Tuần trước',
    'this_month': 'Tháng này',
    'last_month': 'Tháng trước',
    'last_month_to_date': 'Tháng trước (cùng thời điểm)',
    'this_quarter': 'Quý này',
    'last_quarter': 'Quý trước',
    'this_year': 'Năm nay',
    'last_7_days': '7 ngày qua',
    'last_30_days': '30 ngày qua',
    'last_90_days': '90 ngày qua',
}
PERIOD_KEYS = list(PERIODS)
METRIC_KEYS = list(METRICS)


def strip_accents(text):
    text = (text or '').lower().replace('đ', 'd')
    text = unicodedata.normalize('NFD', text)
    return ''.join(c for c in text if unicodedata.category(c) != 'Mn')


def resolve_period(key, today):
    """(date_from, date_to, nhãn) cho một kỳ có tên. Kỳ đang chạy kết thúc ở cuối kỳ (số liệu tới hôm nay)."""
    key = key if key in PERIODS else 'this_month'
    if key == 'today':
        d_from = d_to = today
    elif key == 'this_week':
        d_from = today - timedelta(days=today.weekday())
        d_to = d_from + timedelta(days=6)
    elif key == 'last_week':
        d_to = today - timedelta(days=today.weekday() + 1)
        d_from = d_to - timedelta(days=6)
    elif key == 'this_month':
        d_from, d_to = period_bounds('month', today)
    elif key == 'last_month':
        d_from, d_to = period_bounds('month', today.replace(day=1) - timedelta(days=1))
    elif key == 'last_month_to_date':
        d_from = (today.replace(day=1) - relativedelta(months=1))
        d_to = min(d_from + timedelta(days=today.day - 1), period_bounds('month', d_from)[1])
    elif key == 'this_quarter':
        d_from, d_to = period_bounds('quarter', today)
    elif key == 'last_quarter':
        start = period_bounds('quarter', today)[0]
        d_from, d_to = period_bounds('quarter', start - timedelta(days=1))
    elif key == 'this_year':
        d_from, d_to = period_bounds('year', today)
    else:
        days = {'last_7_days': 7, 'last_30_days': 30, 'last_90_days': 90}[key]
        d_to = today
        d_from = today - timedelta(days=days - 1)
    label = PERIODS[key]
    return d_from, d_to, '%s (%s → %s)' % (label, d_from.strftime('%d/%m'), d_to.strftime('%d/%m/%Y'))


def previous_period(key):
    return {
        'this_month': 'last_month_to_date', 'last_month': None, 'this_week': 'last_week',
        'this_quarter': 'last_quarter', 'last_7_days': None, 'last_30_days': None,
    }.get(key)


def fmt(metric_or_unit, value):
    unit = METRICS[metric_or_unit]['unit'] if metric_or_unit in METRICS else metric_or_unit
    return fmt_value(unit, value)


def vnd(value):
    return fmt_value('money', value)
