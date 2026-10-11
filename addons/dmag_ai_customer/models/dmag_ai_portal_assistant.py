"""AI-17 – Trợ lý trên cổng bệnh nhân /my/dental: giải thích kế hoạch, đơn thuốc, hướng dẫn chăm sóc bằng lời dễ hiểu.

Phạm vi dữ liệu: CHỈ những bệnh nhân người dùng cổng được xem (bản thân, người được giám hộ, thành viên gia đình khi
là chủ hộ – ``res.partner._dmag_portal_patients``). Mọi công cụ kiểm tra phạm vi ở phía máy chủ.
"""
import re

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import html2plaintext

from .dmag_ai_reception import EMERGENCY_WORDS, MEDICAL_WORDS
from .text_utils import fold, has_any, match_words, money

PLAIN_TERMS = [
    ('nội nha', 'chữa tủy – làm sạch và trám kín ống tủy bên trong răng'),
    ('điều trị tủy', 'chữa tủy – làm sạch và trám kín ống tủy bên trong răng'),
    ('mão sứ', 'bọc răng sứ – chụp sứ ôm ngoài để bảo vệ răng yếu'),
    ('chụp sứ', 'bọc răng sứ – chụp sứ ôm ngoài để bảo vệ răng yếu'),
    ('implant', 'trồng răng implant – trụ nhân tạo đặt vào xương hàm thay chân răng đã mất'),
    ('cạo vôi', 'lấy cao răng – làm sạch mảng bám cứng quanh chân răng'),
    ('trám', 'hàn răng – lấp chỗ sâu / mẻ bằng vật liệu cùng màu răng'),
    ('composite', 'vật liệu trám cùng màu răng'),
    ('nhổ răng khôn', 'nhổ răng số 8 (răng mọc cuối cùng)'),
    ('tiểu phẫu', 'thủ thuật nhỏ có gây tê tại chỗ'),
    ('veneer', 'mặt dán sứ mỏng phía trước răng'),
    ('chỉnh nha', 'niềng răng – dùng mắc cài hoặc khay để kéo răng về đúng vị trí'),
    ('x-quang', 'chụp phim để bác sĩ nhìn được chân răng và xương'),
    ('cbct', 'chụp phim 3D để đo xương trước khi cấy implant'),
]

TOOLS = [
    {'name': 'list_my_visits', 'strict': True,
     'description': 'Danh sách lượt khám gần đây và lịch hẹn sắp tới của bệnh nhân đang đăng nhập (và người họ được xem).',
     'input_schema': {'type': 'object', 'properties': {'limit': {'type': 'integer'}}, 'required': ['limit'],
                      'additionalProperties': False}},
    {'name': 'get_visit_detail', 'strict': True,
     'description': 'Nội dung một lượt khám: việc đã làm, chẩn đoán (tên), lời dặn, hướng dẫn chăm sóc, đơn thuốc, lịch tiếp. '
                    'visit_id = 0 → lượt khám hoàn tất gần nhất.',
     'input_schema': {'type': 'object', 'properties': {'visit_id': {'type': 'integer'}}, 'required': ['visit_id'],
                      'additionalProperties': False}},
    {'name': 'get_treatment_plans', 'strict': True,
     'description': 'Kế hoạch điều trị của bệnh nhân: các phương án, dịch vụ từng bước, tổng chi phí theo bảng giá, số buổi, trả góp.',
     'input_schema': {'type': 'object', 'properties': {}, 'required': [], 'additionalProperties': False}},
    {'name': 'get_prescriptions', 'strict': True,
     'description': 'Đơn thuốc đã phát hành: tên thuốc, cách dùng, số ngày, lời dặn. visit_id = 0 → các đơn gần nhất.',
     'input_schema': {'type': 'object', 'properties': {'visit_id': {'type': 'integer'}}, 'required': ['visit_id'],
                      'additionalProperties': False}},
]

SYSTEM = (
    'Bạn là trợ lý trên tài khoản nha khoa của bệnh nhân. Giải thích BẰNG LỜI DỄ HIỂU (không thuật ngữ, câu ngắn, '
    'gạch đầu dòng) dựa DUY NHẤT vào dữ liệu lấy từ công cụ: kế hoạch điều trị, việc đã làm, đơn thuốc, hướng dẫn chăm sóc. '
    'Không chẩn đoán, không đổi / thêm thuốc hay liều, không khuyên khác với lời dặn của bác sĩ, không báo giá ngoài số liệu '
    'trong kế hoạch. Câu hỏi ngoài dữ liệu hoặc cần chuyên môn → khuyên hỏi bác sĩ ở lần hẹn tới hoặc gọi hotline {hotline}. '
    'Dấu hiệu khẩn (chảy máu không cầm, sưng to, sốt, khó thở) → khuyên gọi hotline ngay / đến cơ sở y tế gần nhất. '
    'Xưng "mình", gọi người dùng là "bạn". Tối đa ~150 từ.'
)


