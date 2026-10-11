"""AI-08 – Dự báo khách không đến (LOCAL, không dùng LLM, không gửi dữ liệu ra ngoài).

Hồi quy logistic thuần Python học trên lịch sử hẹn của chính phòng khám (lượt *Hoàn tất* = đến, *Không đến* = 1).
Ít dữ liệu (< 40 lượt hoặc < 5 lượt không đến) → dùng bộ trọng số kinh nghiệm (heuristic) có cùng dạng.
"""
import json
import math
from collections import defaultdict
from datetime import timedelta

import pytz

from odoo import _, api, fields, models

FEATURES = [
    # (mã, nhãn khi làm TĂNG nguy cơ, nhãn khi làm GIẢM nguy cơ)
    ('lead', 'Đặt trước lâu ({lead} ngày)', 'Đặt sát ngày'),
    ('prior_rate', 'Đã từng không đến {ns}/{pv} lần', 'Luôn đến đúng hẹn'),
    ('is_new', 'Khách mới (chưa đến lần nào)', 'Khách quen'),
    ('weekend', 'Hẹn cuối tuần', 'Hẹn ngày thường'),
    ('evening', 'Hẹn buổi tối', 'Hẹn trong giờ hành chính'),
    ('early', 'Hẹn sáng sớm', 'Hẹn sau 9 giờ'),
    ('unconfirmed', 'Chưa xác nhận (gọi / Zalo)', 'Đã xác nhận'),
    ('light', 'Ca nhẹ (khám / cạo vôi)', 'Ca điều trị nặng'),
    ('online', 'Tự đặt online / Zalo', 'Đặt tại quầy / qua điện thoại'),
]
# Trọng số kinh nghiệm (log-odds) khi chưa đủ dữ liệu để học
HEURISTIC = {'intercept': -2.2, 'lead': 0.45, 'prior_rate': 2.6, 'is_new': 0.5, 'weekend': 0.25, 'evening': 0.2,
             'early': 0.15, 'unconfirmed': 0.9, 'light': 0.35, 'online': 0.4}
MIN_SAMPLES, MIN_POSITIVES = 40, 5
METHOD_TEXT = ('Hồi quy logistic học trên {n} lượt hẹn đã kết thúc của phòng khám (tỷ lệ không đến {rate}%), '
               'tính tại máy chủ, không gửi dữ liệu ra ngoài. Yếu tố: thời gian đặt trước, lịch sử không đến, khách mới, '
               'ngày / giờ hẹn, đã xác nhận chưa, loại ca, kênh đặt.')
HEURISTIC_TEXT = ('Chưa đủ dữ liệu để học ({n} lượt, {pos} lần không đến) – dùng trọng số kinh nghiệm: '
                  'đặt trước lâu, từng không đến, khách mới, chưa xác nhận… làm tăng nguy cơ. Tính tại chỗ.')


def feature_vector(raw):
    """raw: lead_days, prior_visits, prior_noshow, weekday (0=T2), hour, confirmed, heavy, light, online."""
    pv = raw.get('prior_visits') or 0
    ns = raw.get('prior_noshow') or 0
    return {
        'lead': math.log1p(max(raw.get('lead_days') or 0.0, 0.0)),
        'prior_rate': (ns + 0.1) / (pv + 1.0) if pv else 0.0,
        'is_new': 1.0 if pv == 0 else 0.0,
        'weekend': 1.0 if raw.get('weekday') in (5, 6) else 0.0,
        'evening': 1.0 if (raw.get('hour') or 0) >= 17 else 0.0,
        'early': 1.0 if (raw.get('hour') or 12) < 9 else 0.0,
        'unconfirmed': 0.0 if raw.get('confirmed') else 1.0,
        'light': 1.0 if raw.get('light') else 0.0,
        'online': 1.0 if raw.get('online') else 0.0,
    }


def _sigmoid(z):
    if z < -30:
        return 0.0
    if z > 30:
        return 1.0
    return 1.0 / (1.0 + math.exp(-z))


def train_logreg(rows, labels, iterations=600, lr=0.3, l2=0.02):
    """Hồi quy logistic (gradient descent toàn lô, chuẩn hóa z-score, L2) – xác định, không ngẫu nhiên."""
    keys = [f[0] for f in FEATURES]
    n = len(rows)
    means = {k: sum(r[k] for r in rows) / n for k in keys}
    stds = {}
    for k in keys:
        var = sum((r[k] - means[k]) ** 2 for r in rows) / n
        stds[k] = math.sqrt(var) or 1.0
    xs = [[(r[k] - means[k]) / stds[k] for k in keys] for r in rows]
    base = min(max(sum(labels) / float(n), 1e-3), 1 - 1e-3)
    w = [0.0] * len(keys)
    b = math.log(base / (1 - base))
    for _it in range(iterations):
        grad_w = [0.0] * len(keys)
        grad_b = 0.0
        for x, y in zip(xs, labels):
            err = _sigmoid(b + sum(wi * xi for wi, xi in zip(w, x))) - y
            grad_b += err
            for j, xj in enumerate(x):
                grad_w[j] += err * xj
        b -= lr * grad_b / n
        w = [wi - lr * (gw / n + l2 * wi) for wi, gw in zip(w, grad_w)]
    model = {'intercept': b, 'coef': dict(zip(keys, w)), 'mean': means, 'std': stds}
    probs = [predict(model, r) for r in rows]
    model['auc'] = _auc(probs, labels)
    return model


