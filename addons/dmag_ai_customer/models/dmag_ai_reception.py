"""AI-07 – Trợ lý Zalo OA 24/7: công cụ (tool) gọi dữ liệu THẬT của Odoo + bộ trả lời giả lập theo dữ liệu.

* Chế độ Claude: ``dmag.ai.run('AI-07', tools=TOOLS, tool_handlers=...)`` – Claude tự quyết gọi công cụ
  (không ép ``tool_choice``), công cụ ``strict`` + ``additionalProperties: false``.
* Chế độ giả lập: nhận diện ý định bằng từ khóa → gọi ĐÚNG các công cụ trên → giờ trống / giá thật, đặt lịch
  nháp thật để lễ tân xác nhận.

Nguyên tắc: không chẩn đoán, không báo giá ngoài bảng giá, khiếu nại / ca khẩn → chuyển nhân viên ngay.
"""
import json
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .text_utils import (extract_date, extract_part_of_day, extract_phone, extract_time, fold, given_name, has_any,
                         match_words, money)

EMERGENCY_WORDS = ['chảy máu không cầm', 'chảy máu nhiều', 'sưng to', 'sưng mặt', 'sốt cao', 'khó thở', 'khó nuốt',
                   'tai nạn', 'gãy răng', 'văng răng', 'rơi răng', 'đau dữ dội', 'đau không chịu nổi', 'cấp cứu',
                   'mủ', 'ngất']
COMPLAINT_WORDS = ['khiếu nại', 'phàn nàn', 'bực', 'tệ', 'thất vọng', 'lừa', 'hoàn tiền', 'đền', 'không hài lòng',
                   'quá tệ', 'thái độ', 'kiện', 'review xấu', 'bóc phốt', 'chờ lâu quá', 'làm ăn']
MEDICAL_WORDS = ['có sao không', 'bị gì', 'bệnh gì', 'uống thuốc gì', 'thuốc gì', 'có nguy hiểm', 'chẩn đoán',
                 'có phải bị', 'có cần nhổ không', 'nên làm gì', 'có bình thường không']
BOOK_WORDS = ['đặt lịch', 'đặt hẹn', 'hẹn lịch', 'đặt chỗ', 'book', 'lấy lịch', 'muốn khám', 'muốn đến', 'qua khám',
              'đến khám', 'đăng ký khám', 'giữ chỗ', 'lịch trống', 'giờ trống', 'còn lịch', 'đổi lịch']
PRICE_WORDS = ['giá', 'bao nhiêu', 'chi phí', 'bảng giá', 'phí', 'tiền', 'báo giá']
HOURS_WORDS = ['mấy giờ', 'giờ mở cửa', 'giờ làm việc', 'mở cửa', 'đóng cửa', 'làm việc', 'chủ nhật', 'giờ giấc']
ADDRESS_WORDS = ['địa chỉ', 'ở đâu', 'chỗ nào', 'đường nào', 'chỉ đường', 'bản đồ', 'gửi xe', 'đậu xe']
PAYMENT_WORDS = ['trả góp', 'thanh toán', 'quẹt thẻ', 'chuyển khoản']
PREP_WORDS = ['chuẩn bị', 'mang theo', 'cần mang', 'nhịn ăn', 'trước khi khám']
GREET_WORDS = ['xin chào', 'chào', 'hello', 'hi', 'alo', 'ad ơi', 'shop ơi', 'phòng khám ơi']
YES_WORDS = ['đồng ý', 'ok', 'oke', 'okay', 'được', 'vâng', 'dạ', 'ừ', 'yes', 'chốt', 'xác nhận', 'đúng rồi', 'có']
NO_WORDS = ['không đồng ý', 'không', 'thôi', 'hủy']
THANKS_WORDS = ['cảm ơn', 'cám ơn', 'thanks', 'thank']

# Gợi ý dịch vụ theo triệu chứng – KHÔNG chẩn đoán, chỉ gợi ý "khám" phù hợp
SERVICE_HINTS = [
    (['cạo vôi', 'lấy cao', 'vôi răng', 'cao răng', 'vệ sinh răng', 'làm sạch'], ['cạo vôi', 'lấy cao', 'vệ sinh']),
    (['niềng', 'chỉnh nha', 'răng hô', 'răng móm', 'răng lệch', 'invisalign', 'khay trong'], ['chỉnh nha', 'niềng']),
    (['implant', 'cấy ghép', 'trồng răng', 'mất răng'], ['implant']),
    (['tẩy trắng', 'trắng răng', 'răng ố', 'răng vàng'], ['tẩy trắng']),
    (['bọc sứ', 'răng sứ', 'mão sứ', 'veneer', 'dán sứ'], ['sứ', 'veneer']),
    (['trám', 'hàn răng', 'sâu răng', 'lỗ sâu'], ['trám']),
    (['nhổ răng', 'răng khôn', 'nhổ'], ['nhổ']),
    (['tủy', 'lấy tủy', 'chữa tủy', 'nội nha'], ['tủy', 'nội nha']),
    (['x-quang', 'chụp phim', 'cbct', 'xquang'], ['x-quang', 'cbct', 'phim']),
    (['đau răng', 'ê buốt', 'nhức răng', 'khám', 'kiểm tra', 'tư vấn'], ['khám']),
]

