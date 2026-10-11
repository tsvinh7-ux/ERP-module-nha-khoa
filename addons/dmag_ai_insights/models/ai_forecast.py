"""AI-16 – Dự báo doanh thu & nhu cầu vật tư (TẠI CHỖ, không gửi dữ liệu, không thư viện nặng).

Doanh thu từng ngày làm việc còn lại của kỳ = phần đã có lịch + phần sẽ phát sinh thêm:
* **Lịch đã đặt**: Σ giá trị dịch vụ dự kiến của lượt hẹn (hoặc giá trị trung bình / lượt nếu chưa ghi dịch vụ)
  × tỷ lệ đến khám lịch sử × hệ số quy đổi lịch sử (doanh thu thực / giá trị dự kiến của lượt đã đến);
* **Sẽ phát sinh**: dự báo chuỗi doanh thu ngày mở cửa theo Lịch làm việc phòng khám (Holt-Winters cộng tính, mùa vụ
  tuần = số thứ mở cửa, mặc định 6; ngày nghỉ lễ không tính, xu hướng hãm) ×
  (1 − tỷ trọng doanh thu thường đã có lịch ở cùng khoảng cách ngày) – học từ thời điểm đặt lịch trong lịch sử;
* **Mùa vụ theo tháng**: chỉ số tháng khi có ≥ 13 tháng lịch sử (chưa đủ → 1,0 và ghi rõ);
* **Khoảng tin cậy 80 %**: sai số dự báo một bước của mô hình + phương sai nhị thức của việc khách đến / không đến.
Vật tư 30 ngày tới = max(nhịp tiêu hao lịch sử, lịch hẹn × định mức + kế hoạch tồn đọng × tỷ lệ thực hiện) so với tồn
kho → gợi ý đặt hàng.
"""
import math
from collections import defaultdict
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

from odoo.addons.dmag_dental_base.models.dmag_access import is_manager
from odoo.addons.dmag_dental_goals.models.dmag_goal_metrics import period_bounds

from . import forecast_math as fm
from .ai_common import vnd

HISTORY_DAYS = 120
MAX_LEAD = 30