def heuristic_model():
    keys = [f[0] for f in FEATURES]
    return {'intercept': HEURISTIC['intercept'], 'coef': {k: HEURISTIC[k] for k in keys},
            'mean': {k: 0.0 for k in keys}, 'std': {k: 1.0 for k in keys}, 'auc': None}


def contributions(model, row):
    return {k: model['coef'][k] * (row[k] - model['mean'][k]) / (model['std'][k] or 1.0) for k in model['coef']}


def predict(model, row):
    return _sigmoid(model['intercept'] + sum(contributions(model, row).values()))


def _auc(probs, labels):
    pos = [p for p, y in zip(probs, labels) if y]
    neg = [p for p, y in zip(probs, labels) if not y]
    if not pos or not neg:
        return None
    wins = sum((1.0 if p > q else 0.5 if p == q else 0.0) for p in pos for q in neg)
    return wins / (len(pos) * len(neg))


def explain(model, row, raw, top=3):
    contrib = contributions(model, row)
    labels = {f[0]: f for f in FEATURES}
    ordered = sorted(contrib.items(), key=lambda kv: -kv[1])
    out = []
    for key, value in ordered:
        if value <= 0.05 or len(out) >= top:
            break
        out.append(labels[key][1].format(lead=int(raw.get('lead_days') or 0), ns=raw.get('prior_noshow') or 0,
                                         pv=raw.get('prior_visits') or 0))
    return out