TOOLS = [
    {
        'name': 'search_services',
        'description': 'Tra dịch vụ nha khoa trong BẢNG GIÁ của phòng khám (tên, giá niêm yết VNĐ, thời lượng). '
                       'Dùng trước khi nói về giá – không bao giờ tự nêu giá không có trong kết quả.',
        'strict': True,
        'input_schema': {
            'type': 'object',
            'properties': {'query': {'type': 'string', 'description': 'Từ khóa dịch vụ, ví dụ "cạo vôi", "implant"; để trống = tất cả'}},
            'required': ['query'], 'additionalProperties': False,
        },
    },
    {
        'name': 'get_free_slots',
        'description': 'Giờ còn trống (giờ Việt Nam) trong một ngày cho các dịch vụ đã chọn, đã xếp hạng gợi ý. '
                       'Trả về tối đa 6 khung kèm bác sĩ dự kiến.',
        'strict': True,
        'input_schema': {
            'type': 'object',
            'properties': {
                'date': {'type': 'string', 'description': 'YYYY-MM-DD'},
                'service_ids': {'type': 'array', 'items': {'type': 'integer'}},
                'part_of_day': {'type': 'string', 'enum': ['any', 'morning', 'afternoon', 'evening']},
            },
            'required': ['date', 'service_ids', 'part_of_day'], 'additionalProperties': False,
        },
    },
    {
        'name': 'find_patient_by_phone',
        'description': 'Kiểm tra số điện thoại đã có hồ sơ chưa. Chỉ trả về có/không và tên gọi để chào – '
                       'không trả dữ liệu khám chữa bệnh (khách nhắn qua Zalo chưa được xác minh danh tính).',
        'strict': True,
        'input_schema': {
            'type': 'object',
            'properties': {'phone': {'type': 'string'}},
            'required': ['phone'], 'additionalProperties': False,
        },
    },
    {
        'name': 'book_appointment',
        'description': 'Giữ chỗ lịch hẹn: tạo lịch ở trạng thái "Đã đặt lịch" (nháp) để LỄ TÂN GỌI XÁC NHẬN. '
                       'Chỉ gọi khi đã có họ tên, số điện thoại, ngày, giờ lấy từ get_free_slots và khách đã ĐỒNG Ý '
                       'cho phòng khám lưu thông tin (NĐ 13/2023).',
        'strict': True,
        'input_schema': {
            'type': 'object',
            'properties': {
                'name': {'type': 'string'},
                'phone': {'type': 'string'},
                'date': {'type': 'string', 'description': 'YYYY-MM-DD'},
                'time': {'type': 'string', 'description': 'HH:MM'},
                'service_ids': {'type': 'array', 'items': {'type': 'integer'}},
                'doctor_id': {'type': 'integer', 'description': '0 = bác sĩ bất kỳ'},
                'note': {'type': 'string'},
                'consent': {'type': 'boolean', 'description': 'Khách đã đồng ý cho lưu & xử lý thông tin cá nhân'},
            },
            'required': ['name', 'phone', 'date', 'time', 'service_ids', 'doctor_id', 'note', 'consent'],
            'additionalProperties': False,
        },
    },
    {
        'name': 'get_clinic_info',
        'description': 'Thông tin phòng khám: giờ làm việc, địa chỉ, hotline, gửi xe, thanh toán, chuẩn bị trước khi khám.',
        'strict': True,
        'input_schema': {
            'type': 'object',
            'properties': {'topic': {'type': 'string', 'enum': ['hours', 'address', 'parking', 'payment', 'preparation', 'all']}},
            'required': ['topic'], 'additionalProperties': False,
        },
    },
    {
        'name': 'handoff_to_staff',
        'description': 'Chuyển hội thoại cho nhân viên ngay khi: khách khiếu nại / bực bội, ca khẩn (chảy máu không cầm, '
                       'sưng to, sốt, chấn thương), câu hỏi chuyên môn cần bác sĩ, hoặc khách muốn gặp người.',
        'strict': True,
        'input_schema': {
            'type': 'object',
            'properties': {
                'reason': {'type': 'string', 'enum': ['complaint', 'emergency', 'medical_question', 'human_request', 'other']},
                'summary': {'type': 'string', 'description': 'Tóm tắt 1–2 câu cho nhân viên'},
            },
            'required': ['reason', 'summary'], 'additionalProperties': False,
        },
    },
]

