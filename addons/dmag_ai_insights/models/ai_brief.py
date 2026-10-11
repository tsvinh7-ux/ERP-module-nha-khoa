"""AI-14 – Bản tin điều hành hằng tuần (sáng thứ Hai 07:00 + nút "Soạn bản tin").

Dữ kiện (số liệu tháng đến hôm nay + tuần vừa qua so với tuần trước, chỉ tiêu lệch, nguyên nhân từ phễu / bác sĩ /
nhóm dịch vụ, việc tồn đọng cụ thể) được tính tại chỗ bằng bộ máy chỉ số. Sau đó:
* **Claude API**: MỘT lần gọi với JSON dữ kiện + JSON schema → AI viết bản tin (dễ chuyển sang Message Batches
  giảm 50 % phí vì một yêu cầu độc lập, không gọi công cụ – xem ``_brief_request``);
* **Giả lập**: dựng bản tin cùng cấu trúc từ chính dữ kiện đó.
Bản tin lưu thành ``dmag.ai.brief`` (có chatter) và gửi thông báo cho Giám đốc.
"""
import json
from datetime import timedelta

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

from odoo.addons.dmag_dental_base.models.dmag_access import is_manager
from odoo.addons.dmag_dental_goals.models.dmag_goal_metrics import METRICS

from .ai_common import fmt, vnd

BRIEF_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'required': ['headline', 'summary', 'off_track', 'causes', 'actions', 'highlights'],
    'properties': {
        'headline': {'type': 'string', 'description': 'Một câu tiêu đề (≤ 15 từ)'},
        'summary': {'type': 'string', 'description': '2–3 câu tóm tắt tình hình, có số liệu'},
        'off_track': {'type': 'array', 'items': {
            'type': 'object', 'additionalProperties': False, 'required': ['metric', 'detail'],
            'properties': {'metric': {'type': 'string'}, 'detail': {'type': 'string'}}}},
        'causes': {'type': 'array', 'items': {'type': 'string'}},
        'actions': {'type': 'array', 'items': {
            'type': 'object', 'additionalProperties': False, 'required': ['title', 'detail', 'owner'],
            'properties': {'title': {'type': 'string'}, 'detail': {'type': 'string'}, 'owner': {'type': 'string'}}}},
        'highlights': {'type': 'array', 'items': {'type': 'string'}},
    },
}
BRIEF_SYSTEM = """Bạn soạn BẢN TIN ĐIỀU HÀNH HẰNG TUẦN cho Giám đốc phòng khám nha khoa, đọc trong 2 phút trước họp giao ban
sáng thứ Hai. Dữ kiện JSON bên dưới đã được tính sẵn từ phần mềm – chỉ dùng số liệu trong đó, không bịa.
Yêu cầu:
- off_track: mỗi chỉ tiêu đang lệch (Nguy cơ / Chậm / Không đạt) một dòng, nêu thực tế – mục tiêu – dự báo.
- causes: 2–4 nguyên nhân có thể, mỗi nguyên nhân dẫn số liệu từ phần "drivers" (phễu, bác sĩ, nhóm dịch vụ, công suất).
- actions: ĐÚNG 3 việc cụ thể nên làm tuần này, có số lượng / đối tượng rõ ràng (dựa vào "backlog"), ghi người phụ trách
  theo vai trò (Lễ tân, Tư vấn viên, Bác sĩ, Quản lý, Giám đốc).
- highlights: 2–3 điểm sáng có số liệu.
Tiếng Việt, câu ngắn, tiền kiểu Việt Nam (450,5 tr; 1,25 tỷ). Không nêu tên bệnh nhân."""