class DmagAiNoshowModel(models.Model):
    _name = 'dmag.ai.noshow.model'
    _description = 'Mô hình dự báo không đến (AI-08)'
    _order = 'id desc'

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)
    trained_at = fields.Datetime('Huấn luyện lúc', default=fields.Datetime.now)
    method = fields.Selection([('logreg', 'Hồi quy logistic (học từ dữ liệu phòng khám)'),
                               ('heuristic', 'Trọng số kinh nghiệm (chưa đủ dữ liệu)')], string='Phương pháp', required=True)
    n_samples = fields.Integer('Số lượt học')
    n_noshow = fields.Integer('Số lượt không đến')
    base_rate = fields.Float('Tỷ lệ không đến (%)', digits=(5, 1))
    auc = fields.Float('AUC trên dữ liệu học', digits=(4, 3))
    params = fields.Text('Tham số (JSON)')
    coef_summary = fields.Text('Trọng số (dễ đọc)', compute='_compute_coef_summary')
    method_text = fields.Char('Giải thích', compute='_compute_coef_summary')

    def _compute_coef_summary(self):
        labels = {f[0]: f[1].split(' (')[0].replace('{ns}/{pv}', 'N') for f in FEATURES}
        for rec in self:
            params = rec._params()
            rec.coef_summary = '\n'.join('%s: %+.2f' % (labels[k], v) for k, v in
                                         sorted(params['coef'].items(), key=lambda kv: -abs(kv[1])))
            rec.method_text = (METHOD_TEXT.format(n=rec.n_samples, rate=round(rec.base_rate)) if rec.method == 'logreg'
                               else HEURISTIC_TEXT.format(n=rec.n_samples, pos=rec.n_noshow))

    def _params(self):
        self.ensure_one()
        try:
            return json.loads(self.params or '{}') or heuristic_model()
        except ValueError:
            return heuristic_model()

    # ------------------------------------------------------------------ data
    @api.model
    def _raw_features(self, visits, as_of_now=False):
        """Đặc trưng thô của các lượt khám (chỉ dùng lịch sử TRƯỚC giờ hẹn → không rò rỉ nhãn)."""
        Visit = self.env['dmag.dental.visit'].sudo()
        patients = visits.mapped('patient_id')
        history = Visit.search([('patient_id', 'in', patients.ids), ('state', 'in', ('done', 'no_show'))],
                               order='scheduled_start')
        by_patient = defaultdict(list)
        for h in history:
            by_patient[h.patient_id.id].append((h.scheduled_start, h.state, h.id))
        confirmed_ids = self._confirmed_visit_ids(visits)
        online_codes = ('ZALO_AI', 'WEB', 'ONLINE')
        tz_name = self.env.user.tz or 'Asia/Ho_Chi_Minh'
        tz = pytz.timezone(tz_name)
        result = {}
        for visit in visits:
            past = [(s, st) for s, st, vid in by_patient[visit.patient_id.id]
                    if s < visit.scheduled_start and vid != visit.id]
            local = pytz.utc.localize(visit.scheduled_start).astimezone(tz)
            created = visit.create_date or fields.Datetime.now()
            source = visit.source_id
            result[visit.id] = {
                'lead_days': max((visit.scheduled_start - created).total_seconds() / 86400.0, 0.0),
                'prior_visits': len(past),
                'prior_noshow': sum(1 for _s, st in past if st == 'no_show'),
                'weekday': local.weekday(), 'hour': local.hour,
                'confirmed': visit.id in confirmed_ids or visit.state in ('confirmed', 'arrived', 'in_chair'),
                'light': not visit.is_heavy and (not visit.service_ids or all(
                    c in ('exam', 'imaging', 'hygiene') for c in visit.service_ids.mapped('dental_category'))),
                'online': bool(source and ((source.code or '').upper() in online_codes
                                           or any(w in (source.name or '').lower() for w in ('online', 'zalo', 'web', 'facebook')))),
            }
        return result

    @api.model
    def _confirmed_visit_ids(self, visits):
        """Lượt đã được xác nhận trước giờ hẹn: trạng thái từng là "Đã xác nhận" (nhật ký) hoặc ZNS nhắc lịch đã tới khách."""
        if not visits:
            return set()
        field = self.env['ir.model.fields']._get('dmag.dental.visit', 'state')
        tracking = self.env['mail.tracking.value'].sudo().search([
            ('field_id', '=', field.id), ('new_value_char', '=', 'Đã xác nhận'),
            ('mail_message_id.model', '=', 'dmag.dental.visit'), ('mail_message_id.res_id', 'in', visits.ids)])
        ids = set(tracking.mapped('mail_message_id.res_id')) | set(visits.filtered('dmag_was_confirmed').ids)
        zns = self.env['dmag.zns.message'].sudo().search([
            ('res_model', '=', 'dmag.dental.visit'), ('res_id', 'in', visits.ids), ('state', '=', 'delivered')])
        ids |= set(zns.mapped('res_id'))
        return ids

    # ------------------------------------------------------------------ train / score
    @api.model
    def train(self, company=None):
        company = company or self.env.company
        Visit = self.env['dmag.dental.visit'].sudo()
        since = fields.Datetime.now() - timedelta(days=365)
        visits = Visit.search([('company_id', '=', company.id), ('state', 'in', ('done', 'no_show')),
                               ('scheduled_start', '>=', since)], order='scheduled_start')
        raw = self._raw_features(visits)
        rows = [feature_vector(raw[v.id]) for v in visits]
        labels = [1 if v.state == 'no_show' else 0 for v in visits]
        positives = sum(labels)
        if len(rows) >= MIN_SAMPLES and positives >= MIN_POSITIVES and positives < len(rows):
            params, method = train_logreg(rows, labels), 'logreg'
        else:
            params, method = heuristic_model(), 'heuristic'
        return self.sudo().create({
            'company_id': company.id, 'method': method, 'n_samples': len(rows), 'n_noshow': positives,
            'base_rate': 100.0 * positives / len(rows) if rows else 0.0,
            'auc': params.get('auc') or 0.0, 'params': json.dumps(params),
        })

    @api.model
    def _current(self, company=None):
        company = company or self.env.company
        model = self.sudo().search([('company_id', '=', company.id)], limit=1)
        return model or self.train(company)

    @api.model
    def score_visits(self, visits):
        visits = visits.sudo().filtered(lambda v: v.state in ('draft', 'confirmed') and v.scheduled_start)
        if not visits or not self.env['dmag.ai'].is_feature_active('AI-08'):
            return False
        for company in visits.mapped('company_id'):
            model = self._current(company)
            params = model._params()
            batch = visits.filtered(lambda v: v.company_id == company)
            raw = self._raw_features(batch)
            for visit in batch:
                row = feature_vector(raw[visit.id])
                risk = predict(params, row)
                factors = explain(params, row, raw[visit.id])
                visit.with_context(dmag_workflow=True, dmag_noshow_scoring=True).write({
                    'dmag_noshow_risk': risk, 'dmag_noshow_factors': '; '.join(factors),
                    'dmag_noshow_scored_at': fields.Datetime.now(), 'dmag_noshow_model_id': model.id,
                })
        return True

    @api.model
    def _cron_train_and_score(self):
        for company in self.env['res.company'].sudo().search([]):
            self.with_company(company).train(company)
        upcoming = self.env['dmag.dental.visit'].sudo().search([
            ('state', 'in', ('draft', 'confirmed')), ('scheduled_start', '>=', fields.Datetime.now()),
            ('scheduled_start', '<=', fields.Datetime.now() + timedelta(days=14))])
        self.score_visits(upcoming)
        return True

    def action_retrain(self):
        model = self.train(self.company_id or self.env.company)
        upcoming = self.env['dmag.dental.visit'].sudo().search([
            ('state', 'in', ('draft', 'confirmed')), ('scheduled_start', '>=', fields.Datetime.now())])
        self.score_visits(upcoming)
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': model.id,
                'views': [[False, 'form']], 'target': 'current', 'name': _('Mô hình dự báo không đến')}
