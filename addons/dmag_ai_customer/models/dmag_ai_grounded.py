"""AI-07 – chế độ "Tự động – chỉ trả lời từ dữ liệu đã nạp" (MẶC ĐỊNH).

Trợ lý thay nhân viên trả lời khách 24/7 nhưng mọi câu trả lời phải có NGUỒN trong dữ liệu đã nạp (kho tri thức đã
duyệt + công cụ đọc dữ liệu thật của Odoo). Không có nguồn → không trả lời bừa: gửi khách tin giữ chỗ cố định, báo lễ
tân ĐANG TRỰC (Lịch nghỉ luân phiên), quá hạn → báo Quản lý; câu hỏi vào hàng "Câu hỏi ngoài dữ liệu" của Hộp thư.

* Giả lập: an toàn tại chỗ → luồng đặt lịch (công cụ thật) → kịch bản đã duyệt → tìm kho tri thức (BM25, không dấu)
  → bảng giá → chào hỏi cố định → ngoài dữ liệu.
* Claude: ``dmag.ai.run`` với công cụ chỉ đọc (search_knowledge, search_services, get_free_slots, get_clinic_info,
  find_patient_by_phone) + book_appointment (lịch nháp) + handoff_to_staff và structured output
  ``{answer, grounded, sources, needs_staff, reason}``.
* Kiểm tra phía máy chủ (cả hai chế độ): ``grounded`` sai, không có nguồn, nguồn không thuộc các công cụ / mục tri thức
  đã gọi trong lượt, hoặc câu trả lời có CON SỐ (giá, giờ, ngày…) không có trong nguồn → KHÔNG gửi.
"""
import json
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .dmag_ai_reception import BOOK_WORDS, GREET_WORDS, PRICE_WORDS, THANKS_WORDS, WEEKDAY_VI
from .text_utils import extract_date, extract_time, fold, has_any, numbers_in

GROUNDED_TOOLS = {'search_knowledge', 'search_services', 'get_free_slots', 'get_clinic_info', 'find_patient_by_phone',
                  'book_appointment', 'handoff_to_staff'}
# Ý định đặt lịch rõ ràng (không tính "muốn khám", "đến khám"… vốn hay xuất hiện trong câu hỏi khác)
STRONG_BOOK_WORDS = ['đặt lịch', 'đặt hẹn', 'hẹn lịch', 'đặt chỗ', 'book', 'lấy lịch', 'đăng ký khám', 'giữ chỗ',
                     'lịch trống', 'giờ trống', 'còn lịch']
BOOKING_TOOLS = {'search_services', 'get_free_slots', 'find_patient_by_phone', 'book_appointment', 'get_clinic_info'}
TOOL_LABELS = {
    'search_services': 'Bảng giá', 'get_free_slots': 'Giờ trống', 'get_clinic_info': 'Thông tin phòng khám',
    'book_appointment': 'Đặt lịch (nháp)', 'find_patient_by_phone': 'Hồ sơ khách', 'search_knowledge': 'Kho tri thức',
}
# Cụm cố định của bộ trả lời giả lập (gợi ý ngày, căn cứ NĐ 13/2023) – được phép xuất hiện trong câu trả lời
FIXED_PHRASES = 'Thứ 2 Thứ 3 Thứ 4 Thứ 5 Thứ 6 Thứ 7 Chủ nhật · Nghị định 13/2023 · NĐ 13/2023'
GREETING = ('Dạ {clinic} xin chào! Em là trợ lý tự động của phòng khám – em trả lời theo thông tin phòng khám đã cung cấp '
            '(bảng giá, giờ làm việc, lịch bác sĩ, chính sách) và giữ chỗ lịch hẹn giúp anh/chị. Anh/chị cần em hỗ '
            'trợ gì ạ?')
THANKS = 'Dạ không có gì ạ! Chúc anh/chị một ngày vui – cần gì cứ nhắn em nhé.'
DEFAULT_HOLDING = ('Dạ câu hỏi này em cần nhân viên phụ trách kiểm tra để trả lời chính xác cho anh/chị. Em đã chuyển cho '
                   'lễ tân đang trực, anh/chị vui lòng chờ trong ít phút ạ.')

