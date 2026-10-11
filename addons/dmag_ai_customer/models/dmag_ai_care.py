"""AI-12 – Nội dung chăm sóc cá nhân hóa: kịch bản gọi hỏi thăm +24h và tin nhắn OA theo ca điều trị.

AI chỉ soạn NHÁP; nhân viên sửa → duyệt → gửi (tin OA trong hội thoại / ghi nhận cuộc gọi). Tin ZNS chủ động vẫn
dùng mẫu đã đăng ký của module hành trình.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext

from .text_utils import given_name, salutation

SCHEMA = {
    'type': 'object',
    'properties': {
        'call_script': {'type': 'string'},
        'oa_message': {'type': 'string'},
        'key_points': {'type': 'array', 'items': {'type': 'string'}},
        'warning_signs': {'type': 'array', 'items': {'type': 'string'}},
    },
    'required': ['call_script', 'oa_message', 'key_points', 'warning_signs'],
    'additionalProperties': False,
}
SYSTEM = (
    'Soạn nội dung chăm sóc sau điều trị nha khoa cho nhân viên CSKH: (1) kịch bản gọi hỏi thăm sau 24 giờ – có lời chào, '
    'câu hỏi mức đau 0–10, chảy máu, sưng, sốt, nhắc lời dặn chính, hẹn lần sau, lời cảm ơn; (2) tin nhắn Zalo OA ngắn '
    '(≤ 600 ký tự), ấm áp, cá nhân hóa theo thủ thuật đã làm. CHỈ dùng lời dặn có trong dữ liệu, không thêm chỉ định / '
    'thuốc mới, không chẩn đoán, không quảng cáo dịch vụ khác. key_points: 3–5 lời dặn quan trọng nhất; warning_signs: '
    'dấu hiệu cần báo bác sĩ ngay. Giữ nguyên các mã ẩn danh như [BN_1].'
)
WARNING_DEFAULT = ['Chảy máu không cầm sau khi cắn gạc 30 phút', 'Sưng tăng dần sau 48 giờ hoặc sưng lan xuống cổ',
                   'Sốt trên 38,5°C', 'Đau tăng dần, uống thuốc giảm đau không đỡ']


class DmagAiCareDraft(models.Model):
    _name = 'dmag.ai.care.draft'
    _description = 'Nội dung chăm sóc cá nhân hóa (AI-12)'
    _inherit = ['mail.thread']
    _order = 'id desc'

    name = fields.Char('Tiêu đề', compute='_compute_name', store=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)
    visit_id = fields.Many2one('dmag.dental.visit', string='Lượt khám', required=True, ondelete='cascade', index=True)
    patient_id = fields.Many2one(related='visit_id.patient_id', store=True, string='Bệnh nhân')
    doctor_id = fields.Many2one(related='visit_id.doctor_id', store=True, string='Bác sĩ')
    procedures = fields.Char('Thủ thuật', readonly=True)
    call_script = fields.Text('Kịch bản gọi hỏi thăm (+24h)')
    oa_message = fields.Text('Tin nhắn Zalo OA')
    key_points = fields.Text('Lời dặn chính')
    warning_signs = fields.Text('Dấu hiệu cần báo bác sĩ')
    state = fields.Selection([('draft', 'Nháp – chờ duyệt'), ('sent', 'Đã gửi tin'), ('called', 'Đã gọi'),
                              ('done', 'Hoàn tất'), ('cancel', 'Bỏ')], default='draft', required=True, tracking=True)
    approved_by_id = fields.Many2one('res.users', string='Người duyệt', readonly=True)
    sent_at = fields.Datetime('Gửi lúc', readonly=True)
    send_channel = fields.Char('Kênh gửi', readonly=True)
    call_note = fields.Text('Ghi chú cuộc gọi')
    call_pain = fields.Integer('Điểm đau khách báo (0–10)', default=-1)
    mode = fields.Selection([('simulate', 'Giả lập'), ('live', 'Claude')], string='Soạn bởi', readonly=True)
    cost_vnd = fields.Float('Chi phí AI (đ)', digits=(12, 0), readonly=True)
    estimated_cost_vnd = fields.Float('Chi phí nếu chạy thật (đ)', digits=(12, 0), readonly=True)

    @api.depends('visit_id', 'patient_id')
    def _compute_name(self):
        for draft in self:
            draft.name = _('Chăm sóc %s – %s', draft.patient_id.name or '', draft.visit_id.name or '')

    # ------------------------------------------------------------------ generate
    @api.model
    def _visit_facts(self, visit):
        visit = visit.sudo()
        procs = visit.procedure_ids.filtered(lambda p: p.state == 'done') or visit.procedure_ids
        lines = []
        for p in procs:
            teeth = ', '.join(p.tooth_ids.mapped('code'))
            lines.append('%s%s' % (p.product_id.name, (' (răng %s)' % teeth) if teeth else ''))
        if not lines:
            lines = visit.service_ids.mapped('name')
        aftercare = []
        for product in (procs.mapped('product_id') | visit.service_ids):
            note = html2plaintext(product.aftercare_note or '').strip()
            if note and (product.name, note) not in aftercare:
                aftercare.append((product.name, note))
        next_visit = visit.search([('patient_id', '=', visit.patient_id.id), ('id', '!=', visit.id),
                                   ('state', 'in', ('draft', 'confirmed')),
                                   ('scheduled_start', '>', visit.scheduled_start)], order='scheduled_start', limit=1)
        next_text = ''
        if next_visit:
            local = fields.Datetime.context_timestamp(self, next_visit.scheduled_start)
            next_text = local.strftime('%H:%M ngày %d/%m/%Y')
        return {
            'patient': visit.patient_id, 'salutation': salutation(visit.patient_id),
            'given': given_name(visit.patient_id.name), 'doctor': visit.doctor_id.name or '',
            'procedures': lines, 'aftercare': aftercare, 'advice': (visit.advice or '').strip(),
            'next_visit': next_text, 'clinic': visit.company_id.name, 'hotline': visit.company_id.phone or '',
            'invasive': visit.is_heavy or any(c in ('surgery', 'implant', 'endo') for c in procs.mapped('product_id.dental_category')),
        }

    @api.model
    def _simulate(self, facts):
        sal, given = facts['salutation'], facts['given']
        sal_cap = sal[:1].upper() + sal[1:]
        procs = ', '.join(facts['procedures']) or 'khám răng'
        points = []
        for _name, note in facts['aftercare']:
            for line in note.replace('•', '\n').replace(';', '\n').split('\n'):
                line = line.strip(' -–.')
                if len(line) > 8 and line not in points:
                    points.append(line)
        if facts['advice']:
            points.insert(0, facts['advice'].split('\n')[0][:160])
        points = points[:5] or ['Vệ sinh răng miệng nhẹ nhàng, chải răng 2 lần/ngày', 'Tái khám đúng hẹn']
        warnings = WARNING_DEFAULT if facts['invasive'] else WARNING_DEFAULT[2:]
        script = '\n'.join(filter(None, [
            '1. Chào hỏi: "Dạ em chào %s %s, em là ... gọi từ %s. Em gọi hỏi thăm %s sau buổi %s hôm qua với BS %s ạ."'
            % (sal, given, facts['clinic'], sal, procs, facts['doctor'] or 'phụ trách'),
            '2. Hỏi mức đau: "%s thấy đau ở mức nào, từ 0 (không đau) đến 10 (rất đau) ạ?" – ghi điểm vào hệ thống; '
            '≥ 7 điểm: báo ngay bác sĩ.' % sal_cap,
            '3. Hỏi dấu hiệu: còn chảy máu không? có sưng không? có sốt không? ăn uống được chưa?',
            '4. Nhắc lời dặn chính:\n' + '\n'.join('   • %s' % p for p in points),
            '5. Dấu hiệu cần quay lại / gọi hotline %s ngay:\n' % (facts['hotline'] or '') + '\n'.join('   • %s' % w for w in warnings),
            ('6. Nhắc lịch hẹn tiếp theo: %s.' % facts['next_visit']) if facts['next_visit'] else
            '6. Hỏi %s có muốn đặt lịch tái khám / bước điều trị tiếp theo không.' % sal,
            '7. Cảm ơn: "Cảm ơn %s đã tin tưởng %s. Có gì bất thường %s cứ gọi hoặc nhắn Zalo cho phòng khám nhé ạ!"'
            % (sal, facts['clinic'], sal),
        ]))
        message = ('%s %s ơi, %s cảm ơn %s đã đến %s hôm qua.\n'
                   'Sau buổi %s, %s nhớ giúp phòng khám:\n%s\n'
                   'Nếu %s thấy %s, hãy gọi ngay %s nhé.%s\nChúc %s mau khỏe!'
                   % (sal_cap, given, facts['clinic'], sal, 'điều trị' if facts['invasive'] else 'khám', procs, sal,
                      '\n'.join('• %s' % p for p in points[:3]), sal, warnings[0].lower(), facts['hotline'] or 'phòng khám',
                      ('\nLịch hẹn tiếp theo: %s.' % facts['next_visit']) if facts['next_visit'] else '', sal))
        return {'call_script': script, 'oa_message': message[:900], 'key_points': points, 'warning_signs': warnings}

    @api.model
    def generate_for_visit(self, visit):
        visit.check_access_rights('read')
        facts = self._visit_facts(visit)
        user = '\n'.join([
            'Phòng khám: %s – hotline %s' % (facts['clinic'], facts['hotline']),
            'Bệnh nhân: %s (xưng hô: %s)' % (visit.patient_id.name, facts['salutation']),
            'Bác sĩ: %s' % facts['doctor'],
            'Thủ thuật đã làm: %s' % '; '.join(facts['procedures']),
            'Lời dặn của bác sĩ: %s' % (facts['advice'] or '(không có)'),
            'Hướng dẫn chăm sóc theo dịch vụ:\n%s' % '\n'.join('- %s: %s' % a for a in facts['aftercare']),
            'Lịch hẹn tiếp theo: %s' % (facts['next_visit'] or '(chưa có)'),
        ])
        res = self.env['dmag.ai'].run('AI-12', SYSTEM, user, schema=SCHEMA, record=visit, patient=visit.patient_id,
                                      simulate=lambda: {'data': self._simulate(facts), 'text': ''})
        data = res.get('data') or self._simulate(facts)
        return self.create({
            'visit_id': visit.id, 'company_id': visit.company_id.id,
            'procedures': ', '.join(facts['procedures'])[:250],
            'call_script': data.get('call_script'), 'oa_message': data.get('oa_message'),
            'key_points': '\n'.join('• %s' % p for p in data.get('key_points') or []),
            'warning_signs': '\n'.join('• %s' % p for p in data.get('warning_signs') or []),
            'mode': 'simulate' if res.get('simulated') else 'live',
            'cost_vnd': res.get('cost_vnd') or 0, 'estimated_cost_vnd': res.get('estimated_cost_vnd') or 0,
        })

    # ------------------------------------------------------------------ approve & send
    def action_approve_send(self):
        """Nhân viên đã đọc / sửa → duyệt và gửi tin OA (qua hội thoại Zalo nếu khách đã nhắn OA; nếu không: ghi nhận
        để gửi tay). Ghi vết vào lượt khám."""
        for draft in self:
            if not (draft.oa_message or '').strip():
                raise UserError(_('Tin nhắn trống.'))
            conv = self.env['dmag.ai.conversation'].sudo().search([
                ('partner_id', '=', draft.patient_id.id), ('channel', '=', 'zalo'),
                ('external_user_id', '!=', False)], limit=1)
            channel = _('Ghi nhận – gửi tay (khách chưa nhắn OA)')
            if conv:
                msg = self.env['dmag.ai.conversation.message'].sudo().create({
                    'conversation_id': conv.id, 'role': 'staff', 'body': draft.oa_message, 'state': 'ready',
                    'author_id': self.env.uid})
                msg._deliver()
                channel = _('Zalo OA (%s)', dict(msg._fields['state'].selection)[msg.state])
            draft.write({'state': 'sent', 'approved_by_id': self.env.uid, 'sent_at': fields.Datetime.now(),
                         'send_channel': channel})
            draft.visit_id.sudo().message_post(body=_('Đã duyệt & gửi tin chăm sóc (AI-12, %(mode)s) – %(ch)s:\n%(msg)s',
                                                      mode=draft.mode, ch=channel, msg=draft.oa_message))
        return True

    def action_log_call(self):
        for draft in self:
            if 0 <= draft.call_pain <= 10 and hasattr(draft.visit_id, 'record_pain_score_24h'):
                draft.visit_id.record_pain_score_24h(draft.call_pain, draft.call_note or False)
            else:
                draft.visit_id.sudo().message_post(body=_('Đã gọi hỏi thăm: %s', draft.call_note or '-'))
            draft.write({'state': 'called' if draft.state == 'draft' else 'done', 'approved_by_id': self.env.uid})
        return True

    def action_regenerate(self):
        self.ensure_one()
        new = self.generate_for_visit(self.visit_id)
        self.write({'state': 'cancel'})
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': new.id,
                'views': [[False, 'form']], 'target': 'new'}
