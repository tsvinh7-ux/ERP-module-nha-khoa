"""Bảng điều hành mục tiêu – một RPC ``get_goal_dashboard(period_type, date_ref)`` trả về toàn bộ màn hình.

Mọi thẻ đều theo cùng một khung "mục tiêu – thực tế – nhịp độ":
* % đạt = thực tế / mục tiêu; % kỳ đã qua (theo ngày làm việc thứ Hai–thứ Bảy);
* dự báo cuối kỳ (chỉ số cộng dồn) = thực tế / ngày làm việc đã qua × tổng ngày làm việc của kỳ;
* còn thiếu + "cần thêm X / ngày làm việc còn lại";
* trạng thái: Đúng tiến độ (dự báo ≥ 100% mục tiêu) / Chậm (90–100%) / Nguy cơ (< 90%);
  chỉ số tỷ lệ so trực tiếp giá trị hiện tại với mục tiêu (cùng ngưỡng 90%; NPS: lệch ≤ 10 điểm = Chậm);
* xu hướng 6 kỳ gần nhất + so với cùng thời điểm kỳ trước.
"""
from datetime import date, datetime

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

from odoo.addons.dmag_dental_base.models.dmag_access import is_director, is_manager

from .dmag_goal_engine import ACCEPTED, SHOWED
from .dmag_goal_metrics import (AFTER_CARE, METRICS, NORTH_STAR, PERIOD_MONTHS, SERVICE, period_bounds,
                                period_label, period_short_label, shift_period, working_days)

STATUS_LABELS = {
    'on_track': 'Đúng tiến độ', 'behind': 'Chậm', 'at_risk': 'Nguy cơ', 'achieved': 'Đã đạt',
    'missed': 'Không đạt', 'no_target': 'Chưa đặt mục tiêu', 'no_data': 'Chưa có số liệu',
    'not_started': 'Chưa bắt đầu',
}
STATUS_RANK = {'at_risk': 5, 'missed': 5, 'behind': 4, 'no_data': 2, 'no_target': 1, 'not_started': 1,
               'on_track': 0, 'achieved': 0}
TREND_PERIODS = 6


def _jsonable(value):
    if isinstance(value, datetime):
        return fields.Datetime.to_string(value)
    if isinstance(value, date):
        return fields.Date.to_string(value)
    return value


def fmt_value(unit, value):
    """Định dạng số cho câu cảnh báo (kiểu Việt Nam)."""
    if value is None:
        return '–'
    if unit == 'money':
        if abs(value) >= 1e9:
            return ('%.2f tỷ' % (value / 1e9)).replace('.', ',')
        if abs(value) >= 1e6:
            return ('%.1f tr' % (value / 1e6)).replace('.', ',')
        return '{:,.0f} ₫'.format(value).replace(',', '.')
    text = ('%.1f' % value).rstrip('0').rstrip('.').replace('.', ',')
    return {'pct': text + '%', 'min': text + ' phút', 'score': text + ' điểm'}.get(unit, text)


def _clean_domain(domain):
    return [tuple(_jsonable(v) for v in leaf) if isinstance(leaf, (list, tuple)) else leaf for leaf in domain]


