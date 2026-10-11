"""AI-18 – Theo dõi sau điều trị: câu hỏi 24h / 72h (đau 0–10, chảy máu, sưng, sốt + mô tả tự do).

Ngưỡng cố định tại chỗ quyết định cảnh báo; AI chỉ ĐỌC phần mô tả tự do để phát hiện dấu hiệu bất thường mà ngưỡng
không bắt được (không chẩn đoán). Bất thường → việc cần làm cho bác sĩ phụ trách + ghi lượt khám.
"""
import secrets
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .text_utils import match_words

INVASIVE_CATEGORIES = ('surgery', 'implant', 'endo', 'prosthodontic', 'orthodontic')
LEVELS = [('normal', 'Bình thường'), ('watch', 'Cần theo dõi'), ('urgent', 'Báo bác sĩ ngay')]
LEVEL_RANK = {'normal': 0, 'watch': 1, 'urgent': 2}
FREE_TEXT_URGENT = ['sốt', 'mủ', 'hôi', 'chảy máu nhiều', 'không cầm', 'sưng to', 'sưng lan', 'khó nuốt', 'khó thở',
                    'há miệng khó', 'không há được', 'tê môi', 'tê kéo dài', 'mất cảm giác', 'phát ban', 'ngứa', 'nổi mẩn',
                    'chóng mặt', 'lung lay trụ', 'trụ lỏng', 'rơi chỉ']
FREE_TEXT_WATCH = ['đau nhói', 'ê buốt', 'đau tăng', 'nhức', 'cộm', 'vướng', 'khó nhai', 'mắc thức ăn', 'sưng nhẹ',
                   'rỉ máu', 'lệch khớp cắn']
SCHEMA = {
    'type': 'object',
    'properties': {
        'level': {'type': 'string', 'enum': ['normal', 'watch', 'urgent']},
        'red_flags': {'type': 'array', 'items': {'type': 'string'}},
        'summary_for_doctor': {'type': 'string'},
        'reply_to_patient': {'type': 'string'},
    },
    'required': ['level', 'red_flags', 'summary_for_doctor', 'reply_to_patient'],
    'additionalProperties': False,
}
SYSTEM = (
    'Đọc câu trả lời theo dõi sau thủ thuật nha khoa của bệnh nhân (điểm đau, chảy máu, sưng, sốt và mô tả tự do). '
    'Phân mức: urgent nếu có dấu hiệu có thể là biến chứng (chảy máu không cầm, sưng lan / tăng sau 48h, sốt, mủ, khó '
    'nuốt / khó thở / há miệng hạn chế, tê kéo dài, dị ứng thuốc); watch nếu khó chịu cần bác sĩ gọi hỏi; normal nếu '
    'diễn tiến bình thường. KHÔNG chẩn đoán, KHÔNG khuyên thuốc. reply_to_patient: 1–2 câu trấn an, nhắc gọi hotline nếu '
    'khẩn. summary_for_doctor: 1–2 câu khách quan.'
)


def evaluate_local(answers, checkpoint='24h', previous_pain=None):
    """Ngưỡng cố định tại chỗ. answers: pain (0–10), bleeding (none/light/heavy), swelling (none/mild/severe), fever (bool)."""
    flags, level = [], 'normal'

    def raise_to(lvl, flag):
        nonlocal level
        flags.append(flag)
        if LEVEL_RANK[lvl] > LEVEL_RANK[level]:
            level = lvl

    pain = answers.get('pain')
    if pain is not None and pain >= 0:
        if pain >= 7:
            raise_to('urgent', 'Đau %s/10' % pain)
        elif pain >= 4 and checkpoint == '72h':
            raise_to('watch', 'Còn đau %s/10 sau 72 giờ' % pain)
        elif pain >= 5:
            raise_to('watch', 'Đau %s/10' % pain)
        if previous_pain is not None and previous_pain >= 0 and pain > previous_pain and checkpoint == '72h':
            raise_to('urgent', 'Đau tăng (%s → %s)' % (previous_pain, pain))
    if answers.get('bleeding') == 'heavy':
        raise_to('urgent', 'Chảy máu nhiều')
    elif answers.get('bleeding') == 'light' and checkpoint == '72h':
        raise_to('watch', 'Còn rỉ máu sau 72 giờ')
    if answers.get('swelling') == 'severe':
        raise_to('urgent', 'Sưng nhiều')
    elif answers.get('swelling') == 'mild' and checkpoint == '72h':
        raise_to('watch', 'Còn sưng sau 72 giờ')
    if answers.get('fever'):
        raise_to('urgent', 'Sốt')
    return level, flags