GROUNDED_PROMPT = """Bạn là trợ lý Zalo OA của {clinic}, thay nhân viên trả lời khách 24/7 NHƯNG CHỈ được trả lời bằng
dữ liệu phòng khám đã nạp. Hôm nay là {today} ({weekday}), giờ Việt Nam.

QUY TẮC BẮT BUỘC
1. Mọi thông tin (giá, giờ, ngày, bác sĩ, chính sách, địa chỉ, số điện thoại, bảo hành…) PHẢI lấy từ kết quả công cụ
   trong lượt này: search_knowledge (kho tri thức đã duyệt), search_services (bảng giá), get_clinic_info,
   get_free_slots. Không dùng kiến thức chung, không suy đoán, không làm tròn / quy đổi con số.
2. Không tìm thấy trong dữ liệu → grounded=false, needs_staff=true, answer="" (hệ thống tự gửi tin giữ chỗ và báo lễ
   tân đang trực).
3. Không chẩn đoán, không kê thuốc, không hứa kết quả. Câu hỏi chuyên môn → needs_staff=true, reason="medical".
   Khiếu nại / ca khẩn → handoff_to_staff ngay.
4. Đặt lịch: get_free_slots → khách chọn giờ → họ tên + số điện thoại + khách ĐỒNG Ý cho lưu thông tin (NĐ 13/2023)
   → book_appointment (lịch nháp, lễ tân gọi xác nhận). Không tự bịa giờ trống.
5. sources: id các kết quả search_knowledge đã dùng (dạng "kb:12") và / hoặc tên công cụ đã dùng (search_services,
   get_clinic_info, get_free_slots, book_appointment).
6. answer: tiếng Việt thân thiện, xưng "em", gọi "anh/chị", tối đa 5 câu.
"""
GROUNDED_SCHEMA = {
    'type': 'object',
    'properties': {
        'answer': {'type': 'string', 'description': 'Câu trả lời gửi khách (rỗng nếu không có dữ liệu)'},
        'grounded': {'type': 'boolean', 'description': 'Mọi thông tin trong answer đều có trong kết quả công cụ'},
        'sources': {'type': 'array', 'items': {'type': 'string'},
                    'description': 'Nguồn đã dùng: "kb:<id>" hoặc tên công cụ'},
        'needs_staff': {'type': 'boolean', 'description': 'Cần nhân viên trả lời (ngoài dữ liệu / chuyên môn)'},
        'reason': {'type': 'string', 'description': 'Lý do ngắn cho nhân viên'},
    },
    'required': ['answer', 'grounded', 'sources', 'needs_staff', 'reason'], 'additionalProperties': False,
}


def _excerpt(content, query, limit=420):
    """Trích các câu liên quan nhất của một đoạn dài (giữ thứ tự gốc)."""
    content = (content or '').strip()
    if len(content) <= limit:
        return content
    words = set(re.findall(r'[a-z0-9]{2,}', fold(query)))
    sentences = [s.strip() for s in re.split(r'(?<=[.!?…])\s+|\n+', content) if s.strip()]
    ranked = sorted(range(len(sentences)),
                    key=lambda i: -len(words & set(re.findall(r'[a-z0-9]{2,}', fold(sentences[i])))))
    keep, total = set(), 0
    for i in ranked:
        if total + len(sentences[i]) > limit and keep:
            break
        keep.add(i)
        total += len(sentences[i])
    return ' '.join(sentences[i] for i in sorted(keep))


