"""Lịch làm việc của phòng khám (theo công ty): ca làm việc theo thứ trong tuần, ngày nghỉ lễ / nghỉ đột xuất,
ngày làm việc riêng của từng bác sĩ.

Đây là NGUỒN DUY NHẤT cho mọi chỗ cần biết "phòng khám mở cửa lúc nào": giờ trống đặt lịch, kiểm tra đặt lịch ngoài
giờ, gợi ý xếp lịch AI-11, trợ lý Zalo AI-07, số ngày làm việc / nhịp mục tiêu và công suất ghế (dmag_dental_goals),
dự báo AI-16, dữ liệu demo.

Mặc định (khi phòng khám chưa khai báo): Thứ Hai – Thứ Bảy 08:00–12:00 và 13:30–20:00, Chủ nhật nghỉ.
"""
from datetime import datetime, time, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .dmag_access import is_manager

WEEKDAYS = [
    ('0', 'Thứ Hai'), ('1', 'Thứ Ba'), ('2', 'Thứ Tư'), ('3', 'Thứ Năm'), ('4', 'Thứ Sáu'), ('5', 'Thứ Bảy'),
    ('6', 'Chủ nhật'),
]
WEEKDAY_SHORT = ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ nhật']
# Ca mặc định (giờ thập phân, giờ địa phương)
DEFAULT_SHIFTS = {wd: [(8.0, 12.0), (13.5, 20.0)] for wd in range(6)}
DEFAULT_SHIFTS[6] = []
NOON = 12 * 60
MORNING_WINDOW = (0, NOON)          # buổi sáng = giờ mở cửa trước 12:00
AFTERNOON_WINDOW = (NOON, 24 * 60)  # buổi chiều – tối = giờ mở cửa từ 12:00

# Ngày nghỉ lễ mẫu năm 2026 – [CẦN XÁC MINH] theo thông báo chính thức của Chính phủ / Bộ LĐ-TB-XH (lịch nghỉ Tết
# Âm lịch, nghỉ bù) và quyết định mở cửa ngày lễ của chính phòng khám.
VN_HOLIDAYS_2026 = [
    ('Tết Dương lịch [CẦN XÁC MINH]', '2026-01-01', '2026-01-01'),
    ('Tết Nguyên đán Bính Ngọ [CẦN XÁC MINH]', '2026-02-16', '2026-02-20'),
    ('Giỗ Tổ Hùng Vương (nghỉ bù) [CẦN XÁC MINH]', '2026-04-27', '2026-04-27'),
    ('Ngày Giải phóng miền Nam 30/4 [CẦN XÁC MINH]', '2026-04-30', '2026-04-30'),
    ('Quốc tế Lao động 1/5 [CẦN XÁC MINH]', '2026-05-01', '2026-05-01'),
    ('Quốc khánh 2/9 [CẦN XÁC MINH]', '2026-09-01', '2026-09-02'),
]


