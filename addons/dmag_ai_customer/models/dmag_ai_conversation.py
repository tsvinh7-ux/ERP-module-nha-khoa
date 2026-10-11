"""AI-07 – Hội thoại với khách (Zalo OA / cổng / web / mô phỏng) và tin nhắn."""
import json
import logging
import re
import uuid
from collections import Counter
from datetime import timedelta

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .text_utils import extract_date, extract_time, fold

_logger = logging.getLogger(__name__)

# Gửi tin tư vấn trong hội thoại OA (khách chủ động nhắn). [CẦN XÁC MINH] endpoint/payload theo tài liệu Zalo OA v3.
ZALO_OA_CS_URL = 'https://openapi.zalo.me/v3.0/oa/message/cs'
EMERGENCY_TEMPLATE = ('Phòng khám đã nhận tin và chuyển ngay cho nhân viên trực. Vui lòng gọi hotline %s để được hướng '
                      'dẫn; nếu chảy máu không cầm, sưng lan, sốt cao hoặc khó thở hãy đến cơ sở y tế gần nhất.')
COMPLAINT_ACK = ('Dạ em thành thật xin lỗi vì trải nghiệm chưa tốt của anh/chị. Em đã chuyển ngay cho quản lý chăm sóc '
                 'khách hàng – anh/chị sẽ được liên hệ sớm nhất trong hôm nay ạ.')
HUMAN_ACK = 'Dạ em đã chuyển cho nhân viên tư vấn, anh/chị vui lòng chờ trong giây lát ạ.'
# Soạn nháp chờ duyệt: chỉ công cụ ĐỌC (không giữ chỗ, không chuyển người)
READ_ONLY_TOOLS = {'search_services', 'get_free_slots', 'find_patient_by_phone', 'get_clinic_info'}
DECISIONS = [
    ('script_auto', 'Tự gửi – khớp kịch bản đã duyệt'),
    ('script_flow', 'Tự gửi – luồng đặt lịch của kịch bản'),
    ('handoff_script', 'Tự gửi mẫu an toàn – chuyển nhân viên'),
    ('full_auto', 'Tự gửi – chế độ tự động hoàn toàn'),
    ('staff_review', 'Chờ duyệt – chế độ nhân viên duyệt mọi câu'),
    ('no_match', 'Chờ duyệt – không khớp kịch bản'),
    ('low_confidence', 'Chờ duyệt – độ tin cậy thấp'),
    ('medical', 'Chờ duyệt – câu hỏi chuyên môn'),
    ('complaint', 'Chuyển nhân viên – khiếu nại'),
    ('human_request', 'Chuyển nhân viên – khách yêu cầu'),
    ('emergency', 'Ca khẩn – mẫu an toàn cố định'),
    ('ack', 'Tin báo đã nhận (mẫu cố định)'),
    ('error', 'Trợ lý lỗi – chuyển nhân viên'),
]
AUTO_DECISIONS = ('script_auto', 'script_flow', 'handoff_script', 'full_auto')
ESCALATED_DECISIONS = ('staff_review', 'no_match', 'low_confidence', 'medical', 'complaint', 'human_request',
                       'emergency', 'error')
HANDOFF_REASONS = [
    ('complaint', 'Khiếu nại / bực bội'),
    ('emergency', 'Dấu hiệu khẩn'),
    ('medical_question', 'Câu hỏi chuyên môn'),
    ('human_request', 'Khách muốn gặp nhân viên'),
    ('other', 'Khác'),
]


