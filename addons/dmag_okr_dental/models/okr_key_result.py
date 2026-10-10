import logging
from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

DENTAL_METHODS = [
    ('dmag_nps', 'Nha khoa: NPS (khảo sát sau điều trị)'),
    ('dmag_wait_time', 'Nha khoa: thời gian chờ TB (phút, check-in → lên ghế)'),
    ('dmag_pain_ok_rate', 'Nha khoa: tỷ lệ ca điểm đau ≤ 2 (%)'),
    ('dmag_ortho_new', 'Nha khoa: số ca niềng mới'),
    ('dmag_plan_acceptance', 'Nha khoa: tỷ lệ chốt kế hoạch điều trị (%)'),
    ('dmag_referral_revenue', 'Nha khoa: doanh thu từ khách giới thiệu'),
    ('dmag_afternoon_util', 'Nha khoa: công suất ghế chiều 13:30–16:30 (%)'),
    ('dmag_associate_share', 'Nha khoa: % thủ thuật do bác sĩ phụ thực hiện'),
    ('dmag_material_cost', 'Nha khoa: chi phí vật tư / doanh thu (%)'),
]
DENTAL_KEYS = {key for key, _label in DENTAL_METHODS}
AFTERNOON = (time(13, 30), time(16, 30))
ORTHO = 'orthodontic'


