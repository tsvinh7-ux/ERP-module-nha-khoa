"""Cổng gọi AI dùng chung cho mọi module DMAG.

Mọi tính năng AI gọi ``self.env['dmag.ai'].run('AI-xx', ...)``:

* **Chế độ giả lập** (mặc định, không cần khóa API): gọi hàm ``simulate`` của tính năng → kết quả mẫu giống thật,
  không tốn phí; nhật ký vẫn ghi kèm *chi phí ước tính nếu chạy thật*.
* **Chế độ Claude API**: gọi Claude (Anthropic) qua SDK chính thức, có ẩn danh dữ liệu bệnh nhân trước khi gửi
  và ghép lại khi nhận, vòng gọi công cụ (tool use) để AI tra/ghi dữ liệu Odoo qua hàm được phép, structured output
  (JSON schema), kiểm tra trần ngân sách tháng, xử lý AI từ chối, ghi nhật ký token + chi phí.

AI chỉ gợi ý: các module gọi phải để kết quả ở trạng thái nháp cho người duyệt.
"""
import json
import logging
import re
import time

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    import anthropic
except ImportError:  # chạy được ở chế độ giả lập khi chưa cài thư viện
    anthropic = None

# Giá công bố (USD / 1 triệu token): vào, ra, đọc bộ nhớ đệm, ghi bộ nhớ đệm
PRICES = {
    'claude-opus-5-5': (4.0, 20.0, 0.20, 5.0),
    'claude-sonnet-5-5': (2.0, 10.0, 0.20, 2.5),
    'claude-haiku-5-5': (0.10, 0.50, 0.01, 0.125),
}
FALLBACK_MODELS = ('claude-opus-5-5', 'claude-sonnet-5-5')  # mô hình hỗ trợ fallbacks="default"
MAX_TOOL_ROUNDS = 8

SAFETY_PREAMBLE = (
    "Bạn là trợ lý AI trong phần mềm quản lý phòng khám nha khoa DMAG tại Việt Nam. Trả lời bằng tiếng Việt, "
    "chính xác, ngắn gọn, dùng thuật ngữ nha khoa chuẩn. Bạn chỉ GỢI Ý để nhân viên y tế xem xét: không tự kết luận "
    "chẩn đoán, không tự kê đơn, không cam kết kết quả điều trị, không báo giá ngoài dữ liệu được cung cấp. "
    "Nếu thiếu dữ liệu, nói rõ là thiếu thay vì đoán. Thông tin định danh đã được thay bằng mã như [BN_1], [SĐT_1] – "
    "giữ nguyên các mã này trong câu trả lời."
)


class DmagAiPseudonymizer:
    """Thay thông tin định danh bằng mã trước khi gửi ra ngoài, ghép lại khi nhận kết quả."""

    LABELS = {'name': 'BN', 'phone': 'SĐT', 'citizen_id': 'CCCD', 'email': 'EMAIL', 'address': 'ĐC', 'other': 'TT'}

    def __init__(self):
        self.forward = {}   # giá trị thật -> mã
        self.backward = {}  # mã -> giá trị thật
        self.counter = {}

    def add(self, value, kind='other'):
        value = (value or '').strip()
        if len(value) < 3 or value in self.forward:
            return
        label = self.LABELS.get(kind, 'TT')
        self.counter[label] = self.counter.get(label, 0) + 1
        token = '[%s_%d]' % (label, self.counter[label])
        self.forward[value] = token
        self.backward[token] = value

    def add_partner(self, partner):
        if not partner:
            return
        partner = partner.sudo()
        self.add(partner.name, 'name')
        for fname in ('phone', 'mobile', 'zalo_phone'):
            if fname in partner._fields:
                self.add(partner[fname], 'phone')
        if 'citizen_id' in partner._fields:
            self.add(partner.citizen_id, 'citizen_id')
        self.add(partner.email, 'email')
        self.add(partner.street, 'address')

    def mask(self, text):
        if not isinstance(text, str) or not self.forward:
            return text
        for value in sorted(self.forward, key=len, reverse=True):
            text = text.replace(value, self.forward[value])
        return text

    def unmask(self, obj):
        if isinstance(obj, str):
            if not self.backward or '[' not in obj:
                return obj
            return re.sub(r'\[[A-ZĐ]+_\d+\]', lambda m: self.backward.get(m.group(0), m.group(0)), obj)
        if isinstance(obj, list):
            return [self.unmask(v) for v in obj]
        if isinstance(obj, dict):
            return {k: self.unmask(v) for k, v in obj.items()}
        return obj

    def mask_content(self, content):
        """Ẩn danh nội dung tin nhắn (chuỗi hoặc danh sách khối; chỉ khối text)."""
        if isinstance(content, str):
            return self.mask(content)
        masked = []
        for block in content:
            if isinstance(block, dict) and block.get('type') == 'text':
                block = dict(block, text=self.mask(block['text']))
            elif isinstance(block, dict) and block.get('type') == 'tool_result' and isinstance(block.get('content'), str):
                block = dict(block, content=self.mask(block['content']))
            masked.append(block)
        return masked


