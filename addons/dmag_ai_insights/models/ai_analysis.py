"""Bộ phân tích số liệu điều hành dùng chung cho Hỏi đáp (AI-13) và Bản tin tuần (AI-14).

Mọi con số đi qua ``dmag.goal.engine`` (cùng định nghĩa với Bảng điều hành mục tiêu) → câu trả lời của AI, bản tin
và bảng điều hành luôn khớp nhau. Chỉ ĐỌC dữ liệu.
"""
from collections import defaultdict
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models

from odoo.addons.dmag_dental_goals.models.dmag_goal_dashboard import GoalBoard
from odoo.addons.dmag_dental_goals.models.dmag_goal_metrics import METRICS, period_bounds

from .ai_common import fmt, strip_accents, vnd

CATEGORY_LABELS = {
    'exam': 'Khám & chẩn đoán', 'imaging': 'Chẩn đoán hình ảnh', 'hygiene': 'Dự phòng / vệ sinh',
    'restorative': 'Điều trị bảo tồn', 'endo': 'Nội nha', 'surgery': 'Phẫu thuật / nhổ răng', 'implant': 'Implant',
    'prosthodontic': 'Phục hình', 'orthodontic': 'Chỉnh nha', 'cosmetic': 'Thẩm mỹ', 'pediatric': 'Nha khoa trẻ em',
    'other': 'Khác',
}
TOP_METRICS = ['revenue', 'collected', 'plan_acceptance', 'new_patients', 'nps', 'show_up_rate', 'no_show', 'cases',
               'implant_cases', 'gross_profit', 'avg_wait', 'discount']
TOP_LABELS = {'no_show': ('Số lượt không đến', 'count'), 'cases': ('Số lượt khám hoàn tất', 'count'),
              'discount': ('Tiền giảm giá', 'money')}


