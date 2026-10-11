"""Danh mục chỉ số mục tiêu + tiện ích kỳ (tháng / quý / năm) – dùng chung cho mô hình, bộ máy tính và bảng điều hành.

Mỗi chỉ số:
* ``kind`` – ``sum``: cộng dồn trong kỳ (doanh thu, số ca…) → có tiến độ, dự báo cuối kỳ theo nhịp hiện tại;
  ``rate``: tỷ lệ / trung bình (tỷ lệ chốt, NPS, thời gian chờ…) → so trực tiếp với mục tiêu.
* ``unit`` – ``money`` / ``count`` / ``pct`` / ``min`` / ``score``.
* ``direction`` – ``higher`` (càng cao càng tốt) / ``lower``.
* ``default`` – chuẩn DMAG dùng khi Giám đốc chưa đặt mục tiêu (chỉ cho chỉ số có chuẩn), hiển thị nhãn "chuẩn DMAG".
* ``formula`` – cách tính, hiển thị cho chủ phòng khám.
"""
from datetime import timedelta

from dateutil.relativedelta import relativedelta

PERIOD_TYPES = [('month', 'Tháng'), ('quarter', 'Quý'), ('year', 'Năm')]
PERIOD_MONTHS = {'month': 1, 'quarter': 3, 'year': 12}

GROUPS = [('north', 'Mục tiêu kinh doanh'), ('journey', 'Hành trình khách hàng'), ('service', 'Chất lượng dịch vụ')]


def _m(label, group, kind, unit, formula, direction='higher', default=None, short=None):
    return {'label': label, 'group': group, 'kind': kind, 'unit': unit, 'formula': formula,
            'direction': direction, 'default': default, 'short': short or label}


METRICS = {
    # ------------------------------------------------------------ mục tiêu kinh doanh (north-star)
    'revenue': _m('Doanh thu dịch vụ', 'north', 'sum', 'money',
                  'Tổng thành tiền các thủ thuật đã hoàn tất, theo ngày của lượt khám (chưa phải tiền đã thu).'),
    'collected': _m('Thực thu', 'north', 'sum', 'money',
                    'Tiền đã thu (tiền mặt, chuyển khoản, quẹt thẻ) theo ngày thu – nhật ký thu tiền.'),
    'new_patients': _m('Khách mới', 'north', 'sum', 'count',
                       'Số lượt khám hoàn tất của khách lần đầu điều trị tại phòng khám.'),
    'implant_cases': _m('Ca implant', 'north', 'sum', 'count',
                        'Số trụ implant đã cấy: thủ thuật nhóm Implant hoàn tất, tính theo số răng.'),
    'ortho_new': _m('Ca chỉnh nha mới', 'north', 'sum', 'count',
                    'Số khách bắt đầu chỉnh nha trong kỳ (thủ thuật chỉnh nha hoàn tất đầu tiên của khách).'),
    'plan_acceptance': _m('Tỷ lệ chốt kế hoạch', 'north', 'rate', 'pct',
                          'Kế hoạch được khách đồng ý / kế hoạch đã tư vấn (theo ngày lập kế hoạch).',
                          default=60.0, short='Chốt kế hoạch'),
    'gross_profit': _m('Lợi nhuận gộp', 'north', 'sum', 'money',
                       'Doanh thu dịch vụ − vật tư tiêu hao − chi phí labo − hoa hồng / thủ thuật phí.'),
    # ------------------------------------------------------------ hành trình khách hàng
    'booked': _m('Lịch hẹn', 'journey', 'sum', 'count',
                 'Số lịch hẹn có giờ hẹn trong kỳ (không tính lịch đã hủy).'),
    'show_up_rate': _m('Tỷ lệ đến khám (show-up)', 'journey', 'rate', 'pct',
                       'Lượt đã đến / (lượt đã đến + không đến), lịch hẹn trong kỳ.', default=85.0,
                       short='Đến khám'),
    'consult_rate': _m('Tỷ lệ được tư vấn kế hoạch', 'journey', 'rate', 'pct',
                       'Khách được tư vấn kế hoạch điều trị / khách đã đến khám trong kỳ.', short='Được tư vấn'),
    'completion_rate': _m('Tỷ lệ hoàn tất điều trị', 'journey', 'rate', 'pct',
                          'Kế hoạch đã hoàn thành / kế hoạch đã chốt (cùng nhóm kế hoạch lập trong kỳ).',
                          short='Hoàn tất'),
    'return_rate': _m('Tái khám đúng hẹn', 'journey', 'rate', 'pct',
                      'Khách cũ đến đúng lịch hẹn: lượt đã đến / (đã đến + không đến) của khách đã từng điều trị.',
                      short='Tái khám đúng hẹn'),
    'referral_rate': _m('Tỷ lệ khách mới do giới thiệu', 'journey', 'rate', 'pct',
                        'Khách mới có người giới thiệu hoặc nguồn "giới thiệu" / tổng khách mới.',
                        short='Giới thiệu'),
    # ------------------------------------------------------------ chất lượng dịch vụ / vận hành
    'avg_wait': _m('Thời gian chờ trung bình', 'service', 'rate', 'min',
                   'Trung bình (giờ lên ghế − giờ check-in) của lượt đã điều trị.', direction='lower',
                   default=15.0),
    'chair_util_am': _m('Công suất ghế buổi sáng', 'service', 'rate', 'pct',
                        'Phút ghế có lịch 08:00–12:00 / (số ghế × ngày làm việc đã qua × 240 phút).'),
    'chair_util_pm': _m('Công suất ghế buổi chiều', 'service', 'rate', 'pct',
                        'Phút ghế có lịch 13:30–16:30 / (số ghế × ngày làm việc đã qua × 180 phút).',
                        default=65.0),
    'nps': _m('NPS sau điều trị', 'service', 'rate', 'score',
              '% khách ủng hộ (9–10 điểm) − % khách không hài lòng (0–6 điểm), thang −100…100.', default=50.0),
    'complaint_rate': _m('Tỷ lệ khiếu nại', 'service', 'rate', 'pct',
                         'Phiếu phàn nàn / lượt khám hoàn tất trong kỳ.', direction='lower', default=2.0),
    'associate_share': _m('Ca do bác sĩ phụ đảm nhận', 'service', 'rate', 'pct',
                          'Thủ thuật do bác sĩ bậc 1–2 thực hiện / tổng thủ thuật hoàn tất.', default=50.0),
    'cogs_ratio': _m('Giá vốn vật tư + labo / doanh thu', 'service', 'rate', 'pct',
                     '(Vật tư tiêu hao + chi phí labo) / doanh thu dịch vụ.', direction='lower', default=22.0),
}

