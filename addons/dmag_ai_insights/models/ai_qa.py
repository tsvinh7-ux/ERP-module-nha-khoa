"""AI-13 – Hỏi đáp số liệu điều hành bằng tiếng Việt.

* **Claude API**: một lần ``dmag.ai.run('AI-13', ...)`` với 5 công cụ CHỈ ĐỌC (strict JSON schema) – AI tự chọn
  công cụ (không ép ``tool_choice``), đọc số liệu từ bộ máy chỉ số và trả lời kèm số liệu; mỗi công cụ trả mã
  đường dẫn (``link``) để giao diện hiện nút "Mở danh sách".
* **Giả lập**: bộ định tuyến ý định (chỉ số + mốc thời gian + bác sĩ + kiểu câu hỏi) gọi CHÍNH các công cụ đó và
  ghép câu trả lời – số liệu thật, có vết gọi công cụ hiển thị cho người dùng.
"""
import json
import re

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

from odoo.addons.dmag_dental_base.models.dmag_access import is_manager
from odoo.addons.dmag_dental_goals.models.dmag_goal_metrics import METRICS

from .ai_analysis import TOP_METRICS
from .ai_common import METRIC_KEYS, PERIOD_KEYS, PERIODS, fmt, resolve_period, strip_accents

SYSTEM_PROMPT = """Bạn là trợ lý phân tích số liệu điều hành cho Giám đốc / Quản lý phòng khám nha khoa.
Bạn CHỈ ĐỌC dữ liệu qua các công cụ được cấp; không đoán số. Quy tắc:
1. Mọi con số trong câu trả lời phải lấy từ kết quả công cụ; ghi rõ kỳ (từ ngày – đến ngày).
2. Câu hỏi "vì sao / tại sao" → so sánh với kỳ trước (compare_periods), xem phân tích theo bác sĩ / dịch vụ (list_top)
   và nêu 2–4 nguyên nhân có số liệu, rồi gợi ý 1–3 việc nên làm.
3. Khi nhắc tới một nhóm chứng từ (lượt khám, thủ thuật, kế hoạch…), gọi drill_records để có đường dẫn; giao diện
   tự hiện nút "Mở danh sách" – không tự viết URL.
4. Trả lời tiếng Việt, ngắn gọn (tối đa ~180 từ), dùng **in đậm** cho con số chính và gạch đầu dòng "- ".
5. Tiền viết kiểu Việt Nam: 1,25 tỷ; 450,5 tr; 85.000 ₫. Không bịa chỉ số không có trong danh mục.
Danh mục chỉ số (key: tên – cách tính):
%s"""

