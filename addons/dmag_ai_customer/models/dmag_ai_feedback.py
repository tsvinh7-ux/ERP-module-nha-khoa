"""AI-09 – Phân loại phản hồi & khiếu nại (NPS, góp ý, tin nhắn Zalo)."""
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .text_utils import fold, has_any, match_words

_logger = logging.getLogger(__name__)

TOPICS = [
    ('wait_time', 'Thời gian chờ'),
    ('pain', 'Đau / khó chịu sau điều trị'),
    ('result_quality', 'Kết quả điều trị'),
    ('staff_attitude', 'Thái độ nhân viên'),
    ('price', 'Chi phí'),
    ('billing', 'Thanh toán / hóa đơn'),
    ('booking', 'Đặt lịch / liên lạc'),
    ('hygiene', 'Vệ sinh / cơ sở vật chất'),
    ('praise', 'Khen ngợi'),
    ('other', 'Khác'),
]
SEVERITIES = [('low', 'Thấp'), ('medium', 'Trung bình'), ('high', 'Cao'), ('critical', 'Khẩn')]
SEVERITY_RANK = {'low': 1, 'medium': 2, 'high': 3, 'critical': 4}

LEXICON = {
    'wait_time': ['chờ lâu', 'đợi lâu', 'chờ', 'đợi', 'trễ', 'muộn', 'lâu quá', 'trễ hẹn'],
    'pain': ['đau', 'ê buốt', 'nhức', 'sưng', 'chảy máu', 'tê', 'buốt', 'khó chịu'],
    'result_quality': ['bong', 'rơi', 'lệch', 'không đều', 'vẫn đau', 'hỏng', 'bể', 'mẻ', 'không ưng', 'không đẹp',
                       'làm lại', 'sai màu', 'cộm'],
    'staff_attitude': ['thái độ', 'khó chịu', 'cáu', 'gắt', 'bất lịch sự', 'thờ ơ', 'không nhiệt tình', 'hỗn', 'lạnh nhạt'],
    'price': ['đắt', 'giá cao', 'mắc', 'chi phí', 'phát sinh', 'chặt chém', 'tiền'],
    'billing': ['hóa đơn', 'tính sai', 'thu sai', 'hoàn tiền', 'thu thêm', 'trừ tiền'],
    'booking': ['đặt lịch', 'hủy lịch', 'đổi lịch', 'không ai nghe', 'không trả lời', 'gọi mãi', 'nhắn mãi'],
    'hygiene': ['bẩn', 'vệ sinh', 'dụng cụ', 'mùi', 'nhà vệ sinh', 'nóng', 'chật'],
    'praise': ['tốt', 'nhiệt tình', 'chu đáo', 'cảm ơn', 'hài lòng', 'tuyệt vời', 'nhẹ nhàng', 'không đau', 'tận tâm',
               'dễ thương', 'chuyên nghiệp', 'ưng', 'đẹp'],
}
NEGATIVE = ['không hài lòng', 'tệ', 'thất vọng', 'bực', 'kém', 'chán', 'không ưng', 'đau', 'lâu', 'đắt', 'sai',
            'khó chịu', 'không chuyên nghiệp', 'quá', 'lừa', 'phàn nàn', 'khiếu nại', 'hỏng', 'bong']
CRITICAL = ['chảy máu nhiều', 'chảy máu không cầm', 'sưng to', 'sưng mặt', 'sốt', 'nhiễm trùng', 'mủ', 'kiện', 'báo chí',
            'sở y tế', 'bóc phốt', '1 sao', 'một sao', 'tố cáo', 'khó thở']
CHURN = ['không quay lại', 'không bao giờ', 'chuyển phòng khám', 'lần cuối', 'đi chỗ khác', 'không giới thiệu',
         'cạch', 'bỏ điều trị', 'ngưng điều trị', 'hủy kế hoạch']