NORTH_STAR = ['revenue', 'collected', 'new_patients', 'implant_cases', 'ortho_new', 'plan_acceptance',
              'gross_profit']
FUNNEL = ['booked', 'show_up_rate', 'consult_rate', 'plan_acceptance', 'completion_rate']
AFTER_CARE = ['return_rate', 'referral_rate']
SERVICE = ['avg_wait', 'chair_util_am', 'chair_util_pm', 'nps', 'complaint_rate', 'associate_share', 'cogs_ratio']

METRIC_SELECTION = [(key, vals['label']) for key, vals in METRICS.items()]

UNIT_LABELS = {'money': '₫', 'count': '', 'pct': '%', 'min': 'phút', 'score': 'điểm'}


# ---------------------------------------------------------------------------- periods
def period_start(period_type, day):
    if period_type == 'year':
        return day.replace(month=1, day=1)
    if period_type == 'quarter':
        return day.replace(month=((day.month - 1) // 3) * 3 + 1, day=1)
    return day.replace(day=1)


def period_bounds(period_type, day):
    start = period_start(period_type, day)
    end = start + relativedelta(months=PERIOD_MONTHS[period_type]) - timedelta(days=1)
    return start, end


def shift_period(period_type, start, count):
    return start + relativedelta(months=PERIOD_MONTHS[period_type] * count)


def period_label(period_type, start):
    if period_type == 'year':
        return 'Năm %s' % start.year
    if period_type == 'quarter':
        return 'Quý %s/%s' % ((start.month - 1) // 3 + 1, start.year)
    return 'Tháng %s/%s' % (start.month, start.year)


def period_short_label(period_type, start):
    if period_type == 'year':
        return str(start.year)
    if period_type == 'quarter':
        return 'Q%s/%s' % ((start.month - 1) // 3 + 1, str(start.year)[2:])
    return 'T%s/%s' % (start.month, str(start.year)[2:])


def working_days(date_from, date_to):
    """Số ngày làm việc (thứ Hai – thứ Bảy, nghỉ Chủ nhật) trong [date_from, date_to]."""
    if not date_from or not date_to or date_to < date_from:
        return 0
    days = (date_to - date_from).days + 1
    full_weeks, rest = divmod(days, 7)
    count = full_weeks * 6
    for i in range(rest):
        if (date_from + timedelta(days=full_weeks * 7 + i)).weekday() != 6:
            count += 1
    return count
