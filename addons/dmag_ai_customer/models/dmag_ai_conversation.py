"""AI-07 – Hội thoại với khách (Zalo OA / cổng / web / mô phỏng) và tin nhắn."""
import json
import logging
import uuid

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Gửi tin tư vấn trong hội thoại OA (khách chủ động nhắn). [CẦN XÁC MINH] endpoint/payload theo tài liệu Zalo OA v3.
ZALO_OA_CS_URL = 'https://openapi.zalo.me/v3.0/oa/message/cs'
EMERGENCY_TEMPLATE = ('Phòng khám đã nhận tin và chuyển ngay cho nhân viên trực. Vui lòng gọi hotline %s để được hướng '
                      'dẫn; nếu chảy máu không cầm, sưng lan, sốt cao hoặc khó thở hãy đến cơ sở y tế gần nhất.')
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
        reply = self._ai_reply(text)
        self.env['dmag.ai.feedback'].sudo()._auto_from_message(customer)
        return {'customer_message_id': customer.id, 'reply': reply.read_for_ui()[0] if reply else False}

    def _ai_reply(self, text):
        self.ensure_one()
        Reception = self.env['dmag.ai.reception'].sudo()
        conv = self.sudo()
        patient = conv.partner_id if conv.partner_id and conv.partner_id.is_patient else None
        history = conv._history_for_ai()
        user_text = text
        if history and history[-1]['role'] == 'user':  # tin khách chưa được trả lời → gộp vào lượt hiện tại
            user_text = history.pop()['content'] + '\n' + text
        try:
            res = self.env['dmag.ai'].sudo().run(
                'AI-07', Reception._system_prompt(), user_text,
                history=history,
                tools=Reception.get_tools(),
                tool_handlers=Reception._handlers(conv),
                simulate=lambda: Reception.simulate_reply(conv, text),
                record=conv, patient=patient, pii=[conv.phone] if conv.phone else None,
                max_tokens=4000)
        except UserError as e:
            # Tính năng tắt / hết ngân sách / lỗi API → chuyển nhân viên, không im lặng với khách
            conv._handoff('other', _('Trợ lý không trả lời được: %s', e))
            return self.env['dmag.ai.conversation.message'].sudo().create({
                'conversation_id': conv.id, 'role': 'system', 'state': 'received',
                'body': _('Trợ lý AI không trả lời được (%s). Đã chuyển nhân viên.', e)})
        data = res.get('data') or {}
        quick = data.get('quick_replies') if isinstance(data, dict) else None
        if quick is None:
            quick = Reception._quick_replies_from_trace(res.get('tool_trace'))
        visit_ids = [t['output'].get('visit_id') for t in res.get('tool_trace') or []
                     if t.get('tool') == 'book_appointment' and isinstance(t.get('output'), dict) and t['output'].get('visit_id')]
        needs_approval = conv.channel == 'zalo' and conv.company_id.dmag_ai_zalo_reply_mode == 'approve'
        reply = self.env['dmag.ai.conversation.message'].sudo().create({
            'conversation_id': conv.id, 'role': 'bot', 'body': res.get('text') or '…',
            'state': 'pending' if needs_approval else 'ready',
            'tool_trace': Reception.dumps(res.get('tool_trace') or []),
            'quick_replies': Reception.dumps(quick or []),
            'simulated': res.get('simulated'), 'model': res.get('model'),
            'cost_vnd': res.get('cost_vnd') or 0, 'estimated_cost_vnd': res.get('estimated_cost_vnd') or 0,
            'log_id': res.get('log_id'), 'visit_id': visit_ids[-1] if visit_ids else False,
        })
        conv.write({'last_message_at': fields.Datetime.now(), 'last_message_preview': reply.body[:120]})
        if not needs_approval:
            reply._deliver()
        elif conv.state == 'handoff' and conv.handoff_reason == 'emergency':
            # Ca khẩn: không chờ duyệt – gửi ngay câu trả lời an toàn theo mẫu cố định
            self.env['dmag.ai.conversation.message'].sudo().create({
                'conversation_id': conv.id, 'role': 'system', 'state': 'ready',
                'body': EMERGENCY_TEMPLATE % (conv.company_id.phone or _('của phòng khám')),
            })._deliver()
        return reply

    @api.model
    def _cron_reply_pending(self, limit=30):
        for conv in self.sudo().search([('awaiting_reply', '=', True)], limit=limit):
            conv.awaiting_reply = False
            last = conv.message_line_ids.filtered(lambda m: m.role == 'customer').sorted('id')[-1:]
            if conv.state == 'bot' and last:
                conv.with_company(conv.company_id)._ai_reply(last.body)
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
        msg = self.env['dmag.ai.conversation.message'].create({
            'conversation_id': self.id, 'role': 'staff', 'body': text, 'state': 'ready',
            'author_id': self.env.uid})
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
            })
        return res

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
        self.write({'body': body or self.body, 'approved_by_id': self.env.uid})
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
