"""Bộ máy tính chỉ số mục tiêu: một hàm Python cho mỗi chỉ số, tính THỰC TẾ trong một khoảng ngày (giờ địa phương)
cho toàn phòng khám hoặc một bác sĩ.

Nguồn số liệu (đọc bằng quyền hệ thống, lọc theo công ty được phép):
* lượt khám / thủ thuật / kế hoạch điều trị – ``dmag_dental_clinic``;
* nhật ký thu tiền – ``dmag_payment_sepay`` (nếu cài), nếu không: phiếu thu kế toán (account.payment);
* vật tư tiêu hao – ``dmag_dental_stock`` (cùng định nghĩa với ``dmag.material.usage.get_material_kpis``);
* chi phí labo – ``dmag_dental_lab`` (cùng định nghĩa với ``dmag.lab.order.get_lab_kpis``: theo ngày gửi);
* hoa hồng / thủ thuật phí – ``dmag_dental_commission`` (dòng hợp lệ, theo ngày ghi nhận);
* NPS / phàn nàn – ``dmag_dental_journey``.
Module tùy chọn được kiểm tra mềm (``'model' in env``) – chưa cài thì chỉ số tương ứng trả ``None`` (không bịa số).
"""
from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models

from odoo.addons.dmag_dental_base.models.dmag_clinic_schedule import AFTERNOON_WINDOW, MORNING_WINDOW

from .dmag_goal_metrics import METRICS

# Buổi sáng / chiều = phần giờ mở cửa trước / sau 12:00 theo Lịch làm việc phòng khám (dmag.clinic.schedule)
MORNING = MORNING_WINDOW
AFTERNOON = AFTERNOON_WINDOW
SHOWED = ('arrived', 'in_chair', 'done')
PRESENTED = ('presented', 'accepted', 'in_progress', 'done', 'cancel')
ACCEPTED = ('accepted', 'in_progress', 'done')