class DmagAiAnalysis(models.AbstractModel):
    _name = 'dmag.ai.analysis'
    _description = 'DMAG AI – phân tích số liệu điều hành (chỉ đọc)'

    # ------------------------------------------------------------------ basics
    @api.model
    def _today(self):
        return fields.Date.context_today(self)

    @api.model
    def _companies(self):
        return self.env.companies

    @api.model
    def _value(self, metric, d_from, d_to, doctor=None):
        engine = self.env['dmag.goal.engine']
        scope = engine._scope(d_from, d_to, self._companies(), doctor, today=self._today())
        return engine.compute_metric(metric, scope)

    @api.model
    def _scope(self, d_from, d_to, doctor=None):
        return self.env['dmag.goal.engine']._scope(d_from, d_to, self._companies(), doctor, today=self._today())

    @api.model
    def _doctors(self):
        return self.env['dmag.dental.practitioner'].sudo().search([
            ('role', '=', 'doctor'), ('company_id', 'in', self._companies().ids)])

    @api.model
    def _find_doctor(self, name):
        """Tìm bác sĩ theo tên gõ tự do (không dấu, một phần tên)."""
        if not name:
            return None
        query = strip_accents(name).replace('bac si', '').replace('bs.', '').replace('bs ', '').strip(' .')
        if not query:
            return None
        best = None
        for doctor in self._doctors():
            full = strip_accents(doctor.name)
            words = [w for w in full.replace('.', ' ').split() if w not in ('bs', 'ths', 'ts', 'cki', 'ckii')]
            if query in full or (words and words[-1] == query.split()[-1]):
                best = best or doctor
        return best

    @api.model
    def _prev_range(self, d_from, d_to):
        """Kỳ trước cùng độ dài; kỳ đang chạy → so cùng thời điểm (đến cùng ngày tương ứng)."""
        today = self._today()
        if d_from.day == 1 and d_to == period_bounds('month', d_to)[1] and d_to > d_from + timedelta(days=20):
            months = (d_to.year - d_from.year) * 12 + d_to.month - d_from.month + 1
            p_from = d_from - relativedelta(months=months)
            p_end = d_from - timedelta(days=1)
        else:
            length = (d_to - d_from).days + 1
            p_from = d_from - timedelta(days=length)
            p_end = d_from - timedelta(days=1)
        if d_from <= today <= d_to:
            p_to = min(p_from + (today - d_from), p_end)
        else:
            p_to = p_end
        return p_from, p_to

    @api.model
    def _drill(self, metric, d_from, d_to, doctor=None, name=None):
        board = GoalBoard(self.env, 'month', d_from, d_to, self._companies(), self._today())
        action = board.drill(metric, doctor) if metric in METRICS else None
        if action and name:
            action['name'] = name
        return action

    @staticmethod
    def _delta_text(metric, cur, prev):
        if cur is None or prev is None:
            return ''
        if METRICS.get(metric, {}).get('kind', 'sum') == 'sum':
            if not prev:
                return ''
            pct = (cur - prev) * 100.0 / abs(prev)
            return ('+' if pct >= 0 else '−') + ('%.1f%%' % abs(pct)).replace('.', ',')
        diff = cur - prev
        unit = METRICS[metric]['unit']
        suffix = ' điểm %' if unit == 'pct' else (' phút' if unit == 'min' else ' điểm')
        return ('+' if diff >= 0 else '−') + ('%.1f' % abs(diff)).rstrip('0').rstrip('.').replace('.', ',') + suffix

    # ------------------------------------------------------------------ xếp hạng
    @api.model
    def _top(self, entity, metric, d_from, d_to, order='desc', limit=5):
        rows = []
        if entity == 'doctor':
            for doctor in self._doctors():
                scope = self._scope(d_from, d_to, doctor)
                if metric == 'no_show':
                    value = float(len(scope.visits.filtered(lambda v: v.state == 'no_show')))
                elif metric == 'cases':
                    value = float(len(scope.done_visits))
                elif metric == 'discount':
                    value = sum(p.quantity * p.price_unit * (p.discount or 0) / 100.0 for p in scope.procedures)
                else:
                    value = self.env['dmag.goal.engine'].compute_metric(metric, scope)
                rows.append({'name': doctor.name, 'id': doctor.id, 'value': value,
                             'cases': len(scope.done_visits)})
        elif entity == 'service':
            scope = self._scope(d_from, d_to)
            agg = defaultdict(lambda: {'value': 0.0, 'cases': 0})
            for proc in scope.procedures:
                key = proc.product_id.name
                if metric == 'discount':
                    agg[key]['value'] += proc.quantity * proc.price_unit * (proc.discount or 0) / 100.0
                elif metric == 'cases':
                    agg[key]['value'] += 1
                else:
                    metric = 'revenue'
                    agg[key]['value'] += proc.amount
                agg[key]['cases'] += 1
            rows = [{'name': k, 'value': v['value'], 'cases': v['cases']} for k, v in agg.items()]
        elif entity == 'source':
            scope = self._scope(d_from, d_to)
            agg = defaultdict(float)
            for visit in scope.done_visits.filtered('is_new_patient'):
                agg[visit.patient_id.customer_source_id.name or 'Chưa ghi nguồn'] += 1
            metric = 'new_patients'
            rows = [{'name': k, 'value': v, 'cases': int(v)} for k, v in agg.items()]
        rows = [r for r in rows if r['value'] is not None]
        reverse = order != 'asc'
        rows.sort(key=lambda r: (r['value'], r['name']), reverse=reverse)
        label, unit = TOP_LABELS.get(metric, (METRICS.get(metric, {}).get('label', metric),
                                             METRICS.get(metric, {}).get('unit', 'count')))
        for r in rows:
            r['text'] = fmt(unit, r['value'])
        return {'entity': entity, 'metric': metric, 'label': label, 'unit': unit, 'rows': rows[:max(1, limit)]}

    # ------------------------------------------------------------------ nguyên nhân
    @api.model
    def _drivers(self, metric, d_from, d_to, doctor=None):
        """Các yếu tố giải thích biến động của ``metric`` so với kỳ trước (cùng thời điểm). Mỗi yếu tố có số liệu."""
        p_from, p_to = self._prev_range(d_from, d_to)
        cur_scope, prev_scope = self._scope(d_from, d_to, doctor), self._scope(p_from, p_to, doctor)
        engine = self.env['dmag.goal.engine']
        out = []

        def add(text, weight, kind='driver'):
            out.append({'text': text, 'weight': round(weight, 2), 'kind': kind})

        money = metric in ('revenue', 'gross_profit', 'collected')
        if money or metric in ('new_patients', 'booked', 'implant_cases', 'ortho_new'):
            # Lượng khách × giá trị trung bình
            c_done, p_done = len(cur_scope.done_visits), len(prev_scope.done_visits)
            c_rev, p_rev = engine.compute_metric('revenue', cur_scope), engine.compute_metric('revenue', prev_scope)
            c_avg = c_rev / c_done if c_done else 0.0
            p_avg = p_rev / p_done if p_done else 0.0
            if p_done:
                vol = (c_done - p_done) * 100.0 / p_done
                add('Lượt khám hoàn tất %s so với cùng kỳ (%s → %s lượt, %s%.0f%%).' % (
                    'giảm' if vol < 0 else 'tăng', p_done, c_done, '−' if vol < 0 else '+', abs(vol)), abs(vol))
            if p_avg and money:
                tick = (c_avg - p_avg) * 100.0 / p_avg
                add('Giá trị trung bình mỗi lượt %s: %s → %s (%s%.0f%%).' % (
                    'giảm' if tick < 0 else 'tăng', vnd(p_avg), vnd(c_avg), '−' if tick < 0 else '+', abs(tick)),
                    abs(tick))
            # Phễu: đặt lịch → đến khám → chốt kế hoạch
            for key in ('booked', 'show_up_rate', 'plan_acceptance'):
                c, p = engine.compute_metric(key, cur_scope), engine.compute_metric(key, prev_scope)
                if c is None or p is None:
                    continue
                if METRICS[key]['kind'] == 'sum':
                    change = (c - p) * 100.0 / p if p else 0.0
                    weight = abs(change)
                else:
                    change = c - p
                    weight = abs(change) * 1.5
                if weight < 3:
                    continue
                add('%s: %s → %s (%s).' % (METRICS[key]['label'], fmt(key, p), fmt(key, c),
                                           self._delta_text(key, c, p)), weight, 'funnel')
            if not doctor:
                # Bác sĩ đóng góp nhiều nhất vào chênh lệch
                deltas = []
                for doc in self._doctors():
                    c = engine.compute_metric('revenue', self._scope(d_from, d_to, doc)) or 0.0
                    p = engine.compute_metric('revenue', self._scope(p_from, p_to, doc)) or 0.0
                    deltas.append((c - p, doc.name, c, p))
                deltas.sort()
                if deltas and deltas[0][0] < 0 and p_rev:
                    d = deltas[0]
                    add('Doanh thu của %s giảm %s (%s → %s) – chiếm phần lớn mức hụt.' % (
                        d[1], vnd(-d[0]), vnd(d[3]), vnd(d[2])), abs(d[0]) * 100.0 / p_rev, 'doctor')
                if deltas and deltas[-1][0] > 0 and p_rev:
                    d = deltas[-1]
                    add('%s tăng %s (%s → %s).' % (d[1], vnd(d[0]), vnd(d[3]), vnd(d[2])),
                        abs(d[0]) * 100.0 / p_rev * 0.6, 'doctor')
                # Nhóm dịch vụ
                cats = defaultdict(lambda: [0.0, 0.0])
                for proc in cur_scope.procedures:
                    cats[proc.product_id.dental_category or 'other'][0] += proc.amount
                for proc in prev_scope.procedures:
                    cats[proc.product_id.dental_category or 'other'][1] += proc.amount
                ranked = sorted(cats.items(), key=lambda kv: kv[1][0] - kv[1][1])
                if ranked and p_rev:
                    cat, (c, p) = ranked[0]
                    if c < p:
                        add('Nhóm dịch vụ %s giảm mạnh nhất: %s → %s.' % (
                            CATEGORY_LABELS.get(cat, cat), vnd(p), vnd(c)), (p - c) * 100.0 / p_rev, 'service')
                    cat, (c, p) = ranked[-1]
                    if c > p:
                        add('Nhóm %s tăng tốt nhất: %s → %s.' % (CATEGORY_LABELS.get(cat, cat), vnd(p), vnd(c)),
                            (c - p) * 100.0 / p_rev * 0.5, 'service')
            pm = engine.compute_metric('chair_util_pm', cur_scope)
            if pm is not None and pm < 65:
                add('Ghế buổi chiều mới dùng %s công suất (chuẩn ≥ 65%%) – còn nhiều giờ trống 13:30–16:30.' % fmt(
                    'pct', pm), (65 - pm) * 0.6, 'capacity')
        if metric == 'collected':
            moves = self.env['account.move'].sudo().search([
                ('company_id', 'in', self._companies().ids), ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'), ('amount_residual', '>', 0)])
            if moves:
                add('Còn %s hóa đơn chưa thu đủ, tổng %s.' % (len(moves), vnd(sum(moves.mapped('amount_residual')))),
                    20, 'receivable')
        if metric in ('plan_acceptance', 'consult_rate'):
            pending = cur_scope.plans.filtered(lambda p: p.state == 'presented')
            if pending:
                add('%s kế hoạch đã tư vấn đang chờ khách quyết định, giá trị khuyến nghị %s.' % (
                    len(pending), vnd(sum(pending.mapped(lambda p: max(p.option_ids.mapped('amount_total') or [0]))))),
                    25, 'pipeline')
            if not doctor:
                for doc in self._doctors():
                    rate = engine.compute_metric('plan_acceptance', self._scope(d_from, d_to, doc))
                    if rate is not None:
                        add('%s: tỷ lệ chốt %s.' % (doc.name, fmt('pct', rate)), 10 + (100 - rate) / 10, 'doctor')
        if metric == 'show_up_rate':
            no_show = cur_scope.visits.filtered(lambda v: v.state == 'no_show')
            if no_show:
                pm = no_show.filtered(lambda v: cur_scope.local(v.scheduled_start).hour >= 12)
                add('%s lượt không đến, trong đó %s lượt buổi chiều.' % (len(no_show), len(pm)), 30, 'no_show')
                new = no_show.filtered('is_new_patient')
                if new:
                    add('%s lượt không đến là khách mới (chưa từng điều trị) – cần gọi xác nhận trước 1 ngày.'
                        % len(new), 20, 'no_show')
        if metric in ('nps', 'complaint_rate') and cur_scope.nps_responses:
            low = cur_scope.nps_responses.filtered(lambda r: r.score <= 6)
            add('%s phiếu chấm 0–6 điểm trên %s phiếu.' % (len(low), len(cur_scope.nps_responses)), 25, 'nps')
        if metric == 'new_patients' and not doctor:
            top = self._top('source', 'new_patients', d_from, d_to, limit=3)
            if top['rows']:
                add('Nguồn khách mới chính: %s.' % ', '.join('%s (%s)' % (r['name'], int(r['value']))
                                                            for r in top['rows']), 15, 'source')
        out.sort(key=lambda d: -d['weight'])
        return {'prev_from': p_from, 'prev_to': p_to, 'drivers': out}