class DmagAi(models.AbstractModel):
    _name = 'dmag.ai'
    _description = 'Cổng gọi AI DMAG'

    # ------------------------------------------------------------------ public API
    @api.model
    def run(self, feature, system, user, *, history=None, schema=None, tools=None, tool_handlers=None,
            simulate=None, record=None, patient=None, pii=None, max_tokens=8000):
        """Chạy một tác vụ AI.

        :param feature: mã tính năng (vd. ``'AI-01'``)
        :param system: hướng dẫn hệ thống (tiếng Việt) – nên cố định để tận dụng bộ nhớ đệm
        :param user: nội dung lượt người dùng (chuỗi hoặc danh sách khối text/image)
        :param history: các lượt trước ``[{'role': 'user'|'assistant', 'content': str}]`` (hội thoại)
        :param schema: JSON schema → kết quả ``data`` là dict đã kiểm tra
        :param tools: định nghĩa công cụ (Messages API); ``tool_handlers``: ``{tên: hàm(input_dict) -> dict|str}``
        :param simulate: hàm không tham số trả ``{'text':..., 'data':..., 'tool_trace': [...]}`` cho chế độ giả lập
        :param record: bản ghi liên quan (truy vết); ``patient``: res.partner (đồng ý + ẩn danh)
        :param pii: danh sách chuỗi định danh khác cần ẩn
        :return: dict ``text, data, mode, simulated, model, log_id, cost_vnd, estimated_cost_vnd, tool_trace``
        """
        feature_rec = self._get_feature(feature)
        company = self.env.company
        self._check_consent(feature_rec, patient, company)
        mode = 'live' if company.dmag_ai_mode == 'live' else 'simulate'
        pseudo = DmagAiPseudonymizer()
        pseudo.add_partner(patient)
        for value in pii or []:
            pseudo.add(value, 'other')
        log_vals = {
            'feature_id': feature_rec.id, 'company_id': company.id, 'mode': mode, 'model': feature_rec.model,
            'res_model': record._name if record else False, 'res_id': record.id if record else False,
            'patient_id': patient.id if patient else False, 'pseudonymized': len(pseudo.forward),
        }
        started = time.time()
        if mode == 'live':
            self._check_budget(company, feature_rec, log_vals)
            result = self._run_live(feature_rec, system, user, history, schema, tools, tool_handlers, pseudo,
                                    max_tokens, log_vals)
        else:
            result = self._run_simulated(feature_rec, system, user, history, simulate, pseudo, log_vals)
        log_vals['duration_ms'] = int((time.time() - started) * 1000)
        log = self.env['dmag.ai.log'].create(log_vals)
        result.update({'mode': mode, 'simulated': mode == 'simulate', 'model': log_vals.get('model'),
                       'log_id': log.id, 'cost_vnd': log.cost_vnd, 'estimated_cost_vnd': log.estimated_cost_vnd,
                       'feature': feature_rec.code})
        return result

    @api.model
    def get_ai_status(self):
        """Trạng thái AI cho giao diện: chế độ, khóa, chi phí tháng, các tính năng đang bật."""
        company = self.env.company
        spent = self._month_spent(company)
        features = self.env['dmag.ai.feature'].sudo().search([])
        return {
            'mode': company.dmag_ai_mode,
            'key_set': company.dmag_ai_key_set,
            'library': bool(anthropic),
            'budget_vnd': company.dmag_ai_monthly_budget,
            'spent_vnd': spent,
            'features': {f.code: {'active': f.active, 'name': f.name, 'model': f.model} for f in features},
        }

    @api.model
    def is_feature_active(self, code):
        return bool(self.env['dmag.ai.feature'].sudo().search_count([('code', '=', code), ('active', '=', True)]))

    # ------------------------------------------------------------------ checks
    def _get_feature(self, code):
        feature = self.env['dmag.ai.feature'].sudo().with_context(active_test=False).search([('code', '=', code)], limit=1)
        if not feature:
            raise UserError(_('Chưa khai báo tính năng AI %s.', code))
        if not feature.active:
            raise UserError(_('Tính năng AI "%s" đang tắt (Nha khoa → Cấu hình → Trợ lý AI).', feature.name))
        return feature

    def _check_consent(self, feature, patient, company):
        if not (feature.sends_patient_data and patient and company.dmag_ai_require_consent):
            return
        if not patient.sudo().dmag_ai_consent:
            raise UserError(_(
                'Bệnh nhân %s chưa đồng ý cho phép hỗ trợ bằng AI. Hỏi ý kiến bệnh nhân rồi đánh dấu '
                '"Đồng ý hỗ trợ bằng AI" trên hồ sơ (NĐ 13/2023).', patient.name))

    def _month_spent(self, company):
        month_start = fields.Datetime.to_datetime(fields.Date.context_today(self).replace(day=1))
        logs = self.env['dmag.ai.log'].sudo().search([('company_id', '=', company.id), ('create_date', '>=', month_start)])
        return sum(logs.mapped('cost_vnd'))

    def _check_budget(self, company, feature, log_vals):
        budget = company.dmag_ai_monthly_budget
        if budget and self._month_spent(company) >= budget:
            log_vals.update(status='budget', error=_('Vượt trần ngân sách AI tháng.'))
            self.env['dmag.ai.log'].create(log_vals)
            raise UserError(_('Đã dùng hết ngân sách AI tháng này (%s đ). Giám đốc có thể nâng trần tại '
                              'Cấu hình → Trợ lý AI.', '{:,.0f}'.format(budget).replace(',', '.')))

    # ------------------------------------------------------------------ cost
    @api.model
    def _cost_usd(self, model, usage):
        price = PRICES.get(model) or PRICES['claude-opus-5-5']
        return (usage.get('input', 0) * price[0] + usage.get('output', 0) * price[1]
                + usage.get('cache_read', 0) * price[2] + usage.get('cache_write', 0) * price[3]) / 1e6

    @api.model
    def _estimate_tokens(self, *texts):
        # Tiếng Việt ~ 2,5–3 ký tự / token
        return int(sum(len(t if isinstance(t, str) else json.dumps(t, ensure_ascii=False)) for t in texts if t) / 2.7)

    # ------------------------------------------------------------------ simulate
    def _run_simulated(self, feature, system, user, history, simulate, pseudo, log_vals):
        result = dict(simulate() if simulate else {'text': _('(Giả lập) Chưa có kết quả mẫu cho tính năng này.')})
        result.setdefault('text', '')
        result.setdefault('data', None)
        result.setdefault('tool_trace', [])
        usage = {
            'input': self._estimate_tokens(system, user, history),
            'output': self._estimate_tokens(result.get('text'), result.get('data')) or 200,
        }
        est_usd = self._cost_usd(feature.model, usage)
        log_vals.update({
            'model': '%s (giả lập)' % feature.model,
            'input_tokens': usage['input'], 'output_tokens': usage['output'],
            'tool_calls': len(result['tool_trace']),
            'estimated_cost_vnd': est_usd * self.env.company.dmag_ai_usd_rate,
            'request_preview': pseudo.mask(self._preview(user)),
            'response_preview': self._preview(result.get('text') or result.get('data')),
        })
        return result

    # ------------------------------------------------------------------ live (Claude API)
    def _client(self):
        if anthropic is None:
            raise UserError(_('Máy chủ chưa cài thư viện "anthropic" (pip install anthropic).'))
        key = self.env.company.sudo().dmag_ai_api_key
        if not key:
            raise UserError(_('Chưa nhập khóa API Claude (Cấu hình → Trợ lý AI) – hoặc chuyển về chế độ Giả lập.'))
        return anthropic.Anthropic(api_key=key, max_retries=2, timeout=180.0)

    def _run_live(self, feature, system, user, history, schema, tools, tool_handlers, pseudo, max_tokens, log_vals):
        client = self._client()
        model = feature.model or 'claude-opus-5-5'
        messages = []
        for turn in history or []:
            messages.append({'role': turn['role'], 'content': pseudo.mask_content(turn['content'])})
        messages.append({'role': 'user', 'content': pseudo.mask_content(user)})
        params = {
            'model': model,
            'max_tokens': max_tokens,
            # Hướng dẫn cố định đặt trước + bộ nhớ đệm → các lần gọi sau rẻ hơn
            'system': [{'type': 'text', 'text': SAFETY_PREAMBLE + '\n\n' + pseudo.mask(system),
                        'cache_control': {'type': 'ephemeral'}}],
            'output_config': {'effort': feature.effort or 'medium'},
        }
        if schema:
            params['output_config']['format'] = {'type': 'json_schema', 'schema': schema}
        if tools:
            params['tools'] = tools
        if model in FALLBACK_MODELS:
            params['betas'] = ['server-side-fallback-2026-07-01']
            params['fallbacks'] = 'default'
        usage = {'input': 0, 'output': 0, 'cache_read': 0, 'cache_write': 0}
        trace = []
        response = None
        try:
            for _round in range(MAX_TOOL_ROUNDS):
                if 'betas' in params:
                    response = client.beta.messages.create(messages=messages, **params)
                else:
                    response = client.messages.create(messages=messages, **params)
                u = response.usage
                usage['input'] += u.input_tokens or 0
                usage['output'] += u.output_tokens or 0
                usage['cache_read'] += getattr(u, 'cache_read_input_tokens', 0) or 0
                usage['cache_write'] += getattr(u, 'cache_creation_input_tokens', 0) or 0
                log_vals['model'] = response.model or model
                log_vals['request_id'] = getattr(response, '_request_id', None)
                if response.stop_reason == 'refusal':
                    log_vals.update(status='refusal', error=str(getattr(response, 'stop_details', '') or ''))
                    raise UserError(_('AI từ chối xử lý yêu cầu này. Vui lòng thực hiện thủ công.'))
                if response.stop_reason != 'tool_use':
                    break
                messages.append({'role': 'assistant', 'content': response.content})
                results = []
                for block in response.content:
                    if block.type != 'tool_use':
                        continue
                    handler = (tool_handlers or {}).get(block.name)
                    tool_input = pseudo.unmask(dict(block.input or {}))
                    try:
                        if not handler:
                            raise UserError(_('Công cụ %s không được phép.', block.name))
                        output = handler(tool_input)
                        is_error = False
                    except Exception as e:  # trả lỗi cho AI tự xử lý, không làm hỏng giao dịch
                        output = {'error': str(e)}
                        is_error = True
                    trace.append({'tool': block.name, 'input': tool_input, 'output': output, 'error': is_error})
                    content = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False, default=str)
                    results.append({'type': 'tool_result', 'tool_use_id': block.id,
                                    'content': pseudo.mask(content), 'is_error': is_error})
                messages.append({'role': 'user', 'content': results})
        except UserError:
            self._finish_live_log(log_vals, usage, trace, user, pseudo, None)
            self.env['dmag.ai.log'].create(log_vals)
            raise
        except Exception as e:  # lỗi mạng / khóa / quota
            _logger.warning('DMAG AI lỗi: %s', e)
            log_vals.update(status='error', error=str(e))
            self._finish_live_log(log_vals, usage, trace, user, pseudo, None)
            self.env['dmag.ai.log'].create(log_vals)
            raise UserError(self._friendly_error(e)) from e
        text = '\n'.join(b.text for b in response.content if b.type == 'text').strip()
        data = None
        if schema and text:
            try:
                data = json.loads(text)
            except ValueError:
                data = None
        text = pseudo.unmask(text)
        data = pseudo.unmask(data)
        self._finish_live_log(log_vals, usage, trace, user, pseudo, text or data)
        return {'text': text, 'data': data, 'tool_trace': trace}

    def _finish_live_log(self, log_vals, usage, trace, user, pseudo, output):
        cost = self._cost_usd(log_vals.get('model') or 'claude-opus-5-5', usage)
        rate = self.env.company.dmag_ai_usd_rate
        log_vals.update({
            'input_tokens': usage['input'], 'output_tokens': usage['output'],
            'cache_read_tokens': usage['cache_read'], 'tool_calls': len(trace),
            'cost_usd': cost, 'cost_vnd': cost * rate, 'estimated_cost_vnd': cost * rate,
            'request_preview': pseudo.mask(self._preview(user)),
            'response_preview': self._preview(output) if output else False,
        })

    @staticmethod
    def _friendly_error(e):
        name = type(e).__name__
        if name == 'AuthenticationError':
            return _('Khóa API Claude không hợp lệ.')
        if name == 'RateLimitError':
            return _('AI đang quá tải, thử lại sau ít phút.')
        if name in ('APIConnectionError', 'APITimeoutError'):
            return _('Không kết nối được dịch vụ AI (kiểm tra mạng máy chủ).')
        return _('Dịch vụ AI báo lỗi: %s', e)

    @staticmethod
    def _preview(value, limit=1500):
        if value is None:
            return False
        if isinstance(value, list):  # khối nội dung: chỉ lấy phần chữ, bỏ ảnh
            value = '\n'.join(b.get('text', '[ảnh]') if isinstance(b, dict) else str(b) for b in value)
        if not isinstance(value, str):
            value = json.dumps(value, ensure_ascii=False, default=str)
        return value[:limit]