class GoalBoard:
    """Bộ dựng dữ liệu cho một lần mở bảng điều hành (bộ đệm phạm vi + mục tiêu)."""

    def __init__(self, env, period_type, d_from, d_to, companies, today):
        self.env = env
        self.engine = env['dmag.goal.engine']
        self.ptype = period_type
        self.d_from, self.d_to = d_from, d_to
        self.companies = companies
        self.today = today
        self.wd_total = working_days(d_from, d_to)
        self.wd_elapsed = working_days(d_from, min(today, d_to)) if today >= d_from else 0
        self.wd_left = self.wd_total - self.wd_elapsed
        self.is_past = today > d_to
        self.is_future = today < d_from
        self._scopes = {}
        self.targets = env['dmag.business.target'].sudo().search([
            ('state', '=', 'confirmed'), ('company_id', 'in', companies.ids),
            ('date_from', '>=', d_from), ('date_from', '<=', d_to)])
        # cùng thời điểm của kỳ trước (so sánh "kỳ này đến hôm nay" với "kỳ trước đến cùng ngày")
        self.prev_from = shift_period(period_type, d_from, -1)
        prev_end = period_bounds(period_type, self.prev_from)[1]
        span = (min(today, d_to) - d_from) if not self.is_future else (d_to - d_from)
        self.prev_to = min(self.prev_from + span, prev_end)

    # ---------------------------------------------------------------- scopes
    def scope(self, date_from, date_to, doctor=None):
        key = (date_from, date_to, doctor.id if doctor else 0)
        if key not in self._scopes:
            self._scopes[key] = self.engine._scope(date_from, date_to, self.companies, doctor, today=self.today)
        return self._scopes[key]

    def value(self, metric, date_from, date_to, doctor=None):
        return self.engine.compute_metric(metric, self.scope(date_from, date_to, doctor))

    # ---------------------------------------------------------------- targets
    def target_for(self, metric, doctor=None):
        """(giá trị, nguồn, bản ghi) – nguồn: target (Giám đốc đặt) / derived (cộng các kỳ nhỏ) / dmag (chuẩn)."""
        info = METRICS[metric]
        doctor_id = doctor.id if doctor else False
        rows = self.targets.filtered(lambda t: t.metric == metric and t.practitioner_id.id == doctor_id)

        def combine(recs):
            values = recs.mapped('target_value')
            return sum(values) if info['kind'] == 'sum' else sum(values) / len(values)

        explicit = rows.filtered(lambda t: t.period_type == self.ptype and t.date_from == self.d_from)
        if explicit:
            return combine(explicit), 'target', explicit
        for sub in ('month', 'quarter'):
            if PERIOD_MONTHS[sub] >= PERIOD_MONTHS[self.ptype]:
                continue
            subrows = rows.filtered(lambda t, s=sub: t.period_type == s)
            if not subrows:
                continue
            expected = PERIOD_MONTHS[self.ptype] // PERIOD_MONTHS[sub]
            complete = all(len(set(subrows.filtered(lambda t, c=c: t.company_id == c).mapped('date_from'))) == expected
                           for c in subrows.mapped('company_id'))
            if info['kind'] == 'sum' and not complete:
                continue
            return combine(subrows), 'derived', subrows
        if not doctor and info.get('default') is not None:
            default = info['default']
            if metric == 'cogs_ratio':
                thresholds = [c.dmag_cogs_threshold for c in self.companies
                              if 'dmag_cogs_threshold' in c._fields and c.dmag_cogs_threshold]
                default = max(thresholds) if thresholds else default
            return default, 'dmag', rows.browse()
        return None, None, rows.browse()

    # ---------------------------------------------------------------- status
    def evaluate(self, metric, actual, target):
        info = METRICS[metric]
        res = {'achieved_pct': None, 'forecast': None, 'forecast_pct': None, 'gap': None, 'per_day': None,
               'status': 'no_data'}
        if actual is None:
            return res
        if target is None:
            res['status'] = 'no_target'
            if info['kind'] == 'sum' and self.wd_elapsed:
                res['forecast'] = actual if self.is_past else actual / self.wd_elapsed * self.wd_total
            return res
        if info['kind'] == 'sum':
            res['achieved_pct'] = round(actual * 100.0 / target, 1) if target else None
            forecast = actual if self.is_past else (actual / self.wd_elapsed * self.wd_total if self.wd_elapsed
                                                    else None)
            res['forecast'] = forecast
            res['gap'] = max(target - actual, 0.0)
            if res['gap'] and self.wd_left and not self.is_past:
                res['per_day'] = res['gap'] / self.wd_left
            if forecast is not None and target:
                res['forecast_pct'] = round(forecast * 100.0 / target, 1)
            if self.is_past:
                res['status'] = 'achieved' if actual >= target else 'missed'
            elif actual >= target:
                res['status'] = 'achieved'
            elif forecast is None:
                res['status'] = 'not_started'
            else:
                ratio = forecast / target if target else 1.0
                res['status'] = 'on_track' if ratio >= 1 else 'behind' if ratio >= 0.9 else 'at_risk'
            return res
        # chỉ số tỷ lệ / trung bình: so trực tiếp
        if info['unit'] == 'score':
            diff = actual - target
            ratio = 1.0 if diff >= 0 else (0.95 if diff >= -10 else 0.0)
            res['achieved_pct'] = round(actual * 100.0 / target, 1) if target > 0 else None
        elif info['direction'] == 'lower':
            ratio = (target / actual) if actual > 0 else 10.0
            res['achieved_pct'] = round(min(ratio, 9.99) * 100.0, 1)
        else:
            ratio = (actual / target) if target else 1.0
            res['achieved_pct'] = round(ratio * 100.0, 1)
        res['gap'] = round((target - actual) if info['direction'] == 'higher' else (actual - target), 1)
        if self.is_past:
            res['status'] = 'achieved' if ratio >= 1 else 'missed'
        else:
            res['status'] = 'on_track' if ratio >= 1 else 'behind' if ratio >= 0.9 else 'at_risk'
        return res

    # ---------------------------------------------------------------- cards
    def card(self, metric, doctor=None, trend=True):
        info = METRICS[metric]
        actual = self.value(metric, self.d_from, self.d_to, doctor)
        target, source, records = self.target_for(metric, doctor)
        card = {
            'key': metric if not doctor else '%s_%s' % (metric, doctor.id),
            'metric': metric, 'label': info['label'], 'short': info['short'], 'kind': info['kind'],
            'unit': info['unit'], 'direction': info['direction'], 'formula': info['formula'],
            'actual': actual, 'target': target, 'target_source': source,
            'owner': ', '.join(n for n in records.mapped('user_id.name') if n),
            'objective': ', '.join(sorted(set(n for n in records.mapped('objective') if n))),
            'note': '\n'.join(n for n in records.mapped('note') if n),
            'target_ids': records.ids,
        }
        card.update(self.evaluate(metric, actual, target))
        card['status_label'] = STATUS_LABELS[card['status']]
        if trend:
            if not self.is_future:
                prev = self.value(metric, self.prev_from, self.prev_to, doctor)
                card['prev'] = prev
                if prev is not None and actual is not None:
                    if info['kind'] == 'sum':
                        card['delta'] = round((actual - prev) * 100.0 / abs(prev), 1) if prev else None
                        card['delta_unit'] = '%'
                    else:
                        card['delta'] = round(actual - prev, 1)
                        card['delta_unit'] = ' điểm' if info['unit'] == 'score' else ('′' if info['unit'] == 'min'
                                                                                  else ' điểm %')
            points = []
            for i in range(TREND_PERIODS - 1, -1, -1):
                start = shift_period(self.ptype, self.d_from, -i)
                end = period_bounds(self.ptype, start)[1]
                points.append({'label': period_short_label(self.ptype, start),
                               'value': self.value(metric, start, end, doctor),
                               'partial': i == 0 and not self.is_past})
            card['spark'] = points
        card['action'] = self.drill(metric, doctor)
        return card

    # ---------------------------------------------------------------- drill-down
    def act(self, model, name, domain, context=None):
        if model not in self.env or not self.env[model].check_access_rights('read', raise_exception=False):
            return None
        return {'type': 'ir.actions.act_window', 'name': name, 'res_model': model,
                'domain': _clean_domain(domain), 'views': [[False, 'list'], [False, 'form']],
                'target': 'current', 'context': dict(context or {}, create=False)}

    def drill(self, metric, doctor=None):
        s = self.scope(self.d_from, self.d_to, doctor)
        label = METRICS[metric]['label']
        name = '%s · %s' % (label, period_label(self.ptype, self.d_from))
        if doctor:
            name = '%s · %s' % (name, doctor.name)
        proc = s.dom_procedures()
        visits = s.dom_visits()
        plans = s.dom_plans()
        if metric in ('revenue', 'gross_profit', 'associate_share'):
            return self.act('dmag.dental.procedure', name, proc)
        if metric == 'implant_cases':
            return self.act('dmag.dental.procedure', name, proc + [('product_id.dental_category', '=', 'implant')])
        if metric == 'ortho_new':
            ids = self.engine._ortho_first_procedures(s).ids
            return self.act('dmag.dental.procedure', name, [('id', 'in', ids)])
        if metric == 'collected':
            if 'dmag.payment.log' in self.env:
                return self.act('dmag.payment.log', name, [
                    ('company_id', 'in', self.companies.ids), ('local_date', '>=', s.date_from),
                    ('local_date', '<=', s.date_to)] + s.doctor_domain('visit_id.doctor_id'))
            return None
        if metric in ('new_patients', 'referral_rate'):
            return self.act('dmag.dental.visit', name, visits + [('state', '=', 'done'), ('is_new_patient', '=', True)])
        if metric in ('plan_acceptance', 'consult_rate'):
            return self.act('dmag.treatment.plan', name, plans + [('state', '!=', 'draft')])
        if metric == 'completion_rate':
            return self.act('dmag.treatment.plan', name, plans + [('state', 'in', ACCEPTED)])
        if metric == 'booked':
            return self.act('dmag.dental.visit', name, visits + [('state', '!=', 'cancel')])
        if metric == 'show_up_rate':
            return self.act('dmag.dental.visit', name, visits + [('state', 'in', SHOWED + ('no_show',))])
        if metric == 'return_rate':
            return self.act('dmag.dental.visit', name, visits + [('is_new_patient', '=', False),
                                                                 ('state', 'in', SHOWED + ('no_show',))])
        if metric == 'avg_wait':
            return self.act('dmag.dental.visit', name, visits + [('chair_time', '!=', False)])
        if metric in ('chair_util_am', 'chair_util_pm'):
            return self.act('dmag.dental.visit', name, visits + [('state', 'not in', ('cancel', 'no_show'))])
        if metric == 'nps':
            return self.act('dmag.nps.response', name, s.dom_nps())
        if metric == 'complaint_rate':
            return self.act('dmag.nps.response', name, [('company_id', 'in', self.companies.ids),
                                                        ('is_complaint', '=', True), ('date', '>=', s.dt_from),
                                                        ('date', '<', s.dt_to)] + s.doctor_domain())
        if metric == 'cogs_ratio':
            return self.act('dmag.material.usage', name, [('company_id', 'in', self.companies.ids),
                                                          ('date', '>=', s.dt_from), ('date', '<', s.dt_to)])
        return None