class OkrKeyResult(models.Model):
    _inherit = 'okr.scale.key.result'

    progress_method = fields.Selection(selection_add=DENTAL_METHODS,
                                       ondelete={key: 'set default' for key in DENTAL_KEYS})
    dmag_is_dental = fields.Boolean(compute='_compute_dmag_is_dental')
    dmag_date_from = fields.Date('Đo từ ngày', help='Để trống: ngày bắt đầu chu kỳ OKR.')
    dmag_date_to = fields.Date('Đo đến ngày', help='Để trống: ngày kết thúc chu kỳ OKR.')
    dmag_doctor_ids = fields.Many2many('dmag.dental.practitioner', string='Chỉ tính bác sĩ',
                                       help='Để trống: toàn phòng khám.')
    dmag_value_date = fields.Datetime('Cập nhật số liệu lúc', readonly=True)
    dmag_guardrail_ids = fields.Many2many('dmag.okr.guardrail', 'dmag_okr_guardrail_kr_rel',
                                          'key_result_id', 'guardrail_id', string='Chỉ số cầu chì')
    dmag_guardrail_breached = fields.Boolean('Vi phạm cầu chì', compute='_compute_dmag_guardrail_breached',
                                             store=True)

    @api.depends('progress_method')
    def _compute_dmag_is_dental(self):
        for kr in self:
            kr.dmag_is_dental = kr.progress_method in DENTAL_KEYS

    @api.depends('dmag_guardrail_ids.breached')
    def _compute_dmag_guardrail_breached(self):
        for kr in self:
            kr.dmag_guardrail_breached = any(kr.dmag_guardrail_ids.mapped('breached'))

    @api.depends('progress', 'confidence', 'cycle_id.date_start', 'cycle_id.date_end', 'deadline',
                 'dmag_guardrail_breached')
    def _compute_status(self):
        res = super()._compute_status()
        for kr in self.filtered('dmag_guardrail_breached'):
            # Cầu chì y đức / sức khỏe bị vượt → KR chuyển đỏ, bất kể tiến độ
            kr.status = 'off_track'
        return res

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('progress_method') in DENTAL_KEYS:
                # Chưa có số liệu → đứng ở mức xuất phát (không "đạt" giả với KR giảm dần)
                vals.setdefault('current_value', vals.get('start_value', 0.0))
        return super().create(vals_list)

    # ------------------------------------------------------------------ progress hook
    def _compute_progress_by_method(self):
        self.ensure_one()
        if self.progress_method not in DENTAL_KEYS:
            return super()._compute_progress_by_method()
        value = self._dmag_compute_value()
        if value is None:
            value = self.current_value
        return self._dmag_progress_for(value)

    def _dmag_progress_for(self, value):
        span = self.target_value - self.start_value
        if not span:
            return 100.0 if value == self.target_value else 0.0
        return max(0.0, min(100.0, (value - self.start_value) * 100.0 / span))

    def _dmag_window(self):
        """(datetime bắt đầu, datetime kết thúc – không gồm) theo chu kỳ OKR."""
        self.ensure_one()
        date_from = self.dmag_date_from or self.cycle_id.date_start or fields.Date.context_today(self)
        date_to = self.dmag_date_to or self.cycle_id.date_end or fields.Date.context_today(self)
        return datetime.combine(date_from, time.min), datetime.combine(date_to, time.min) + timedelta(days=1)

    def _dmag_compute_value(self):
        self.ensure_one()
        method = getattr(self, '_dmag_value_%s' % self.progress_method[len('dmag_'):], None)
        if not method or not self.company_id:
            return None
        start, end = self._dmag_window()
        try:
            return method(start, end)
        except Exception:  # nguồn mềm: không làm hỏng OKR
            _logger.exception('Không tính được KR nha khoa %s', self.progress_method)
            return None

    def _dmag_doctor_domain(self, field='doctor_id'):
        return [(field, 'in', self.dmag_doctor_ids.ids)] if self.dmag_doctor_ids else []

    def _dmag_done_procedures(self, start, end):
        return self.env['dmag.dental.procedure'].sudo().search([
            ('state', '=', 'done'), ('company_id', '=', self.company_id.id),
            ('visit_id.scheduled_start', '>=', start), ('visit_id.scheduled_start', '<', end),
        ] + self._dmag_doctor_domain())

    # ------------------------------------------------------------------ metrics
    def _dmag_value_nps(self, start, end):
        if 'dmag.nps.response' not in self.env:
            return None
        Response = self.env['dmag.nps.response'].sudo()
        score_field = next((f for f in ('score', 'nps_score', 'rating') if f in Response._fields), None)
        if not score_field:
            return None
        date_field = next((f for f in ('date', 'response_date') if f in Response._fields), 'create_date')
        domain = [(date_field, '>=', start), (date_field, '<', end)]
        if 'company_id' in Response._fields:
            domain.append(('company_id', '=', self.company_id.id))
        scores = [s for s in Response.search(domain).mapped(score_field) if s is not False and s is not None]
        if not scores:
            return None
        promoters = len([s for s in scores if s >= 9])
        detractors = len([s for s in scores if s <= 6])
        return round((promoters - detractors) * 100.0 / len(scores), 1)

    def _dmag_value_wait_time(self, start, end):
        visits = self.env['dmag.dental.visit'].sudo().search([
            ('company_id', '=', self.company_id.id), ('checkin_time', '>=', start), ('checkin_time', '<', end),
            ('chair_time', '!=', False)] + self._dmag_doctor_domain())
        if not visits:
            return None
        return round(sum(visits.mapped('wait_minutes')) / len(visits), 1)

    def _dmag_value_pain_ok_rate(self, start, end):
        visits = self.env['dmag.dental.visit'].sudo().search([
            ('company_id', '=', self.company_id.id), ('state', '=', 'done'),
            ('done_time', '>=', start), ('done_time', '<', end)] + self._dmag_doctor_domain())
        visits = visits.filtered('procedure_ids')
        if not visits:
            return None
        return round(len(visits.filtered(lambda v: v.pain_score <= 2)) * 100.0 / len(visits), 1)

    def _dmag_value_ortho_new(self, start, end):
        procs = self._dmag_done_procedures(start, end).filtered(
            lambda p: p.product_id.dental_category == ORTHO)
        patients = procs.mapped('patient_id')
        if not patients:
            return 0.0
        earlier = self.env['dmag.dental.procedure'].sudo().search([
            ('state', '=', 'done'), ('patient_id', 'in', patients.ids),
            ('visit_id.scheduled_start', '<', start),
        ]).filtered(lambda p: p.product_id.dental_category == ORTHO).mapped('patient_id')
        return float(len(patients - earlier))

    def _dmag_value_plan_acceptance(self, start, end):
        plans = self.env['dmag.treatment.plan'].sudo().search([
            ('company_id', '=', self.company_id.id), ('state', '!=', 'draft'),
            ('date', '>=', start.date()), ('date', '<', end.date())] + self._dmag_doctor_domain())
        if not plans:
            return None
        accepted = plans.filtered(lambda p: p.state in ('accepted', 'in_progress', 'done'))
        return round(len(accepted) * 100.0 / len(plans), 1)

    def _dmag_value_referral_revenue(self, start, end):
        procs = self._dmag_done_procedures(start, end).filtered(
            lambda p: p.patient_id.referrer_id or p.patient_id.customer_source_id.is_referral)
        return sum(procs.mapped('amount'))

    def _dmag_value_afternoon_util(self, start, end):
        tz = pytz.timezone(self.env.user.tz or 'Asia/Ho_Chi_Minh')
        chairs = self.env['dmag.dental.chair'].sudo().search([('company_id', '=', self.company_id.id)])
        if not chairs:
            return None
        last_day = min(end.date() - timedelta(days=1), fields.Date.context_today(self))
        days = [start.date() + timedelta(days=i) for i in range((last_day - start.date()).days + 1)]
        days = [d for d in days if d.weekday() != 6]  # nghỉ Chủ nhật
        if not days:
            return None
        slot = (datetime.combine(days[0], AFTERNOON[1]) - datetime.combine(days[0], AFTERNOON[0])).seconds / 60
        available = len(days) * len(chairs) * slot
        visits = self.env['dmag.dental.visit'].sudo().search([
            ('company_id', '=', self.company_id.id), ('state', 'not in', ('cancel', 'no_show')),
            ('scheduled_start', '>=', start - timedelta(days=1)), ('scheduled_start', '<', end + timedelta(days=1)),
            ('chair_id', '!=', False)])
        day_set = set(days)
        booked = 0.0
        for visit in visits:
            local_start = pytz.utc.localize(visit.scheduled_start).astimezone(tz).replace(tzinfo=None)
            local_end = pytz.utc.localize(visit.scheduled_end or visit.scheduled_start).astimezone(tz).replace(tzinfo=None)
            day = local_start.date()
            if day not in day_set:
                continue
            win_start = datetime.combine(day, AFTERNOON[0])
            win_end = datetime.combine(day, AFTERNOON[1])
            overlap = (min(local_end, win_end) - max(local_start, win_start)).total_seconds() / 60
            booked += max(0.0, overlap)
        return round(booked * 100.0 / available, 1) if available else None

    def _dmag_value_associate_share(self, start, end):
        procs = self._dmag_done_procedures(start, end)
        if not procs:
            return None
        return round(len(procs.filtered('doctor_id.dmag_is_associate')) * 100.0 / len(procs), 1)

    def _dmag_value_material_cost(self, start, end):
        for model in ('dmag.dental.visit', 'dmag.dental.procedure', 'stock.move', 'stock.picking'):
            if model not in self.env or not hasattr(self.env[model], 'get_material_kpis'):
                continue
            try:
                kpis = self.env[model].sudo().with_company(self.company_id).get_material_kpis(
                    start.date(), (end - timedelta(days=1)).date())
            except TypeError:
                kpis = self.env[model].sudo().with_company(self.company_id).get_material_kpis()
            if isinstance(kpis, dict):
                for key in ('material_cost_ratio', 'cost_ratio', 'material_ratio'):
                    if kpis.get(key) is not None:
                        return float(kpis[key])
            elif isinstance(kpis, (int, float)):
                return float(kpis)
        return None

    # ------------------------------------------------------------------ refresh
    def action_dmag_refresh(self):
        now = fields.Datetime.now()
        for kr in self.filtered(lambda k: k.progress_method in DENTAL_KEYS):
            value = kr._dmag_compute_value()
            vals = {'dmag_value_date': now}
            if value is not None:
                vals['current_value'] = value
            kr.sudo().write(vals)
        return True

    @api.model
    def _cron_dmag_refresh(self):
        krs = self.search([('progress_method', 'in', list(DENTAL_KEYS)), ('cycle_id.state', '=', 'open')])
        krs.action_dmag_refresh()
        self.env['dmag.okr.guardrail'].search([('active', '=', True)]).action_check()