class GoalScope:
    """Một khoảng ngày + phạm vi (công ty, bác sĩ) với bộ đệm các tập bản ghi dùng chung giữa các chỉ số."""

    def __init__(self, env, companies, date_from, date_to, doctor=None, today=None, tz=None):
        self.env = env
        self.companies = companies
        self.date_from = date_from
        self.date_to = date_to
        self.doctor = doctor
        self.today = today or fields.Date.context_today(env['res.partner'])
        self.tz = tz or pytz.timezone(env.user.tz or 'Asia/Ho_Chi_Minh')
        self.dt_from = self.utc(date_from)
        self.dt_to = self.utc(date_to + timedelta(days=1))
        self._cache = {}

    # ---------------------------------------------------------------- helpers
    def utc(self, day, at=time.min):
        local = self.tz.localize(datetime.combine(day, at))
        return local.astimezone(pytz.utc).replace(tzinfo=None)

    def local(self, dt):
        return pytz.utc.localize(dt).astimezone(self.tz).replace(tzinfo=None)

    def has(self, model):
        return model in self.env

    def M(self, model):
        return self.env[model].sudo()

    def cached(self, key, func):
        if key not in self._cache:
            self._cache[key] = func()
        return self._cache[key]

    def doctor_domain(self, field='doctor_id'):
        return [(field, '=', self.doctor.id)] if self.doctor else []

    @property
    def schedule(self):
        """Lịch làm việc phòng khám (ngày mở cửa, ca) – của công ty đầu tiên trong phạm vi."""
        return self.cached('schedule', lambda: self.env['dmag.clinic.schedule'].get_info(
            self.companies[:1] or self.env.company))

    def open_days(self, date_from=None, date_to=None):
        return self.schedule.open_days(date_from or self.date_from, date_to or self.date_to)

    @property
    def elapsed_to(self):
        """Ngày cuối đã qua (để đo công suất / show-up không tính tương lai)."""
        return min(self.date_to, self.today)

    # ---------------------------------------------------------------- domains (cũng dùng cho drill-down)
    def dom_procedures(self):
        return [('state', '=', 'done'), ('company_id', 'in', self.companies.ids),
                ('visit_id.scheduled_start', '>=', self.dt_from), ('visit_id.scheduled_start', '<', self.dt_to)] \
            + self.doctor_domain()

    def dom_visits(self):
        return [('company_id', 'in', self.companies.ids),
                ('scheduled_start', '>=', self.dt_from), ('scheduled_start', '<', self.dt_to)] + self.doctor_domain()

    def dom_plans(self):
        return [('company_id', 'in', self.companies.ids), ('date', '>=', self.date_from),
                ('date', '<=', self.date_to)] + self.doctor_domain()

    def dom_nps(self):
        return [('company_id', 'in', self.companies.ids), ('state', '=', 'answered'),
                ('date', '>=', self.dt_from), ('date', '<', self.dt_to)] + self.doctor_domain()

    # ---------------------------------------------------------------- datasets
    @property
    def procedures(self):
        return self.cached('procedures', lambda: self.M('dmag.dental.procedure').search(self.dom_procedures()))

    @property
    def visits(self):
        return self.cached('visits', lambda: self.M('dmag.dental.visit').search(self.dom_visits()))

    @property
    def done_visits(self):
        return self.visits.filtered(lambda v: v.state == 'done')

    @property
    def plans(self):
        return self.cached('plans', lambda: self.M('dmag.treatment.plan').search(self.dom_plans()))

    @property
    def presented_plans(self):
        # Kế hoạch đã đưa cho khách (kể cả bị từ chối sau khi tư vấn); kế hoạch nháp bị hủy không tính
        return self.plans.filtered(lambda p: p.state in PRESENTED and (p.state != 'cancel' or p.reject_reason))

    @property
    def accepted_plans(self):
        return self.plans.filtered(lambda p: p.state in ACCEPTED)

    @property
    def nps_responses(self):
        if not self.has('dmag.nps.response'):
            return None
        return self.cached('nps', lambda: self.M('dmag.nps.response').search(self.dom_nps()))

    # ---------------------------------------------------------------- costs
    def material_cost(self):
        if not self.has('dmag.material.usage'):
            return None
        return self.cached('material', lambda: sum(self.M('dmag.material.usage').search(
            [('company_id', 'in', self.companies.ids), ('date', '>=', self.dt_from), ('date', '<', self.dt_to)]
            + self.doctor_domain()).mapped('cost')))

    def lab_cost(self):
        if not self.has('dmag.lab.order'):
            return None
        return self.cached('lab', lambda: sum(self.M('dmag.lab.order').search(
            [('company_id', 'in', self.companies.ids), ('state', 'not in', ('draft', 'cancelled')),
             ('sent_date', '>=', self.date_from), ('sent_date', '<=', self.date_to)]
            + self.doctor_domain()).mapped('cost')))

    def commission_cost(self):
        if not self.has('dmag.commission.line'):
            return None

        def compute():
            domain = [('company_id', 'in', self.companies.ids), ('state', '=', 'valid'),
                      ('date', '>=', self.date_from), ('date', '<=', self.date_to)]
            if self.doctor:
                domain += ['|', ('procedure_id.doctor_id', '=', self.doctor.id),
                           '&', ('procedure_id', '=', False), ('visit_id.doctor_id', '=', self.doctor.id)]
            return sum(self.M('dmag.commission.line').search(domain).mapped('amount'))
        return self.cached('commission', compute)