_NULLABLE_STR = {'type': ['string', 'null']}
TOOLS = [
    {
        'name': 'get_goal_dashboard', 'strict': True,
        'description': 'Tổng quan Bảng điều hành mục tiêu của một kỳ: các chỉ số chính (thực tế, mục tiêu, % đạt, dự báo '
                       'cuối kỳ, trạng thái), phễu hành trình khách hàng, bác sĩ, cảnh báo. Dùng cho câu hỏi tổng quan.',
        'input_schema': {'type': 'object', 'additionalProperties': False, 'required': ['period'], 'properties': {
            'period': {'type': 'string', 'enum': ['this_month', 'last_month', 'this_quarter', 'last_quarter',
                                                  'this_year']}}},
    },
    {
        'name': 'metric', 'strict': True,
        'description': 'Giá trị một chỉ số trong khoảng ngày (YYYY-MM-DD), toàn phòng khám hoặc một bác sĩ (tên).',
        'input_schema': {'type': 'object', 'additionalProperties': False,
                         'required': ['key', 'date_from', 'date_to', 'doctor'], 'properties': {
                             'key': {'type': 'string', 'enum': METRIC_KEYS},
                             'date_from': {'type': 'string', 'description': 'YYYY-MM-DD'},
                             'date_to': {'type': 'string', 'description': 'YYYY-MM-DD'},
                             'doctor': dict(_NULLABLE_STR, description='Tên bác sĩ, null = toàn phòng khám')}},
    },
    {
        'name': 'compare_periods', 'strict': True,
        'description': 'So sánh một chỉ số giữa hai kỳ có tên (vd this_month với last_month_to_date = tháng trước tới '
                       'cùng thời điểm) và trả các yếu tố giải thích chênh lệch (lượt khám, giá trị trung bình, phễu, '
                       'bác sĩ, nhóm dịch vụ).',
        'input_schema': {'type': 'object', 'additionalProperties': False,
                         'required': ['key', 'period_a', 'period_b', 'doctor'], 'properties': {
                             'key': {'type': 'string', 'enum': METRIC_KEYS},
                             'period_a': {'type': 'string', 'enum': PERIOD_KEYS},
                             'period_b': {'type': 'string', 'enum': PERIOD_KEYS},
                             'doctor': _NULLABLE_STR}},
    },
    {
        'name': 'list_top', 'strict': True,
        'description': 'Xếp hạng bác sĩ / dịch vụ / nguồn khách theo một chỉ số trong một kỳ.',
        'input_schema': {'type': 'object', 'additionalProperties': False,
                         'required': ['entity', 'metric', 'period', 'order', 'limit'], 'properties': {
                             'entity': {'type': 'string', 'enum': ['doctor', 'service', 'source']},
                             'metric': {'type': 'string', 'enum': TOP_METRICS},
                             'period': {'type': 'string', 'enum': PERIOD_KEYS},
                             'order': {'type': 'string', 'enum': ['desc', 'asc']},
                             'limit': {'type': 'integer'}}},
    },
    {
        'name': 'drill_records', 'strict': True,
        'description': 'Đếm các chứng từ đứng sau một chỉ số (lượt khám, thủ thuật, kế hoạch, phiếu NPS…) và tạo nút '
                       '"Mở danh sách" cho người dùng.',
        'input_schema': {'type': 'object', 'additionalProperties': False,
                         'required': ['key', 'period', 'doctor'], 'properties': {
                             'key': {'type': 'string', 'enum': METRIC_KEYS},
                             'period': {'type': 'string', 'enum': PERIOD_KEYS},
                             'doctor': _NULLABLE_STR}},
    },
]

# ---------------------------------------------------------------------------- bộ định tuyến giả lập
METRIC_WORDS = [
    ('collected', ['thuc thu', 'da thu', 'thu duoc', 'thu tien', 'tien thu']),
    ('gross_profit', ['loi nhuan', 'lai gop']),
    ('implant_cases', ['implant', 'cay ghep']),
    ('ortho_new', ['chinh nha', 'nieng']),
    ('plan_acceptance', ['ty le chot', 'chot ke hoach', 'chot', 'dong y ke hoach']),
    ('new_patients', ['khach moi', 'benh nhan moi']),
    ('show_up_rate', ['no-show', 'no show', 'khong den', 'bo hen', 'den kham', 'show-up', 'show up', 'vang']),
    ('consult_rate', ['duoc tu van', 'ty le tu van']),
    ('completion_rate', ['hoan tat dieu tri', 'hoan thanh dieu tri', 'bo do']),
    ('return_rate', ['tai kham']),
    ('referral_rate', ['gioi thieu']),
    ('avg_wait', ['thoi gian cho', 'cho doi', 'cho bao lau', 'phai cho']),
    ('chair_util_pm', ['ghe buoi chieu', 'cong suat chieu', 'buoi chieu']),
    ('chair_util_am', ['ghe buoi sang', 'cong suat sang', 'buoi sang']),
    ('nps', ['nps', 'hai long', 'diem danh gia', 'cham diem']),
    ('complaint_rate', ['khieu nai', 'phan nan']),
    ('cogs_ratio', ['gia von', 'vat tu', 'labo']),
    ('associate_share', ['bac si phu']),
    ('booked', ['lich hen', 'dat lich', 'so lich']),
    ('revenue', ['doanh thu', 'doanh so', 'ban duoc']),
]
PERIOD_WORDS = [
    ('last_month', ['thang truoc', 'thang roi']),
    ('this_month', ['thang nay']),
    ('last_quarter', ['quy truoc']),
    ('this_quarter', ['quy nay', 'quy ']),
    ('this_year', ['nam nay', 'tu dau nam']),
    ('last_week', ['tuan truoc']),
    ('this_week', ['tuan nay']),
    ('today', ['hom nay']),
    ('last_7_days', ['7 ngay']),
    ('last_30_days', ['30 ngay']),
    ('last_90_days', ['90 ngay', '3 thang']),
]
SAMPLE_QUESTIONS = [
    'Doanh thu tháng này thế nào?',
    'Vì sao doanh thu tháng này chậm?',
    'Bác sĩ nào chốt kế hoạch thấp nhất quý này?',
    'Thực thu tháng trước bao nhiêu?',
    'Tỷ lệ khách không đến tháng này?',
    'Dịch vụ nào mang lại doanh thu cao nhất 30 ngày qua?',
    'Khách mới tháng này đến từ nguồn nào?',
    'Vì sao khách mới tháng này thấp?',
    'NPS tuần này so với tuần trước?',
]