class DmagAiBrief(models.Model):
    _name = 'dmag.ai.brief'
    _description = 'Bản tin điều hành hằng tuần (AI-14)'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'

    name = fields.Char('Bản tin', required=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)
    date = fields.Date('Ngày lập', required=True, default=fields.Date.context_today)
    week_from = fields.Date('Tuần từ')
    week_to = fields.Date('Tuần đến')
    period_label = fields.Char('Kỳ mục tiêu')
    headline = fields.Char('Tiêu đề')
    summary = fields.Text('Tóm tắt')
    body_html = fields.Html('Nội dung', sanitize=True, readonly=True)
    data_json = fields.Text('Dữ liệu (JSON)', readonly=True)
    facts_json = fields.Text('Dữ kiện đầu vào (JSON)', readonly=True)
    off_track_count = fields.Integer('Chỉ tiêu lệch')
    mode = fields.Selection([('simulate', 'Giả lập'), ('live', 'Claude API')], string='Chế độ', readonly=True)
    trigger = fields.Selection([('cron', 'Tự động sáng thứ Hai'), ('manual', 'Bấm tay')], default='manual',
                               string='Cách tạo', readonly=True)
    log_id = fields.Many2one('dmag.ai.log', string='Nhật ký AI', readonly=True)
    estimated_cost_vnd = fields.Float('Chi phí (hoặc ước tính nếu chạy thật)', digits=(12, 0), readonly=True)
    state = fields.Selection([('draft', 'Nháp'), ('sent', 'Đã gửi Giám đốc')], default='draft', string='Trạng thái',
                             tracking=True)

    # ------------------------------------------------------------------ actions
    @api.model
    def action_generate(self):
        """Nút "Soạn bản tin tuần" – trả về hành động mở bản tin vừa tạo."""
        if not is_manager(self.env):
            raise AccessError(_('Chỉ Quản lý / Giám đốc được soạn bản tin điều hành.'))
        brief = self._generate(trigger='manual')
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': brief.id,
                'views': [[False, 'form']], 'target': 'current', 'name': brief.name}

    @api.model
    def _cron_weekly_brief(self):
        for company in self.env['res.company'].search([]):
            env = self.with_company(company).with_context(allowed_company_ids=[company.id])
            if not env.env['dmag.ai'].is_feature_active('AI-14'):
                continue
            try:
                with self.env.cr.savepoint():
                    env._generate(trigger='cron')
            except Exception as e:  # noqa: BLE001 – một công ty lỗi không chặn công ty khác
                self.env['ir.logging'].sudo().create({
                    'name': 'dmag_ai_insights', 'type': 'server', 'level': 'WARNING', 'path': 'dmag.ai.brief',
                    'func': '_cron_weekly_brief', 'line': '0', 'message': 'Bản tin tuần lỗi: %s' % e})

    def action_send(self):
        for brief in self:
            brief._notify_directors()
            brief.state = 'sent'

    def action_open_dashboard(self):
        return self.env['ir.actions.actions']._for_xml_id('dmag_clinic_workspace.action_dmag_owner_cockpit')

    # ------------------------------------------------------------------ facts
    @api.model
    def _collect_facts(self):
        today = fields.Date.context_today(self)
        an = self.env['dmag.ai.analysis']
        dash = self.env['dmag.goal.dashboard'].sudo().get_goal_dashboard('month')
        week_to = today - timedelta(days=today.weekday() + 1)  # Chủ nhật vừa qua
        week_from = week_to - timedelta(days=6)
        prev_to, prev_from = week_from - timedelta(days=1), week_from - timedelta(days=7)
        week = []
        for key in ('revenue', 'collected', 'new_patients', 'booked', 'show_up_rate', 'plan_acceptance', 'nps'):
            cur, prev = an._value(key, week_from, week_to), an._value(key, prev_from, prev_to)
            week.append({'metric': key, 'label': METRICS[key]['label'], 'this_week': cur, 'prev_week': prev,
                         'text': fmt(key, cur), 'prev_text': fmt(key, prev), 'change': an._delta_text(key, cur, prev)})
        cards = dash['north_star'] + dash['service']
        off = [c for c in cards if c['status'] in ('at_risk', 'behind', 'missed')]
        good = [c for c in cards if c['status'] in ('on_track', 'achieved')]
        d_from, d_to = fields.Date.to_date(dash['period']['from']), fields.Date.to_date(dash['period']['to'])
        drivers = []
        seen = set()
        for card in sorted(off, key=lambda c: c['status'] != 'at_risk')[:3]:
            for drv in an._drivers(card['metric'], d_from, d_to)['drivers'][:4]:
                if drv['text'] not in seen:
                    seen.add(drv['text'])
                    drivers.append(dict(drv, metric=card['metric']))
        if not drivers:
            for drv in an._drivers('revenue', d_from, d_to)['drivers'][:4]:
                drivers.append(dict(drv, metric='revenue'))
        doctors = [{'name': d['name'], 'revenue': d['revenue']['actual'], 'revenue_text': vnd(d['revenue']['actual']),
                    'target': d['revenue']['target'], 'achieved_pct': d['revenue']['achieved_pct'],
                    'plan_acceptance': d['plan_acceptance'], 'nps': d['nps']} for d in dash['people']['doctors']]
        return {
            'today': str(today), 'period': dash['period']['label'], 'elapsed_pct': dash['period']['elapsed_pct'],
            'wd_left': dash['period']['wd_left'],
            'week': {'from': str(week_from), 'to': str(week_to), 'metrics': week},
            'off_track': [self._card_fact(c) for c in off],
            'on_track': [self._card_fact(c) for c in good],
            'drivers': drivers, 'doctors': doctors, 'backlog': self._backlog(today),
            'alerts': [{'level': a['level'], 'title': a['title'], 'todo': a['todo']} for a in dash['alerts'][:8]],
            'finance': {'margin_pct': dash['finance']['margin_pct'], 'receivable': dash['finance']['receivable'],
                        'overdue': dash['finance']['overdue'], 'overdue_count': dash['finance']['overdue_count']},
        }

    @staticmethod
    def _card_fact(card):
        return {'metric': card['metric'], 'label': card['label'], 'actual': fmt(card['metric'], card['actual']),
                'target': fmt(card['metric'], card['target']) if card['target'] is not None else None,
                'achieved_pct': card['achieved_pct'], 'forecast': fmt(card['metric'], card['forecast'])
                if card.get('forecast') is not None else None, 'forecast_pct': card.get('forecast_pct'),
                'status': card['status_label'], 'per_day': fmt(card['metric'], card['per_day'])
                if card.get('per_day') else None}

    @api.model
    def _backlog(self, today):
        """Việc tồn đọng cụ thể (đếm được) – nguyên liệu cho 3 việc nên làm."""
        companies = self.env.companies.ids
        Plan = self.env['dmag.treatment.plan'].sudo()
        pending = Plan.search([('company_id', 'in', companies), ('state', '=', 'presented')])
        pending_value = sum(max(p.option_ids.mapped('amount_total') or [0]) for p in pending)
        Visit = self.env['dmag.dental.visit'].sudo()
        an = self.env['dmag.ai.analysis']
        scope = an._scope(today + timedelta(days=1), today + timedelta(days=7))
        upcoming = scope.visits.filtered(lambda v: v.state in ('draft', 'confirmed'))
        unconfirmed = upcoming.filtered(lambda v: v.state == 'draft')
        pm_slots = scope.visits.filtered(lambda v: v.state not in ('cancel', 'no_show')
                                         and scope.local(v.scheduled_start).hour >= 13)
        no_show_recent = Visit.search_count([('company_id', 'in', companies), ('state', '=', 'no_show'),
                                             ('scheduled_start', '>=', fields.Datetime.now() - timedelta(days=14))])
        moves = self.env['account.move'].sudo().search([
            ('company_id', 'in', companies), ('move_type', '=', 'out_invoice'), ('state', '=', 'posted'),
            ('amount_residual', '>', 0)])
        stalled = self.env['dmag.treatment.plan'].sudo().search([
            ('company_id', 'in', companies), ('state', 'in', ('accepted', 'in_progress'))])
        stalled = stalled.filtered(lambda p: not Visit.search_count([
            ('treatment_plan_id', '=', p.id), ('state', 'in', ('draft', 'confirmed'))]))
        res = {
            'pending_plans': len(pending), 'pending_value': pending_value, 'pending_value_text': vnd(pending_value),
            'next7_bookings': len(upcoming), 'next7_unconfirmed': len(unconfirmed),
            'next7_afternoon_bookings': len(pm_slots), 'no_show_14d': no_show_recent,
            'open_invoices': len(moves), 'open_amount_text': vnd(sum(moves.mapped('amount_residual'))),
            'plans_without_next_visit': len(stalled),
        }
        if 'dmag.nps.response' in self.env:
            res['open_complaints'] = self.env['dmag.nps.response'].sudo().search_count([
                ('company_id', 'in', companies), ('is_complaint', '=', True), ('complaint_resolved', '=', False)])
        if 'dmag.ai.anomaly' in self.env:
            res['open_anomalies'] = self.env['dmag.ai.anomaly'].sudo().search_count([
                ('company_id', 'in', companies), ('state', 'in', ('new', 'review'))])
        return res

    # ------------------------------------------------------------------ AI
    @api.model
    def _brief_request(self, facts):
        """(system, user, schema) – một yêu cầu độc lập, phù hợp gửi theo lô (Message Batches)."""
        user = 'Dữ kiện tuần (JSON):\n' + json.dumps(facts, ensure_ascii=False, default=str)
        return BRIEF_SYSTEM, user, BRIEF_SCHEMA

    @api.model
    def _simulate_brief(self, facts):
        off = facts['off_track']
        week = {m['metric']: m for m in facts['week']['metrics']}
        rev = week['revenue']
        backlog = facts['backlog']
        if off:
            headline = '%s chỉ tiêu đang lệch – ưu tiên %s' % (len(off), off[0]['label'].lower())
        else:
            headline = 'Các chỉ tiêu chính đang đúng tiến độ'
        summary = ('%s đã qua %s%% (còn %s ngày làm việc). Tuần qua doanh thu %s (%s so với tuần trước), '
                   'thực thu %s, %s khách mới.') % (
            facts['period'], fmt('count', facts['elapsed_pct']), facts['wd_left'], rev['text'],
            rev['change'] or 'chưa có số liệu so sánh', week['collected']['text'], week['new_patients']['text'])
        off_track = []
        for item in off[:6]:
            detail = 'Thực tế %s / mục tiêu %s' % (item['actual'], item['target'] or '–')
            if item.get('forecast') and item.get('forecast_pct'):
                detail += ', dự báo cuối kỳ %s (%s%%)' % (item['forecast'], fmt('count', item['forecast_pct']))
            if item.get('per_day'):
                detail += '; cần thêm %s / ngày làm việc' % item['per_day']
            off_track.append({'metric': item['label'], 'detail': detail + ' – %s.' % item['status'].lower()})
        causes = [d['text'] for d in facts['drivers'][:4]] or ['Chưa thấy biến động lớn so với cùng kỳ.']
        actions = []
        if backlog['pending_plans']:
            actions.append({'title': 'Gọi lại %s khách đang cân nhắc kế hoạch' % backlog['pending_plans'],
                            'detail': 'Tổng giá trị khuyến nghị %s; hẹn tư vấn lại với bác sĩ, giới thiệu trả góp.'
                                      % backlog['pending_value_text'], 'owner': 'Tư vấn viên'})
        if backlog['next7_unconfirmed'] or backlog['no_show_14d']:
            actions.append({'title': 'Xác nhận %s lịch hẹn 7 ngày tới chưa xác nhận' % backlog['next7_unconfirmed'],
                            'detail': '14 ngày qua có %s lượt không đến – nhắn ZNS + gọi trước 1 ngày, ưu tiên khách mới.'
                                      % backlog['no_show_14d'], 'owner': 'Lễ tân'})
        pm_off = any(i['metric'] in ('revenue', 'chair_util_pm') for i in off)
        if pm_off or backlog['next7_afternoon_bookings'] < 15:
            actions.append({'title': 'Lấp ghế trống buổi chiều 13:30–16:30',
                            'detail': ('Mới có %s lịch buổi chiều 7 ngày tới' % backlog['next7_afternoon_bookings'])
                            + ('; mời %s khách có kế hoạch chưa hẹn buổi tiếp theo vào khung chiều.'
                               % backlog['plans_without_next_visit'] if backlog['plans_without_next_visit'] else
                               '; ưu đãi khung chiều cho khách khám tổng quát, cạo vôi.'),
                            'owner': 'Lễ tân + Bác sĩ'})
        if backlog['open_invoices']:
            actions.append({'title': 'Thu %s hóa đơn còn nợ' % backlog['open_invoices'],
                            'detail': 'Tổng còn phải thu %s – nhắc khách trả góp đến hạn.' % backlog['open_amount_text'],
                            'owner': 'Thu ngân'})
        if backlog.get('open_anomalies'):
            actions.append({'title': 'Rà %s cảnh báo bất thường' % backlog['open_anomalies'],
                            'detail': 'Giảm giá / hoàn tiền / vật tư vượt định mức chưa được giải trình.',
                            'owner': 'Quản lý'})
        highlights = []
        for item in facts['on_track'][:2]:
            highlights.append('%s: %s / mục tiêu %s – %s.' % (item['label'], item['actual'], item['target'] or '–',
                                                              item['status'].lower()))
        best = max(facts['doctors'], key=lambda d: d['achieved_pct'] or 0, default=None)
        if best and best['achieved_pct']:
            highlights.append('%s dẫn đầu: doanh thu %s (%s%% mục tiêu cá nhân).' % (
                best['name'], best['revenue_text'], fmt('count', best['achieved_pct'])))
        if week['nps']['this_week'] is not None:
            highlights.append('NPS tuần qua %s (tuần trước %s).' % (week['nps']['text'], week['nps']['prev_text']))
        return {'headline': headline, 'summary': summary, 'off_track': off_track, 'causes': causes,
                'actions': actions[:3], 'highlights': highlights[:3]}

    @api.model
    def _generate(self, trigger='manual'):
        facts = self._collect_facts()
        system, user, schema = self._brief_request(facts)
        res = self.env['dmag.ai'].run('AI-14', system, user, schema=schema,
                                      simulate=lambda: {'data': self._simulate_brief(facts)}, max_tokens=6000)
        data = res.get('data') or self._simulate_brief(facts)
        week_from = fields.Date.to_date(facts['week']['from'])
        week_to = fields.Date.to_date(facts['week']['to'])
        brief = self.sudo().create({
            'name': 'Bản tin điều hành tuần %s → %s' % (week_from.strftime('%d/%m'), week_to.strftime('%d/%m/%Y')),
            'company_id': self.env.company.id, 'week_from': week_from, 'week_to': week_to,
            'period_label': facts['period'], 'headline': data.get('headline'), 'summary': data.get('summary'),
            'data_json': json.dumps(data, ensure_ascii=False), 'facts_json': json.dumps(facts, ensure_ascii=False,
                                                                                         default=str),
            'body_html': self._render_html(data, facts, res), 'off_track_count': len(facts['off_track']),
            'mode': res['mode'], 'trigger': trigger, 'log_id': res['log_id'],
            'estimated_cost_vnd': res.get('cost_vnd') or res.get('estimated_cost_vnd'),
        })
        brief._notify_directors()
        brief.state = 'sent'
        return brief

    @api.model
    def _render_html(self, data, facts, res):
        e = escape
        parts = [Markup('<div class="dmag-brief-html">')]
        parts.append(Markup('<p><b>%s</b></p><p>%s</p>') % (data.get('headline') or '', data.get('summary') or ''))
        week = facts['week']['metrics']
        parts.append(Markup('<h4>Tuần qua (%s → %s)</h4><table class="table table-sm"><thead><tr><th>Chỉ số</th>'
                            '<th class="text-end">Tuần này</th><th class="text-end">Tuần trước</th>'
                            '<th class="text-end">Thay đổi</th></tr></thead><tbody>') % (
            facts['week']['from'][8:10] + '/' + facts['week']['from'][5:7],
            facts['week']['to'][8:10] + '/' + facts['week']['to'][5:7]))
        for m in week:
            parts.append(Markup('<tr><td>%s</td><td class="text-end">%s</td><td class="text-end">%s</td>'
                                '<td class="text-end">%s</td></tr>') % (m['label'], m['text'], m['prev_text'],
                                                                       m['change'] or '–'))
        parts.append(Markup('</tbody></table>'))

        def section(title, items):
            if not items:
                return
            parts.append(Markup('<h4>%s</h4><ul>') % title)
            for item in items:
                parts.append(Markup('<li>%s</li>') % item)
            parts.append(Markup('</ul>'))

        section('Chỉ tiêu đang lệch', [Markup('<b>%s</b>: %s') % (i['metric'], i['detail'])
                                       for i in data.get('off_track') or []])
        section('Nguyên nhân có thể', data.get('causes') or [])
        section('3 việc nên làm tuần này', [Markup('<b>%s</b> – %s <i>(%s)</i>') % (a['title'], a['detail'],
                                                                                     a['owner'])
                                            for a in data.get('actions') or []])
        section('Điểm sáng', data.get('highlights') or [])
        parts.append(Markup('<p class="text-muted small">%s · AI-14 · %s</p>') % (
            'Giả lập (số liệu thật, chưa gọi AI)' if res['simulated'] else 'Claude API (%s)' % (res.get('model') or ''),
            e('Chi phí %s' % vnd(res.get('cost_vnd') or 0) if not res['simulated'] else
              'Chi phí nếu chạy thật ≈ %s' % vnd(res.get('estimated_cost_vnd') or 0))))
        parts.append(Markup('</div>'))
        return Markup('').join(parts)

    def _notify_directors(self):
        group = self.env.ref('dmag_dental_base.group_dmag_director', raise_if_not_found=False)
        for brief in self:
            users = group.users.filtered(lambda u: brief.company_id in u.company_ids and not u.share) if group else []
            partners = users.mapped('partner_id') if users else self.env['res.partner']
            if partners:
                brief.message_subscribe(partner_ids=partners.ids)
            brief.message_post(body=brief.body_html, subject=brief.name, partner_ids=partners.ids,
                               message_type='comment', subtype_xmlid='mail.mt_comment')

    def get_brief_view(self):
        self.ensure_one()
        return {'id': self.id, 'name': self.name, 'headline': self.headline, 'summary': self.summary,
                'data': json.loads(self.data_json or '{}'), 'facts': json.loads(self.facts_json or '{}'),
                'mode': self.mode, 'date': str(self.date), 'trigger': self.trigger,
                'estimated_cost_vnd': self.estimated_cost_vnd}

    @api.model
    def get_brief_screen(self, brief_id=False):
        if not is_manager(self.env):
            raise AccessError(_('Bản tin điều hành chỉ dành cho Quản lý / Giám đốc.'))
        briefs = self.search([('company_id', 'in', self.env.companies.ids)], limit=30)
        current = self.browse(brief_id) if brief_id else briefs[:1]
        cron = self.env.ref('dmag_ai_insights.cron_dmag_ai_weekly_brief', raise_if_not_found=False)
        status = self.env['dmag.ai'].get_ai_status()
        return {
            'list': [{'id': b.id, 'name': b.name, 'headline': b.headline, 'date': str(b.date),
                      'off_track': b.off_track_count, 'trigger': b.trigger, 'mode': b.mode} for b in briefs],
            'current': current.get_brief_view() if current else None,
            'next_run': fields.Datetime.to_string(cron.sudo().nextcall) if cron else False,
            'mode': status['mode'], 'active': status['features'].get('AI-14', {}).get('active', False),
        }

    @api.model
    def generate_from_screen(self):
        if not is_manager(self.env):
            raise AccessError(_('Chỉ Quản lý / Giám đốc được soạn bản tin điều hành.'))
        return self._generate(trigger='manual').id