class DmagGoalDashboard(models.AbstractModel):
    _name = 'dmag.goal.dashboard'
    _description = 'DMAG – Bảng điều hành mục tiêu'

    @api.model
    def get_goal_dashboard(self, period_type='month', date_ref=False, company_id=False):
        """Toàn bộ dữ liệu Bảng điều hành mục tiêu cho kỳ chứa ``date_ref`` (mặc định hôm nay)."""
        if not is_manager(self.env):
            raise AccessError(_('Bảng điều hành mục tiêu chỉ dành cho Quản lý phòng khám / Giám đốc.'))
        if period_type not in PERIOD_MONTHS:
            period_type = 'month'
        today = fields.Date.context_today(self)
        ref = fields.Date.to_date(date_ref) if date_ref else today
        d_from, d_to = period_bounds(period_type, ref)
        companies = self.env.companies
        if company_id and company_id in companies.ids:
            companies = self.env['res.company'].browse(company_id)
        board = GoalBoard(self.env, period_type, d_from, d_to, companies, today)

        north = [board.card(m) for m in NORTH_STAR]
        result = {
            'period': {
                'type': period_type, 'from': fields.Date.to_string(d_from), 'to': fields.Date.to_string(d_to),
                'label': period_label(period_type, d_from), 'today': fields.Date.to_string(today),
                'wd_total': board.wd_total, 'wd_elapsed': board.wd_elapsed, 'wd_left': board.wd_left,
                'elapsed_pct': round(board.wd_elapsed * 100.0 / board.wd_total, 1) if board.wd_total else 0.0,
                'is_past': board.is_past, 'is_future': board.is_future,
                'prev_ref': fields.Date.to_string(shift_period(period_type, d_from, -1)),
                'next_ref': fields.Date.to_string(shift_period(period_type, d_from, 1)),
                'prev_label': '%s → %s' % (board.prev_from.strftime('%d/%m'), board.prev_to.strftime('%d/%m/%Y')),
            },
            'companies': [{'id': c.id, 'name': c.name} for c in self.env.companies],
            'company_id': companies.id if len(companies) == 1 else False,
            'company_names': ', '.join(companies.mapped('name')),
            'can_edit_targets': is_director(self.env),
            'targets': self._targets_meta(board),
            'north_star': north,
            'okr': self._okr(board),
            'funnel': self._funnel(board),
            'service': [board.card(m) for m in SERVICE],
            'people': self._people(board),
            'finance': self._finance(board),
        }
        result['alerts'] = self._alerts(board, result)
        return result

    # ------------------------------------------------------------------ targets meta
    def _targets_meta(self, board):
        explicit = board.targets.filtered(lambda t: t.period_type == board.ptype and t.date_from == board.d_from)
        Target = self.env['dmag.business.target']
        domain = [('company_id', 'in', board.companies.ids), ('period_type', '=', board.ptype),
                  ('date_from', '=', board.d_from)]
        action = {
            'type': 'ir.actions.act_window', 'name': 'Mục tiêu kinh doanh · %s' % period_label(board.ptype, board.d_from),
            'res_model': 'dmag.business.target', 'domain': _clean_domain(domain),
            'views': [[False, 'list'], [False, 'form']], 'target': 'current',
            'context': {'default_period_type': board.ptype, 'default_date_from': fields.Date.to_string(board.d_from)},
        }
        drafts = Target.sudo().search_count(domain + [('state', '=', 'draft')])
        return {'count': len(explicit), 'company_level': len(explicit.filtered(lambda t: not t.practitioner_id)),
                'doctor_level': len(explicit.filtered('practitioner_id')), 'drafts': drafts,
                'action': action if Target.check_access_rights('read', raise_exception=False) else None}

    # ------------------------------------------------------------------ OKR
    def _okr(self, board):
        res = {'okr_scale': False, 'objectives': [], 'guardrails': [], 'target_objectives': []}
        env = self.env
        if 'okr.scale.objective' in env:
            res['okr_scale'] = True
            objectives = env['okr.scale.objective'].sudo().search([
                ('company_id', 'in', board.companies.ids), ('state', 'not in', ('draft', 'cancelled')),
                ('cycle_id.date_start', '<=', board.d_to), ('cycle_id.date_end', '>=', board.d_from)],
                order='level_sequence, sequence, id', limit=12)
            for obj in objectives:
                krs = []
                for kr in obj.key_result_ids:
                    breached = bool(getattr(kr, 'dmag_guardrail_breached', False))
                    krs.append({
                        'id': kr.id, 'name': kr.name, 'owner': kr.owner_id.name or '', 'progress': kr.progress,
                        'current': kr.current_value, 'start': kr.start_value, 'target': kr.target_value,
                        'unit': kr.unit or '', 'status': kr.status or '', 'confidence': kr.confidence or '',
                        'breached': breached,
                    })
                res['objectives'].append({
                    'id': obj.id, 'name': obj.name, 'owner': obj.owner_id.name or '', 'progress': obj.progress,
                    'cycle': obj.cycle_id.name, 'level': obj.level, 'krs': krs,
                    'expected': getattr(obj, 'expected_progress', 0.0) or 0.0,
                    'action': {'type': 'ir.actions.act_window', 'res_model': 'okr.scale.objective', 'res_id': obj.id,
                               'views': [[False, 'form']], 'target': 'current', 'name': obj.name},
                })
        if 'dmag.okr.guardrail' in env:
            for guard in env['dmag.okr.guardrail'].sudo().search([('company_id', 'in', board.companies.ids),
                                                                  ('active', '=', True)]):
                res['guardrails'].append({'id': guard.id, 'name': guard.name, 'value': guard.value,
                                          'threshold': guard.threshold, 'unit': guard.unit or '',
                                          'breached': guard.breached})
            res['guardrail_action'] = board.act('dmag.okr.guardrail', 'Chỉ số cầu chì',
                                                [('company_id', 'in', board.companies.ids)])
        # OKR từ mục tiêu kinh doanh của Giám đốc (Objective → các chỉ số đã chốt)
        explicit = board.targets.filtered(lambda t: t.period_type == board.ptype and t.date_from == board.d_from
                                          and t.objective)
        groups = {}
        for target in explicit.sorted(lambda t: (t.sequence, t.id)):
            groups.setdefault(target.objective.strip(), []).append(target)
        for name, targets in groups.items():
            krs = []
            for target in targets:
                card = board.card(target.metric, target.practitioner_id or None, trend=False)
                if target.practitioner_id:
                    card['label'] = '%s – %s' % (card['label'], target.practitioner_id.name)
                card['owner'] = target.user_id.name or target.practitioner_id.name or ''
                card['progress'] = max(0.0, min(100.0, card['achieved_pct'] or 0.0))
                krs.append(card)
            worst = max(krs, key=lambda k: STATUS_RANK.get(k['status'], 0))['status'] if krs else 'no_data'
            owners = sorted(set(k['owner'] for k in krs if k['owner']))
            res['target_objectives'].append({
                'name': name, 'owner': ', '.join(owners[:2]), 'krs': krs,
                'progress': round(sum(k['progress'] for k in krs) / len(krs), 1) if krs else 0.0,
                'status': worst, 'status_label': STATUS_LABELS[worst],
            })
        return res

    # ------------------------------------------------------------------ funnel
    def _funnel(self, board):
        s = board.scope(board.d_from, board.d_to)
        showed = s.visits.filtered(lambda v: v.state in SHOWED)
        consulted = s.presented_plans.mapped('patient_id') & showed.mapped('patient_id')
        accepted = s.accepted_plans
        steps = [
            ('booked', 'Đặt lịch', len(s.visits.filtered(lambda v: v.state != 'cancel')), 'lượt hẹn', None),
            ('show_up_rate', 'Đến khám', len(showed), 'lượt đến', 'show_up_rate'),
            ('consult_rate', 'Được tư vấn kế hoạch', len(consulted), 'khách', 'consult_rate'),
            ('plan_acceptance', 'Chốt kế hoạch', len(accepted), 'kế hoạch', 'plan_acceptance'),
            ('completion_rate', 'Hoàn tất điều trị', len(accepted.filtered(lambda p: p.state == 'done')),
             'kế hoạch', 'completion_rate'),
        ]
        result = []
        for key, label, count, unit, rate_metric in steps:
            step = {'key': key, 'label': label, 'count': count, 'unit': unit, 'rate': None}
            if rate_metric:
                step['rate'] = board.card(rate_metric, trend=False)
                step['rate']['prev'] = board.value(rate_metric, board.prev_from, board.prev_to) \
                    if not board.is_future else None
            step['action'] = board.drill(key)
            result.append(step)
        booked_card = board.card('booked', trend=False)
        return {'steps': result, 'booked': booked_card, 'after_care': [board.card(m) for m in AFTER_CARE],
                'no_show': len(s.visits.filtered(lambda v: v.state == 'no_show'))}

    # ------------------------------------------------------------------ people
    def _people(self, board):
        doctors = self.env['dmag.dental.practitioner'].sudo().search([
            ('role', '=', 'doctor'), ('company_id', 'in', board.companies.ids)])
        rows = []
        for doctor in doctors:
            s = board.scope(board.d_from, board.d_to, doctor)
            revenue = board.card('revenue', doctor, trend=False)
            extra = []
            for target in board.targets.filtered(lambda t, d=doctor: t.practitioner_id == d and t.metric != 'revenue'
                                                 and t.period_type == board.ptype and t.date_from == board.d_from):
                extra.append(board.card(target.metric, doctor, trend=False))
            rows.append({
                'id': doctor.id, 'name': doctor.name, 'title': doctor.title or '',
                'level': doctor.clinical_level_id.name or '', 'revenue': revenue,
                'plan_acceptance': board.value('plan_acceptance', board.d_from, board.d_to, doctor),
                'nps': board.value('nps', board.d_from, board.d_to, doctor),
                'cases': len(s.done_visits), 'new_patients': board.value('new_patients', board.d_from, board.d_to, doctor),
                'gross_profit': board.value('gross_profit', board.d_from, board.d_to, doctor),
                'extra': extra, 'action': board.drill('revenue', doctor),
            })
        rows.sort(key=lambda r: -(r['revenue']['actual'] or 0.0))
        return {'doctors': rows, 'plan_target': board.target_for('plan_acceptance')[0],
                'nps_target': board.target_for('nps')[0], 'roles': self._role_kpis(board)}

    def _role_kpis(self, board):
        if 'dmag.kpi.result' not in self.env:
            return {'installed': False, 'employees': [], 'profiles': []}
        results = self.env['dmag.kpi.result'].sudo().search([
            ('company_id', 'in', board.companies.ids), ('date_from', '>=', board.d_from),
            ('date_from', '<=', board.d_to)])
        by_emp = {}
        for res in results:
            emp = by_emp.setdefault(res.employee_id.id, {
                'id': res.employee_id.id, 'name': res.employee_id.name,
                'profile': (res.employee_id.dmag_profile_id.name if 'dmag_profile_id' in res.employee_id._fields
                            else '') or res.employee_id.job_title or '',
                'lines': {}, 'weighted': 0.0, 'weights': 0.0})
            line = emp['lines'].setdefault(res.kpi_id.id, {'name': res.kpi_id.name, 'unit': res.unit or '',
                                                           'actual': [], 'target': [], 'achievement': [],
                                                           'auto': res.is_auto})
            line['actual'].append(res.actual)
            line['target'].append(res.target or res.kpi_id.target)
            line['achievement'].append(res.achievement)
            emp['weighted'] += res.achievement * (res.weight or 0.0)
            emp['weights'] += res.weight or 0.0
        employees = []
        for emp in by_emp.values():
            lines = []
            for line in emp['lines'].values():
                n = len(line['actual'])
                lines.append({'name': line['name'], 'unit': line['unit'], 'auto': line['auto'],
                              'actual': round(sum(line['actual']) / n, 1), 'target': round(sum(line['target']) / n, 1),
                              'achievement': round(sum(line['achievement']) / n, 1)})
            score = round(emp['weighted'] / emp['weights'], 1) if emp['weights'] else (
                round(sum(l['achievement'] for l in lines) / len(lines), 1) if lines else 0.0)
            employees.append({'id': emp['id'], 'name': emp['name'], 'profile': emp['profile'], 'score': score,
                              # kỳ đang chạy: KPI cộng dồn chưa đủ kỳ → chỉ "tạm tính", không tô đỏ sớm
                              'status': ('provisional' if not board.is_past else
                                         'on_track' if score >= 100 else 'behind' if score >= 80 else 'at_risk'),
                              'lines': lines})
        employees.sort(key=lambda e: (e['profile'], -e['score']))
        profiles = {}
        for emp in employees:
            profiles.setdefault(emp['profile'] or 'Khác', []).append(emp['score'])
        return {
            'installed': True, 'employees': employees,
            'profiles': [{'name': k, 'score': round(sum(v) / len(v), 1), 'count': len(v)} for k, v in profiles.items()],
            'action': board.act('dmag.kpi.result', 'Kết quả KPI · %s' % period_label(board.ptype, board.d_from), [
                ('company_id', 'in', board.companies.ids), ('date_from', '>=', board.d_from),
                ('date_from', '<=', board.d_to)]),
        }

    # ------------------------------------------------------------------ finance
    def _finance(self, board):
        s = board.scope(board.d_from, board.d_to)
        engine = board.engine
        revenue = engine.compute_metric('revenue', s)
        material, lab, commission = s.material_cost(), s.lab_cost(), s.commission_cost()
        gross = engine.compute_metric('gross_profit', s)
        collected = engine.compute_metric('collected', s)
        moves = self.env['account.move'].sudo().search([
            ('company_id', 'in', board.companies.ids), ('move_type', '=', 'out_invoice'), ('state', '=', 'posted'),
            ('amount_residual', '>', 0)])
        overdue = moves.filtered(lambda m: m.invoice_date_due and m.invoice_date_due < board.today)
        visit_dom = [('company_id', 'in', board.companies.ids), ('invoice_ids', 'in', moves.ids)]
        overdue_dom = [('company_id', 'in', board.companies.ids), ('invoice_ids', 'in', overdue.ids)]
        steps = [
            {'key': 'revenue', 'label': 'Doanh thu dịch vụ', 'value': revenue, 'kind': 'total',
             'action': board.drill('revenue')},
            {'key': 'material', 'label': 'Vật tư tiêu hao', 'value': material, 'kind': 'minus',
             'action': board.act('dmag.material.usage', 'Vật tư tiêu hao', [
                 ('company_id', 'in', board.companies.ids), ('date', '>=', s.dt_from), ('date', '<', s.dt_to)])},
            {'key': 'lab', 'label': 'Chi phí labo', 'value': lab, 'kind': 'minus',
             'action': board.act('dmag.lab.order', 'Phiếu labo', [
                 ('company_id', 'in', board.companies.ids), ('state', 'not in', ('draft', 'cancelled')),
                 ('sent_date', '>=', board.d_from), ('sent_date', '<=', board.d_to)])},
            {'key': 'commission', 'label': 'Hoa hồng / thủ thuật phí', 'value': commission, 'kind': 'minus',
             'action': board.act('dmag.commission.line', 'Hoa hồng', [
                 ('company_id', 'in', board.companies.ids), ('state', '=', 'valid'),
                 ('date', '>=', board.d_from), ('date', '<=', board.d_to)])},
            {'key': 'gross_profit', 'label': 'Lợi nhuận gộp', 'value': gross, 'kind': 'total',
             'action': None},
        ]
        return {
            'waterfall': steps, 'revenue': revenue, 'gross_profit': gross,
            'margin_pct': round(gross * 100.0 / revenue, 1) if revenue else None,
            'collected': collected,
            'collection_pct': round(collected * 100.0 / revenue, 1) if revenue and collected is not None else None,
            'receivable': sum(moves.mapped('amount_residual')), 'receivable_count': len(moves),
            'overdue': sum(overdue.mapped('amount_residual')), 'overdue_count': len(overdue),
            'receivable_action': board.act('dmag.dental.visit', 'Lượt khám còn công nợ', visit_dom),
            'overdue_action': board.act('dmag.dental.visit', 'Công nợ quá hạn', overdue_dom),
            'cogs': board.card('cogs_ratio', trend=False),
        }

    # ------------------------------------------------------------------ alerts
    def _alerts(self, board, data):
        alerts = []

        def add(level, title, detail, todo, action, label='Mở danh sách'):
            alerts.append({'level': level, 'title': title, 'detail': detail, 'todo': todo,
                           'action': action, 'action_label': label})

        if not data['targets']['count'] and not board.is_past:
            add('info', 'Kỳ này chưa có mục tiêu kinh doanh được chốt',
                'Thẻ hiển thị "Chưa đặt mục tiêu" hoặc chuẩn DMAG – chưa đo được tiến độ theo kế hoạch của phòng khám.',
                'Giám đốc đặt mục tiêu doanh thu, thực thu, khách mới, ca implant/chỉnh nha… rồi bấm "Chốt".',
                data['targets']['action'], 'Đặt mục tiêu')
        for card in data['north_star'] + data['service']:
            if card['status'] not in ('at_risk', 'missed'):
                continue
            if card['kind'] == 'sum' and card['forecast_pct'] is not None:
                detail = 'Thực tế %s / mục tiêu %s – dự báo cuối kỳ %s (%s%% mục tiêu).' % (
                    fmt_value(card['unit'], card['actual']), fmt_value(card['unit'], card['target']),
                    fmt_value(card['unit'], card['forecast']), round(card['forecast_pct']))
                if card['per_day']:
                    detail += ' Cần thêm %s / ngày làm việc còn lại.' % fmt_value(card['unit'], card['per_day'])
            else:
                detail = 'Hiện tại %s – mục tiêu %s%s.' % (
                    fmt_value(card['unit'], card['actual']), '≤ ' if card['direction'] == 'lower' else '≥ ',
                    fmt_value(card['unit'], card['target']))
            todo = {
                'revenue': 'Lấp ghế trống buổi chiều, gọi lại khách đang cân nhắc kế hoạch.',
                'collected': 'Rà công nợ, nhắc khách trả góp đến hạn, kiểm tra lượt hoàn tất chưa thu.',
                'new_patients': 'Đẩy kênh giới thiệu và chương trình khám tổng quát.',
                'implant_cases': 'Gọi lại khách đã tư vấn implant nhưng chưa chốt.',
                'ortho_new': 'Gọi lại khách đã tư vấn chỉnh nha nhưng chưa chốt.',
                'plan_acceptance': 'Rà các kế hoạch "Đã tư vấn" chưa chốt, hẹn tư vấn lại với bác sĩ.',
                'gross_profit': 'Rà vật tư phát sinh ngoài định mức và chi phí labo làm lại.',
                'avg_wait': 'Xem lại xếp lịch: tránh 2 ca nặng trùng giờ, gọi khách đến đúng giờ.',
                'chair_util_pm': 'Ưu tiên xếp lịch khung 13:30–16:30, ưu đãi khung chiều.',
                'nps': 'Gọi khách chấm điểm thấp, xử lý phàn nàn trong 24 giờ.',
                'complaint_rate': 'Xử lý phiếu phàn nàn đang mở, họp rút kinh nghiệm.',
                'cogs_ratio': 'Rà vật tư dùng vượt định mức và labo làm lại.',
                'associate_share': 'Chuyển bớt ca thường cho bác sĩ phụ đủ phạm vi hành nghề.',
            }.get(card['metric'], 'Xem chi tiết để tìm nguyên nhân.')
            add('danger', '%s: %s' % (card['label'], card['status_label'].lower()), detail, todo, card['action'],
                'Xem chi tiết')
        for step in data['funnel']['steps']:
            rate = step['rate']
            if rate and rate['status'] == 'at_risk':
                add('warning', 'Hành trình khách hàng: %s thấp' % rate['short'].lower(),
                    'Hiện %s – mục tiêu ≥ %s.' % (fmt_value('pct', rate['actual']), fmt_value('pct', rate['target'])),
                    {'show_up_rate': 'Gọi / nhắn ZNS xác nhận lịch hẹn ngày mai, gọi lại khách không đến.',
                     'consult_rate': 'Bác sĩ lập kế hoạch điều trị cho mọi khách có chỉ định.',
                     'plan_acceptance': 'Hẹn tư vấn lại khách đang cân nhắc.',
                     'completion_rate': 'Gọi khách bỏ dở kế hoạch, đặt lịch buổi tiếp theo.'}.get(step['key'], ''),
                    rate['action'])
        env = self.env
        finance = data['finance']
        if finance['overdue']:
            add('warning', 'Công nợ quá hạn %s lượt khám' % finance['overdue_count'],
                'Tổng %s đã quá hạn thanh toán.' % fmt_value('money', finance['overdue']),
                'Lễ tân / thu ngân gọi nhắc khách, ghi chú hẹn thanh toán.', finance['overdue_action'])
        if 'dmag.lab.order' in env:
            late = env['dmag.lab.order'].sudo().search_count([('company_id', 'in', board.companies.ids),
                                                               ('is_late', '=', True)])
            if late:
                add('warning', '%s phiếu labo trễ hẹn' % late, 'Phục hình chưa về đúng hẹn – nguy cơ dời lịch gắn.',
                    'Gọi labo xác nhận ngày trả, báo khách dời lịch nếu cần.',
                    board.act('dmag.lab.order', 'Phiếu labo trễ hẹn', [('company_id', 'in', board.companies.ids),
                                                                       ('is_late', '=', True)]))
        if 'dmag.nps.response' in env:
            open_complaints = env['dmag.nps.response'].sudo().search_count([
                ('company_id', 'in', board.companies.ids), ('is_complaint', '=', True),
                ('complaint_resolved', '=', False)])
            if open_complaints:
                add('danger', '%s phàn nàn chưa xử lý' % open_complaints, 'Khách chấm điểm thấp / phàn nàn chưa được phản hồi.',
                    'Quản lý gọi khách trong 24 giờ, ghi nhận và đánh dấu "Đã xử lý".',
                    board.act('dmag.nps.response', 'Phàn nàn chưa xử lý', [
                        ('company_id', 'in', board.companies.ids), ('is_complaint', '=', True),
                        ('complaint_resolved', '=', False)]))
        if 'dmag.compliance.doc' in env and hasattr(env['dmag.compliance.doc'], 'get_compliance_status'):
            red, names = 0, []
            for company in board.companies:
                try:
                    status = env['dmag.compliance.doc'].sudo().get_compliance_status(company.id)
                except Exception:  # noqa: BLE001 – module tùy chọn không làm hỏng bảng điều hành
                    continue
                red += len(status.get('red_items') or [])
                names += [i.get('name') for i in status.get('red_items') or []]
            if red:
                add('danger', 'Pháp chế: %s hồ sơ / thiết bị cần xử lý ngay' % red, ', '.join(names[:4])
                    + ('…' if len(names) > 4 else ''),
                    'Gia hạn giấy phép / kiểm định, bổ sung hồ sơ còn thiếu trước khi bị thanh tra.',
                    board.act('dmag.compliance.doc', 'Hồ sơ pháp chế', [('company_id', 'in', board.companies.ids)]))
        for guard in data['okr']['guardrails']:
            if guard['breached']:
                add('danger', 'Cầu chì OKR vượt ngưỡng: %s' % guard['name'],
                    'Giá trị %s%s > ngưỡng %s%s.' % (fmt_value(None, guard['value']), guard['unit'],
                                                     fmt_value(None, guard['threshold']), guard['unit']),
                    'Dừng đẩy chỉ tiêu liên quan, họp xử lý nguyên nhân (y đức / trải nghiệm khách).',
                    data['okr'].get('guardrail_action'))
        order = {'danger': 0, 'warning': 1, 'info': 2}
        alerts.sort(key=lambda a: order[a['level']])
        return alerts