class DmagAiConversationGrounded(models.Model):
    _inherit = 'dmag.ai.conversation'

    gap_ids = fields.One2many('dmag.ai.kb.gap', 'conversation_id', string='Câu hỏi ngoài dữ liệu')
    open_gap_count = fields.Integer('Câu hỏi ngoài dữ liệu đang chờ', compute='_compute_open_gap_count', store=True)

    @api.depends('gap_ids.state')
    def _compute_open_gap_count(self):
        for conv in self:
            conv.open_gap_count = len(conv.gap_ids.filtered(lambda g: g.state == 'open'))

    # ------------------------------------------------------------------ an toàn (dùng chung với chế độ kịch bản)
    def _safety_first(self, text, question):
        """Ca khẩn / khiếu nại / muốn gặp người: xử lý cố định, không qua AI. Trả tin trả lời hoặc None."""
        from .dmag_ai_conversation import COMPLAINT_ACK, HUMAN_ACK
        safety = self.env['dmag.ai.reception'].sudo().safety_precheck(text)
        if safety == 'emergency':
            self._handoff('emergency', text[:200])
            return self._send_emergency_template(question, _('Từ khóa khẩn cấp – chuyển nhân viên trực ngay'))
        if safety in ('complaint', 'human_request'):
            self._handoff(safety, text[:200])
            label = _('Khiếu nại / bực bội') if safety == 'complaint' else _('Khách muốn gặp nhân viên')
            return self._create_reply({'text': COMPLAINT_ACK if safety == 'complaint' else HUMAN_ACK}, 'ready',
                                      safety, question, note=_('%s – chuyển nhân viên, không tự trả lời', label),
                                      role='system')
        return None

    # ------------------------------------------------------------------ chế độ "chỉ trả lời từ dữ liệu đã nạp"
    def _ensure_knowledge(self):
        """Nạp dữ liệu gốc Odoo + kịch bản vào kho tri thức nếu chưa nạp hoặc đã cũ (> 6 giờ)."""
        company = self.company_id.sudo()
        last = company.dmag_ai_kb_refreshed_at
        if not last or (fields.Datetime.now() - last).total_seconds() > 6 * 3600:
            KB = self.env['dmag.ai.knowledge'].sudo().with_company(company)
            KB.load_master_data(company)
            KB.load_scripts(company)
            company.dmag_ai_kb_refreshed_at = fields.Datetime.now()

    def _grounded_reply(self, text, question=None):
        self.ensure_one()
        reply = self._safety_first(text, question)
        if reply:
            return reply
        self._ensure_knowledge()
        Reception = self.env['dmag.ai.reception'].sudo()
        live = self.company_id.dmag_ai_mode == 'live'
        conv = self.sudo()
        holder = {}
        history = conv._history_for_ai()
        user_text = text
        if history and history[-1]['role'] == 'user':
            user_text = history.pop()['content'] + '\n' + text
        today = fields.Date.context_today(self)
        system = GROUNDED_PROMPT.format(clinic=self.company_id.name, today=today.strftime('%d/%m/%Y'),
                                        weekday=WEEKDAY_VI[today.weekday()])
        try:
            res = self.env['dmag.ai'].sudo().run(
                'AI-07', system, user_text, history=history, schema=GROUNDED_SCHEMA,
                tools=Reception.get_tools(GROUNDED_TOOLS), tool_handlers=Reception._handlers(conv, GROUNDED_TOOLS),
                simulate=lambda: conv._grounded_simulate(text, holder), record=conv,
                patient=conv.partner_id if conv.partner_id and conv.partner_id.is_patient else None,
                pii=[conv.phone] if conv.phone else None, max_tokens=3000)
        except UserError as e:
            return self._out_of_data(text, question, 'ai_error', _('Trợ lý không trả lời được: %s', e))
        data = res.get('data') if isinstance(res.get('data'), dict) else {}
        meta = holder if not live else {}
        kind = meta.get('kind') or 'answer'
        if kind == 'handoff_script':
            return self._create_reply(res, 'ready', 'handoff_script', question, meta.get('script'),
                                      meta.get('confidence', 0.0), meta.get('note', ''),
                                      extra={'sources': json.dumps(meta.get('source_items') or [], ensure_ascii=False)})
        answer = (data.get('answer') or '').strip()
        trace = res.get('tool_trace') or []
        if kind == 'out_of_data' or not data.get('grounded') or data.get('needs_staff') or not answer:
            reason = meta.get('reason_code') or ('medical' if 'medical' in (data.get('reason') or '').lower()
                                                 or Reception.is_medical_question(text) else 'no_data')
            note = meta.get('note') or data.get('reason') or _('Không có trong dữ liệu đã nạp')
            return self._out_of_data(text, question, reason, note, res=res)
        sources, problem = self._verify_grounded(answer, data.get('sources') or [], trace, text,
                                                 meta.get('source_texts') or [])
        if problem:
            return self._out_of_data(text, question, 'unverified', problem, res=res, draft=answer)
        kb_ids = [s['id'] for s in sources if s['kind'] == 'kb']
        if kb_ids:
            self.env['dmag.ai.knowledge'].sudo().browse(kb_ids)._mark_used()
        script = meta.get('script')
        if script:
            script._mark_used()
        note = meta.get('note') or _('Trả lời từ: %s', ' · '.join(s['label'] for s in sources))
        res = dict(res, text=answer, quick=meta.get('quick'))
        return self._create_reply(res, 'ready', 'grounded', question, script, meta.get('confidence', 0.0), note,
                                  extra={'sources': json.dumps(sources, ensure_ascii=False)})

    # ------------------------------------------------------------------ kiểm tra phía máy chủ
    def _verify_grounded(self, answer, claimed, trace, customer_text, extra_texts=()):
        """→ (nguồn [{'kind','id','label'}], lỗi hoặc None). Nguồn phải là công cụ / mục tri thức THỰC SỰ được gọi
        trong lượt; mọi con số trong câu trả lời phải có trong nguồn (hoặc trong chính tin của khách)."""
        KB = self.env['dmag.ai.knowledge'].sudo()
        ok_tools = {t['tool'] for t in trace if not t.get('error')}
        kb_seen = set()
        for t in trace:
            if t.get('tool') == 'search_knowledge' and isinstance(t.get('output'), dict):
                kb_seen |= {r['id'] for r in t['output'].get('results') or []}
        sources, labels = [], set()
        for src in claimed or []:
            src = str(src).strip()
            if src.startswith('kb:'):
                if src not in kb_seen:
                    return [], _('Nguồn %s không nằm trong kết quả tra cứu của lượt này', src)
                entry = KB.browse(int(src[3:])).exists()
                if not entry:
                    return [], _('Nguồn %s không tồn tại', src)
                item = {'kind': 'kb', 'id': entry.id, 'label': entry._source_label()}
            elif src in TOOL_LABELS or src.startswith('label:'):
                if src in TOOL_LABELS and src not in ok_tools:
                    return [], _('Công cụ %s không được gọi trong lượt này', src)
                item = {'kind': 'tool', 'id': src, 'label': src[6:] if src.startswith('label:') else TOOL_LABELS[src]}
            else:
                return [], _('Nguồn không hợp lệ: %s', src)
            if item['label'] not in labels:
                labels.add(item['label'])
                sources.append(item)
        if not sources:
            return [], _('Câu trả lời không nêu nguồn dữ liệu')
        source_text = ' '.join([json.dumps(t.get('output'), ensure_ascii=False, default=str) for t in trace]
                               + [json.dumps(t.get('input'), ensure_ascii=False, default=str) for t in trace]
                               + list(extra_texts) + [customer_text or '', FIXED_PHRASES])
        allowed = numbers_in(source_text, parts=True)
        bad = sorted(numbers_in(answer) - allowed)
        if bad:
            return [], _('Câu trả lời có số liệu không có trong nguồn: %s', ', '.join(str(n) for n in bad[:5]))
        return sources, None

    # ------------------------------------------------------------------ ngoài dữ liệu → báo lễ tân đang trực
    def _out_of_data(self, text, question, reason, note, res=None, draft=None):
        self.ensure_one()
        Gap = self.env['dmag.ai.kb.gap'].sudo()
        gap = Gap.create({
            'name': (text or '')[:80], 'question': text, 'company_id': self.company_id.id, 'conversation_id': self.id,
            'question_message_id': question.id if question else False, 'reason': reason, 'reason_note': (note or '')[:250]})
        gap._assign_and_notify()
        res = res or {}
        cost = {'cost_vnd': res.get('cost_vnd') or 0, 'estimated_cost_vnd': res.get('estimated_cost_vnd') or 0,
                'log_id': res.get('log_id'), 'model': res.get('model'), 'simulated': res.get('simulated', True),
                'tool_trace': res.get('tool_trace') or []}
        who = gap.assigned_user_id.name or _('nhân viên phụ trách')
        decision_note = _('Ngoài dữ liệu đã nạp → đã báo lễ tân %(who)s (%(why)s)', who=who, why=note or '')
        if draft:
            # nháp của AI bị chặn vì số liệu không có nguồn – để nhân viên sửa / duyệt
            self._create_reply(dict(cost, text=draft), 'pending', 'blocked_unverified', question,
                               note=note, extra={'gap_id': gap.id})
            cost = {}
        holding = (self.company_id.dmag_ai_grounded_holding or '').strip() or DEFAULT_HOLDING
        last_out = self.message_line_ids.filtered(lambda m: m.role in ('bot', 'staff', 'system')
                                                  and m.state in ('ready', 'sent', 'mock_sent')).sorted('id')[-1:]
        if last_out and last_out.decision == 'out_of_data' and last_out.body == holding:
            # khách hỏi tiếp câu ngoài dữ liệu: không gửi lặp tin giữ chỗ – chỉ ghi nhận cho nhân viên
            return self._create_reply(dict(cost, text=_('(Đã ghi nhận câu hỏi – chờ lễ tân %s trả lời)', who)),
                                      'received', 'out_of_data', question, note=decision_note, role='system',
                                      extra={'gap_id': gap.id})
        return self._create_reply(dict(cost, text=holding), 'ready', 'out_of_data', question, note=decision_note,
                                  role='system', extra={'gap_id': gap.id})

    # ------------------------------------------------------------------ bộ trả lời giả lập (có nguồn)
    def _grounded_simulate(self, text, meta):
        """Giả lập chế độ "chỉ từ dữ liệu đã nạp" – trả ``{'text', 'data', 'tool_trace'}`` như Claude; ``meta`` nhận
        thêm thông tin cho máy chủ (kịch bản, độ tin cậy, nhãn nguồn, câu nguồn để kiểm tra số liệu)."""
        self.ensure_one()
        Reception = self.env['dmag.ai.reception'].sudo()
        Script = self.env['dmag.ai.reply.script'].sudo()
        KB = self.env['dmag.ai.knowledge'].sudo()
        company = self.company_id
        folded = fold(text)
        trace = []

        def done(answer, sources, grounded=True, needs_staff=False, reason='', **extra):
            meta.update(extra)
            return {'text': answer, 'tool_trace': trace + list(extra.get('trace') or []),
                    'data': {'answer': answer, 'grounded': grounded, 'sources': sources, 'needs_staff': needs_staff,
                             'reason': reason}}

        def out(reason_code, note):
            return done('', [], grounded=False, needs_staff=True, reason=note, kind='out_of_data',
                        reason_code=reason_code, note=note)

        # 1. Luồng đặt lịch (đang dở hoặc khách muốn đặt) – công cụ thật, lịch nháp
        scripts = Script._approved(company)
        ranked = Script.match_local(text, scripts) if scripts else []
        best, confidence, why = ranked[0] if ranked else (Script, 0.0, '')
        threshold = Script.threshold_for(best, company) if best else 0.6
        stage = self._sim_state().get('stage')
        booking = (stage and stage != 'done') or (best and best.flow == 'booking' and confidence >= threshold) or (
            has_any(folded, STRONG_BOOK_WORDS) and not has_any(folded, ['đổi lịch', 'hủy lịch', 'huỷ lịch', 'dời lịch'])) \
            or (extract_date(text, fields.Date.context_today(self)) and (extract_time(text) or has_any(folded, BOOK_WORDS)))
        if booking and not (best and best.flow == 'handoff' and confidence >= threshold):
            res = Reception.simulate_reply(self, text, allowed_tools=BOOKING_TOOLS)
            tools = list(dict.fromkeys(t['tool'] for t in res.get('tool_trace') or [] if not t.get('error')))
            sources = [t for t in tools if t in TOOL_LABELS] or ['label:Luồng đặt lịch chuẩn']
            booking_script = best if best and best.flow == 'booking' else Script
            return done(res['text'], sources, trace=res.get('tool_trace'), quick=(res.get('data') or {}).get(
                'quick_replies'), script=booking_script, confidence=confidence if booking_script else 0.0,
                note=_('Luồng đặt lịch – dữ liệu từ: %s', ' · '.join(TOOL_LABELS.get(t, t) for t in tools) or '-'))

        # 2. Kịch bản đã duyệt
        def from_script(script, conf, note):
            rendered = Reception._render_script(script, self, text)
            if rendered['missing'] and script.flow != 'handoff':
                return out('no_data', _('Kịch bản "%(s)s" thiếu dữ liệu: %(m)s', s=script.name,
                                        m=', '.join(rendered['missing'])))
            entry = KB.search([('script_id', '=', script.id), ('company_id', '=', company.id)], limit=1)
            sources = (['kb:%s' % entry.id] if entry else []) + ['label:%s' % l for l in rendered['source_labels']]
            if not entry:
                sources.insert(0, 'label:%s' % _("Kịch bản '%s'", script.name))
            trace.append({'tool': 'search_knowledge', 'input': {'query': text},
                          'output': {'results': [{'id': 'kb:%s' % entry.id, 'title': script.name,
                                                  'source': entry._source_label() if entry else script.name}]
                                     if entry else []}})
            labels = [_("Kịch bản '%s'", script.name)] + rendered['source_labels']
            if script.flow == 'handoff':
                self._handoff(script.handoff_reason or 'medical_question',
                              _('[%(script)s] %(text)s', script=script.name, text=text[:180]))
                return done(rendered['text'], sources, kind='handoff_script', script=script, confidence=conf,
                            trace=rendered['trace'], quick=rendered['quick'], note=note,
                            source_items=[{'kind': 'script', 'id': script.id, 'label': label} for label in labels])
            return done(rendered['text'], sources, trace=rendered['trace'], quick=rendered['quick'], script=script,
                        confidence=conf, source_texts=[script.answer_template or ''],
                        note=_('Trả lời từ: %s', ' · '.join(labels)))

        if best and confidence >= threshold:
            return from_script(best, confidence, why)
        if Reception.is_medical_question(text):
            return out('medical', _('Câu hỏi chuyên môn – cần bác sĩ / nhân viên trả lời (không chẩn đoán qua tin nhắn)'))
        # 3. Kho tri thức đã duyệt
        hits = KB.search_knowledge(text, company=company, limit=4)
        trace.append({'tool': 'search_knowledge', 'input': {'query': text},
                      'output': {'results': [{'id': 'kb:%s' % h['id'], 'title': h['name'], 'source': h['source_label'],
                                              'content': h['content'], 'score': h['score']} for h in hits]}})
        good = [h for h in hits if h['grounded']]
        if good:
            top = good[0]
            if top['source_type'] == 'script' and top['script_id']:
                script = Script.browse(top['script_id'])
                if script.state == 'approved':
                    trace.pop()
                    return from_script(script, top['score'], _('Kho tri thức: giống kịch bản "%s"', script.name))
            used = [top] + [h for h in good[1:2] if h['score'] >= 0.8 * top['score'] and h['category'] == top['category']
                            and h['source_type'] != 'script']
            body = '\n'.join(_excerpt(h['content'], text) for h in used)
            if len(body) > 1 and body[1].islower():
                body = body[0].lower() + body[1:]
            answer = _('Dạ %s', body)
            answer += _('\nAnh/chị cần em hỗ trợ thêm hoặc giữ chỗ lịch khám không ạ?')
            return done(answer, ['kb:%s' % h['id'] for h in used], source_texts=[h['content'] for h in used],
                        note=_('Trả lời từ: %s', ' · '.join(h['source_label'] for h in used)),
                        quick=[_('Đặt lịch khám'), _('Giờ làm việc')])
        # 4. Giá dịch vụ (bảng giá thật) khi kho chưa có mục phù hợp
        service = Reception._detect_service(folded)
        if service and has_any(folded, PRICE_WORDS):
            res = Reception.tool_search_services(service)
            trace.append({'tool': 'search_services', 'input': {'query': service}, 'output': res})
            found = res.get('services') or []
            if found:
                lines = '\n'.join('• %s: %s' % (s['name'], s['price_text']) for s in found[:4])
                return done(_('Dạ giá niêm yết theo bảng giá của phòng khám:\n%s\nChi phí chính xác bác sĩ sẽ báo sau khi '
                              'khám ạ.', lines), ['search_services'], note=_('Trả lời từ: Bảng giá'))
        # 5. Chào hỏi / cảm ơn (mẫu cố định, không chứa thông tin)
        short = len(folded.split()) <= 6
        if short and has_any(folded, THANKS_WORDS):
            return done(THANKS, ['label:Mẫu cố định'], note=_('Mẫu cảm ơn cố định'))
        if short and has_any(folded, GREET_WORDS):
            return done(GREETING.format(clinic=company.name), ['label:Mẫu cố định'], note=_('Mẫu chào hỏi cố định'),
                        quick=[_('Bảng giá'), _('Giờ làm việc'), _('Đặt lịch khám')])
        near = hits[0] if hits else None
        return out('no_data', _('Không có trong dữ liệu đã nạp%s', _(' (gần nhất: "%(n)s" %(s)s%%)', n=near['name'],
                                                                    s=round(near['score'] * 100)) if near else ''))