def _route(question):
    q = ' %s ' % strip_accents(question)
    q = re.sub(r'\s+', ' ', q)
    metric = None
    for key, words in METRIC_WORDS:
        if any(w in q for w in words):
            metric = key
            break
    found = []  # (vị trí, kỳ) – kỳ nhắc trước là kỳ chính, kỳ sau là kỳ so sánh
    taken = []
    for key, words in PERIOD_WORDS:
        for w in words:
            pos = q.find(w)
            if pos >= 0 and not any(a <= pos < b for a, b in taken):
                found.append((pos, key))
                taken.append((pos, pos + len(w)))
                break
    found.sort()
    period = found[0][1] if found else None
    period_b = found[1][1] if len(found) > 1 else None
    entity = None
    if re.search(r'bac si nao|bs nao|ai (chot|lam|co)|xep hang bac si|theo bac si|tung bac si|bac si (cao|thap)', q):
        entity = 'doctor'
    elif re.search(r'dich vu nao|theo dich vu|xep hang dich vu|dich vu (cao|thap|ban)', q):
        entity = 'service'
    elif re.search(r'nguon nao|tu nguon|nguon khach|kenh nao', q):
        entity = 'source'
    order = 'asc' if re.search(r'thap nhat|kem nhat|it nhat|thap|kem', q) else 'desc'
    if re.search(r'vi sao|tai sao|ly do|nguyen nhan|sao (lai|cham|giam|thap)', q):
        intent = 'why'
    elif entity:
        intent = 'top'
    elif re.search(r'so voi|so sanh|tang hay giam|thay doi', q):
        intent = 'compare'
    elif metric:
        intent = 'value'
    elif re.search(r'tong quan|tinh hinh|the nao|ra sao|bao cao|tom tat', q):
        intent = 'overview'
    else:
        intent = 'help'
    no_show = bool(re.search(r'khong den|no.?show|bo hen|vang', q))
    return {'metric': metric, 'period': period, 'period_b': period_b, 'entity': entity, 'order': order, 'intent': intent,
            'no_show': no_show, 'q': q}


class DmagAiQa(models.AbstractModel):
    _name = 'dmag.ai.qa'
    _description = 'DMAG AI-13 – Hỏi đáp số liệu điều hành'

    # ------------------------------------------------------------------ RPC
    @api.model
    def get_qa_context(self):
        status = self.env['dmag.ai'].get_ai_status()
        return {'samples': SAMPLE_QUESTIONS, 'mode': status['mode'],
                'active': status['features'].get('AI-13', {}).get('active', False),
                'model': status['features'].get('AI-13', {}).get('model')}

    @api.model
    def ask(self, question, history=None):
        """Trả lời một câu hỏi. ``history``: các lượt trước ``[{'role','content'}]`` (chỉ chữ)."""
        if not is_manager(self.env):
            raise AccessError(_('Hỏi đáp số liệu điều hành chỉ dành cho Quản lý / Giám đốc.'))
        question = (question or '').strip()[:1000]
        if not question:
            return {'text': _('Hãy nhập câu hỏi.'), 'links': [], 'tool_trace': []}
        box = QaToolbox(self.env)
        handlers = box.handlers()
        catalog = '\n'.join('- %s: %s – %s' % (k, v['label'], v['formula']) for k, v in METRICS.items())
        system = SYSTEM_PROMPT % catalog
        user = 'Hôm nay là %s.\nCâu hỏi: %s' % (box.today.strftime('%d/%m/%Y (%A)'), question)
        clean_history = [{'role': h['role'], 'content': str(h.get('content') or '')[:4000]}
                         for h in (history or [])[-8:] if h.get('role') in ('user', 'assistant')]
        res = self.env['dmag.ai'].run(
            'AI-13', system, user, history=clean_history, tools=TOOLS, tool_handlers=handlers,
            simulate=lambda: box.simulate(question), max_tokens=4000)
        trace = [{'tool': t['tool'], 'input': t.get('input'), 'summary': box.summarize(t)}
                 for t in res.get('tool_trace') or []]
        return {
            'text': res.get('text') or '', 'links': box.links, 'tool_trace': trace, 'mode': res['mode'],
            'simulated': res['simulated'], 'model': res.get('model'), 'cost_vnd': res.get('cost_vnd'),
            'estimated_cost_vnd': res.get('estimated_cost_vnd'), 'data': res.get('data'),
        }