REPLIES = {
    'wait_time': 'Phòng khám thành thật xin lỗi vì {sal} phải chờ lâu. Chúng tôi đang điều chỉnh lịch hẹn để đúng giờ hơn; '
                 'lần tới lễ tân sẽ báo trước nếu bác sĩ trễ. Mong {sal} thông cảm ạ.',
    'pain': 'Phòng khám rất tiếc {sal} còn khó chịu sau điều trị. Bác sĩ phụ trách sẽ gọi hỏi thăm và hướng dẫn cụ thể '
            'cho {sal} ngay hôm nay; nếu cần, mời {sal} ghé lại để bác sĩ kiểm tra miễn phí ạ.',
    'result_quality': 'Cảm ơn {sal} đã phản hồi. Bác sĩ sẽ liên hệ để hẹn kiểm tra lại và xử lý theo chính sách bảo hành '
                      'của phòng khám ạ.',
    'staff_attitude': 'Phòng khám thành thật xin lỗi về trải nghiệm chưa tốt. Quản lý đã ghi nhận và sẽ trao đổi trực tiếp '
                      'với {sal} trong hôm nay ạ.',
    'price': 'Cảm ơn {sal} đã chia sẻ. Tư vấn viên sẽ gửi {sal} bảng chi phí chi tiết theo từng hạng mục và các lựa chọn '
             'trả góp phù hợp ạ.',
    'billing': 'Phòng khám xin lỗi vì sự bất tiện. Kế toán sẽ kiểm tra lại hóa đơn và phản hồi {sal} trong ngày làm việc ạ.',
    'booking': 'Xin lỗi {sal} vì chưa liên lạc được kịp thời. Lễ tân sẽ gọi lại để sắp xếp lịch phù hợp nhất ạ.',
    'hygiene': 'Cảm ơn {sal} đã góp ý. Phòng khám sẽ kiểm tra và cải thiện ngay khu vực {sal} phản ánh ạ.',
    'praise': 'Cảm ơn {sal} rất nhiều vì lời khen! Phòng khám sẽ chuyển lời đến bác sĩ và ê-kíp ạ.',
    'other': 'Cảm ơn {sal} đã phản hồi. Phòng khám đã ghi nhận và sẽ liên hệ lại nếu cần thêm thông tin ạ.',
}
ACTIONS = {
    'wait_time': 'Lễ tân gọi xin lỗi; kiểm tra lịch bác sĩ ngày đó (xếp chồng ca nặng?).',
    'pain': 'Báo bác sĩ điều trị gọi hỏi thăm trong 2 giờ; hẹn tái khám kiểm tra nếu đau ≥ 7/10.',
    'result_quality': 'Bác sĩ hẹn kiểm tra lại; xem thẻ bảo hành / phiếu labo liên quan.',
    'staff_attitude': 'Quản lý gọi khách trong ngày; trao đổi với nhân viên liên quan.',
    'price': 'Tư vấn viên gửi bảng chi phí chi tiết, đề xuất trả góp / gói chăm sóc.',
    'billing': 'Kế toán đối chiếu hóa đơn – thanh toán, phản hồi trong ngày.',
    'booking': 'Lễ tân gọi lại, kiểm tra cuộc gọi nhỡ / tin Zalo chưa trả lời.',
    'hygiene': 'Quản lý kiểm tra khu vực, ghi nhận vào checklist vệ sinh.',
    'praise': 'Cảm ơn khách, mời đánh giá Google / giới thiệu bạn bè.',
    'other': 'CSKH đọc và phân loại thủ công.',
}

SCHEMA = {
    'type': 'object',
    'properties': {
        'topic': {'type': 'string', 'enum': [t[0] for t in TOPICS]},
        'severity': {'type': 'string', 'enum': [s[0] for s in SEVERITIES]},
        'sentiment': {'type': 'string', 'enum': ['positive', 'neutral', 'negative']},
        'churn_risk': {'type': 'boolean'},
        'summary': {'type': 'string'},
        'suggested_reply': {'type': 'string'},
        'suggested_action': {'type': 'string'},
        'red_flags': {'type': 'array', 'items': {'type': 'string'}},
    },
    'required': ['topic', 'severity', 'sentiment', 'churn_risk', 'summary', 'suggested_reply', 'suggested_action', 'red_flags'],
    'additionalProperties': False,
}
SYSTEM = (
    'Phân loại phản hồi của khách nha khoa (NPS, góp ý, tin nhắn). Chọn chủ đề chính, mức độ nghiêm trọng '
    '(critical: dấu hiệu biến chứng y khoa như chảy máu không cầm, sưng to, sốt, nhiễm trùng – hoặc đe dọa khiếu nại '
    'lên cơ quan / truyền thông; high: khách rất bực hoặc NPS 0–3; medium: không hài lòng; low: góp ý nhẹ / khen), '
    'cảm xúc, nguy cơ rời bỏ. Soạn câu trả lời ngắn, lịch sự (xưng "phòng khám", gọi khách bằng mã đã ẩn danh nếu cần) '
    '– KHÔNG hứa bồi thường, KHÔNG chẩn đoán; và một hành động nội bộ cụ thể (ai làm gì, khi nào). '
    'red_flags: liệt kê dấu hiệu y khoa cần bác sĩ xem (nếu có).'
)