class DmagAiConversation(models.Model):
    _name = 'dmag.ai.conversation'
    _description = 'Hội thoại trợ lý AI (Zalo OA)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'last_message_at desc, id desc'

    name = fields.Char('Khách', required=True, default='Khách Zalo')
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)
    channel = fields.Selection([
        ('zalo', 'Zalo OA'), ('portal', 'Cổng bệnh nhân'), ('web', 'Website'), ('simulator', 'Mô phỏng Zalo'),
    ], string='Kênh', required=True, default='zalo', index=True)
    external_user_id = fields.Char('Zalo user_id', index=True, help='ID người dùng Zalo theo OA (từ webhook).')
    phone = fields.Char('Số điện thoại')
    partner_id = fields.Many2one('res.partner', string='Bệnh nhân', index=True)
    state = fields.Selection([
        ('bot', 'Trợ lý đang trả lời'),
        ('handoff', 'Cần nhân viên'),
        ('human', 'Nhân viên đang xử lý'),
        ('closed', 'Đã đóng'),
    ], string='Trạng thái', default='bot', required=True, tracking=True, index=True)
    handoff_reason = fields.Selection(HANDOFF_REASONS, string='Lý do chuyển', tracking=True)
    handoff_summary = fields.Char('Tóm tắt cho nhân viên')
    handoff_at = fields.Datetime('Chuyển lúc', readonly=True)
    assigned_user_id = fields.Many2one('res.users', string='Nhân viên phụ trách', tracking=True)
    message_line_ids = fields.One2many('dmag.ai.conversation.message', 'conversation_id', string='Tin nhắn')
    line_count = fields.Integer('Số tin', compute='_compute_counts')
    pending_count = fields.Integer('Tin chờ duyệt', compute='_compute_pending_count', store=True)
    last_message_at = fields.Datetime('Tin cuối lúc', index=True)
    last_message_preview = fields.Char('Tin cuối')
    visit_ids = fields.Many2many('dmag.dental.visit', string='Lịch đã giữ chỗ')
    visit_count = fields.Integer(compute='_compute_counts')
    cost_vnd = fields.Float('Chi phí AI (đ)', compute='_compute_counts', digits=(12, 0))
    estimated_cost_vnd = fields.Float('Chi phí nếu chạy thật (đ)', compute='_compute_counts', digits=(12, 0))
    awaiting_reply = fields.Boolean('Chờ trợ lý trả lời', index=True, copy=False)
    sim_state = fields.Text('Trạng thái bộ trả lời giả lập', copy=False)
    feedback_ids = fields.One2many('dmag.ai.feedback', 'conversation_id', string='Phân loại phản hồi')
    script_id = fields.Many2one('dmag.ai.reply.script', string='Kịch bản đang theo', copy=False,
                                help='Kịch bản đặt lịch đang dẫn hội thoại (các lượt sau tiếp tục luồng giữ chỗ).')

    @api.depends('message_line_ids.state')
    def _compute_pending_count(self):
        for conv in self:
            conv.pending_count = len(conv.message_line_ids.filtered(lambda m: m.state == 'pending'))

    @api.depends('message_line_ids.cost_vnd', 'visit_ids')
    def _compute_counts(self):
        for conv in self:
            lines = conv.message_line_ids
            conv.line_count = len(lines)
            conv.visit_count = len(conv.visit_ids)
            conv.cost_vnd = sum(lines.mapped('cost_vnd'))
            conv.estimated_cost_vnd = sum(lines.mapped('estimated_cost_vnd'))

    # ------------------------------------------------------------------ simulated state
    def _sim_state(self):
        self.ensure_one()
        try:
            return json.loads(self.sim_state or '{}')
        except ValueError:
            return {}

    def _sim_save(self, state):
        self.ensure_one()
        self.sudo().sim_state = json.dumps(state, ensure_ascii=False, default=str)

    # ------------------------------------------------------------------ core
    @api.model
    def _get_or_create(self, channel, external_user_id=None, name=None, phone=None, partner=None):
        domain = [('channel', '=', channel), ('company_id', '=', self.env.company.id), ('state', '!=', 'closed')]
        if external_user_id:
            domain.append(('external_user_id', '=', external_user_id))
        elif partner:
            domain.append(('partner_id', '=', partner.id))
        conv = self.sudo().search(domain, limit=1) if (external_user_id or partner) else self.browse()
        if not conv:
            conv = self.sudo().create({
                'channel': channel, 'external_user_id': external_user_id,
                'name': name or (partner.name if partner else _('Khách Zalo')),
                'phone': phone or (partner.mobile if partner else False),
                'partner_id': partner.id if partner else False,
            })
        return conv

    def _history_for_ai(self, limit=20):
        """Lịch sử hội thoại cho Claude (bỏ tin cuối – là lượt hiện tại), gộp các lượt cùng vai trò."""
        self.ensure_one()
        lines = self.message_line_ids.filtered(lambda m: m.role in ('customer', 'bot', 'staff') and m.state != 'discarded')
        lines = lines.sorted('id')[:-1][-limit:]
        history = []
        for line in lines:
            role = 'user' if line.role == 'customer' else 'assistant'
            text = line.body if line.role != 'staff' else _('(Nhân viên) %s', line.body)
            if history and history[-1]['role'] == role:
                history[-1]['content'] += '\n' + text
            else:
                history.append({'role': role, 'content': text})
        while history and history[0]['role'] != 'user':
            history.pop(0)
        return history

    def receive_customer_message(self, text, auto_reply=True, defer=False):
        """Ghi tin của khách; nếu hội thoại đang do trợ lý xử lý → AI trả lời (giả lập hoặc Claude)."""
        self.ensure_one()
        text = (text or '').strip()
        if not text:
            raise UserError(_('Tin nhắn trống.'))
        Msg = self.env['dmag.ai.conversation.message'].sudo()
        customer = Msg.create({'conversation_id': self.id, 'role': 'customer', 'body': text, 'state': 'received'})
        self.sudo().write({'last_message_at': fields.Datetime.now(), 'last_message_preview': text[:120]})
        if self.state != 'bot' or not auto_reply:
            if self.state in ('handoff', 'human'):
                self._notify_staff(_('Khách nhắn thêm: %s', text[:200]))
            return {'customer_message_id': customer.id, 'reply': False}
        if defer:
            # webhook phải trả lời Zalo nhanh: gọi Claude ở tác vụ nền
            self.sudo().awaiting_reply = True
            self.env.ref('dmag_ai_customer.ir_cron_dmag_ai_zalo_reply')._trigger()
            return {'customer_message_id': customer.id, 'reply': False, 'deferred': True}
        reply = self._ai_reply(text, customer)
        self.env['dmag.ai.feedback'].sudo()._auto_from_message(customer)
        return {'customer_message_id': customer.id, 'reply': reply.read_for_ui()[0] if reply else False}

    def _reply_mode(self):
        """Chế độ gửi áp cho kênh Zalo OA và Mô phỏng Zalo: approve | script | auto."""
        self.ensure_one()
        if self.channel not in ('zalo', 'simulator'):
            return 'auto'
        return self.company_id.dmag_ai_zalo_reply_mode or 'script'

    def _run_responder(self, text, allowed_tools=None):
        """Bộ trả lời AI-07 (giả lập hoặc Claude + công cụ). ``allowed_tools`` giới hạn công cụ (None = tất cả)."""
        self.ensure_one()
        Reception = self.env['dmag.ai.reception'].sudo()
        conv = self.sudo()
        patient = conv.partner_id if conv.partner_id and conv.partner_id.is_patient else None
        history = conv._history_for_ai()
        user_text = text
        if history and history[-1]['role'] == 'user':  # tin khách chưa được trả lời → gộp vào lượt hiện tại
            user_text = history.pop()['content'] + '\n' + text
        return self.env['dmag.ai'].sudo().run(
            'AI-07', Reception._system_prompt(), user_text,
            history=history,
            tools=Reception.get_tools(allowed_tools),
            tool_handlers=Reception._handlers(conv, allowed_tools),
            simulate=lambda: Reception.simulate_reply(conv, text, allowed_tools=allowed_tools),
            record=conv, patient=patient, pii=[conv.phone] if conv.phone else None,
            max_tokens=4000)

    def _create_reply(self, res, state, decision, question=None, script=None, confidence=0.0, note='',
                      role='bot', extra=None):
        """Ghi câu trả lời của trợ lý (kèm quyết định: khớp kịch bản nào / vì sao chuyển nhân viên) rồi gửi nếu được."""
        self.ensure_one()
        Reception = self.env['dmag.ai.reception'].sudo()
        res = res or {}
        data = res.get('data') or {}
        quick = res.get('quick')
        if quick is None:
            quick = data.get('quick_replies') if isinstance(data, dict) else None
        if quick is None:
            quick = Reception._quick_replies_from_trace(res.get('tool_trace'))
        visit_ids = [t['output'].get('visit_id') for t in res.get('tool_trace') or []
                     if t.get('tool') == 'book_appointment' and isinstance(t.get('output'), dict)
                     and t['output'].get('visit_id')]
        vals = {
            'conversation_id': self.id, 'role': role, 'body': res.get('text') or '…', 'state': state,
            'tool_trace': Reception.dumps(res.get('tool_trace') or []),
            'quick_replies': Reception.dumps(quick or []),
            'simulated': res.get('simulated', self.company_id.dmag_ai_mode != 'live'), 'model': res.get('model'),
            'cost_vnd': res.get('cost_vnd') or 0, 'estimated_cost_vnd': res.get('estimated_cost_vnd') or 0,
            'log_id': res.get('log_id'), 'visit_id': visit_ids[-1] if visit_ids else False,
            'decision': decision, 'script_id': script.id if script else False, 'match_confidence': confidence,
            'decision_note': (note or '')[:250], 'question_id': question.id if question else False,
            'reply_mode': self._reply_mode(),
        }
        vals.update(extra or {})
        reply = self.env['dmag.ai.conversation.message'].sudo().create(vals)
        self.sudo().write({'last_message_at': fields.Datetime.now(), 'last_message_preview': reply.body[:120]})
        if state == 'ready':
            reply._deliver()
        return reply

    def _ai_reply(self, text, question=None):
        self.ensure_one()
        conv = self.sudo()
        mode = conv._reply_mode()
        try:
            if mode == 'script':
                return conv._script_reply(text, question)
            res = conv._run_responder(text)
        except UserError as e:
            # Tính năng tắt / hết ngân sách / lỗi API → chuyển nhân viên, không im lặng với khách
            conv._handoff('other', _('Trợ lý không trả lời được: %s', e))
            return self.env['dmag.ai.conversation.message'].sudo().create({
                'conversation_id': conv.id, 'role': 'system', 'state': 'received', 'decision': 'error',
                'question_id': question.id if question else False,
                'body': _('Trợ lý AI không trả lời được (%s). Đã chuyển nhân viên.', e)})
        needs_approval = mode == 'approve'
        decision = 'staff_review' if needs_approval else 'full_auto'
        reply = conv._create_reply(res, 'pending' if needs_approval else 'ready', decision, question,
                                   note=_('Chế độ "Nhân viên duyệt mọi câu"') if needs_approval else
                                   _('Chế độ "Tự động hoàn toàn"'))
        if needs_approval and conv.state == 'handoff' and conv.handoff_reason == 'emergency':
            # Ca khẩn: không chờ duyệt – gửi ngay câu trả lời an toàn theo mẫu cố định
            conv._send_emergency_template(question)
        return reply

    def _send_emergency_template(self, question=None, note=''):
        return self._create_reply({'text': EMERGENCY_TEMPLATE % (self.company_id.phone or _('của phòng khám'))},
                                  'ready', 'emergency', question, note=note or _('Dấu hiệu khẩn – mẫu an toàn cố định'),
                                  role='system')

    def _send_ack(self, question, decision, note):
        """Tin báo đã nhận (mẫu cố định) khi câu hỏi được chuyển nhân viên – gửi một lần mỗi đợt chờ."""
        ack = (self.company_id.dmag_ai_escalation_ack or '').strip()
        last_out = self.message_line_ids.filtered(lambda m: m.role in ('bot', 'staff', 'system')
                                                  and m.state in ('ready', 'sent', 'mock_sent')).sorted('id')[-1:]
        if not ack or (last_out and last_out.decision == 'ack'):
            return False
        return self._create_reply({'text': ack}, 'ready', 'ack', question, note=note, role='system')

    def _script_reply(self, text, question=None):
        """Chế độ "Tự động theo kịch bản đã duyệt": chỉ TỰ GỬI khi khớp kịch bản (độ tin cậy ≥ ngưỡng); còn lại
        soạn nháp chờ nhân viên duyệt / chuyển nhân viên. Ca khẩn: mẫu an toàn cố định gửi ngay."""
        self.ensure_one()
        Reception = self.env['dmag.ai.reception'].sudo()
        Script = self.env['dmag.ai.reply.script'].sudo()
        company = self.company_id
        live = company.dmag_ai_mode == 'live'
        safety = Reception.safety_precheck(text)
        if safety == 'emergency':
            self._handoff('emergency', text[:200])
            return self._send_emergency_template(question, _('Từ khóa khẩn cấp – chuyển nhân viên trực ngay'))
        if safety in ('complaint', 'human_request'):
            self._handoff(safety, text[:200])
            label = _('Khiếu nại / bực bội') if safety == 'complaint' else _('Khách muốn gặp nhân viên')
            return self._create_reply({'text': COMPLAINT_ACK if safety == 'complaint' else HUMAN_ACK}, 'ready',
                                      safety, question, note=_('%s – chuyển nhân viên, không tự trả lời', label),
                                      role='system')
        scripts = Script._approved(company)
        threshold = company.dmag_ai_script_threshold or 0.6
        best, confidence, note, classify = Script, 0.0, '', None
        ranked = Script.match_local(text, scripts) if scripts else []
        if live and scripts:
            classify = Reception.classify_live(self, text, scripts)
            if classify['safety'] == 'emergency':
                self._handoff('emergency', text[:200])
                return self._send_emergency_template(question, _('Claude nhận diện dấu hiệu khẩn'))
            if classify['safety'] == 'complaint':
                self._handoff('complaint', text[:200])
                return self._create_reply({'text': COMPLAINT_ACK}, 'ready', 'complaint', question,
                                          note=_('Claude nhận diện khiếu nại'), role='system')
            best = Script.browse(classify['script_id'])
            confidence = classify['confidence']
            note = _('Claude: %s', classify['reason'] or '-')
        elif ranked:
            best, confidence, note = ranked[0]
        cost = {}
        if classify:
            cost = {'cost_vnd': classify['res'].get('cost_vnd') or 0,
                    'estimated_cost_vnd': classify['res'].get('estimated_cost_vnd') or 0}
        # đang trong luồng đặt lịch của kịch bản → tiếp tục (trừ khi tin mới khớp rõ kịch bản mẫu khác)
        flow_script = self.script_id if self.script_id and self.script_id.state == 'approved' else Script
        switch = best and best != flow_script and confidence >= Script.threshold_for(best, company)
        medical = Reception.is_medical_question(text)
        if flow_script and not switch and not (medical and best != flow_script):
            return self._script_flow_reply(text, question, flow_script, confidence if best == flow_script else 0.0,
                                           _('Tiếp tục luồng "%s" đang dở', flow_script.name), cost)
        if best and confidence >= Script.threshold_for(best, company):
            best._mark_used()
            if best.flow == 'booking':
                return self._script_flow_reply(text, question, best, confidence, note, cost, start=True)
            rendered = Reception._render_script(best, self, text)
            body, extra_res = rendered['text'], None
            if live and best.allow_rephrase:
                body, extra_res = Reception.rephrase_live(self, body)
                if extra_res:
                    cost = {'cost_vnd': cost.get('cost_vnd', 0) + (extra_res.get('cost_vnd') or 0),
                            'estimated_cost_vnd': cost.get('estimated_cost_vnd', 0)
                            + (extra_res.get('estimated_cost_vnd') or 0)}
            res = {'text': body, 'tool_trace': rendered['trace'], 'quick': rendered['quick'],
                   'simulated': not live, 'model': classify['res'].get('model') if classify else
                   _('Mẫu đã duyệt (không gọi AI)'), 'log_id': classify['res'].get('log_id') if classify else False}
            res.update(cost)
            if best.flow == 'handoff':
                reply = self._create_reply(res, 'ready', 'handoff_script', question, best, confidence, note)
                self._handoff(best.handoff_reason or 'medical_question',
                              _('[%(script)s] %(text)s', script=best.name, text=text[:180]))
                return reply
            return self._create_reply(res, 'ready', 'script_auto', question, best, confidence, note)
        # Không khớp / tin cậy thấp → soạn nháp (chỉ công cụ đọc) chờ nhân viên duyệt
        if best and confidence >= 0.25:
            decision = 'low_confidence'
            why = _('Độ tin cậy %(conf)s%% < ngưỡng %(thr)s%% (gần nhất: "%(name)s" – %(note)s)',
                    conf=round(confidence * 100), thr=round(Script.threshold_for(best, company) * 100),
                    name=best.name, note=note)
        else:
            decision = 'no_match'
            why = _('Không khớp kịch bản đã duyệt nào') if scripts else _('Chưa có kịch bản nào được Giám đốc duyệt')
            best = Script
        if classify and not best:
            why = '%s (%s)' % (why, note)
        if medical:
            decision, why = 'medical', _('Câu hỏi chuyên môn – cần nhân viên / bác sĩ trả lời. %s', why)
        draft = self._run_responder(text, allowed_tools=READ_ONLY_TOOLS)
        draft = dict(draft, cost_vnd=(draft.get('cost_vnd') or 0) + cost.get('cost_vnd', 0),
                     estimated_cost_vnd=(draft.get('estimated_cost_vnd') or 0) + cost.get('estimated_cost_vnd', 0))
        reply = self._create_reply(draft, 'pending', decision, question, best, confidence, why)
        self._send_ack(question, decision, why)
        self._notify_staff(_('Trợ lý chờ duyệt câu trả lời: %(why)s – khách hỏi: %(q)s', why=why, q=text[:150]))
        return reply

    def _script_flow_reply(self, text, question, script, confidence, note, cost=None, start=False):
        """Kịch bản đặt lịch: luồng giữ chỗ chuẩn với ĐÚNG các công cụ kịch bản cho phép (lịch tạo ở trạng thái nháp).
        Lượt đầu chưa nêu ngày → gửi nguyên mẫu đã duyệt (kèm giờ trống thật)."""
        Reception = self.env['dmag.ai.reception'].sudo()
        live = self.company_id.dmag_ai_mode == 'live'
        allowed = set(script.tool_ids.mapped('code'))
        self.sudo().script_id = script
        today = fields.Date.context_today(self)
        if start and not extract_date(text, today) and not extract_time(text):
            rendered = Reception._render_script(script, self, text)
            res = {'text': rendered['text'], 'tool_trace': rendered['trace'], 'quick': rendered['quick'],
                   'simulated': not live, 'model': _('Mẫu đã duyệt (không gọi AI)')}
            res.update(cost or {})
            state = self._sim_state()
            state.setdefault('stage', 'collect')
            self._sim_save(state)
            return self._create_reply(res, 'ready', 'script_auto', question, script, confidence, note)
        res = self._run_responder(text, allowed_tools=allowed)
        if cost:
            res = dict(res, cost_vnd=(res.get('cost_vnd') or 0) + cost.get('cost_vnd', 0),
                       estimated_cost_vnd=(res.get('estimated_cost_vnd') or 0) + cost.get('estimated_cost_vnd', 0))
        booked = any(t.get('tool') == 'book_appointment' and isinstance(t.get('output'), dict)
                     and t['output'].get('booked') for t in res.get('tool_trace') or [])
        if booked or self._sim_state().get('stage') in (None, 'done'):
            self.sudo().script_id = False
        return self._create_reply(res, 'ready', 'script_flow', question, script, confidence, note)

    @api.model
    def _cron_reply_pending(self, limit=30):
        for conv in self.sudo().search([('awaiting_reply', '=', True)], limit=limit):
            conv.awaiting_reply = False
            last = conv.message_line_ids.filtered(lambda m: m.role == 'customer').sorted('id')[-1:]
            if conv.state == 'bot' and last:
                conv.with_company(conv.company_id)._ai_reply(last.body, last)
                self.env['dmag.ai.feedback'].sudo()._auto_from_message(last)
            if not self.env.registry.in_test_mode():
                self.env.cr.commit()  # mỗi hội thoại một giao dịch
        return True

    def _handoff(self, reason, summary):
        for conv in self.sudo():
            conv.write({'state': 'handoff', 'handoff_reason': reason if reason in dict(HANDOFF_REASONS) else 'other',
                        'handoff_summary': (summary or '')[:250], 'handoff_at': fields.Datetime.now()})
            conv._notify_staff(_('Trợ lý AI chuyển hội thoại – %(reason)s: %(summary)s',
                                 reason=dict(HANDOFF_REASONS).get(reason, reason), summary=summary or ''),
                               urgent=reason in ('emergency', 'complaint'))
            if reason == 'complaint':
                self.env['dmag.ai.feedback'].sudo()._create_from_text(
                    summary or conv.last_message_preview or '', source='conversation', conversation=conv,
                    partner=conv.partner_id)
        return True

    def _notify_staff(self, summary, urgent=False):
        self.ensure_one()
        rule = self.env['dmag.journey.rule'].sudo()
        user = self.assigned_user_id or rule._dmag_responsible_user('cskh', None, self.company_id)
        existing = self.activity_ids.filtered(lambda a: a.user_id == user)
        if existing:
            existing[:1].sudo().write({'note': summary})
            return existing[:1]
        return self.sudo().activity_schedule(
            'dmag_dental_journey.activity_type_complaint' if urgent else 'dmag_dental_journey.activity_type_cskh_call',
            date_deadline=fields.Date.context_today(self),
            summary=(_('KHẨN – ') if urgent else '') + _('Hội thoại Zalo: %s', self.name),
            note=summary, user_id=user.id)

    # ------------------------------------------------------------------ actions (lễ tân)
    def action_take_over(self):
        self.write({'state': 'human', 'assigned_user_id': self.env.uid})
        return True

    def action_back_to_bot(self):
        self.write({'state': 'bot', 'handoff_reason': False, 'handoff_summary': False})
        self.activity_ids.action_feedback(feedback=_('Trả hội thoại về trợ lý AI.'))
        return True

    def action_close(self):
        self.write({'state': 'closed'})
        self.activity_ids.action_feedback(feedback=_('Đóng hội thoại.'))
        return True

    def staff_reply(self, text):
        """Nhân viên trả lời khách (gửi qua kênh Zalo nếu có)."""
        self.ensure_one()
        text = (text or '').strip()
        if not text:
            raise UserError(_('Tin nhắn trống.'))
        last_question = self.message_line_ids.filtered(lambda m: m.role == 'customer').sorted('id')[-1:]
        msg = self.env['dmag.ai.conversation.message'].create({
            'conversation_id': self.id, 'role': 'staff', 'body': text, 'state': 'ready',
            'author_id': self.env.uid, 'question_id': last_question.id})
        if self.state in ('bot', 'handoff'):
            self.write({'state': 'human', 'assigned_user_id': self.env.uid})
        self.write({'last_message_at': fields.Datetime.now(), 'last_message_preview': text[:120]})
        msg._deliver()
        return msg.read_for_ui()[0]

    # ------------------------------------------------------------------ data for OWL
    def get_thread(self):
        self.ensure_one()
        return {
            'id': self.id, 'name': self.name, 'channel': self.channel, 'state': self.state,
            'state_label': dict(self._fields['state'].selection)[self.state],
            'handoff_reason': dict(HANDOFF_REASONS).get(self.handoff_reason, ''),
            'handoff_summary': self.handoff_summary or '', 'phone': self.phone or '',
            'partner': {'id': self.partner_id.id, 'name': self.partner_id.name,
                        'code': self.partner_id.patient_code or ''} if self.partner_id else False,
            'messages': self.message_line_ids.sorted('id').read_for_ui(),
            'visits': [self._visit_card(v) for v in self.visit_ids.sorted('id')],
            'cost_vnd': self.cost_vnd, 'estimated_cost_vnd': self.estimated_cost_vnd,
            'reply_mode': self._reply_mode(),
            'flow_script': self.script_id.name or '',
            'feedback': [{'id': f.id, 'topic': f.topic_label, 'severity': f.severity, 'sentiment': f.sentiment,
                          'churn_risk': f.churn_risk, 'suggested_action': f.suggested_action or ''}
                         for f in self.feedback_ids],
        }

    @api.model
    def _visit_card(self, visit):
        visit = visit.sudo()
        start = fields.Datetime.context_timestamp(self, visit.scheduled_start) if visit.scheduled_start else False
        return {
            'id': visit.id, 'name': visit.name, 'state': visit.state,
            'state_label': dict(visit._fields['state'].selection).get(visit.state),
            'patient': visit.patient_id.name, 'patient_code': visit.patient_id.patient_code or '',
            'time': start.strftime('%H:%M') if start else '', 'date': start.strftime('%d/%m/%Y') if start else '',
            'doctor': visit.doctor_id.name or '', 'chair': visit.chair_id.name or '',
            'services': visit.service_ids.mapped('name'),
            'is_today': bool(start and start.date() == fields.Date.context_today(self)),
        }

    @api.model
    def get_inbox(self, filter_key='attention'):
        domain = [('company_id', 'in', self.env.companies.ids)]
        if filter_key == 'attention':
            domain += ['|', ('state', 'in', ('handoff', 'human')), ('pending_count', '>', 0)]
        elif filter_key == 'bot':
            domain += [('state', '=', 'bot')]
        elif filter_key == 'closed':
            domain += [('state', '=', 'closed')]
        convs = self.search(domain, limit=80)
        counts = {
            'attention': self.search_count([('company_id', 'in', self.env.companies.ids), '|',
                                            ('state', 'in', ('handoff', 'human')), ('pending_count', '>', 0)]),
            'bot': self.search_count([('company_id', 'in', self.env.companies.ids), ('state', '=', 'bot')]),
        }
        return {
            'counts': counts,
            'mode': self.env.company.dmag_ai_mode,
            'reply_mode': self.env.company.dmag_ai_zalo_reply_mode,
            'conversations': [{
                'id': c.id, 'name': c.name, 'channel': c.channel, 'state': c.state,
                'state_label': dict(c._fields['state'].selection)[c.state],
                'handoff_reason': dict(HANDOFF_REASONS).get(c.handoff_reason, ''),
                'preview': c.last_message_preview or '', 'pending': c.pending_count, 'visits': c.visit_count,
                'last': fields.Datetime.to_string(c.last_message_at) if c.last_message_at else '',
            } for c in convs],
        }

    # ------------------------------------------------------------------ thống kê kịch bản
    @api.model
    def get_script_stats(self, days=30):
        """Tỷ lệ tự trả lời / chuyển nhân viên và các câu hỏi CHƯA khớp kịch bản nhiều nhất (để thành kịch bản mới)."""
        since = fields.Datetime.now() - timedelta(days=int(days or 30))
        Msg = self.env['dmag.ai.conversation.message']
        domain = [('company_id', 'in', self.env.companies.ids), ('create_date', '>=', since),
                  ('conversation_id.channel', 'in', ('zalo', 'simulator')), ('decision', '!=', False),
                  ('decision', '!=', 'ack')]
        msgs = Msg.search(domain)
        total = len(msgs)
        auto = len(msgs.filtered(lambda m: m.decision in AUTO_DECISIONS))
        escalated = len(msgs.filtered(lambda m: m.decision in ESCALATED_DECISIONS))
        by_script = Counter(m.script_id.name for m in msgs if m.script_id and m.decision in AUTO_DECISIONS)
        unmatched = msgs.filtered(lambda m: m.decision in ('no_match', 'low_confidence', 'medical', 'staff_review'))
        groups = {}
        for m in unmatched:
            q = m.question_id.body if m.question_id else ''
            if not q:
                continue
            key = ' '.join(sorted(set(re.findall(r'[a-z0-9]{3,}', fold(q)))))[:80] or fold(q)
            item = groups.setdefault(key, {'question': q, 'count': 0, 'message_id': m.id,
                                           'decision': dict(DECISIONS).get(m.decision, ''),
                                           'promotable': False})
            item['count'] += 1
            if m.state in ('sent', 'mock_sent', 'ready') and m._is_promotable():
                item['message_id'], item['promotable'] = m.id, True
        top = sorted(groups.values(), key=lambda g: (-g['count'], g['question']))[:8]
        Script = self.env['dmag.ai.reply.script']
        return {
            'days': int(days or 30), 'total': total, 'auto': auto, 'escalated': escalated,
            'auto_pct': round(auto * 100.0 / total) if total else 0,
            'escalated_pct': round(escalated * 100.0 / total) if total else 0,
            'top_scripts': [{'name': n, 'count': c} for n, c in by_script.most_common(5)],
            'top_unmatched': top,
            'scripts_approved': Script.search_count([('state', '=', 'approved'),
                                                     ('company_id', 'in', self.env.companies.ids)]),
            'scripts_draft': Script.search_count([('state', '=', 'draft'),
                                                  ('company_id', 'in', self.env.companies.ids)]),
            'examples_draft': self.env['dmag.ai.reply.example'].search_count([
                ('state', '=', 'draft'), ('company_id', 'in', self.env.companies.ids)]),
            'reply_mode': self.env.company.dmag_ai_zalo_reply_mode,
            'threshold': round((self.env.company.dmag_ai_script_threshold or 0.6) * 100),
        }

    # ------------------------------------------------------------------ simulator
    @api.model
    def simulator_start(self, partner_id=False, name=False, phone=False):
        """Mở một hội thoại mô phỏng mới (người dùng Odoo đóng vai khách nhắn Zalo OA)."""
        partner = self.env['res.partner'].browse(partner_id) if partner_id else None
        conv = self.sudo().create({
            'channel': 'simulator', 'external_user_id': 'sim-%s' % uuid.uuid4().hex[:10],
            'name': (partner.name if partner else name) or _('Khách mô phỏng'),
            'phone': (partner.mobile if partner else phone) or False,
            'partner_id': partner.id if partner else False,
        })
        return conv.get_thread()

    def simulator_send(self, text):
        self.ensure_one()
        self.receive_customer_message(text)
        return self.get_thread()