SYSTEM_PROMPT = """Bạn là trợ lý tư vấn qua Zalo OA của {clinic}. Hôm nay là {today} ({weekday}), giờ Việt Nam.
Nhiệm vụ: trả lời thân thiện, ngắn gọn (tối đa 4–5 câu, có thể gạch đầu dòng), xưng "em", gọi khách là "anh/chị"
(hoặc theo tên khách nếu biết).

QUY TẮC BẮT BUỘC
1. Giá: chỉ nêu giá lấy từ công cụ search_services (bảng giá phòng khám), ghi rõ "giá niêm yết, bác sĩ sẽ tư vấn
   chi phí chính xác sau khi khám". Không có trong bảng giá → nói chưa có giá niêm yết và đề nghị khám.
2. KHÔNG chẩn đoán, không kê thuốc, không hứa kết quả. Câu hỏi chuyên môn → khuyên đặt lịch khám; nếu khách cần
   bác sĩ trả lời ngay → handoff_to_staff (medical_question).
3. Khiếu nại, khách bực bội, hoặc dấu hiệu khẩn (chảy máu không cầm, sưng to, sốt, khó thở, chấn thương) →
   gọi handoff_to_staff NGAY, xin lỗi / trấn an; ca khẩn: khuyên gọi hotline {hotline} hoặc đến cơ sở y tế gần nhất.
4. Đặt lịch: hỏi dịch vụ + ngày mong muốn → get_free_slots → đưa 2–4 giờ gợi ý → xin họ tên và số điện thoại →
   hỏi khách ĐỒNG Ý cho phòng khám lưu thông tin để đặt lịch (NĐ 13/2023) → book_appointment. Nói rõ lịch đang
   "giữ chỗ, lễ tân sẽ gọi/nhắn xác nhận". Không tự bịa giờ trống.
5. Không hỏi / không tiết lộ thông tin sức khỏe qua Zalo. find_patient_by_phone chỉ để chào đúng tên.
6. Không gửi đường dẫn lạ; chỉ dùng thông tin từ công cụ get_clinic_info.
"""

WEEKDAY_VI = ['Thứ Hai', 'Thứ Ba', 'Thứ Tư', 'Thứ Năm', 'Thứ Sáu', 'Thứ Bảy', 'Chủ nhật']