class QaToolbox:
    """Các công cụ chỉ đọc + bộ định tuyến giả lập. Giữ danh sách đường dẫn sinh ra trong lần hỏi."""

    def __init__(self, env):
        self.env = env
        self.an = env['dmag.ai.analysis']
        self.today = self.an._today()
        self.links = []
        self.trace = []

    def handlers(self):
        return {'get_goal_dashboard': self.t_dashboard, 'metric': self.t_metric, 'compare_periods': self.t_compare,
                'list_top': self.t_top, 'drill_records': self.t_drill}

    def _link(self, action, label):
        if not action:
            return None
        self.links.append({'id': len(self.links) + 1, 'label': label, 'action': action})
        return len(self.links)

    def _doctor(self, name):
        doctor = self.an._find_doctor(name) if name else None
        if name and not doctor:
            raise ValueError('Không tìm thấy bác sĩ "%s". Bác sĩ hiện có: %s' % (
                name, ', '.join(self.an._doctors().mapped('name'))))
        return doctor

    # ------------------------------------------------------------------ tools
    def t_dashboard(self, inp):
        period = inp.get('period') or 'this_month'
        d_from = resolve_period(period, self.today)[0]
        ptype = 'quarter' if 'quarter' in period else 'year' if 'year' in period else 'month'
        data = self.env['dmag.goal.dashboard'].get_goal_dashboard(ptype, d_from)
        cards = []
        for card in data['north_star'] + data['service']:
            cards.append({k: card.get(k) for k in ('metric', 'label', 'actual', 'target', 'achieved_pct', 'forecast',
                                                   'forecast_pct', 'status_label', 'delta', 'delta_unit')}
                         | {'text': fmt(card['metric'], card.get('actual'))})
        funnel = [{'step': s['label'], 'count': s['count'], 'rate': s['rate'] and s['rate'].get('actual')}
                  for s in data['funnel']['steps']]
        doctors = [{'name': d['name'], 'revenue': d['revenue']['actual'], 'revenue_target': d['revenue']['target'],
                    'plan_acceptance': d['plan_acceptance'], 'nps': d['nps'], 'cases': d['cases']}
                   for d in data['people']['doctors']]
        return {'period': data['period']['label'], 'from': data['period']['from'], 'to': data['period']['to'],
                'elapsed_pct': data['period']['elapsed_pct'], 'cards': cards, 'funnel': funnel, 'doctors': doctors,
                'alerts': [a['title'] for a in data['alerts']][:8],
                'finance': {k: data['finance'].get(k) for k in ('revenue', 'gross_profit', 'margin_pct', 'collected',
                                                                 'receivable', 'overdue')}}

    def t_metric(self, inp):
        key = inp['key']
        d_from, d_to = fields.Date.to_date(inp['date_from']), fields.Date.to_date(inp['date_to'])
        if d_to < d_from:
            d_from, d_to = d_to, d_from
        doctor = self._doctor(inp.get('doctor'))
        value = self.an._value(key, d_from, d_to, doctor)
        name = '%s · %s → %s%s' % (METRICS[key]['label'], d_from.strftime('%d/%m'), d_to.strftime('%d/%m/%Y'),
                                   ' · %s' % doctor.name if doctor else '')
        link = self._link(self.an._drill(key, d_from, d_to, doctor, name), name)
        return {'key': key, 'label': METRICS[key]['label'], 'value': value, 'text': fmt(key, value),
                'from': str(d_from), 'to': str(d_to), 'doctor': doctor.name if doctor else None,
                'formula': METRICS[key]['formula'], 'link': link}

    def t_compare(self, inp):
        key = inp['key']
        doctor = self._doctor(inp.get('doctor'))
        a_from, a_to, a_label = resolve_period(inp['period_a'], self.today)
        b_from, b_to, b_label = resolve_period(inp['period_b'], self.today)
        a = self.an._value(key, a_from, a_to, doctor)
        b = self.an._value(key, b_from, b_to, doctor)
        drivers = self.an._drivers(key, a_from, a_to, doctor)['drivers'] if inp['period_a'] in (
            'this_month', 'this_quarter', 'this_week', 'last_month', 'last_week', 'last_30_days') else []
        return {'key': key, 'label': METRICS[key]['label'], 'a': {'period': a_label, 'value': a, 'text': fmt(key, a)},
                'b': {'period': b_label, 'value': b, 'text': fmt(key, b)},
                'change': self.an._delta_text(key, a, b), 'drivers': [d['text'] for d in drivers[:6]]}

    def t_top(self, inp):
        d_from, d_to, label = resolve_period(inp['period'], self.today)
        limit = max(1, min(int(inp.get('limit') or 5), 10))
        res = self.an._top(inp['entity'], inp['metric'], d_from, d_to, inp.get('order') or 'desc', limit)
        res['period'] = label
        if inp['entity'] == 'doctor' and res['metric'] in METRICS:
            for row in res['rows']:
                doctor = self.env['dmag.dental.practitioner'].browse(row['id'])
                name = '%s · %s · %s' % (METRICS[res['metric']]['label'], label, doctor.name)
                row['link'] = self._link(self.an._drill(res['metric'], d_from, d_to, doctor, name), name)
        for row in res['rows']:
            row.pop('id', None)
        return res

    def t_drill(self, inp):
        key = inp['key']
        d_from, d_to, label = resolve_period(inp['period'], self.today)
        doctor = self._doctor(inp.get('doctor'))
        name = '%s · %s%s' % (METRICS[key]['label'], label, ' · %s' % doctor.name if doctor else '')
        action = self.an._drill(key, d_from, d_to, doctor, name)
        if not action:
            return {'count': None, 'link': None, 'note': 'Chỉ số này không có danh sách chứng từ.'}
        count = self.env[action['res_model']].search_count(action['domain'])
        return {'model': action['res_model'], 'count': count, 'link': self._link(action, name), 'label': name}

    @staticmethod
    def summarize(trace):
        out = trace.get('output')
        if trace.get('error'):
            return 'Lỗi: %s' % (out.get('error') if isinstance(out, dict) else out)
        if not isinstance(out, dict):
            return str(out)[:160]
        tool = trace['tool']
        if tool == 'metric':
            return '%s = %s' % (out.get('label'), out.get('text'))
        if tool == 'compare_periods':
            return '%s: %s vs %s (%s)' % (out['label'], out['a']['text'], out['b']['text'], out.get('change') or '–')
        if tool == 'list_top':
            return ', '.join('%s %s' % (r['name'], r['text']) for r in out.get('rows', [])[:3])
        if tool == 'drill_records':
            return '%s chứng từ' % out.get('count')
        if tool == 'get_goal_dashboard':
            return '%s – %s chỉ số, %s cảnh báo' % (out.get('period'), len(out.get('cards', [])), len(out.get('alerts', [])))
        return json.dumps(out, ensure_ascii=False, default=str)[:160]

    # ------------------------------------------------------------------ giả lập
    def call(self, tool, inp):
        try:
            out = self.handlers()[tool](inp)
            self.trace.append({'tool': tool, 'input': inp, 'output': out, 'error': False})
            return out
        except Exception as e:  # noqa: BLE001 – giống cổng AI: lỗi công cụ trả lại cho bộ định tuyến
            self.trace.append({'tool': tool, 'input': inp, 'output': {'error': str(e)}, 'error': True})
            return None

    def simulate(self, question):
        r = _route(question)
        doctor = None
        for doc in self.an._doctors():
            words = [w for w in strip_accents(doc.name).replace('.', ' ').split() if w not in ('bs', 'ths', 'ts')]
            if not words:
                continue
            full = ' '.join(words)
            given = words[-1]
            if (' %s ' % full) in r['q'] or any(('%s %s ' % (p, given)) in r['q'] for p in (' bac si', ' bs', ' bsi')):
                doctor = doc
        dname = doctor.name if doctor else None
        intent, metric = r['intent'], r['metric']
        period = r['period'] or ('this_quarter' if intent == 'top' and 'quy' in r['q'] else 'this_month')
        lines, facts = [], []
        if intent == 'help':
            return {'text': 'Tôi trả lời các câu hỏi về số liệu điều hành (doanh thu, thực thu, khách mới, tỷ lệ chốt, '
                            'không đến, NPS, công suất ghế, bác sĩ, dịch vụ…) theo kỳ: hôm nay, tuần này / trước, '
                            'tháng này / trước, quý, năm, 30 ngày qua. Ví dụ:\n'
                            + '\n'.join('- %s' % s for s in SAMPLE_QUESTIONS[:5]),
                    'data': {'intent': 'help', 'facts': []}, 'tool_trace': self.trace}
        if intent == 'overview' or (intent == 'why' and not metric):
            ptype_period = period if period in ('this_month', 'last_month', 'this_quarter', 'last_quarter',
                                                'this_year') else 'this_month'
            dash = self.call('get_goal_dashboard', {'period': ptype_period})
            if dash:
                lines.append('**Tổng quan %s** (đã qua %.0f%% kỳ):' % (dash['period'], dash['elapsed_pct']))
                for card in dash['cards'][:7]:
                    if card['actual'] is None:
                        continue
                    target = ' / mục tiêu %s' % fmt(card['metric'], card['target']) if card['target'] else ''
                    lines.append('- %s: **%s**%s – %s' % (card['label'], card['text'], target,
                                                          card['status_label'].lower()))
                    facts.append({'metric': card['metric'], 'value': card['actual']})
                if dash['alerts']:
                    lines.append('Cần chú ý: %s.' % '; '.join(dash['alerts'][:3]))
            drill = self.call('drill_records', {'key': 'revenue', 'period': ptype_period, 'doctor': None})
            return self._result(lines, facts, r)
        metric = metric or 'revenue'
        label = METRICS[metric]['label']
        if intent == 'top':
            top_metric = metric if metric in TOP_METRICS else 'revenue'
            if r['no_show']:
                top_metric = 'no_show'
            entity = r['entity']
            if entity == 'source':
                top_metric = 'new_patients'
            order = r['order']
            if top_metric == 'no_show' and 'nhieu' in r['q']:
                order = 'desc'
            res = self.call('list_top', {'entity': entity, 'metric': top_metric, 'period': period, 'order': order,
                                         'limit': 5})
            if res and res['rows']:
                ent = {'doctor': 'Bác sĩ', 'service': 'Dịch vụ', 'source': 'Nguồn khách'}[entity]
                first = res['rows'][0]
                lines.append('%s có **%s %s** trong %s: **%s** – %s.' % (
                    ent, res['label'].lower(), 'thấp nhất' if order == 'asc' else 'cao nhất',
                    res['period'], first['name'], first['text']))
                lines.append('Xếp hạng:')
                for i, row in enumerate(res['rows'], 1):
                    extra = ' (%s lượt)' % row['cases'] if entity == 'doctor' and row.get('cases') is not None else ''
                    lines.append('%s. %s: **%s**%s' % (i, row['name'], row['text'], extra))
                    facts.append({'metric': res['metric'], 'name': row['name'], 'value': row['value']})
                if entity == 'doctor' and top_metric == 'plan_acceptance':
                    target = self.an._value('plan_acceptance', *resolve_period(period, self.today)[:2])
                    lines.append('Toàn phòng khám: %s. Gợi ý: bác sĩ có tỷ lệ thấp cùng tư vấn viên rà các kế hoạch '
                                 '"Đã tư vấn" chưa chốt, hẹn tư vấn lại với hình ảnh / phương án trả góp.'
                                 % fmt('pct', target))
            elif res:
                lines.append('Chưa có số liệu %s trong %s.' % (res['label'].lower(), res['period']))
            return self._result(lines, facts, r)
        d_from, d_to, plabel = resolve_period(period, self.today)
        value = self.call('metric', {'key': metric, 'date_from': str(d_from), 'date_to': str(d_to), 'doctor': dname})
        if not value:
            return self._result(['Không đọc được số liệu.'], facts, r)
        facts.append({'metric': metric, 'value': value['value'], 'from': value['from'], 'to': value['to']})
        subject = '%s%s' % (label, ' của %s' % dname if dname else '')
        if metric == 'show_up_rate' and r['no_show'] and value['value'] is not None:
            lines.append('Tỷ lệ khách **không đến** %s: **%s** (tỷ lệ đến khám %s).' % (
                plabel, fmt('pct', 100 - value['value']), value['text']))
        else:
            lines.append('**%s** %s: **%s**.' % (subject, plabel, value['text']))
        prev_key = {'this_month': 'last_month_to_date', 'this_week': 'last_week', 'this_quarter': 'last_quarter',
                    'last_month': None}.get(period)
        if r['period_b'] and r['period_b'] != period:
            prev_key = r['period_b']
        if intent in ('why', 'compare', 'value') and prev_key:
            cmp_ = self.call('compare_periods', {'key': metric, 'period_a': period, 'period_b': prev_key,
                                                 'doctor': dname})
            if cmp_:
                lines.append('- So với %s: %s → **%s**.' % (cmp_['b']['period'], cmp_['b']['text'],
                                                           cmp_['change'] or 'không đổi'))
                if intent == 'why':
                    a_val, b_val = cmp_['a']['value'], cmp_['b']['value']
                    better = a_val is not None and b_val is not None and (
                        a_val >= b_val if METRICS[metric]['direction'] == 'higher' else a_val <= b_val)
                    if better:
                        lines.append('Lưu ý: so với cùng kỳ, chỉ số này **không giảm** – xem mục tiêu bên dưới để '
                                     'biết có chậm so với kế hoạch không.')
                    lines.append('Các yếu tố tác động chính (theo số liệu):')
                    for text in cmp_['drivers'][:4] or ['Chưa thấy yếu tố nổi bật – số liệu kỳ này còn ít.']:
                        lines.append('- %s' % text)
        if not dname and period in ('this_month', 'this_quarter', 'this_year'):
            dash = self.call('get_goal_dashboard', {'period': period})
            card = dash and next((c for c in dash['cards'] if c['metric'] == metric), None)
            if card and card['target']:
                extra = ''
                if card.get('forecast') and METRICS[metric]['kind'] == 'sum':
                    extra = '; dự báo cuối kỳ **%s** (%.0f%% mục tiêu)' % (fmt(metric, card['forecast']),
                                                                          card['forecast_pct'] or 0)
                lines.append('- Mục tiêu: %s – đạt %.0f%%%s → **%s**.' % (
                    fmt(metric, card['target']), card['achieved_pct'] or 0, extra,
                    card['status_label'].lower()))
        if intent == 'why':
            todo = {
                'revenue': 'Lấp ghế trống buổi chiều; gọi lại khách đang cân nhắc kế hoạch.',
                'collected': 'Rà công nợ, nhắc khách trả góp đến hạn.',
                'plan_acceptance': 'Hẹn tư vấn lại các kế hoạch "Đã tư vấn" chưa chốt.',
                'show_up_rate': 'Nhắn ZNS / gọi xác nhận lịch hẹn trước 1 ngày, nhất là khách mới.',
                'new_patients': 'Đẩy chương trình giới thiệu bạn bè và khám tổng quát.',
                'nps': 'Gọi lại khách chấm điểm thấp trong 24 giờ.',
            }.get(metric)
            if todo:
                lines.append('Việc nên làm: %s' % todo)
        else:
            lines.append('Cách tính: %s' % METRICS[metric]['formula'])
        return self._result(lines, facts, r)

    def _result(self, lines, facts, route):
        return {'text': '\n'.join(lines), 'data': {'intent': route['intent'], 'facts': facts},
                'tool_trace': self.trace}

    @staticmethod
    def period_labels():
        return PERIODS