def classify_local(text, score=None):
    """Bộ phân loại tại chỗ theo từ điển – dùng cho chế độ giả lập và khi bệnh nhân chưa đồng ý AI."""
    folded = fold(text)
    hits = {topic: len(match_words(text, words)) for topic, words in LEXICON.items()}
    low = (text or '').lower()
    neg_text = low.replace('không đau', ' ').replace('hết đau', ' ').replace('không lâu', ' ').replace('không phải chờ', ' ')
    negative = bool(match_words(neg_text, NEGATIVE)) or has_any(folded, ['không tốt', 'chưa tốt']) \
        or (score is not None and score <= 6)
    if not match_words(neg_text, LEXICON['pain']):
        hits_pain_off = True
    else:
        hits_pain_off = False
    positive = hits['praise'] > 0 and not negative or (score is not None and score >= 9 and not match_words(neg_text, NEGATIVE))
    if hits_pain_off:
        hits['pain'] = 0
    if negative:
        hits['praise'] = 0
    topic = max(hits, key=lambda t: (hits[t], t != 'praise')) if any(hits.values()) else 'other'
    if not hits.get(topic):
        topic = 'praise' if positive else 'other'
    red_flags = match_words(text, CRITICAL)
    if red_flags:
        severity = 'critical'
    elif (score is not None and score <= 3) or (negative and match_words(text, ['khiếu nại', 'thất vọng', 'quá tệ', 'lừa', 'bực'])):
        severity = 'high'
    elif negative:
        severity = 'medium'
    else:
        severity = 'low'
    sentiment = 'negative' if negative else 'positive' if positive else 'neutral'
    churn = bool(match_words(text, CHURN) or (negative and score is not None and score <= 4))
    medical = [w for w in red_flags if w not in ('kiện', 'báo chí', 'sở y tế', 'bóc phốt', '1 sao', 'một sao', 'tố cáo')]
    return {
        'topic': topic, 'severity': severity, 'sentiment': sentiment, 'churn_risk': churn,
        'summary': (text or '').strip()[:160],
        'suggested_reply': REPLIES[topic].format(sal='anh/chị'),
        'suggested_action': ('KHẨN: báo bác sĩ điều trị gọi ngay. ' if medical else '') + ACTIONS[topic],
        'red_flags': red_flags,
    }