def fmt_hour(value):
    minutes = int(round((value or 0.0) * 60))
    return '%02d:%02d' % (minutes // 60, minutes % 60)


def fmt_minutes(minutes):
    return '%02d:%02d' % (minutes // 60, minutes % 60)


class ScheduleInfo:
    """Ảnh chụp lịch làm việc (thuần Python) để tính nhanh trên nhiều ngày – không truy vấn lại cơ sở dữ liệu.

    * ``weekly``: {thứ (0=Thứ Hai): [(phút bắt đầu, phút kết thúc)]}
    * ``closures``: [(từ ngày, đến ngày, tên)]
    """

    def __init__(self, weekly, closures=(), slot_step=15, enforce='block'):
        self.weekly = {wd: sorted(weekly.get(wd) or []) for wd in range(7)}
        self.closures = list(closures)
        self.slot_step = slot_step or 15
        self.enforce = enforce or 'block'

    @classmethod
    def default(cls):
        return cls({wd: [(int(a * 60), int(b * 60)) for a, b in shifts] for wd, shifts in DEFAULT_SHIFTS.items()})

    # ---------------------------------------------------------------- ngày
    def closure(self, day):
        for d_from, d_to, name in self.closures:
            if d_from <= day <= d_to:
                return name
        return None

    def shifts(self, day):
        """Ca làm việc trong ngày ``[(phút bắt đầu, phút kết thúc)]`` – rỗng nếu nghỉ."""
        if self.closure(day):
            return []
        return list(self.weekly.get(day.weekday()) or [])

    def is_open_day(self, day):
        return bool(self.shifts(day))

    def open_days(self, date_from, date_to):
        if not date_from or not date_to or date_to < date_from:
            return []
        return [d for d in (date_from + timedelta(days=i) for i in range((date_to - date_from).days + 1))
                if self.is_open_day(d)]

    def count_open_days(self, date_from, date_to):
        return len(self.open_days(date_from, date_to))

    def open_weekdays(self):
        return [wd for wd in range(7) if self.weekly.get(wd)]

    def day_minutes(self, day, window=None):
        """Số phút mở cửa trong ngày (giao với ``window=(phút từ, phút đến)`` nếu có)."""
        total = 0
        for start, end in self.shifts(day):
            if window:
                start, end = max(start, window[0]), min(end, window[1])
            total += max(0, end - start)
        return total

    def busy_minutes(self, day, local_start, local_end, window=None):
        """Số phút của khoảng [local_start, local_end) (datetime địa phương) nằm trong giờ mở cửa ngày ``day``
        (giao thêm ``window`` theo phút nếu có) – dùng tính công suất ghế."""
        base = datetime.combine(day, time.min)
        start = (local_start - base).total_seconds() / 60
        end = (local_end - base).total_seconds() / 60
        total = 0.0
        for s, e in self.shifts(day):
            if window:
                s, e = max(s, window[0]), min(e, window[1])
            total += max(0.0, min(end, e) - max(start, s))
        return total

    def chair_utilization(self, days, n_units, intervals, window=None):
        """Công suất (%) = phút đã xếp lịch / (phút mở cửa × số ghế) trên các ngày ``days``.

        :param intervals: [(datetime bắt đầu, datetime kết thúc)] giờ địa phương của các lịch có ghế
        :return: % (1 chữ số thập phân) hoặc None khi không có giờ mở cửa
        """
        day_set = {d for d in days if self.is_open_day(d)}
        available = sum(self.day_minutes(d, window) for d in day_set) * n_units
        if not available:
            return None
        booked = sum(self.busy_minutes(start.date(), start, end, window)
                     for start, end in intervals if start.date() in day_set)
        return round(booked * 100.0 / available, 1)

    def bounds(self, day):
        shifts = self.shifts(day)
        return (shifts[0][0], shifts[-1][1]) if shifts else None

    def contains(self, day, start_min, end_min):
        """Khoảng [start, end) nằm trọn trong một ca của ngày ``day``."""
        return any(s <= start_min and end_min <= e for s, e in self.shifts(day))

    def shift_of(self, day, minute):
        for start, end in self.shifts(day):
            if start <= minute < end:
                return (start, end)
        return None

    def check_interval(self, local_start, local_end):
        """Kiểm tra lịch hẹn (giờ địa phương, naive). Trả ``None`` nếu hợp lệ, hoặc lý do (chuỗi)."""
        day = local_start.date()
        closure = self.closure(day)
        if closure:
            return _('ngày %(day)s phòng khám nghỉ (%(name)s)', day=day.strftime('%d/%m/%Y'), name=closure)
        shifts = self.weekly.get(day.weekday()) or []
        if not shifts:
            return _('%(wd)s phòng khám không làm việc', wd=WEEKDAY_SHORT[day.weekday()])
        start = local_start.hour * 60 + local_start.minute
        end_day = local_end.date()
        end = (local_end.hour * 60 + local_end.minute) if end_day == day else 24 * 60 + 1
        if not self.contains(day, start, max(end, start + 1)):
            return _('%(time)s ngoài giờ làm việc (%(hours)s)', time=fmt_minutes(start),
                     hours=self.day_text(day))
        return None

    def day_text(self, day):
        shifts = self.shifts(day)
        if not shifts:
            return _('nghỉ')
        return ', '.join('%s–%s' % (fmt_minutes(s), fmt_minutes(e)) for s, e in shifts)

    def weekly_text(self):
        """Ví dụ: "Thứ 2 – Thứ 7: 08:00–12:00, 13:30–20:00 · Chủ nhật: nghỉ"."""
        groups = []
        for wd in range(7):
            key = tuple(self.weekly.get(wd) or [])
            if groups and groups[-1][1] == key:
                groups[-1][0].append(wd)
            else:
                groups.append(([wd], key))
        parts = []
        for days, key in groups:
            label = WEEKDAY_SHORT[days[0]] if len(days) == 1 else '%s – %s' % (WEEKDAY_SHORT[days[0]],
                                                                              WEEKDAY_SHORT[days[-1]])
            hours = ', '.join('%s–%s' % (fmt_minutes(s), fmt_minutes(e)) for s, e in key) if key else _('nghỉ')
            parts.append('%s: %s' % (label, hours))
        return ' · '.join(parts)

    def next_open_days(self, start, count=3, horizon=60):
        days = []
        for i in range(horizon):
            day = start + timedelta(days=i)
            if self.is_open_day(day):
                days.append(day)
                if len(days) >= count:
                    break
        return days


class DmagWeekday(models.Model):
    _name = 'dmag.weekday'
    _description = 'Thứ trong tuần'
    _order = 'code'

    name = fields.Char('Thứ', required=True, translate=False)
    code = fields.Integer('Mã (0 = Thứ Hai)', required=True)

    _sql_constraints = [('code_uniq', 'unique(code)', 'Mỗi thứ chỉ có một bản ghi.')]


class DmagClinicSchedule(models.Model):
    _name = 'dmag.clinic.schedule'
    _description = 'Lịch làm việc phòng khám'
    _inherit = ['mail.thread']
    _rec_name = 'name'

    name = fields.Char('Tên', required=True, default='Lịch làm việc')
    company_id = fields.Many2one('res.company', string='Phòng khám', required=True, index=True,
                                 default=lambda self: self.env.company, ondelete='cascade')
    line_ids = fields.One2many('dmag.clinic.schedule.line', 'schedule_id', string='Ca làm việc trong tuần', copy=True)
    closure_ids = fields.One2many('dmag.clinic.closure', 'schedule_id', string='Ngày nghỉ lễ / nghỉ đột xuất',
                                  copy=True)
    slot_step = fields.Integer('Bước khung giờ đặt lịch (phút)', default=15, required=True,
                               help='Khoảng cách giữa các giờ trống gợi ý khi đặt lịch (15 = 08:00, 08:15, …).')
    enforce = fields.Selection([
        ('block', 'Chặn – chỉ Quản lý trở lên được đặt ngoài giờ'),
        ('warn', 'Chỉ cảnh báo (vẫn cho đặt)'),
    ], string='Đặt lịch ngoài giờ làm việc', default='block', required=True, tracking=True)
    note = fields.Text('Ghi chú cho khách', help='Hiện kèm giờ làm việc khi trợ lý trả lời khách, ví dụ: '
                                                  '"Ngày lễ phòng khám vẫn nhận ca khẩn qua hotline".')
    hours_text = fields.Char('Giờ làm việc (tóm tắt)', compute='_compute_hours_text')
    weekday_summary = fields.Html('Tóm tắt tuần', compute='_compute_hours_text', sanitize=False)

    _sql_constraints = [('company_uniq', 'unique(company_id)', 'Mỗi phòng khám chỉ có một lịch làm việc.')]

    @api.depends('line_ids.weekday', 'line_ids.hour_from', 'line_ids.hour_to')
    def _compute_hours_text(self):
        for schedule in self:
            info = schedule._info()
            schedule.hours_text = info.weekly_text()
            rows = []
            for wd in range(7):
                shifts = info.weekly.get(wd) or []
                chips = ''.join('<span class="badge rounded-pill text-bg-success me-1">%s–%s</span>'
                                % (fmt_minutes(s), fmt_minutes(e)) for s, e in shifts) \
                    or '<span class="badge rounded-pill text-bg-light text-muted">Nghỉ</span>'
                rows.append('<tr><td class="pe-3 fw-bold">%s</td><td>%s</td></tr>' % (WEEKDAYS[wd][1], chips))
            schedule.weekday_summary = '<table class="o_dmag_week">%s</table>' % ''.join(rows)

    # ------------------------------------------------------------------ CRUD
    @api.model
    def _default_line_vals(self):
        return [(0, 0, {'weekday': str(wd), 'hour_from': a, 'hour_to': b, 'sequence': i})
                for wd, shifts in DEFAULT_SHIFTS.items() for i, (a, b) in enumerate(shifts)]

    @api.model
    def _get_for_company(self, company=None):
        """Lịch làm việc của phòng khám – tự tạo lịch mặc định nếu chưa có (không ghi đè lịch đã khai)."""
        company = company or self.env.company
        schedule = self.sudo().search([('company_id', '=', company.id)], limit=1)
        if not schedule:
            schedule = self.sudo().create({
                'company_id': company.id,
                'line_ids': self._default_line_vals(),
                'closure_ids': [(0, 0, {'name': name, 'date_from': d_from, 'date_to': d_to, 'kind': 'holiday',
                                        'to_verify': True}) for name, d_from, d_to in VN_HOLIDAYS_2026],
            })
        return schedule

    @api.model
    def get_info(self, company=None):
        """``ScheduleInfo`` của phòng khám (dùng trong Python)."""
        return self._get_for_company(company)._info()

    def _info(self):
        self.ensure_one()
        if not self.id and not self.line_ids:
            return ScheduleInfo.default()
        weekly = {wd: [] for wd in range(7)}
        for line in self.line_ids:
            if line.hour_to > line.hour_from:
                weekly[int(line.weekday)].append((int(round(line.hour_from * 60)), int(round(line.hour_to * 60))))
        closures = [(c.date_from, c.date_to or c.date_from, c.name) for c in self.closure_ids
                    if c.date_from and c.closed]
        return ScheduleInfo(weekly, closures, self.slot_step, self.enforce)

    @api.model
    def action_open_for_company(self):
        schedule = self._get_for_company(self.env.company)
        return {
            'type': 'ir.actions.act_window', 'name': _('Lịch làm việc'), 'res_model': self._name,
            'res_id': schedule.id, 'view_mode': 'form', 'target': 'current',
        }

    def action_reset_default(self):
        """Đặt lại ca mặc định (Thứ 2 – Thứ 7 08:00–12:00, 13:30–20:00; Chủ nhật nghỉ)."""
        for schedule in self:
            schedule.line_ids.unlink()
            schedule.write({'line_ids': self._default_line_vals()})
            schedule.message_post(body=_('Đặt lại ca làm việc mặc định.'))
        return True

    def action_add_holidays_2026(self):
        for schedule in self:
            existing = {(c.date_from, c.date_to) for c in schedule.closure_ids}
            vals = [(0, 0, {'name': name, 'date_from': d_from, 'date_to': d_to, 'kind': 'holiday', 'to_verify': True})
                    for name, d_from, d_to in VN_HOLIDAYS_2026
                    if (fields.Date.to_date(d_from), fields.Date.to_date(d_to)) not in existing]
            if vals:
                schedule.write({'closure_ids': vals})
        return True

    # ------------------------------------------------------------------ API cho giao diện
    @api.model
    def get_day_info(self, date):
        """Thông tin một ngày cho giao diện đặt lịch: mở / nghỉ, các ca, lý do nghỉ."""
        day = fields.Date.to_date(date)
        info = self.get_info()
        closure = info.closure(day)
        return {
            'date': fields.Date.to_string(day), 'open': info.is_open_day(day), 'closure': closure or '',
            'weekday': WEEKDAY_SHORT[day.weekday()],
            'shifts': [{'from': fmt_minutes(s), 'to': fmt_minutes(e)} for s, e in info.shifts(day)],
            'text': info.day_text(day) if not closure else _('Nghỉ – %s', closure),
            'weekly': info.weekly_text(),
            'can_override': is_manager(self.env),
        }


class DmagClinicScheduleLine(models.Model):
    _name = 'dmag.clinic.schedule.line'
    _description = 'Ca làm việc của phòng khám'
    _order = 'weekday, hour_from'

    schedule_id = fields.Many2one('dmag.clinic.schedule', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='schedule_id.company_id', store=True)
    sequence = fields.Integer(default=10)
    weekday = fields.Selection(WEEKDAYS, string='Thứ', required=True, default='0')
    hour_from = fields.Float('Từ giờ', required=True, default=8.0)
    hour_to = fields.Float('Đến giờ', required=True, default=12.0)
    name = fields.Char('Ca', compute='_compute_name')

    @api.depends('hour_from', 'hour_to')
    def _compute_name(self):
        for line in self:
            label = _('Ca sáng') if line.hour_from < 12 and line.hour_to <= 13 else \
                _('Ca chiều – tối') if line.hour_from >= 12 else _('Cả ngày')
            line.name = '%s (%s–%s)' % (label, fmt_hour(line.hour_from), fmt_hour(line.hour_to))

    @api.constrains('hour_from', 'hour_to', 'weekday')
    def _check_hours(self):
        for line in self:
            if not (0 <= line.hour_from < line.hour_to <= 24):
                raise ValidationError(_('Ca %s: giờ bắt đầu phải trước giờ kết thúc, trong khoảng 00:00–24:00.',
                                        dict(WEEKDAYS)[line.weekday]))
            others = line.schedule_id.line_ids.filtered(lambda o: o != line and o.weekday == line.weekday)
            if any(o.hour_from < line.hour_to and line.hour_from < o.hour_to for o in others):
                raise ValidationError(_('%s có hai ca chồng giờ nhau.', dict(WEEKDAYS)[line.weekday]))


class DmagClinicClosure(models.Model):
    _name = 'dmag.clinic.closure'
    _description = 'Ngày nghỉ của phòng khám'
    _order = 'date_from'

    schedule_id = fields.Many2one('dmag.clinic.schedule', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='schedule_id.company_id', store=True)
    name = fields.Char('Lý do / tên ngày lễ', required=True)
    date_from = fields.Date('Từ ngày', required=True)
    date_to = fields.Date('Đến ngày', required=True)
    kind = fields.Selection([('holiday', 'Nghỉ lễ, Tết'), ('closure', 'Nghỉ đột xuất / bảo trì / đào tạo')],
                            string='Loại', default='holiday', required=True)
    closed = fields.Boolean('Đóng cửa', default=True,
                            help='Bỏ chọn nếu phòng khám vẫn mở cửa ngày lễ này (giữ dòng để ghi nhớ).')
    to_verify = fields.Boolean('Cần xác minh', help='Ngày nghỉ mẫu – kiểm tra lại theo thông báo chính thức.')

    @api.onchange('date_from')
    def _onchange_date_from(self):
        if self.date_from and (not self.date_to or self.date_to < self.date_from):
            self.date_to = self.date_from

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for closure in self:
            if closure.date_to < closure.date_from:
                raise ValidationError(_('"%s": ngày kết thúc phải sau ngày bắt đầu.', closure.name))


def local_naive(env, dt):
    """UTC naive → giờ địa phương naive (theo múi giờ người dùng, mặc định Asia/Ho_Chi_Minh)."""
    import pytz
    tz = pytz.timezone(env.user.tz or 'Asia/Ho_Chi_Minh')
    return pytz.utc.localize(dt).astimezone(tz).replace(tzinfo=None)