def plain(text):
    out = text or ''
    for term, meaning in PLAIN_TERMS:
        if term in out.lower() and meaning not in out:
            out = re.sub('(%s)' % re.escape(term), r'\1 (%s)' % meaning, out, count=1, flags=re.IGNORECASE)
    return out


class DmagAiPortalAssistant(models.AbstractModel):
    _name = 'dmag.ai.portal.assistant'
    _description = 'Trợ lý cổng bệnh nhân (AI-17)'

    # ------------------------------------------------------------------ scope
    @api.model
    def _scope(self, partner):
        if not partner:
            raise AccessError(_('Cần đăng nhập tài khoản bệnh nhân.'))
        return partner.sudo()._dmag_portal_patients()

    @api.model
    def _visit_in_scope(self, partner, visit_id):
        patients = self._scope(partner)
        Visit = self.env['dmag.dental.visit'].sudo()
        if not visit_id:
            visit = Visit.search([('patient_id', 'in', patients.ids), ('state', '=', 'done')],
                                 order='scheduled_start desc', limit=1)
            if not visit:
                raise UserError(_('Chưa có lượt khám hoàn tất.'))
            return visit
        visit = Visit.browse(int(visit_id)).exists()
        if not visit or visit.patient_id not in patients:
            raise AccessError(_('Không có quyền xem lượt khám này.'))
        return visit

    # ------------------------------------------------------------------ tools
    @api.model
    def tool_list_my_visits(self, partner, limit=5):
        patients = self._scope(partner)
        Visit = self.env['dmag.dental.visit'].sudo()
        now = fields.Datetime.now()
        upcoming = Visit.search([('patient_id', 'in', patients.ids), ('state', 'in', ('draft', 'confirmed')),
                                 ('scheduled_start', '>=', now)], order='scheduled_start', limit=3)
        recent = Visit.search([('patient_id', 'in', patients.ids), ('state', '=', 'done')],
                              order='scheduled_start desc', limit=max(1, min(int(limit or 5), 10)))
        return {'upcoming': [v._dmag_portal_card() for v in upcoming], 'recent': [v._dmag_portal_card() for v in recent]}

    @api.model
    def tool_get_visit_detail(self, partner, visit_id=0):
        visit = self._visit_in_scope(partner, visit_id)
        detail = visit._dmag_portal_detail()
        keep = ('id', 'name', 'patient', 'date_display', 'doctor', 'complaint', 'diagnoses', 'procedure_lines', 'advice',
                'aftercare', 'next_visit', 'prescriptions')
        return {k: detail.get(k) for k in keep}

    @api.model
    def tool_get_treatment_plans(self, partner):
        patients = self._scope(partner)
        plans = self.env['dmag.treatment.plan'].sudo().search([('patient_id', 'in', patients.ids),
                                                                ('state', '!=', 'cancel')], order='date desc', limit=3)
        out = []
        for plan in plans:
            out.append({
                'name': plan.name, 'title': plan.title or '', 'patient': plan.patient_id.name,
                'state': dict(plan._fields['state'].selection).get(plan.state), 'progress': round(plan.progress),
                'options': [{
                    'name': o.name, 'recommended': o.is_recommended, 'accepted': o.is_accepted,
                    'summary': o.summary or '', 'total': o.amount_total, 'total_text': money(o.amount_total),
                    'visits': o.estimated_visits, 'installment_months': o.installment_months,
                    'monthly_text': money(o.monthly_amount) if o.installment_months else '',
                    'steps': [{'phase': l.phase, 'service': l.product_id.name,
                               'teeth': l.tooth_ids.mapped('code'), 'done': l.state == 'done'}
                              for l in o.line_ids.sorted(lambda l: (l.phase, l.sequence))],
                } for o in plan.option_ids],
            })
        return {'plans': out}

    @api.model
    def tool_get_prescriptions(self, partner, visit_id=0):
        if 'dmag.prescription' not in self.env:
            return {'prescriptions': [], 'note': 'Phòng khám chưa dùng phân hệ đơn thuốc điện tử.'}
        patients = self._scope(partner)
        Rx = self.env['dmag.prescription'].sudo()
        domain = [('patient_id', 'in', patients.ids), ('state', 'not in', ('draft', 'cancelled', 'replaced'))]
        if visit_id:
            domain.append(('visit_id', '=', self._visit_in_scope(partner, visit_id).id))
        out = []
        for rx in Rx.search(domain, order='date desc', limit=3):
            out.append({
                'code': rx.name, 'date': fields.Datetime.context_timestamp(self, rx.date).strftime('%d/%m/%Y') if rx.date else '',
                'doctor': rx.doctor_id.name or '', 'advice': rx.advice or '',
                're_exam_date': rx.re_exam_date.strftime('%d/%m/%Y') if rx.re_exam_date else '',
                'lines': [{'drug': l.drug_name or l.drug_id.display_name, 'usage': l.usage or '', 'days': l.days,
                           'quantity': l.quantity, 'unit': l.unit or ''} for l in rx.line_ids],
            })
        return {'prescriptions': out}

    @api.model
    def _handlers(self, partner):
        return {
            'list_my_visits': lambda i: self.tool_list_my_visits(partner, i.get('limit', 5)),
            'get_visit_detail': lambda i: self.tool_get_visit_detail(partner, i.get('visit_id', 0)),
            'get_treatment_plans': lambda i: self.tool_get_treatment_plans(partner),
            'get_prescriptions': lambda i: self.tool_get_prescriptions(partner, i.get('visit_id', 0)),
        }

    # ------------------------------------------------------------------ ask
    @api.model
    def ask(self, partner, question, history=None):
        """Trả lời câu hỏi của bệnh nhân. Trả ``{'answer', 'simulated', 'estimated_cost_vnd', 'cost_vnd', 'tools'}``
        hoặc ``{'need_consent': True}``."""
        question = (question or '').strip()[:1000]
        if not question:
            raise UserError(_('Bạn chưa nhập câu hỏi.'))
        if not self.env['dmag.ai'].is_feature_active('AI-17'):
            return {'answer': _('Trợ lý đang tạm tắt. Bạn vui lòng gọi hotline phòng khám để được hỗ trợ.'), 'off': True}
        partner = partner.sudo()
        if self.env.company.dmag_ai_require_consent and not partner.dmag_ai_consent:
            return {'need_consent': True}
        clean_history = []
        for turn in (history or [])[-10:]:
            if isinstance(turn, dict) and turn.get('role') in ('user', 'assistant') and isinstance(turn.get('content'), str):
                if clean_history and clean_history[-1]['role'] == turn['role']:
                    continue
                clean_history.append({'role': turn['role'], 'content': turn['content'][:2000]})
        while clean_history and clean_history[0]['role'] != 'user':
            clean_history.pop(0)
        if clean_history and clean_history[-1]['role'] == 'user':
            clean_history.pop()
        handlers = self._handlers(partner)
        res = self.env['dmag.ai'].run(
            'AI-17', SYSTEM.format(hotline=self.env.company.phone or ''), question, history=clean_history,
            tools=[dict(t) for t in TOOLS], tool_handlers=handlers, patient=partner, record=partner,
            simulate=lambda: self._simulate(partner, question, handlers), max_tokens=3000)
        return {'answer': res.get('text') or '', 'simulated': res.get('simulated'), 'cost_vnd': res.get('cost_vnd'),
                'estimated_cost_vnd': res.get('estimated_cost_vnd'),
                'tools': [t['tool'] for t in res.get('tool_trace') or []]}

    @api.model
    def _simulate(self, partner, question, handlers):
        trace = []

        def call(name, payload):
            try:
                out = handlers[name](payload)
                trace.append({'tool': name, 'input': payload, 'output': out, 'error': False})
                return out
            except (UserError, AccessError) as e:
                trace.append({'tool': name, 'input': payload, 'output': {'error': str(e)}, 'error': True})
                return {'error': str(e)}

        folded = fold(question)
        hotline = self.env.company.phone or 'của phòng khám'
        if match_words(question, EMERGENCY_WORDS + ['sốt', 'sưng']):
            text = ('Những dấu hiệu bạn mô tả cần bác sĩ xem trực tiếp, mình không đánh giá được qua tin nhắn.\n'
                    '• Gọi ngay hotline %s để được hướng dẫn.\n'
                    '• Nếu chảy máu không cầm, sưng lan nhanh, sốt cao hoặc khó thở: đến cơ sở y tế gần nhất ngay.' % hotline)
            return {'text': text, 'tool_trace': trace}
        if has_any(folded, ['kế hoạch', 'phương án', 'điều trị tiếp', 'niềng', 'implant', 'bọc sứ', 'chi phí', 'trả góp']):
            res = call('get_treatment_plans', {})
            plans = res.get('plans') or []
            if not plans:
                return {'text': 'Hiện bạn chưa có kế hoạch điều trị nào trên hệ thống.', 'tool_trace': trace}
            plan = plans[0]
            lines = ['Kế hoạch "%s" của %s (%s, đã làm %s%%):' % (plan['title'] or plan['name'], plan['patient'],
                                                                 plan['state'], plan['progress'])]
            for opt in plan['options']:
                tag = ' – bác sĩ khuyên dùng' if opt['recommended'] else ''
                tag += ' – bạn đã chọn' if opt['accepted'] else ''
                lines.append('\n%s%s: %s, khoảng %s buổi%s.' % (opt['name'], tag, opt['total_text'], opt['visits'] or 1,
                                                                 (', trả góp %s tháng × %s' % (opt['installment_months'], opt['monthly_text']))
                                                                 if opt['installment_months'] else ''))
                for step in opt['steps'][:6]:
                    lines.append('  • Buổi %s: %s%s%s' % (step['phase'], plain(step['service']),
                                                          (' – răng ' + ', '.join(step['teeth'])) if step['teeth'] else '',
                                                          ' (đã xong)' if step['done'] else ''))
                if opt['summary']:
                    lines.append('  Bác sĩ ghi chú: %s' % opt['summary'])
            lines.append('\nChi phí theo bảng giá của phòng khám; câu hỏi chuyên môn bạn hỏi bác sĩ ở lần hẹn tới nhé.')
            return {'text': '\n'.join(lines), 'tool_trace': trace}
        if has_any(folded, ['thuốc', 'đơn thuốc', 'uống', 'kháng sinh', 'giảm đau']):
            res = call('get_prescriptions', {'visit_id': 0})
            rxs = res.get('prescriptions') or []
            if not rxs:
                return {'text': 'Mình chưa thấy đơn thuốc nào đã phát hành cho bạn. %s'
                                % (res.get('note') or ''), 'tool_trace': trace}
            rx = rxs[0]
            lines = ['Đơn thuốc %s ngày %s (BS %s):' % (rx['code'], rx['date'], rx['doctor'])]
            for line in rx['lines']:
                lines.append('• %s: %s%s' % (line['drug'], line['usage'] or 'theo hướng dẫn trên đơn',
                                             (' – trong %s ngày' % line['days']) if line['days'] else ''))
            if rx['advice']:
                lines.append('Lời dặn: %s' % rx['advice'])
            lines.append('Lưu ý chung: uống đúng giờ, đủ số ngày; không tự ý ngưng hay đổi thuốc. Nếu nổi mẩn, ngứa, '
                         'khó thở → ngưng thuốc và gọi %s ngay.' % hotline)
            return {'text': '\n'.join(lines), 'tool_trace': trace}
        if has_any(folded, ['lịch hẹn', 'lịch', 'hẹn', 'khi nào']):
            res = call('list_my_visits', {'limit': 3})
            if res.get('upcoming'):
                lines = ['Lịch hẹn sắp tới của bạn:'] + ['• %s – %s%s' % (v['start_display'], ', '.join(v['services']) or 'Khám',
                                                                          (' với BS %s' % v['doctor']) if v['doctor'] else '')
                                                         for v in res['upcoming']]
            else:
                lines = ['Bạn chưa có lịch hẹn sắp tới. Bạn có thể đặt lịch tại mục "Đặt lịch".']
            return {'text': '\n'.join(lines), 'tool_trace': trace}
        if has_any(folded, MEDICAL_WORDS + ['có sao', 'bị sao', 'bình thường không']):
            return {'text': 'Câu hỏi này cần bác sĩ thăm khám mới trả lời chính xác được – mình không chẩn đoán qua tin '
                            'nhắn. Bạn ghi lại để hỏi bác sĩ ở lần hẹn tới, hoặc gọi hotline %s nếu cần sớm.' % hotline,
                    'tool_trace': trace}
        # mặc định: hướng dẫn chăm sóc của lần khám gần nhất
        res = call('get_visit_detail', {'visit_id': 0})
        if res.get('error'):
            return {'text': 'Mình có thể giải thích kế hoạch điều trị, đơn thuốc, lời dặn sau khám và lịch hẹn của bạn. '
                            'Bạn muốn hỏi về mục nào?', 'tool_trace': trace}
        lines = ['Lần khám %s với BS %s:' % (res.get('date_display'), res.get('doctor') or '')]
        procs = res.get('procedure_lines') or []
        if procs:
            lines.append('Việc đã làm: ' + '; '.join(plain(p['name']) for p in procs) + '.')
        if res.get('advice'):
            lines.append('Bác sĩ dặn: %s' % res['advice'])
        for care in (res.get('aftercare') or [])[:2]:
            note = html2plaintext(care['note']).strip()
            lines.append('Chăm sóc sau %s:\n%s' % (care['service'], note[:600]))
        if res.get('next_visit'):
            lines.append('Lịch tiếp theo: %s.' % res['next_visit'].get('start_display'))
        lines.append('Nếu đau tăng, chảy máu nhiều hoặc sốt, bạn gọi ngay %s nhé.' % hotline)
        return {'text': '\n'.join(lines), 'tool_trace': trace}