class DmagAiForecast(models.AbstractModel):
    _name = 'dmag.ai.forecast'
    _description = 'DMAG AI-16 – Dự báo doanh thu & vật tư'

    # ------------------------------------------------------------------ dữ liệu lịch sử
    @api.model
    def _today(self):
        return fields.Date.context_today(self)

    @api.model
    def _schedule(self):
        """Lịch làm việc phòng khám (ngày mở cửa, nghỉ lễ) – mùa vụ tuần = số thứ mở cửa trong tuần."""
        return self.env['dmag.clinic.schedule'].get_info(self.env.company)

    @api.model
    def _daily_history(self, d_from, d_to):
        """Doanh thu theo ngày mở cửa (Lịch làm việc phòng khám) trong [d_from, d_to] – cùng định nghĩa chỉ số
        'revenue'."""
        engine = self.env['dmag.goal.engine']
        scope = engine._scope(d_from, d_to, self.env.companies, today=self._today())
        daily = defaultdict(float)
        for proc in scope.procedures:
            daily[scope.local(proc.visit_id.scheduled_start).date()] += proc.amount
        days = self._schedule().open_days(d_from, d_to)  # ngày mở cửa (thứ nghỉ, nghỉ lễ không tính)
        return days, [daily.get(d, 0.0) for d in days], scope

    @api.model
    def _first_activity(self):
        Visit = self.env['dmag.dental.visit'].sudo()
        first = Visit.search([('company_id', 'in', self.env.companies.ids), ('state', '=', 'done')],
                             order='scheduled_start asc', limit=1)
        return first.scheduled_start.date() if first else self._today()

    @api.model
    def _booking_stats(self, scope):
        """Tỷ lệ đến khám, hệ số quy đổi giá trị dự kiến → doanh thu, giá trị TB / lượt, tỷ trọng đặt trước theo h."""
        visits = scope.visits.filtered(lambda v: v.state in ('arrived', 'in_chair', 'done', 'no_show'))
        showed = visits.filtered(lambda v: v.state != 'no_show')
        show_rate = len(showed) / len(visits) if visits else 0.85
        done = scope.visits.filtered(lambda v: v.state == 'done')
        rev_by_visit = defaultdict(float)
        for proc in scope.procedures:
            rev_by_visit[proc.visit_id.id] += proc.amount
        planned = sum(sum(v.service_ids.mapped('lst_price')) for v in done)
        actual_planned = sum(rev_by_visit.get(v.id, 0.0) for v in done if v.service_ids)
        conversion = actual_planned / planned if planned else 1.0
        avg_ticket = (sum(rev_by_visit.values()) / len(done)) if done else 0.0
        # tỷ trọng doanh thu đã có lịch trước h ngày (lead time = giờ hẹn − thời điểm tạo lịch)
        total = sum(rev_by_visit.values()) or 1.0
        lead_rev = defaultdict(float)
        for v in done:
            lead = max(0, (v.scheduled_start.date() - v.create_date.date()).days)
            lead_rev[min(lead, MAX_LEAD)] += rev_by_visit.get(v.id, 0.0)
        share = []
        for h in range(MAX_LEAD + 1):
            share.append(sum(val for lead, val in lead_rev.items() if lead >= h) / total)
        return {'show_rate': show_rate, 'conversion': max(0.3, min(conversion, 2.0)), 'avg_ticket': avg_ticket,
                'booked_share': share, 'n_visits': len(visits)}

    @api.model
    def _monthly_index(self, today):
        """Chỉ số mùa vụ theo tháng (cần ≥ 13 tháng lịch sử)."""
        first = self._first_activity()
        months = (today.year - first.year) * 12 + today.month - first.month
        if months < 13:
            return None, months
        engine = self.env['dmag.goal.engine']
        values = defaultdict(list)
        start = (today.replace(day=1) - relativedelta(months=24))
        for i in range(24):
            m_from = start + relativedelta(months=i)
            if m_from < first.replace(day=1):
                continue
            m_to = period_bounds('month', m_from)[1]
            rev = engine.compute_metric('revenue', engine._scope(m_from, m_to, self.env.companies, today=today)) or 0
            wd = self._schedule().count_open_days(m_from, m_to) or 1
            values[m_from.month].append(rev / wd)
        overall = fm.mean([v for vals in values.values() for v in vals]) or 1.0
        return {m: fm.mean(v) / overall for m, v in values.items()}, months

    # ------------------------------------------------------------------ dự báo doanh thu
    @api.model
    def _revenue_forecast(self, month_from=None, today=None):
        today = today or self._today()
        month_from = month_from or today.replace(day=1)
        m_from, m_to = period_bounds('month', month_from)
        hist_from = max(self._first_activity(), today - timedelta(days=HISTORY_DAYS))
        hist_to = today - timedelta(days=1)
        if hist_to < hist_from:
            hist_from = hist_to
        days, series, scope = self._daily_history(hist_from, hist_to)
        stats = self._booking_stats(scope)
        schedule = self._schedule()
        all_future = schedule.open_days(today, m_to) if m_to >= today else []
        while len(series) > 12 and series[0] == 0.0:  # bỏ các ngày trước khi có hoạt động
            series = series[1:]
        capped, spike_rate, spike_var, spike_cap = fm.split_spikes(series)
        # mùa vụ tuần = số ngày mở cửa trong tuần (mặc định 6: Thứ 2 – Thứ 7)
        hw = fm.holt_winters(capped, len(all_future) + 1, season=max(1, len(schedule.open_weekdays())))
        step = {d: i for i, d in enumerate(all_future)}
        future = [d for d in all_future if d >= m_from]
        seasonal, months_hist = self._monthly_index(today)
        # lịch đã đặt cho các ngày còn lại
        engine = self.env['dmag.goal.engine']
        fut_scope = engine._scope(max(today, m_from), m_to, self.env.companies, today=today) if future else None
        booked_by_day = defaultdict(lambda: [0.0, 0.0, 0])  # giá trị kỳ vọng, phương sai, số lượt
        if fut_scope:
            for v in fut_scope.visits.filtered(lambda v: v.state in ('draft', 'confirmed', 'arrived', 'in_chair')):
                day = fut_scope.local(v.scheduled_start).date()
                value = sum(v.service_ids.mapped('lst_price')) * stats['conversion'] or stats['avg_ticket']
                p = 1.0 if v.state in ('arrived', 'in_chair') else stats['show_rate']
                booked_by_day[day][0] += value * p
                booked_by_day[day][1] += value * value * p * (1 - p)
                booked_by_day[day][2] += 1
        actual_to_date = 0.0
        daily_actual = defaultdict(float)
        if today > m_from:
            actual_scope = engine._scope(m_from, min(today - timedelta(days=1), m_to), self.env.companies,
                                         today=today)
            actual_to_date = engine.compute_metric('revenue', actual_scope) or 0.0
            for proc in actual_scope.procedures:
                daily_actual[actual_scope.local(proc.visit_id.scheduled_start).date()] += proc.amount
        # tỷ trọng đặt trước học được chỉ tin cậy khi lịch sử thật sự có lịch đặt trước ≥ 1 ngày
        reliable = len(stats['booked_share']) > 1 and stats['booked_share'][1] >= 0.05
        rows, variance, remaining, booked_total = [], 0.0, 0.0, 0.0
        sigma = hw['sigma']
        for day in future:
            i = step[day]
            h = (day - today).days
            share = stats['booked_share'][min(h, MAX_LEAD)] if stats['booked_share'] else 0.0
            base = (hw['forecast'][i] + spike_rate) * (seasonal.get(day.month, 1.0) if seasonal else 1.0)
            b_val, b_var, b_cnt = booked_by_day.get(day, (0.0, 0.0, 0))
            if reliable:
                unbooked = max(0.0, base * (1.0 - share))
                value = b_val + unbooked
            else:  # lịch sử không cho biết khách đặt trước bao lâu → không cộng trùng phần đã có lịch
                value = max(base, b_val)
                unbooked = value - b_val
            variance += (sigma * (1.0 - share)) ** 2 + spike_var * (1.0 - share) + b_var
            remaining += value
            booked_total += b_val
            rows.append({'date': str(day), 'booked': round(b_val), 'unbooked': round(unbooked), 'value': round(value),
                         'visits': b_cnt, 'share': round(share, 3)})
        total = actual_to_date + remaining
        half = fm.Z80 * math.sqrt(variance)
        board_target = None
        try:
            from odoo.addons.dmag_dental_goals.models.dmag_goal_dashboard import GoalBoard
            board = GoalBoard(self.env, 'month', m_from, m_to, self.env.companies, today)
            board_target = board.target_for('revenue')[0]
        except Exception:  # noqa: BLE001
            board_target = None
        prob = None
        if board_target:
            sd = math.sqrt(variance) or 1.0
            prob = round(100 * (1 - fm.norm_cdf((board_target - total) / sd)), 1) if variance else (
                100.0 if total >= board_target else 0.0)
        cumulative, running = [], 0.0
        for d in [m_from + timedelta(days=i) for i in range((m_to - m_from).days + 1)]:
            if d < today:
                running += daily_actual.get(d, 0.0)
                cumulative.append({'date': str(d), 'actual': round(running)})
        fc_running, lo_var = running, 0.0
        for row in rows:
            fc_running += row['value']
            cumulative.append({'date': row['date'], 'forecast': round(fc_running)})
        # dải tin cậy tích lũy (phương sai cộng dồn)
        acc_var = 0.0
        idx = 0
        for point in cumulative:
            if 'forecast' in point:
                row = rows[idx]
                h_share = row['share']
                acc_var += (sigma * (1 - h_share)) ** 2 + spike_var * (1 - h_share)
                b_var = booked_by_day.get(fields.Date.to_date(row['date']), (0, 0, 0))[1]
                acc_var += b_var
                band = fm.Z80 * math.sqrt(acc_var)
                point['low'] = round(max(running, point['forecast'] - band))
                point['high'] = round(point['forecast'] + band)
                idx += 1
        return {
            'month': '%02d/%s' % (m_from.month, m_from.year), 'from': str(m_from), 'to': str(m_to),
            'today': str(today), 'actual_to_date': actual_to_date, 'remaining': remaining,
            'booked_part': booked_total, 'unbooked_part': remaining - booked_total, 'total': total,
            'low': max(actual_to_date, total - half), 'high': total + half, 'target': board_target,
            'prob_target': prob, 'days': rows, 'cumulative': cumulative,
            'model': {'method': hw['method'], 'params': hw['params'], 'sigma_day': sigma,
                      'history_days': len(series), 'show_rate': round(stats['show_rate'], 3),
                      'conversion': round(stats['conversion'], 3), 'avg_ticket': stats['avg_ticket'],
                      'booked_share_d1': round(stats['booked_share'][1], 3) if stats['booked_share'] else None,
                      'booked_share_d7': round(stats['booked_share'][7], 3) if stats['booked_share'] else None,
                      'monthly_seasonality': bool(seasonal), 'months_history': months_hist,
                      'pickup_reliable': reliable, 'spike_cap': spike_cap, 'spike_rate': spike_rate},
        }

    @api.model
    def _next_month_forecast(self, today):
        nxt = (today.replace(day=1) + relativedelta(months=1))
        res = self._revenue_forecast(month_from=nxt, today=today)
        return {'month': res['month'], 'total': res['total'], 'low': res['low'], 'high': res['high'],
                'booked_part': res['booked_part'], 'working_days': len(res['days']), 'target': res['target']}

    # ------------------------------------------------------------------ vật tư
    @api.model
    def _material_forecast(self, horizon=30, today=None):
        today = today or self._today()
        if 'dmag.material.usage' not in self.env:
            return {'installed': False, 'rows': []}
        companies = self.env.companies
        Usage = self.env['dmag.material.usage'].sudo()
        hist_days = 60
        since = fields.Datetime.to_datetime(today - timedelta(days=hist_days))
        usages = Usage.search([('company_id', 'in', companies.ids), ('date', '>=', since)])
        first = self._first_activity()
        span = max(7, min(hist_days, (today - first).days or hist_days))
        rate = defaultdict(float)
        for u in usages:
            rate[u.product_id] += u.quantity / span
        stats = self._booking_stats(self.env['dmag.goal.engine']._scope(today - timedelta(days=60), today,
                                                                         companies, today=today))
        Bom = self.env['dmag.service.bom'].sudo()
        company = self.env.company

        def requirements(product, teeth=0, qty=1.0):
            bom = Bom._dmag_find(product, company)
            out = {}
            for line in bom.line_ids:
                factor = (teeth or qty or 1.0) if line.basis == 'per_tooth' else 1.0
                out[line.product_id] = out.get(line.product_id, 0.0) + line.uom_id._compute_quantity(
                    line.quantity * factor, line.product_id.uom_id)
            return out

        scheduled = defaultdict(float)
        engine = self.env['dmag.goal.engine']
        fut = engine._scope(today, today + timedelta(days=horizon), companies, today=today)
        planned_visits = fut.visits.filtered(lambda v: v.state in ('draft', 'confirmed', 'arrived', 'in_chair'))
        booked_lines = set()
        for visit in planned_visits:
            if visit.treatment_plan_id:
                booked_lines.update(visit.treatment_plan_id.option_ids.line_ids.filtered(
                    lambda l, v=visit: l.state == 'todo' and l.product_id in v.service_ids).ids)
            for product in visit.service_ids:
                for mat, qty in requirements(product).items():
                    scheduled[mat] += qty * stats['show_rate']
        # kế hoạch đã chốt còn dịch vụ chưa làm × tỷ lệ thực hiện trong 30 ngày (năng suất 30 ngày qua)
        Line = self.env['dmag.treatment.plan.line'].sudo()
        todo = Line.search([('plan_id.company_id', 'in', companies.ids), ('state', '=', 'todo'),
                            ('plan_id.state', 'in', ('accepted', 'in_progress')),
                            ('option_id.is_accepted', '=', True)])
        done_recent = Line.search_count([('plan_id.company_id', 'in', companies.ids), ('state', '=', 'done'),
                                         ('done_visit_id.scheduled_start', '>=', fields.Datetime.to_datetime(
                                             today - timedelta(days=horizon)))])
        throughput = min(1.0, done_recent / len(todo)) if todo else 0.0
        for line in todo:
            if line.id in booked_lines:
                continue
            for mat, qty in requirements(line.product_id, len(line.tooth_ids), line.quantity).items():
                scheduled[mat] += qty * throughput
        products = set(rate) | set(scheduled)
        rows = []
        for product in products:
            if product.type != 'product' and not rate.get(product):
                continue
            run_rate = rate.get(product, 0.0) * horizon
            sched = scheduled.get(product, 0.0)
            demand = max(run_rate, sched)
            on_hand = product.with_company(company).qty_available if product.type == 'product' else 0.0
            daily = demand / horizon if horizon else 0.0
            cover = on_hand / daily if daily else None
            safety = daily * 7
            reorder = max(0.0, demand + safety - on_hand)
            status = 'ok'
            if cover is not None and cover < 7:
                status = 'critical'
            elif cover is not None and cover < horizon:
                status = 'low'
            if product.uom_id.rounding >= 1 or product.tracking == 'serial':
                reorder = math.ceil(reorder)
            rows.append({
                'product': product.display_name, 'product_id': product.id, 'uom': product.uom_id.name,
                'tracking': product.tracking, 'run_rate': round(run_rate, 2), 'scheduled': round(sched, 2),
                'demand': round(demand, 2), 'on_hand': round(on_hand, 2),
                'cover_days': round(cover, 1) if cover is not None else None, 'reorder': round(reorder, 2),
                'reorder_value': round(reorder * product.standard_price), 'status': status,
                'basis': 'Lịch hẹn + kế hoạch' if sched >= run_rate else 'Nhịp tiêu hao',
            })
        order = {'critical': 0, 'low': 1, 'ok': 2}
        rows.sort(key=lambda r: (order[r['status']], r['cover_days'] if r['cover_days'] is not None else 9999))
        return {'installed': True, 'horizon': horizon, 'rows': rows, 'throughput': round(throughput, 3),
                'planned_visits': len(planned_visits), 'todo_lines': len(todo),
                'reorder_value': sum(r['reorder_value'] for r in rows),
                'critical': len([r for r in rows if r['status'] == 'critical']),
                'low': len([r for r in rows if r['status'] == 'low'])}

    # ------------------------------------------------------------------ RPC
    @api.model
    def get_forecast(self):
        if not is_manager(self.env):
            raise AccessError(_('Dự báo doanh thu & vật tư chỉ dành cho Quản lý / Giám đốc.'))
        today = self._today()
        revenue = self._revenue_forecast(today=today)
        res = {'revenue': revenue, 'next_month': self._next_month_forecast(today),
               'materials': self._material_forecast(today=today),
               'history': self._month_history(today)}
        self._log_usage(res)
        return res

    @api.model
    def _month_history(self, today, months=6):
        engine = self.env['dmag.goal.engine']
        out = []
        for i in range(months, 0, -1):
            m_from = today.replace(day=1) - relativedelta(months=i)
            m_to = period_bounds('month', m_from)[1]
            value = engine.compute_metric('revenue', engine._scope(m_from, m_to, self.env.companies, today=today))
            out.append({'month': 'T%s/%s' % (m_from.month, str(m_from.year)[2:]), 'value': value or 0.0})
        return out

    @api.model
    def get_dashboard_summary(self):
        """Ô dự báo gọn cho Bảng điều hành mục tiêu."""
        if not is_manager(self.env):
            return {}
        today = self._today()
        rev = self._revenue_forecast(today=today)
        mats = self._material_forecast(today=today)
        return {
            'total': rev['total'], 'low': rev['low'], 'high': rev['high'], 'target': rev['target'],
            'prob_target': rev['prob_target'], 'actual_to_date': rev['actual_to_date'],
            'booked_part': rev['booked_part'], 'month': rev['month'], 'cumulative': rev['cumulative'],
            'from': rev['from'], 'to': rev['to'],
            'materials_critical': mats.get('critical', 0), 'materials_low': mats.get('low', 0),
            'reorder_value': mats.get('reorder_value', 0), 'text': self._summary_text(rev),
        }

    @api.model
    def _summary_text(self, rev):
        text = _('Dự báo doanh thu tháng %s: %s (80%%: %s – %s).', rev['month'], vnd(rev['total']), vnd(rev['low']),
                 vnd(rev['high']))
        if rev['target']:
            text += _(' Khả năng đạt mục tiêu %s: %s%%.', vnd(rev['target']), rev['prob_target'])
        return text

    @api.model
    def _log_usage(self, res):
        """Ghi nhật ký AI-16 (chạy tại chỗ – chi phí 0, không gọi API) để Trung tâm AI đếm số lần dùng."""
        log_local(self.env, 'AI-16', self._summary_text(res['revenue']))


def log_local(env, code, text, record=None):
    """Nhật ký cho tính năng chạy TẠI CHỖ (không qua Claude): chi phí 0, ghi kết quả rút gọn."""
    feature = env['dmag.ai.feature'].sudo().search([('code', '=', code)], limit=1)
    if not feature:
        return False
    return env['dmag.ai.log'].sudo().create({
        'feature_id': feature.id, 'company_id': env.company.id, 'user_id': env.user.id,
        'mode': 'live' if env.company.dmag_ai_mode == 'live' else 'simulate', 'model': 'tại chỗ (LOCAL)',
        'res_model': record._name if record else False, 'res_id': record.id if record else False,
        'response_preview': (text or '')[:1500], 'cost_vnd': 0.0, 'estimated_cost_vnd': 0.0,
    })