class DmagAiConversationMessage(models.Model):
    _name = 'dmag.ai.conversation.message'
    _description = 'Tin nhắn hội thoại trợ lý AI'
    _order = 'id'

    conversation_id = fields.Many2one('dmag.ai.conversation', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='conversation_id.company_id', store=True, index=True)
    role = fields.Selection([('customer', 'Khách'), ('bot', 'Trợ lý AI'), ('staff', 'Nhân viên'), ('system', 'Hệ thống')],
                            string='Vai trò', required=True)
    body = fields.Text('Nội dung', required=True)
    state = fields.Selection([
        ('received', 'Đã nhận'), ('pending', 'Chờ nhân viên duyệt'), ('ready', 'Hiển thị'),
        ('sent', 'Đã gửi Zalo'), ('mock_sent', 'Đã gửi (giả lập)'), ('failed', 'Gửi lỗi'), ('discarded', 'Bỏ'),
    ], string='Trạng thái', default='ready', required=True, index=True)
    author_id = fields.Many2one('res.users', string='Nhân viên')
    approved_by_id = fields.Many2one('res.users', string='Người duyệt', readonly=True)
    tool_trace = fields.Text('Công cụ đã gọi (JSON)')
    quick_replies = fields.Text('Gợi ý trả lời nhanh (JSON)')
    simulated = fields.Boolean('Giả lập')
    model = fields.Char('Mô hình')
    cost_vnd = fields.Float('Chi phí (đ)', digits=(12, 0))
    estimated_cost_vnd = fields.Float('Chi phí nếu chạy thật (đ)', digits=(12, 0))
    log_id = fields.Many2one('dmag.ai.log', string='Nhật ký AI', readonly=True)
    visit_id = fields.Many2one('dmag.dental.visit', string='Lịch tạo ra')
    send_error = fields.Char('Lỗi gửi')
    # Quyết định của trợ lý (chế độ theo kịch bản đã duyệt)
    reply_mode = fields.Selection([('approve', 'Nhân viên duyệt mọi câu'), ('script', 'Theo kịch bản đã duyệt'),
                                   ('auto', 'Tự động hoàn toàn')], string='Chế độ lúc trả lời', readonly=True)
    decision = fields.Selection(DECISIONS, string='Quyết định của trợ lý', readonly=True, index=True)
    script_id = fields.Many2one('dmag.ai.reply.script', string='Kịch bản', readonly=True, index=True)
    match_confidence = fields.Float('Độ tin cậy khớp kịch bản', readonly=True, digits=(3, 2))
    decision_note = fields.Char('Lý do', readonly=True)
    question_id = fields.Many2one('dmag.ai.conversation.message', string='Câu hỏi của khách', readonly=True)
    edited = fields.Boolean('Nhân viên đã sửa', readonly=True)
    original_body = fields.Text('Nội dung trợ lý soạn ban đầu', readonly=True)
    promoted_script_id = fields.Many2one('dmag.ai.reply.script', string='Đã đề xuất thành kịch bản', readonly=True)
    promoted_example_id = fields.Many2one('dmag.ai.reply.example', string='Đã thêm làm ví dụ', readonly=True)

    def read_for_ui(self):
        res = []
        for m in self:
            try:
                trace = json.loads(m.tool_trace or '[]')
            except ValueError:
                trace = []
            try:
                quick = json.loads(m.quick_replies or '[]')
            except ValueError:
                quick = []
            res.append({
                'id': m.id, 'role': m.role, 'body': m.body, 'state': m.state,
                'state_label': dict(m._fields['state'].selection)[m.state],
                'time': fields.Datetime.context_timestamp(m, m.create_date).strftime('%H:%M') if m.create_date else '',
                'trace': trace, 'quick': quick, 'simulated': m.simulated, 'model': m.model or '',
                'cost_vnd': m.cost_vnd, 'estimated_cost_vnd': m.estimated_cost_vnd,
                'author': m.author_id.name or '', 'visit_id': m.visit_id.id,
                'decision': m.decision or '', 'decision_label': dict(DECISIONS).get(m.decision, ''),
                'auto': m.decision in AUTO_DECISIONS, 'escalated': m.decision in ESCALATED_DECISIONS,
                'script': {'id': m.script_id.id, 'name': m.script_id.name, 'code': m.script_id.code}
                if m.script_id else False,
                'confidence': round((m.match_confidence or 0.0) * 100), 'decision_note': m.decision_note or '',
                'question': m.question_id.body if m.question_id else '',
                'approved_by': m.approved_by_id.name or '', 'edited': m.edited,
                'promotable': m._is_promotable(),
                'promoted_script': {'id': m.promoted_script_id.id, 'name': m.promoted_script_id.name,
                                    'state': m.promoted_script_id.state} if m.promoted_script_id else False,
                'promoted_example': bool(m.promoted_example_id),
            })
        return res

    # ------------------------------------------------------------------ huấn luyện từ hộp thư
    def _is_promotable(self):
        """Câu trả lời nhân viên đã duyệt / đã sửa / tự viết (đã gửi) có câu hỏi của khách đi kèm."""
        self.ensure_one()
        if self.state not in ('ready', 'sent', 'mock_sent') or not self._question_text():
            return False
        if self.role == 'staff':
            return True
        return self.role == 'bot' and bool(self.approved_by_id or self.edited)

    def _question_text(self):
        self.ensure_one()
        if self.question_id:
            return self.question_id.body
        prev = self.conversation_id.message_line_ids.filtered(lambda m: m.role == 'customer' and m.id < self.id)
        return prev.sorted('id')[-1:].body or ''

    def action_promote_to_script(self):
        """Một chạm: câu trả lời đã duyệt / đã sửa → kịch bản NHÁP (Giám đốc đọc, chỉnh ô dữ liệu, duyệt)."""
        self.ensure_one()
        if not self._is_promotable():
            raise UserError(_('Chỉ đề xuất từ câu trả lời nhân viên đã duyệt / đã sửa / tự viết (có câu hỏi của khách).'))
        if self.promoted_script_id:
            return {'id': self.promoted_script_id.id, 'name': self.promoted_script_id.name}
        question = self._question_text()
        Script = self.env['dmag.ai.reply.script']
        best = Script.match_local(question, Script._approved(self.company_id))[:1]
        category = best[0][0].category if best and best[0][1] >= 0.3 else 'info'
        words = [w for w in re.findall(r'\w+', question)][:8]
        script = Script.sudo().create({
            'name': _('Đề xuất: %s', ' '.join(words)[:60]),
            'code': 'de_xuat_%s' % self.id,
            'company_id': self.company_id.id,
            'category': category,
            'sample_questions': question,
            'answer_template': self.body,
            'proposed_by_id': self.env.uid,
            'source_message_id': self.id,
            'tool_ids': [(6, 0, self.env['dmag.ai.reply.tool'].sudo().search([('side_effect', '=', False)]).ids)],
        })
        script.message_post(body=_('%(user)s đề xuất từ hộp thư (hội thoại %(conv)s). Giám đốc đọc lại, thay số liệu cố định '
                                   'bằng ô dữ liệu ({gia_dich_vu}, {gio_trong}…) rồi duyệt.',
                                   user=self.env.user.name, conv=self.conversation_id.name))
        self.sudo().promoted_script_id = script
        self._notify_directors(script, _('Kịch bản trả lời mới chờ duyệt: %s', script.name))
        return {'id': script.id, 'name': script.name}

    def action_promote_to_example(self, script_id=False):
        """Một chạm: thêm (câu hỏi, câu trả lời đã duyệt) làm ví dụ few-shot cho kịch bản – Giám đốc duyệt."""
        self.ensure_one()
        if not self._is_promotable():
            raise UserError(_('Chỉ thêm ví dụ từ câu trả lời nhân viên đã duyệt / đã sửa / tự viết.'))
        question = self._question_text()
        Script = self.env['dmag.ai.reply.script'].sudo()
        script = Script.browse(int(script_id)).exists() if script_id else self.script_id
        if not script:
            ranked = Script.match_local(question, Script._approved(self.company_id))
            script = ranked[0][0] if ranked and ranked[0][1] >= 0.25 else Script
        if not script:
            raise UserError(_('Không đoán được kịch bản phù hợp – dùng "Đề xuất thành kịch bản" hoặc chọn kịch bản.'))
        example = self.env['dmag.ai.reply.example'].sudo().create({
            'script_id': script.id, 'question': question, 'answer': self.body, 'proposed_by_id': self.env.uid,
            'source_message_id': self.id})
        self.sudo().promoted_example_id = example
        self._notify_directors(script, _('Ví dụ hỏi – đáp mới chờ duyệt cho "%s"', script.name))
        return {'id': example.id, 'script': script.name}

    def _notify_directors(self, script, summary):
        group = self.env.ref('dmag_dental_base.group_dmag_director', raise_if_not_found=False)
        users = group.users.filtered(lambda u: script.company_id in u.company_ids and not u.share
                                     and u.id != self.env.ref('base.user_root').id) if group else []
        for user in users[:1]:
            script.sudo().activity_schedule('mail.mail_activity_data_todo', summary=summary, user_id=user.id,
                                            note=_('Đề xuất bởi %s từ hộp thư trợ lý Zalo.', self.env.user.name))

    def action_approve_send(self):
        """Nhân viên duyệt câu trả lời của trợ lý rồi gửi (chế độ "duyệt trước khi gửi")."""
        for msg in self.filtered(lambda m: m.state == 'pending'):
            msg.write({'approved_by_id': self.env.uid})
            msg._deliver()
        return True

    def action_discard(self):
        self.filtered(lambda m: m.state == 'pending').write({'state': 'discarded'})
        return True

    def approve_and_edit(self, body):
        self.ensure_one()
        if self.state != 'pending':
            raise UserError(_('Tin này không ở trạng thái chờ duyệt.'))
        vals = {'body': body or self.body, 'approved_by_id': self.env.uid}
        if body and body.strip() != (self.body or '').strip():
            vals.update(edited=True, original_body=self.body)
        self.write(vals)
        self._deliver()
        return self.read_for_ui()[0]

    def _deliver(self):
        """Gửi tin trợ lý / nhân viên tới khách qua Zalo OA (chế độ theo cấu hình ZNS của phòng khám)."""
        for msg in self.sudo():
            conv = msg.conversation_id
            if conv.channel != 'zalo' or not conv.external_user_id:
                msg.state = 'ready'
                continue
            mode = conv.company_id.dmag_zns_mode
            if mode == 'mock':
                _logger.info('Zalo OA mock reply → %s: %s', conv.external_user_id, msg.body[:80])
                msg.state = 'mock_sent'
                continue
            try:
                result = msg._send_oa_text(conv, mode)
            except Exception as e:  # mạng / token / bizapps
                msg.write({'state': 'failed', 'send_error': str(e)[:250]})
                continue
            if int(result.get('error', -1)) == 0:
                msg.state = 'sent'
            else:
                msg.write({'state': 'failed', 'send_error': str(result.get('message') or result)[:250]})

    def _send_oa_text(self, conv, mode):
        """[CẦN XÁC MINH] Zalo OA API v3 "tin tư vấn": POST /v3.0/oa/message/cs, header access_token,
        body ``{"recipient": {"user_id": ...}, "message": {"text": ...}}`` – chỉ gửi được trong khung thời gian
        Zalo cho phép sau khi khách nhắn."""
        if mode == 'bizapps':
            model = self.env.get('biz.zalo.oa')
            method = getattr(model.sudo(), 'send_text_message', None) if model is not None else None
            if not method:
                raise UserError(_('Chế độ Bizapps: chưa có hàm gửi tin OA (biz.zalo.oa.send_text_message).'))
            res = method(user_id=conv.external_user_id, text=self.body)
            return res if isinstance(res, dict) else {'error': 0 if res else -1}
        token = conv.company_id._dmag_zalo_get_access_token()
        response = requests.post(ZALO_OA_CS_URL, timeout=20, headers={'access_token': token, 'Content-Type': 'application/json'},
                                 json={'recipient': {'user_id': conv.external_user_id}, 'message': {'text': self.body[:2000]}})
        try:
            return response.json()
        except ValueError:
            return {'error': -2, 'message': 'HTTP %s' % response.status_code}