def read_free_text_local(text):
    urgent = match_words(text, FREE_TEXT_URGENT)
    watch = match_words(text, FREE_TEXT_WATCH)
    level = 'urgent' if urgent else 'watch' if watch else 'normal'
    return level, urgent + watch


class DmagAiFollowup(models.Model):
    _name = 'dmag.ai.followup'
    _description = 'Theo dõi sau điều trị (AI-18)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'due_at desc, id desc'

    name = fields.Char(compute='_compute_name', store=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)
    visit_id = fields.Many2one('dmag.dental.visit', string='Lượt khám', required=True, ondelete='cascade', index=True)
    patient_id = fields.Many2one(related='visit_id.patient_id', store=True, string='Bệnh nhân')
    doctor_id = fields.Many2one(related='visit_id.doctor_id', store=True, string='Bác sĩ phụ trách')
    procedures = fields.Char('Thủ thuật')
    checkpoint = fields.Selection([('24h', 'Sau 24 giờ'), ('72h', 'Sau 72 giờ')], string='Mốc hỏi', required=True, default='24h')
    due_at = fields.Datetime('Hỏi lúc', required=True, index=True)
    token = fields.Char(required=True, copy=False, index=True, default=lambda self: secrets.token_urlsafe(16),
                        groups='dmag_dental_base.group_dmag_receptionist')
    url = fields.Char('Link trả lời', compute='_compute_url')
    state = fields.Selection([('scheduled', 'Chờ đến giờ'), ('sent', 'Đã gửi câu hỏi'), ('answered', 'Đã trả lời'),
                              ('alert', 'Bất thường – đã báo bác sĩ'), ('closed', 'Đã xử lý'), ('expired', 'Hết hạn')],
                             string='Trạng thái', default='scheduled', required=True, tracking=True, index=True)
    channel = fields.Selection([('zalo', 'Zalo OA'), ('portal', 'Cổng bệnh nhân'), ('call', 'Gọi điện')], string='Kênh trả lời')
    sent_note = fields.Char('Gửi qua', readonly=True)
    pain = fields.Integer('Mức đau (0–10)', default=-1)
    bleeding = fields.Selection([('none', 'Không'), ('light', 'Rỉ ít'), ('heavy', 'Chảy nhiều')], string='Chảy máu')
    swelling = fields.Selection([('none', 'Không'), ('mild', 'Sưng nhẹ'), ('severe', 'Sưng nhiều')], string='Sưng')
    fever = fields.Boolean('Sốt')
    free_text = fields.Text('Khách mô tả thêm')
    answered_at = fields.Datetime('Trả lời lúc', readonly=True)
    local_level = fields.Selection(LEVELS, string='Theo ngưỡng', readonly=True)
    ai_level = fields.Selection(LEVELS, string='AI đọc mô tả', readonly=True)
    level = fields.Selection(LEVELS, string='Kết luận', readonly=True, index=True)
    flags = fields.Text('Dấu hiệu phát hiện', readonly=True)
    ai_summary = fields.Text('Tóm tắt cho bác sĩ', readonly=True)
    reply_to_patient = fields.Text('Phản hồi cho khách', readonly=True)
    ai_mode = fields.Char('Chế độ AI', readonly=True)
    doctor_note = fields.Text('Bác sĩ xử lý')

    _sql_constraints = [('visit_checkpoint_uniq', 'unique(visit_id, checkpoint)', 'Đã có câu hỏi theo dõi mốc này.')]

    @api.depends('visit_id', 'checkpoint')
    def _compute_name(self):
        for fu in self:
            fu.name = _('Theo dõi %s – %s', dict(fu._fields['checkpoint'].selection).get(fu.checkpoint, ''),
                        fu.visit_id.patient_id.name or '')

    def _compute_url(self):
        for fu in self:
            fu.url = '%s/dmag/followup/%s' % (fu.get_base_url(), fu.sudo().token)

    # ------------------------------------------------------------------ creation & sending
    @api.model
    def _needs_followup(self, visit):
        procs = visit.procedure_ids.filtered(lambda p: p.state == 'done')
        return visit.is_heavy or any(c in INVASIVE_CATEGORIES for c in procs.mapped('product_id.dental_category'))

    @api.model
    def _create_for_visits(self, visits):
        if not self.env['dmag.ai'].is_feature_active('AI-18'):
            return self.browse()
        created = self.browse()
        for visit in visits.sudo():
            if not visit.company_id.dmag_ai_followup_enabled or not self._needs_followup(visit):
                continue
            done = visit.done_time or fields.Datetime.now()
            procs = ', '.join(visit.procedure_ids.filtered(lambda p: p.state == 'done').mapped('product_id.name'))[:200]
            for checkpoint, hours in (('24h', 24), ('72h', 72)):
                if self.search_count([('visit_id', '=', visit.id), ('checkpoint', '=', checkpoint)]):
                    continue
                created |= self.create({'visit_id': visit.id, 'company_id': visit.company_id.id, 'checkpoint': checkpoint,
                                        'due_at': done + timedelta(hours=hours), 'procedures': procs})
        return created

    def _message_text(self):
        self.ensure_one()
        sal = 'anh/chị'
        return _('Phòng khám %(clinic)s hỏi thăm %(sal)s sau %(proc)s: %(sal)s vui lòng trả lời 4 câu hỏi ngắn (mức đau, '
                 'chảy máu, sưng, sốt) tại %(url)s để bác sĩ theo dõi. Khẩn cấp gọi %(hotline)s.',
                 clinic=self.company_id.name, sal=sal, proc=self.procedures or _('buổi điều trị'), url=self.url,
                 hotline=self.company_id.phone or '')

    def action_send(self):
        """Gửi câu hỏi theo kịch bản cố định (không do AI soạn): tin OA nếu khách có hội thoại Zalo, đồng thời hiện
        trên cổng bệnh nhân /my/dental."""
        for fu in self.sudo():
            conv = self.env['dmag.ai.conversation'].sudo().search([
                ('partner_id', '=', fu.patient_id.id), ('channel', '=', 'zalo'), ('external_user_id', '!=', False)], limit=1)
            note = _('Cổng bệnh nhân')
            if conv:
                msg = self.env['dmag.ai.conversation.message'].sudo().create({
                    'conversation_id': conv.id, 'role': 'system', 'body': fu._message_text(), 'state': 'ready'})
                msg._deliver()
                note = _('Zalo OA (%s) + cổng bệnh nhân', dict(msg._fields['state'].selection)[msg.state])
            fu.write({'state': 'sent', 'sent_note': note})
        return True

    @api.model
    def _cron_send_due(self):
        now = fields.Datetime.now()
        self.sudo().search([('state', '=', 'scheduled'), ('due_at', '<=', now)], limit=200).action_send()
        self.sudo().search([('state', '=', 'sent'), ('due_at', '<', now - timedelta(days=5))]).write({'state': 'expired'})
        return True

    # ------------------------------------------------------------------ answer & evaluate
    def submit_answers(self, pain, bleeding, swelling, fever, free_text='', channel='portal'):
        self.ensure_one()
        fu = self.sudo()
        if fu.state in ('answered', 'alert', 'closed'):
            raise UserError(_('Câu hỏi này đã được trả lời. Cảm ơn bạn!'))
        try:
            pain = int(pain)
        except (TypeError, ValueError) as e:
            raise UserError(_('Mức đau phải là số 0–10.')) from e
        if not 0 <= pain <= 10:
            raise UserError(_('Mức đau phải từ 0 đến 10.'))
        fu.write({'pain': pain, 'bleeding': bleeding or 'none', 'swelling': swelling or 'none', 'fever': bool(fever),
                  'free_text': (free_text or '').strip()[:2000], 'channel': channel, 'answered_at': fields.Datetime.now()})
        fu._evaluate()
        return fu.reply_to_patient

    def _evaluate(self):
        for fu in self.sudo():
            prev = self.search([('visit_id', '=', fu.visit_id.id), ('checkpoint', '=', '24h'), ('id', '!=', fu.id)], limit=1)
            local_level, flags = evaluate_local({'pain': fu.pain, 'bleeding': fu.bleeding, 'swelling': fu.swelling,
                                                 'fever': fu.fever}, fu.checkpoint,
                                                prev.pain if prev and prev.answered_at else None)
            ai_level, summary, reply, mode = 'normal', '', '', ''
            if (fu.free_text or '').strip():
                txt_level, txt_flags = read_free_text_local(fu.free_text)
                sim = {'level': txt_level, 'red_flags': txt_flags,
                       'summary_for_doctor': _('Khách mô tả: "%s"', fu.free_text[:200]),
                       'reply_to_patient': ''}
                try:
                    user = _('Mốc: %(cp)s sau %(proc)s\nĐau: %(pain)s/10; chảy máu: %(bl)s; sưng: %(sw)s; sốt: %(fe)s\n'
                             'Mô tả tự do: %(txt)s', cp=fu.checkpoint, proc=fu.procedures or '', pain=fu.pain,
                             bl=dict(fu._fields['bleeding'].selection).get(fu.bleeding),
                             sw=dict(fu._fields['swelling'].selection).get(fu.swelling),
                             fe=_('có') if fu.fever else _('không'), txt=fu.free_text)
                    res = self.env['dmag.ai'].run('AI-18', SYSTEM, user, schema=SCHEMA, record=fu, patient=fu.patient_id,
                                                  simulate=lambda: {'data': sim, 'text': ''})
                    data = res.get('data') or sim
                    mode = 'Giả lập' if res.get('simulated') else 'Claude'
                except UserError as e:  # chưa đồng ý AI / tính năng tắt → đọc tại chỗ
                    data, mode = sim, _('Tại chỗ (%s)', e)
                ai_level = data.get('level') if data.get('level') in LEVEL_RANK else 'normal'
                flags += [f for f in data.get('red_flags') or [] if f]
                summary = data.get('summary_for_doctor') or ''
                reply = data.get('reply_to_patient') or ''
            level = max(local_level, ai_level, key=lambda l: LEVEL_RANK[l])
            if not reply:
                reply = {
                    'normal': _('Cảm ơn bạn! Diễn tiến đang bình thường – bạn tiếp tục làm theo lời dặn của bác sĩ nhé.'),
                    'watch': _('Cảm ơn bạn! Bác sĩ sẽ gọi hỏi thăm trong hôm nay. Nếu thấy nặng hơn, gọi hotline %s.',
                               fu.company_id.phone or ''),
                    'urgent': _('Bác sĩ đã được báo và sẽ liên hệ bạn ngay. Nếu chảy máu không cầm, sưng lan, sốt cao hoặc '
                                'khó thở: gọi %s hoặc đến cơ sở y tế gần nhất ngay.', fu.company_id.phone or ''),
                }[level]
            fu.write({'local_level': local_level, 'ai_level': ai_level if fu.free_text else False, 'level': level,
                      'flags': '\n'.join(dict.fromkeys(flags)) or False, 'ai_summary': summary or False,
                      'reply_to_patient': reply, 'ai_mode': mode or False,
                      'state': 'alert' if level != 'normal' else 'answered'})
            if level != 'normal':
                fu._alert_doctor()
        return True

    def _alert_doctor(self):
        self.ensure_one()
        user = self.env['dmag.journey.rule'].sudo()._dmag_responsible_user('doctor', self.visit_id, self.company_id)
        summary = _('%(lvl)s – theo dõi %(cp)s: %(name)s (đau %(pain)s/10)',
                    lvl=dict(LEVELS)[self.level], cp=self.checkpoint, name=self.patient_id.name, pain=self.pain)
        note = '\n'.join(filter(None, [self.flags, self.ai_summary]))
        self.activity_schedule('dmag_dental_journey.activity_type_complaint' if self.level == 'urgent'
                               else 'dmag_dental_journey.activity_type_cskh_call',
                               date_deadline=fields.Date.context_today(self), summary=summary, note=note, user_id=user.id)
        self.visit_id.message_post(body=_('%(s)s\n%(n)s', s=summary, n=note))

    def action_record_call(self):
        """CSKH gọi điện hỏi và nhập câu trả lời vào phiếu → đánh giá như khách tự trả lời."""
        for fu in self:
            if fu.pain < 0:
                raise UserError(_('Nhập mức đau 0–10 trước.'))
            fu.sudo().write({'channel': 'call', 'answered_at': fields.Datetime.now(),
                             'bleeding': fu.bleeding or 'none', 'swelling': fu.swelling or 'none'})
            fu._evaluate()
        return True

    def action_close(self):
        self.write({'state': 'closed'})
        self.activity_ids.action_feedback(feedback=self.doctor_note or _('Đã xử lý'))
        return True

    def action_open_answer_page(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': '/dmag/followup/%s' % self.sudo().token, 'target': 'new'}