class DmagAiReception(models.AbstractModel):
    _name = 'dmag.ai.reception'
    _description = 'Trợ lý Zalo OA (AI-07): công cụ & bộ trả lời giả lập'

    # ------------------------------------------------------------------ tools (dữ liệu thật)
    @api.model
    def _services(self):
        return self.env['product.product'].sudo().search([
            ('is_dental_service', '=', True), ('sale_ok', '=', True),
            ('company_id', 'in', [False] + self.env.companies.ids)], order='name')

    @api.model
    def _service_price(self, product):
        """Giá niêm yết của dịch vụ = giá bán trên danh mục dịch vụ (cùng nguồn với màn hình đặt lịch / kế hoạch)."""
        return product.lst_price

    @api.model
    def tool_search_services(self, query):
        products = self._services()
        q = fold(query)
        if q:
            words = [w for w in q.split() if len(w) > 1]
            matched = products.filtered(lambda p: q in fold(p.name) or (words and all(w in fold(p.name) for w in words)))
            if not matched:
                for triggers, keys in SERVICE_HINTS:
                    if has_any(q, triggers) or any(fold(k) in q for k in keys):
                        matched = products.filtered(lambda p: any(fold(k) in fold(p.name) for k in keys))
                        if matched:
                            break
            products = matched
        return {'services': [{
            'id': p.id, 'name': p.name, 'price_vnd': round(self._service_price(p)),
            'price_text': money(self._service_price(p)), 'duration_min': p.dental_duration or 30,
            'category': dict(p._fields['dental_category']._description_selection(self.env)).get(p.dental_category, ''),
        } for p in products[:8]], 'note': 'Giá niêm yết theo bảng giá phòng khám; chi phí cuối cùng theo chỉ định sau khi khám.'}

    @api.model
    def tool_get_free_slots(self, date, service_ids=None, part_of_day='any'):
        try:
            day = fields.Date.from_string(date)
        except (TypeError, ValueError):
            raise UserError(_('Ngày không hợp lệ: %s (cần YYYY-MM-DD).', date))
        today = fields.Date.context_today(self)
        if day < today or day > today + timedelta(days=90):
            return {'date': date, 'slots': [], 'message': 'Chỉ nhận đặt lịch từ hôm nay đến 90 ngày tới.'}
        services = self.env['product.product'].sudo().browse([int(s) for s in service_ids or []]).exists()
        duration = sum(services.mapped('dental_duration')) or 30
        res = self.env['dmag.workspace'].sudo().get_slot_suggestions(
            date, False, duration, services.ids, False, part_of_day, limit=6)
        slots = res.get('suggestions') or []
        if not res.get('active'):
            free = self.env['dmag.workspace'].sudo().get_free_slots(date, False, duration)[:6]
            slots = [{'time': s['time'], 'doctor_id': False, 'doctor': '', 'chair_id': s['chairs'][0]} for s in free]
        slots = sorted(slots, key=lambda s: s['time'])
        return {
            'date': date, 'weekday': WEEKDAY_VI[day.weekday()], 'duration_min': duration,
            'services': services.mapped('name'),
            'slots': [{'time': s['time'], 'doctor_id': s.get('doctor_id') or 0, 'doctor': s.get('doctor') or '',
                       'chair_id': s.get('chair_id') or 0} for s in slots],
        }

    @api.model
    def tool_find_patient_by_phone(self, phone):
        num = ''.join(ch for ch in phone or '' if ch.isdigit())
        partner = self.env['dmag.workspace'].sudo()._find_by_phone(num)
        if not partner:
            return {'found': False}
        return {'found': True, 'greeting_name': given_name(partner.name),
                'salutation': 'anh' if partner.gender == 'male' else 'chị' if partner.gender == 'female' else 'anh/chị'}

    @api.model
    def _zalo_source(self):
        Source = self.env['dmag.customer.source'].sudo()
        source = Source.search([('code', '=', 'ZALO_AI')], limit=1) or Source.search([('name', 'ilike', 'zalo')], limit=1)
        return source or Source.create({'name': 'Zalo OA (trợ lý AI)', 'code': 'ZALO_AI'})

    @api.model
    def tool_book_appointment(self, conversation, vals):
        if not vals.get('consent'):
            raise UserError(_('Khách chưa đồng ý cho lưu thông tin cá nhân – hãy hỏi đồng ý trước khi đặt lịch.'))
        name = (vals.get('name') or '').strip()
        phone = ''.join(ch for ch in vals.get('phone') or '' if ch.isdigit())
        if len(name) < 2 or len(phone) < 9:
            raise UserError(_('Cần họ tên và số điện thoại hợp lệ để giữ chỗ.'))
        Workspace = self.env['dmag.workspace'].sudo()
        partner = Workspace._find_by_phone(phone)
        if not partner:
            partner = self.env['res.partner'].sudo().create({
                'name': name, 'mobile': phone, 'is_patient': True, 'data_consent': True,
                'customer_source_id': self._zalo_source().id,
                'comment': _('Tạo từ trợ lý Zalo AI – lễ tân kiểm tra lại thông tin khi khách đến.'),
            })
        elif not partner.data_consent:
            partner.write({'data_consent': True})
        services = self.env['product.product'].sudo().browse([int(s) for s in vals.get('service_ids') or []]).exists()
        duration = sum(services.mapped('dental_duration')) or 30
        free = self.tool_get_free_slots(vals['date'], services.ids, 'any')
        open_slots = Workspace.get_free_slots(vals['date'], False, duration)
        wanted = (vals.get('time') or '').strip()[:5]
        slot = next((s for s in open_slots if s['time'] == wanted), None)
        if not slot:
            return {'booked': False, 'message': 'Giờ %s ngày %s không còn trống.' % (wanted, vals['date']),
                    'alternatives': [s['time'] for s in free['slots'][:4]]}
        doctor_id = int(vals.get('doctor_id') or 0)
        hint = next((s for s in free['slots'] if s['time'] == wanted), None)
        if not doctor_id and hint:
            doctor_id = hint.get('doctor_id') or 0
        chair_id = (hint or {}).get('chair_id') or slot['chairs'][0]
        if chair_id not in slot['chairs']:
            chair_id = slot['chairs'][0]
        note = (vals.get('note') or '').strip()
        res = Workspace.quick_book({
            'patient_id': partner.id, 'doctor_id': doctor_id or False, 'chair_id': chair_id,
            'service_ids': services.ids, 'date': vals['date'], 'time': wanted, 'confirm': False,
            'reason': ('Đặt qua Zalo AI – chờ lễ tân xác nhận' + (': ' + note if note else ''))[:250],
            'source_id': self._zalo_source().id,
        })
        visit = self.env['dmag.dental.visit'].sudo().browse(res['id'])
        visit.write({'dmag_ai_conversation_id': conversation.id if conversation else False})
        visit.message_post(body=_('Lịch giữ chỗ do trợ lý AI tạo từ hội thoại %(conv)s (%(mode)s). Lễ tân gọi xác nhận '
                                  'rồi bấm "Xác nhận".', conv=conversation.display_name if conversation else '-',
                                  mode=self.env.company.dmag_ai_mode))
        if conversation:
            conversation.sudo().write({'partner_id': partner.id, 'phone': conversation.phone or phone,
                                       'visit_ids': [(4, visit.id)]})
        return {'booked': True, 'visit_id': visit.id, 'visit': visit.name, 'patient': partner.name,
                'date': vals['date'], 'time': wanted, 'doctor': visit.doctor_id.name or '', 'chair': visit.chair_id.name or '',
                'services': services.mapped('name'), 'state': 'Đã đặt lịch – chờ lễ tân xác nhận'}

    @api.model
    def tool_get_clinic_info(self, topic='all'):
        company = self.env.company.sudo()
        address = ', '.join(x for x in [company.street, company.street2, company.city] if x) or company.name
        info = {
            'clinic': company.name, 'hours': company.dmag_ai_clinic_hours, 'address': address,
            'hotline': company.phone or '', 'parking': company.dmag_ai_parking_info,
            'payment': company.dmag_ai_payment_info, 'preparation': company.dmag_ai_preparation_info,
        }
        if topic and topic != 'all':
            keep = {'hours': ['hours', 'hotline'], 'address': ['address', 'parking', 'hotline'],
                    'parking': ['parking', 'address'], 'payment': ['payment'], 'preparation': ['preparation']}
            info = {k: v for k, v in info.items() if k in keep.get(topic, info) or k == 'clinic'}
        return info

    @api.model
    def tool_handoff_to_staff(self, conversation, reason, summary):
        if conversation:
            conversation.sudo()._handoff(reason, summary)
        return {'handed_off': True, 'message': 'Đã chuyển nhân viên – nhân viên sẽ trả lời trong giờ làm việc; '
                                                'ca khẩn: gọi hotline.'}

    @api.model
    def _handlers(self, conversation):
        return {
            'search_services': lambda i: self.tool_search_services(i.get('query', '')),
            'get_free_slots': lambda i: self.tool_get_free_slots(i['date'], i.get('service_ids'), i.get('part_of_day', 'any')),
            'find_patient_by_phone': lambda i: self.tool_find_patient_by_phone(i.get('phone')),
            'book_appointment': lambda i: self.tool_book_appointment(conversation, i),
            'get_clinic_info': lambda i: self.tool_get_clinic_info(i.get('topic', 'all')),
            'handoff_to_staff': lambda i: self.tool_handoff_to_staff(conversation, i.get('reason', 'other'), i.get('summary', '')),
        }

    @api.model
    def get_tools(self):
        return [dict(t) for t in TOOLS]

    @api.model
    def _system_prompt(self):
        today = fields.Date.context_today(self)
        company = self.env.company
        return SYSTEM_PROMPT.format(clinic=company.name, today=today.strftime('%d/%m/%Y'),
                                    weekday=WEEKDAY_VI[today.weekday()], hotline=company.phone or '')

    # ------------------------------------------------------------------ simulated responder
    @api.model
    def simulate_reply(self, conversation, text):
        """Bộ trả lời giả lập: ý định theo từ khóa → gọi công cụ thật → câu trả lời + gợi ý trả lời nhanh."""
        trace = []

        def call(name, payload, fn):
            try:
                out = fn()
                trace.append({'tool': name, 'input': payload, 'output': out, 'error': False})
                return out
            except UserError as e:
                trace.append({'tool': name, 'input': payload, 'output': {'error': str(e)}, 'error': True})
                return {'error': str(e)}

        handlers = self._handlers(conversation)
        state = conversation._sim_state()
        folded = fold(text)
        today = fields.Date.context_today(self)
        reply, quick = '', []

        def out(r, q=None):
            conversation._sim_save(state)
            return {'text': r, 'data': {'quick_replies': q or []}, 'tool_trace': trace}

        # 1) Khẩn cấp / khiếu nại → chuyển người ngay
        if match_words(text, EMERGENCY_WORDS):
            payload = {'reason': 'emergency', 'summary': text[:200]}
            call('handoff_to_staff', payload, lambda: handlers['handoff_to_staff'](payload))
            info = handlers['get_clinic_info']({'topic': 'hours'})
            return out('Dạ em rất tiếc anh/chị đang gặp tình trạng này. Đây là dấu hiệu cần được bác sĩ xem ngay – '
                       'em đã chuyển cho nhân viên trực để gọi lại cho anh/chị.\n'
                       '• Gọi ngay hotline %s để được hướng dẫn.\n'
                       '• Nếu chảy máu nhiều, sưng lan, sốt cao hoặc khó thở: anh/chị đến cơ sở y tế gần nhất ngay ạ.'
                       % (info.get('hotline') or 'của phòng khám'))
        if has_any(folded, COMPLAINT_WORDS):
            payload = {'reason': 'complaint', 'summary': text[:200]}
            call('handoff_to_staff', payload, lambda: handlers['handoff_to_staff'](payload))
            return out('Dạ em thành thật xin lỗi vì trải nghiệm chưa tốt của anh/chị. Em đã chuyển ngay cho quản lý '
                       'chăm sóc khách hàng – anh/chị sẽ được liên hệ sớm nhất trong hôm nay để giải quyết ạ.')
        if has_any(folded, ['gặp nhân viên', 'gặp người', 'nói chuyện với người', 'tư vấn viên', 'gặp bác sĩ']):
            payload = {'reason': 'human_request', 'summary': text[:200]}
            call('handoff_to_staff', payload, lambda: handlers['handoff_to_staff'](payload))
            return out('Dạ em đã chuyển cho nhân viên tư vấn, anh/chị vui lòng chờ trong giây lát ạ.')

        # 2) Đang trong luồng đặt lịch: thu thập giờ / tên / SĐT / đồng ý
        stage = state.get('stage')
        phone = extract_phone(text)
        if phone:
            state['phone'] = phone
            found = call('find_patient_by_phone', {'phone': phone}, lambda: handlers['find_patient_by_phone']({'phone': phone}))
            if found.get('found') and not state.get('name'):
                state['known_name'] = found.get('greeting_name')
        name = self._extract_name(text, stage)
        if name:
            state['name'] = name
        wanted_time = extract_time(text)
        if stage == 'pick_slot' and not wanted_time:
            for slot in state.get('slots', []):
                if slot in text:
                    wanted_time = slot
        if wanted_time and state.get('date'):
            state['time'] = wanted_time
        if stage == 'consent':
            if has_any(folded, ['không đồng ý', 'không muốn']) or folded in ('khong', 'thoi'):
                state.update(stage=None)
                return out('Dạ vâng, em chưa lưu thông tin của anh/chị. Khi cần anh/chị cứ nhắn em hoặc gọi hotline ạ.')
            if has_any(folded, YES_WORDS):
                state['consent'] = True

        # 3) Câu hỏi thông tin
        if not stage or stage in ('done',):
            if has_any(folded, HOURS_WORDS) and not has_any(folded, BOOK_WORDS):
                info = call('get_clinic_info', {'topic': 'hours'}, lambda: handlers['get_clinic_info']({'topic': 'hours'}))
                return out('Dạ phòng khám làm việc: %s.\nHotline: %s. Anh/chị muốn em giữ chỗ khung giờ nào không ạ?'
                           % (info.get('hours'), info.get('hotline') or '-'), ['Đặt lịch hôm nay', 'Đặt lịch ngày mai'])
            if has_any(folded, ADDRESS_WORDS):
                info = call('get_clinic_info', {'topic': 'address'}, lambda: handlers['get_clinic_info']({'topic': 'address'}))
                return out('Dạ địa chỉ phòng khám: %s.\n%s' % (info.get('address'), info.get('parking') or ''),
                           ['Giờ làm việc', 'Đặt lịch'])
            if has_any(folded, PAYMENT_WORDS):
                info = call('get_clinic_info', {'topic': 'payment'}, lambda: handlers['get_clinic_info']({'topic': 'payment'}))
                return out('Dạ phòng khám nhận: %s' % info.get('payment'), ['Bảng giá', 'Đặt lịch'])
            if has_any(folded, PREP_WORDS):
                info = call('get_clinic_info', {'topic': 'preparation'}, lambda: handlers['get_clinic_info']({'topic': 'preparation'}))
                return out('Dạ trước khi đến anh/chị chuẩn bị giúp em: %s' % info.get('preparation'), ['Đặt lịch'])
            if has_any(folded, MEDICAL_WORDS):
                return out('Dạ câu hỏi này cần bác sĩ trực tiếp thăm khám mới trả lời chính xác được ạ – em không thể '
                           'chẩn đoán qua tin nhắn. Anh/chị đặt lịch khám để bác sĩ kiểm tra nhé, hoặc em chuyển '
                           'câu hỏi cho nhân viên tư vấn?', ['Đặt lịch khám', 'Gặp nhân viên'])

        # 4) Dịch vụ / giá
        service_query = self._detect_service(folded)
        if service_query:
            res = call('search_services', {'query': service_query},
                       lambda: handlers['search_services']({'query': service_query}))
            found = res.get('services') or []
            if found:
                best = max(found, key=lambda svc: sum(1 for w in fold(svc['name']).split() if len(w) > 1 and w in folded.split()))
                found = [best] + [svc for svc in found if svc is not best]
            if found and (has_any(folded, PRICE_WORDS) or not has_any(folded, BOOK_WORDS) and not stage):
                lines = '\n'.join('• %s: %s (~%s phút)' % (s['name'], s['price_text'], s['duration_min']) for s in found[:5])
                state['service_ids'] = [found[0]['id']]
                return out('Dạ bảng giá niêm yết của phòng khám:\n%s\nChi phí chính xác bác sĩ sẽ tư vấn sau khi khám ạ. '
                           'Anh/chị muốn đặt lịch không ạ?' % lines, ['Đặt lịch hôm nay', 'Đặt lịch ngày mai', 'Địa chỉ'])
            if found:
                state['service_ids'] = [found[0]['id']]
                state['service_name'] = found[0]['name']
        elif has_any(folded, PRICE_WORDS) and not stage:
            res = call('search_services', {'query': ''}, lambda: handlers['search_services']({'query': ''}))
            lines = '\n'.join('• %s: %s' % (s['name'], s['price_text']) for s in (res.get('services') or [])[:6])
            return out('Dạ một số dịch vụ trong bảng giá niêm yết:\n%s\nAnh/chị quan tâm dịch vụ nào ạ?' % lines,
                       ['Cạo vôi răng', 'Niềng răng', 'Implant'])

        # 5) Đặt lịch
        date = extract_date(text, today)
        if stage == 'done' and (has_any(folded, BOOK_WORDS) or date):
            keep = {k: state.get(k) for k in ('name', 'phone', 'consent', 'known_name', 'service_ids', 'service_name')}
            state.clear()
            state.update({k: v for k, v in keep.items() if v})
            stage = None
        if date:
            state['date'] = date.isoformat()
        if has_any(folded, BOOK_WORDS) or date or stage not in (None, 'done'):
            if not state.get('stage'):
                state['stage'] = 'collect'
            if not state.get('date'):
                return out('Dạ anh/chị muốn đặt lịch %sngày nào ạ? (ví dụ: chiều nay, sáng mai, thứ 7)'
                           % (('cho ' + state['service_name'] + ' ') if state.get('service_name') else ''),
                           ['Chiều nay', 'Sáng mai', 'Thứ 7'])
            part = extract_part_of_day(text)
            if part != 'any':
                state['part'] = part
            if not state.get('time'):
                payload = {'date': state['date'], 'service_ids': state.get('service_ids') or [],
                           'part_of_day': state.get('part', 'any')}
                res = call('get_free_slots', payload, lambda: handlers['get_free_slots'](payload))
                slots = res.get('slots') or []
                if not slots and payload['part_of_day'] != 'any':
                    payload = dict(payload, part_of_day='any')
                    res = call('get_free_slots', payload, lambda: handlers['get_free_slots'](payload))
                    slots = res.get('slots') or []
                if not slots:
                    state['date'] = False
                    return out('Dạ ngày %s đã kín lịch hoặc ngoài thời gian nhận đặt. Anh/chị chọn ngày khác giúp em nhé?'
                               % self._fmt_date(payload['date']), ['Ngày mai', 'Thứ 7'])
                state['slots'] = [s['time'] for s in slots[:4]]
                state['slot_doctors'] = {s['time']: s['doctor_id'] for s in slots}
                state['stage'] = 'pick_slot'
                lines = ', '.join(s['time'] + (' (%s)' % s['doctor'] if s['doctor'] else '') for s in slots[:4])
                svc = (' cho %s' % ', '.join(res.get('services'))) if res.get('services') else ''
                return out('Dạ %s %s còn các giờ trống%s: %s.\nAnh/chị chọn giờ nào ạ?'
                           % (res.get('weekday', ''), self._fmt_date(payload['date']), svc, lines), state['slots'])
            if not state.get('name') or not state.get('phone'):
                state['stage'] = 'contact'
                need = []
                if not state.get('name'):
                    need.append('họ tên')
                if not state.get('phone'):
                    need.append('số điện thoại')
                hello = ('Dạ chào %s! ' % state['known_name']) if state.get('known_name') and not state.get('name') else 'Dạ '
                return out('%sem giữ giờ %s ngày %s. Anh/chị cho em xin %s để lễ tân xác nhận ạ.'
                           % (hello, state['time'], self._fmt_date(state['date']), ' và '.join(need)))
            if not state.get('consent'):
                state['stage'] = 'consent'
                return out('Dạ để giữ chỗ, anh/chị đồng ý cho phòng khám lưu họ tên và số điện thoại để đặt lịch và '
                           'chăm sóc sau khám (theo Nghị định 13/2023) không ạ?', ['Đồng ý', 'Không đồng ý'])
            payload = {'name': state['name'], 'phone': state['phone'], 'date': state['date'], 'time': state['time'],
                       'service_ids': state.get('service_ids') or [],
                       'doctor_id': int((state.get('slot_doctors') or {}).get(state['time']) or 0),
                       'note': '', 'consent': True}
            res = call('book_appointment', payload, lambda: handlers['book_appointment'](payload))
            if res.get('booked'):
                state.update(stage='done', last_visit=res['visit'], time=False, slots=[])
                return out('Dạ em đã giữ chỗ cho %s lúc %s %s%s%s.\nMã lịch: %s. Lễ tân sẽ gọi/nhắn xác nhận trong giờ '
                           'làm việc ạ. Anh/chị nhớ mang theo CCCD nhé!'
                           % (res['patient'], res['time'], self._fmt_date(res['date']),
                              (' – %s' % ', '.join(res['services'])) if res['services'] else '',
                              (' với BS %s' % res['doctor']) if res['doctor'] else '', res['visit']),
                           ['Địa chỉ', 'Chuẩn bị gì trước khi khám?'])
            state['time'] = False
            alts = res.get('alternatives') or []
            state['slots'] = alts
            state['stage'] = 'pick_slot'
            return out('Dạ %s Anh/chị chọn giờ khác giúp em: %s' % (res.get('message') or res.get('error') or '',
                                                                    ', '.join(alts)), alts)

        if has_any(folded, THANKS_WORDS):
            return out('Dạ không có gì ạ! Chúc anh/chị một ngày vui – cần gì cứ nhắn em nhé.')
        if has_any(folded, GREET_WORDS) or not conversation.message_line_ids.filtered(lambda m: m.role == 'bot'):
            company = self.env.company
            return out('Dạ %s xin chào! Em là trợ lý tự động của phòng khám. Em có thể báo giá theo bảng giá, xem giờ '
                       'trống và giữ chỗ lịch hẹn cho anh/chị. Anh/chị cần em hỗ trợ gì ạ?' % company.name,
                       ['Đặt lịch khám', 'Bảng giá cạo vôi', 'Giờ làm việc', 'Địa chỉ'])
        return out('Dạ em chưa hiểu rõ ý anh/chị. Em có thể: báo giá dịch vụ, xem giờ trống & đặt lịch, '
                   'giờ làm việc, địa chỉ – hoặc chuyển nhân viên tư vấn ạ.',
                   ['Đặt lịch khám', 'Bảng giá', 'Gặp nhân viên'])

    @staticmethod
    def _fmt_date(iso):
        try:
            return fields.Date.from_string(iso).strftime('%d/%m')
        except (TypeError, ValueError):
            return iso

    @staticmethod
    def _detect_service(folded):
        for triggers, keys in SERVICE_HINTS:
            if has_any(folded, triggers):
                return keys[0]
        return False

    @staticmethod
    def _extract_name(text, stage):
        import re
        raw = (text or '').strip()
        match = re.search(r'(?:tên (?:em |tôi |mình |anh |chị )?(?:là )?|tôi là |em là |mình là |anh là |chị là )'
                          r'([A-ZÀ-Ỹ][\wÀ-ỹ]*(?:\s+[A-ZÀ-Ỹ][\wÀ-ỹ]*){0,4})', raw)
        if match:
            return match.group(1).strip()
        if stage == 'contact':
            candidate = re.sub(r'(?:\+?84|0)(?:[\s.\-]?\d){9}', '', raw).strip(' ,.-')
            words = candidate.split()
            if 2 <= len(words) <= 5 and all(w[:1].isupper() for w in words) and not any(ch.isdigit() for ch in candidate):
                return candidate
        return False

    @api.model
    def _quick_replies_from_trace(self, trace):
        """Chế độ Claude: gợi ý nút trả lời nhanh từ kết quả công cụ (giờ trống)."""
        for item in reversed(trace or []):
            if item.get('tool') == 'get_free_slots' and isinstance(item.get('output'), dict):
                return [s['time'] for s in item['output'].get('slots', [])[:4]]
        return []

    @api.model
    def dumps(self, value):
        return json.dumps(value, ensure_ascii=False, default=str)