class DmagAiFeedback(models.Model):
    _name = 'dmag.ai.feedback'
    _description = 'Phản hồi khách hàng đã phân loại (AI-09)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'state_rank, severity_rank desc, id desc'
    _rec_name = 'summary'

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)
    source = fields.Selection([('nps', 'Khảo sát NPS'), ('conversation', 'Tin nhắn Zalo'), ('followup', 'Theo dõi sau điều trị'),
                               ('manual', 'Nhập tay')], string='Nguồn', required=True, default='manual')
    partner_id = fields.Many2one('res.partner', string='Khách hàng', index=True)
    visit_id = fields.Many2one('dmag.dental.visit', string='Lượt khám')
    doctor_id = fields.Many2one(related='visit_id.doctor_id', store=True, string='Bác sĩ')
    nps_response_id = fields.Many2one('dmag.nps.response', string='Phiếu NPS', index=True)
    conversation_id = fields.Many2one('dmag.ai.conversation', string='Hội thoại', index=True)
    message_line_id = fields.Many2one('dmag.ai.conversation.message', string='Tin nhắn')
    nps_score = fields.Integer('Điểm NPS')
    has_score = fields.Boolean()
    text = fields.Text('Nội dung khách viết', required=True)
    summary = fields.Char('Tóm tắt')
    topic = fields.Selection(TOPICS, string='Chủ đề', index=True)
    topic_label = fields.Char(compute='_compute_labels')
    severity = fields.Selection(SEVERITIES, string='Mức độ', index=True)
    severity_rank = fields.Integer(compute='_compute_ranks', store=True)
    sentiment = fields.Selection([('positive', 'Tích cực'), ('neutral', 'Trung lập'), ('negative', 'Tiêu cực')], string='Cảm xúc')
    churn_risk = fields.Boolean('Nguy cơ rời bỏ', index=True)
    red_flags = fields.Char('Dấu hiệu cần bác sĩ xem')
    suggested_reply = fields.Text('Gợi ý trả lời khách')
    suggested_action = fields.Text('Gợi ý xử lý nội bộ')
    customer_label = fields.Char('Khách', compute='_compute_labels')
    state = fields.Selection([('new', 'Mới'), ('in_progress', 'Đang xử lý'), ('done', 'Đã xử lý')], string='Trạng thái', default='new',
                             required=True, tracking=True, index=True)
    state_rank = fields.Integer(compute='_compute_ranks', store=True)
    user_id = fields.Many2one('res.users', string='Người xử lý', tracking=True)
    resolution = fields.Text('Kết quả xử lý')
    method = fields.Selection([('local', 'Tại chỗ (từ điển)'), ('simulate', 'Giả lập AI'), ('live', 'Claude')],
                              string='Cách phân loại')
    method_note = fields.Char('Ghi chú phân loại')
    cost_vnd = fields.Float('Chi phí AI (đ)', digits=(12, 0))
    estimated_cost_vnd = fields.Float('Chi phí nếu chạy thật (đ)', digits=(12, 0))

    @api.depends('severity', 'state')
    def _compute_ranks(self):
        for fb in self:
            fb.severity_rank = SEVERITY_RANK.get(fb.severity, 0)
            fb.state_rank = {'new': 0, 'in_progress': 1, 'done': 2}.get(fb.state, 0)

    def _compute_labels(self):
        labels = dict(TOPICS)
        for fb in self:
            fb.topic_label = labels.get(fb.topic, '')
            fb.customer_label = fb.partner_id.name or fb.conversation_id.name or ''


    # ------------------------------------------------------------------ classification
    def _classify(self, use_ai=True):
        for fb in self:
            score = fb.nps_score if fb.has_score else None
            local = classify_local(fb.text, score)
            vals, method, note = local, 'local', False
            if use_ai and self.env['dmag.ai'].is_feature_active('AI-09'):
                user = _('Kênh: %(src)s%(score)s\nNội dung khách viết:\n%(text)s',
                         src=dict(fb._fields['source'].selection)[fb.source],
                         score=(_('\nĐiểm NPS: %s/10', score) if score is not None else ''), text=fb.text)
                try:
                    res = self.env['dmag.ai'].run('AI-09', SYSTEM, user, schema=SCHEMA, record=fb,
                                                  patient=fb.partner_id if fb.partner_id.is_patient else None,
                                                  simulate=lambda: {'data': local, 'text': local['summary']})
                    if isinstance(res.get('data'), dict):
                        vals = dict(local, **{k: v for k, v in res['data'].items() if v not in (None, '')})
                    method = 'simulate' if res.get('simulated') else 'live'
                    fb.write({'cost_vnd': res.get('cost_vnd') or 0, 'estimated_cost_vnd': res.get('estimated_cost_vnd') or 0})
                except UserError as e:
                    note = _('Phân loại tại chỗ – %s', e)
            fb.write({
                'topic': vals['topic'] if vals.get('topic') in dict(TOPICS) else 'other',
                'severity': vals['severity'] if vals.get('severity') in SEVERITY_RANK else 'medium',
                'sentiment': vals.get('sentiment') if vals.get('sentiment') in ('positive', 'neutral', 'negative') else 'neutral',
                'churn_risk': bool(vals.get('churn_risk')),
                'summary': (vals.get('summary') or fb.text)[:200],
                'suggested_reply': vals.get('suggested_reply'), 'suggested_action': vals.get('suggested_action'),
                'red_flags': ', '.join(vals.get('red_flags') or []) or False,
                'method': method, 'method_note': note,
            })
            if fb.severity in ('high', 'critical') and not fb.activity_ids:
                fb._schedule_followup()
        return True

    def _schedule_followup(self):
        self.ensure_one()
        rule = self.env['dmag.journey.rule'].sudo()
        role = 'doctor' if self.red_flags and self.visit_id else 'cskh_lead'
        user = rule._dmag_responsible_user(role, self.visit_id or None, self.company_id)
        self.sudo().activity_schedule(
            'dmag_dental_journey.activity_type_complaint', date_deadline=fields.Date.context_today(self),
            summary=_('%(sev)s – %(topic)s: %(name)s', sev=dict(SEVERITIES)[self.severity], topic=self.topic_label,
                      name=self.partner_id.name or self.conversation_id.name or ''),
            note=self.suggested_action or '', user_id=user.id)
        self.sudo().user_id = user

    @api.model
    def _create_from_text(self, text, source='manual', partner=None, visit=None, nps=None, conversation=None,
                          message=None, score=None):
        vals = {
            'source': source, 'text': text or '-', 'partner_id': partner.id if partner else False,
            'visit_id': visit.id if visit else False, 'nps_response_id': nps.id if nps else False,
            'conversation_id': conversation.id if conversation else False,
            'message_line_id': message.id if message else False,
            'nps_score': score or 0, 'has_score': score is not None,
            'company_id': (visit or nps or conversation).company_id.id if (visit or nps or conversation) else self.env.company.id,
        }
        fb = self.sudo().create(vals)
        fb._classify()
        return fb

    @api.model
    def _auto_from_message(self, message):
        """Tin Zalo của khách có dấu hiệu tiêu cực → tạo phiếu phân loại (nếu hội thoại chưa có phiếu mở)."""
        if not self.env['dmag.ai'].is_feature_active('AI-09'):
            return False
        folded = fold(message.body)
        if not (match_words(message.body, NEGATIVE) or match_words(message.body, CRITICAL) or match_words(message.body, CHURN)):
            return False
        conv = message.conversation_id
        if conv.feedback_ids.filtered(lambda f: f.state != 'done'):
            return False
        try:
            with self.env.cr.savepoint():
                return self._create_from_text(message.body, 'conversation', partner=conv.partner_id or None,
                                              conversation=conv, message=message)
        except Exception:  # phân loại không được chặn hội thoại
            _logger.exception('AI-09 classify message %s failed', message.id)
            return False

    @api.model
    def action_classify_backlog(self, limit=200):
        """Phân loại các phiếu NPS đã trả lời (có góp ý hoặc ≤ 8 điểm) chưa có phiếu AI-09 – dùng khi mới bật tính năng."""
        done = self.sudo().search([('nps_response_id', '!=', False)]).mapped('nps_response_id')
        responses = self.env['dmag.nps.response'].sudo().search([
            ('state', '=', 'answered'), ('id', 'not in', done.ids), '|', ('comment', '!=', False), ('score', '<=', 8)],
            limit=limit, order='date desc')
        for resp in responses:
            self._create_from_text(resp.comment or ('Chấm %s/10, không ghi góp ý.' % resp.score), 'nps',
                                   partner=resp.partner_id, visit=resp.visit_id or None, nps=resp, score=resp.score)
        return {'type': 'ir.actions.client', 'tag': 'reload'} if responses else True

    # ------------------------------------------------------------------ actions
    def action_reclassify(self):
        self._classify()
        return True

    def action_start(self):
        self.write({'state': 'in_progress', 'user_id': self.user_id.id or self.env.uid})
        return True

    def action_done(self):
        self.write({'state': 'done'})
        self.activity_ids.action_feedback(feedback=self.resolution or _('Đã xử lý'))
        if self.nps_response_id and self.nps_response_id.is_complaint:
            self.nps_response_id.sudo().action_mark_resolved()
        return True

    def action_open_source(self):
        self.ensure_one()
        target = self.conversation_id or self.nps_response_id or self.visit_id
        if not target:
            return False
        return {'type': 'ir.actions.act_window', 'res_model': target._name, 'res_id': target.id,
                'views': [[False, 'form']], 'target': 'current'}