class DmagGoalEngine(models.AbstractModel):
    """Một hàm ``_metric_<khóa>(scope)`` cho mỗi chỉ số trong ``METRICS``.

    Trả về số thực, hoặc ``None`` khi chưa có số liệu / chưa cài module nguồn (bảng điều hành ghi "Chưa có số liệu").
    Module khác thêm chỉ số: thêm khóa vào ``METRICS`` + định nghĩa ``_metric_<khóa>``.
    """
    _name = 'dmag.goal.engine'
    _description = 'DMAG – bộ máy tính chỉ số mục tiêu'

    @api.model
    def _scope(self, date_from, date_to, companies=None, doctor=None, today=None):
        return GoalScope(self.env, companies or self.env.companies, fields.Date.to_date(date_from),
                         fields.Date.to_date(date_to), doctor=doctor, today=today)

    @api.model
    def compute_metric(self, metric, scope):
        method = getattr(self, '_metric_%s' % metric, None)
        if not method or metric not in METRICS:
            return None
        return scope.cached(('metric', metric), lambda: method(scope))

    @api.model
    def get_metric_value(self, metric, date_from, date_to, doctor_id=False, company_ids=False):
        """API tiện dụng (RPC / module khác): giá trị thực tế của một chỉ số trong khoảng ngày."""
        companies = self.env['res.company'].browse(company_ids) if company_ids else self.env.companies
        doctor = self.env['dmag.dental.practitioner'].browse(doctor_id) if doctor_id else None
        return self.compute_metric(metric, self._scope(date_from, date_to, companies, doctor))

    @staticmethod
    def _rate(part, whole, digits=1):
        return round(100.0 * part / whole, digits) if whole else None

    # ------------------------------------------------------------------ mục tiêu kinh doanh
    def _metric_revenue(self, s):
        return sum(s.procedures.mapped('amount'))

    def _metric_collected(self, s):
        if s.has('dmag.payment.log'):
            domain = [('company_id', 'in', s.companies.ids), ('local_date', '>=', s.date_from),
                      ('local_date', '<=', s.date_to)] + s.doctor_domain('visit_id.doctor_id')
            return sum(s.M('dmag.payment.log').search(domain).mapped('amount'))
        if s.doctor:
            return None  # phiếu thu kế toán không gắn bác sĩ
        payments = s.M('account.payment').search([
            ('company_id', 'in', s.companies.ids), ('payment_type', '=', 'inbound'), ('partner_type', '=', 'customer'),
            ('state', '=', 'posted'), ('date', '>=', s.date_from), ('date', '<=', s.date_to)])
        return sum(payments.mapped('amount_company_currency_signed'))

    def _metric_new_patients(self, s):
        return float(len(s.done_visits.filtered('is_new_patient')))

    def _metric_implant_cases(self, s):
        procs = s.procedures.filtered(lambda p: p.product_id.dental_category == 'implant')
        return float(sum(len(p.tooth_ids) or p.quantity for p in procs))

    def _ortho_first_procedures(self, s):
        procs = s.procedures.filtered(lambda p: p.product_id.dental_category == 'orthodontic')
        if not procs:
            return procs
        earlier = s.M('dmag.dental.procedure').search([
            ('state', '=', 'done'), ('patient_id', 'in', procs.mapped('patient_id').ids),
            ('product_id.dental_category', '=', 'orthodontic'),
            ('visit_id.scheduled_start', '<', s.dt_from)]).mapped('patient_id')
        first = {}
        for proc in procs.sorted(lambda p: (p.visit_id.scheduled_start, p.id)):
            if proc.patient_id not in earlier and proc.patient_id.id not in first:
                first[proc.patient_id.id] = proc.id
        return procs.browse(list(first.values()))

    def _metric_ortho_new(self, s):
        return float(len(self._ortho_first_procedures(s)))

    def _metric_plan_acceptance(self, s):
        return self._rate(len(s.accepted_plans), len(s.presented_plans))

    def _metric_gross_profit(self, s):
        return self._metric_revenue(s) - (s.material_cost() or 0.0) - (s.lab_cost() or 0.0) \
            - (s.commission_cost() or 0.0)

    # ------------------------------------------------------------------ hành trình khách hàng
    def _metric_booked(self, s):
        return float(len(s.visits.filtered(lambda v: v.state != 'cancel')))

    def _metric_show_up_rate(self, s):
        showed = s.visits.filtered(lambda v: v.state in SHOWED)
        return self._rate(len(showed), len(showed) + len(s.visits.filtered(lambda v: v.state == 'no_show')))

    def _metric_consult_rate(self, s):
        showed = s.visits.filtered(lambda v: v.state in SHOWED).mapped('patient_id')
        consulted = s.presented_plans.mapped('patient_id') & showed
        return self._rate(len(consulted), len(showed))

    def _metric_completion_rate(self, s):
        accepted = s.accepted_plans
        return self._rate(len(accepted.filtered(lambda p: p.state == 'done')), len(accepted))

    def _metric_return_rate(self, s):
        visits = s.visits.filtered(lambda v: not v.is_new_patient)
        showed = visits.filtered(lambda v: v.state in SHOWED)
        return self._rate(len(showed), len(showed) + len(visits.filtered(lambda v: v.state == 'no_show')))

    def _metric_referral_rate(self, s):
        new = s.done_visits.filtered('is_new_patient').mapped('patient_id')
        referred = new.filtered(lambda p: p.referrer_id or p.customer_source_id.is_referral)
        return self._rate(len(referred), len(new))

    # ------------------------------------------------------------------ chất lượng dịch vụ
    def _metric_avg_wait(self, s):
        visits = s.visits.filtered(lambda v: v.checkin_time and v.chair_time and v.state in SHOWED)
        if not visits:
            return None
        return round(sum(visits.mapped('wait_minutes')) / len(visits), 1)

    def _chair_util(self, s, window):
        """Công suất ghế trong ``window`` (phút trong ngày) chỉ tính giờ MỞ CỬA của các ngày làm việc đã qua."""
        chairs = s.M('dmag.dental.chair').search([('company_id', 'in', s.companies.ids)])
        last_day = s.elapsed_to
        if not chairs or last_day < s.date_from:
            return None
        days = s.open_days(s.date_from, last_day)
        if s.doctor:  # bác sĩ: chỉ ngày trực của bác sĩ (nghỉ luân phiên / nghỉ phép không tính)
            days = [d for d in days if not s.doctor.off_reason(d, s.schedule)]
        if not days:
            return None
        intervals = [(s.local(v.scheduled_start), s.local(v.scheduled_end or v.scheduled_start))
                     for v in s.visits.filtered(lambda v: v.state not in ('cancel', 'no_show') and v.chair_id)]
        # một bác sĩ: tối đa một ghế tại một thời điểm
        return s.schedule.chair_utilization(days, 1 if s.doctor else len(chairs), intervals, window)

    def _metric_chair_util_am(self, s):
        return self._chair_util(s, MORNING)

    def _metric_chair_util_pm(self, s):
        return self._chair_util(s, AFTERNOON)

    def _metric_nps(self, s):
        responses = s.nps_responses
        if not responses:
            return None
        promoters = len(responses.filtered(lambda r: r.score >= 9))
        detractors = len(responses.filtered(lambda r: r.score <= 6))
        return round((promoters - detractors) * 100.0 / len(responses), 1)

    def _metric_complaint_rate(self, s):
        if not s.has('dmag.nps.response'):
            return None
        complaints = s.M('dmag.nps.response').search_count([
            ('company_id', 'in', s.companies.ids), ('is_complaint', '=', True),
            ('date', '>=', s.dt_from), ('date', '<', s.dt_to)] + s.doctor_domain())
        return self._rate(complaints, len(s.done_visits))

    def _metric_associate_share(self, s):
        procs = s.procedures
        associate = procs.filtered(lambda p: p.doctor_id.clinical_level_id
                                   and p.doctor_id.clinical_level_id.level < 3)
        return self._rate(len(associate), len(procs))

    def _metric_cogs_ratio(self, s):
        material, lab = s.material_cost(), s.lab_cost()
        if material is None and lab is None:
            return None
        revenue = self._metric_revenue(s)
        return self._rate((material or 0.0) + (lab or 0.0), revenue)
