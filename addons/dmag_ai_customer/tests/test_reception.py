import json
from unittest.mock import patch

from odoo.tests import tagged

from .common import AiCustomerCase, block, fake_client, response


@tagged('post_install', '-at_install')
class TestZaloReception(AiCustomerCase):
    """AI-07 – trợ lý Zalo OA: giả lập theo dữ liệu thật + Claude (client giả) với vòng gọi công cụ đặt lịch thật."""

    def _conv(self):
        Conv = self.env['dmag.ai.conversation']
        thread = Conv.simulator_start()
        return Conv.browse(thread['id'])

    def test_simulate_price_and_booking_flow(self):
        conv = self._conv()
        thread = conv.simulator_send('Cạo vôi răng AI test giá bao nhiêu ạ?')
        bot = thread['messages'][-1]
        self.assertEqual(bot['role'], 'bot')
        self.assertIn('345.000 đ', bot['body'], 'Giá lấy đúng từ bảng giá')
        self.assertEqual(bot['trace'][0]['tool'], 'search_services')
        self.assertTrue(bot['simulated'])
        self.assertGreater(bot['estimated_cost_vnd'], 0)

        thread = conv.simulator_send('Cho em đặt lịch cạo vôi răng AI test ngày mai buổi chiều')
        bot = thread['messages'][-1]
        self.assertIn('get_free_slots', [t['tool'] for t in bot['trace']])
        slots = bot['quick']
        self.assertTrue(slots, 'Có giờ trống gợi ý')
        self.assertTrue(all(int(s[:2]) >= 12 for s in slots), 'Buổi chiều')

        conv.simulator_send(slots[0])
        thread = conv.simulator_send('Tên em là Trần Văn Bình, sđt 0909 123 456')
        self.assertIn('đồng ý', thread['messages'][-1]['body'])
        thread = conv.simulator_send('Đồng ý')
        bot = thread['messages'][-1]
        self.assertIn('book_appointment', [t['tool'] for t in bot['trace']])
        self.assertEqual(len(thread['visits']), 1)
        visit = self.env['dmag.dental.visit'].browse(thread['visits'][0]['id'])
        self.assertEqual(visit.state, 'draft', 'Lịch nháp chờ lễ tân xác nhận')
        self.assertEqual(visit.dmag_ai_conversation_id, conv)
        self.assertEqual(visit.patient_id.name, 'Trần Văn Bình')
        self.assertTrue(visit.patient_id.data_consent)
        self.assertEqual(visit.source_id.code, 'ZALO_AI')
        self.assertIn(self.scaling, visit.service_ids)
        self.assertEqual(thread['visits'][0]['time'], slots[0])
        self.assertTrue(visit._workspace_card()['ai_booked'])
        self.assertIn(visit.name, bot['body'])
        # Không đặt trùng trong cùng ngày
        again = self.env['dmag.ai.reception'].tool_book_appointment(conv, {
            'name': 'Trần Văn Bình', 'phone': '0909123456', 'date': self.tomorrow.isoformat(),
            'time': slots[-1], 'service_ids': [self.scaling.id], 'doctor_id': 0, 'note': '', 'consent': True})
        self.assertFalse(again['booked'])
        self.assertEqual(again['existing_visit'], visit.name)

    def test_simulate_no_booking_without_consent(self):
        conv = self._conv()
        conv.simulator_send('Đặt lịch cạo vôi răng AI test ngày mai')
        thread = conv.simulator_send('chiều')
        slot = thread['messages'][-1]['quick'][0]
        conv.simulator_send(slot)
        conv.simulator_send('Tên em là Phạm Minh Khoa 0988777666')
        thread = conv.simulator_send('Không đồng ý')
        self.assertFalse(thread['visits'])
        self.assertFalse(self.env['res.partner'].search([('mobile', '=', '0988777666')]))

    def test_emergency_and_complaint_handoff(self):
        conv = self._conv()
        thread = conv.simulator_send('Em mới nhổ răng, giờ chảy máu không cầm được')
        self.assertEqual(thread['state'], 'handoff')
        self.assertIn('028 3999 9999', thread['messages'][-1]['body'])
        self.assertTrue(conv.activity_ids, 'Có việc cho nhân viên')
        # Đang chờ nhân viên: trợ lý không trả lời tiếp
        thread = conv.simulator_send('Alo có ai không')
        self.assertEqual(thread['messages'][-1]['role'], 'customer')

        conv2 = self._conv()
        thread = conv2.simulator_send('Tôi rất bực, chờ lâu quá mà thái độ lễ tân thì tệ, tôi muốn khiếu nại')
        self.assertEqual(thread['state'], 'handoff')
        self.assertEqual(conv2.handoff_reason, 'complaint')
        feedback = conv2.feedback_ids
        self.assertTrue(feedback, 'AI-09 tạo phiếu phản hồi')
        self.assertIn(feedback[0].severity, ('high', 'critical'))

    def test_medical_question_no_diagnosis(self):
        conv = self._conv()
        thread = conv.simulator_send('Răng em bị ê buốt khi uống nước lạnh, có sao không ạ?')
        body = thread['messages'][-1]['body']
        self.assertIn('không thể chẩn đoán', body)

    def test_approve_mode_holds_reply(self):
        self.company.dmag_ai_zalo_reply_mode = 'approve'
        conv = self.env['dmag.ai.conversation']._get_or_create('zalo', external_user_id='u-123', name='Khách Zalo')
        conv.receive_customer_message('Giờ mở cửa thế nào ạ?')
        reply = conv.message_line_ids.filtered(lambda m: m.role == 'bot')
        self.assertEqual(reply.state, 'pending')
        self.assertEqual(conv.pending_count, 1)
        inbox = self.env['dmag.ai.conversation'].get_inbox('attention')
        self.assertIn(conv.id, [c['id'] for c in inbox['conversations']])
        reply.action_approve_send()
        self.assertEqual(reply.state, 'mock_sent', 'Gửi qua Zalo OA ở chế độ giả lập (mock)')
        # Ca khẩn: câu trả lời an toàn theo mẫu cố định được gửi ngay, không chờ duyệt
        urgent = self.env['dmag.ai.conversation']._get_or_create('zalo', external_user_id='u-911', name='Khách khẩn')
        urgent.receive_customer_message('Em bị sưng mặt và sốt cao sau nhổ răng')
        self.assertEqual(urgent.state, 'handoff')
        safety = urgent.message_line_ids.filtered(lambda m: m.role == 'system')
        self.assertEqual(safety.state, 'mock_sent')
        self.assertIn('028 3999 9999', safety.body)

    def test_webhook_user_send_text(self):
        payload = {'event_name': 'user_send_text', 'app_id': '', 'timestamp': '1760000000000',
                   'sender': {'id': 'zalo-user-777'}, 'recipient': {'id': 'oa-1'},
                   'message': {'text': 'Cho hỏi địa chỉ phòng khám', 'msg_id': 'm1'}}
        event, accepted = self.env['dmag.zns.webhook.event'].sudo()._dmag_receive(json.dumps(payload))
        self.assertTrue(accepted)
        conv = self.env['dmag.ai.conversation'].search([('external_user_id', '=', 'zalo-user-777')])
        self.assertTrue(conv)
        self.assertEqual(conv.channel, 'zalo')
        self.assertIn('Đã chuyển trợ lý AI', event.note)
        bot = conv.message_line_ids.filtered(lambda m: m.role == 'bot')
        self.assertEqual(bot.state, 'mock_sent')
        self.assertIn('get_clinic_info', bot.tool_trace)

    def test_feature_off_hands_off(self):
        self.env.ref('dmag_ai_core.feature_ai_07').active = False
        conv = self._conv()
        thread = conv.simulator_send('Xin chào')
        self.assertEqual(thread['state'], 'handoff')
        self.assertEqual(thread['messages'][-1]['role'], 'system')

    def test_live_tool_loop_books_real_draft_visit(self):
        """Chế độ Claude: client giả trả tool_use → công cụ chạy trên Odoo thật → lịch nháp được tạo."""
        self.company.sudo().write({'dmag_ai_mode': 'live', 'dmag_ai_api_key': 'sk-test'})
        conv = self._conv()
        date = self.tomorrow.isoformat()
        calls = []

        def create(**kw):
            calls.append(kw)
            self.assertNotIn('tool_choice', kw, 'Không ép tool_choice')
            for tool in kw['tools']:
                self.assertTrue(tool['strict'])
                self.assertFalse(tool['input_schema']['additionalProperties'])
            if len(calls) == 1:
                return response([block(type='text', text='Dạ em xem giờ trống ạ.'),
                                 block(type='tool_use', id='t1', name='get_free_slots',
                                       input={'date': date, 'service_ids': [self.scaling.id], 'part_of_day': 'afternoon'})],
                                stop='tool_use')
            if len(calls) == 2:
                result = kw['messages'][-1]['content'][0]
                self.assertEqual(result['type'], 'tool_result')
                slots = json.loads(result['content'])['slots']
                self.assertTrue(slots)
                self.time = slots[0]['time']
                return response([block(type='tool_use', id='t2', name='book_appointment', input={
                    'name': 'Đỗ Quang Huy', 'phone': '0903555777', 'date': date, 'time': self.time,
                    'service_ids': [self.scaling.id], 'doctor_id': 0, 'note': 'Khách hỏi qua Zalo', 'consent': True})],
                                stop='tool_use')
            booked = json.loads(kw['messages'][-1]['content'][0]['content'])
            self.assertTrue(booked['booked'])
            return response([block(type='text', text='Dạ em đã giữ chỗ %s lúc %s, lễ tân sẽ gọi xác nhận ạ.'
                                                     % (booked['visit'], booked['time']))])

        with patch.object(type(self.env['dmag.ai']), '_client', lambda s: fake_client(create)):
            thread = conv.simulator_send('Đặt lịch cạo vôi chiều mai cho anh Huy 0903555777, đồng ý lưu thông tin')
        self.assertEqual(len(calls), 3)
        self.assertIn('Hôm nay là', calls[0]['system'][0]['text'])
        bot = thread['messages'][-1]
        self.assertFalse(bot['simulated'])
        self.assertEqual([t['tool'] for t in bot['trace']], ['get_free_slots', 'book_appointment'])
        self.assertGreater(bot['cost_vnd'], 0)
        visit = conv.visit_ids
        self.assertEqual(len(visit), 1)
        self.assertEqual(visit.state, 'draft')
        self.assertEqual(visit.patient_id.mobile, '0903555777')
        self.assertEqual(thread['visits'][0]['time'], self.time)
        log = self.env['dmag.ai.log'].browse(conv.message_line_ids.filtered(lambda m: m.role == 'bot').log_id.id)
        self.assertEqual(log.tool_calls, 2)

    def test_live_history_alternates(self):
        self.company.sudo().write({'dmag_ai_mode': 'live', 'dmag_ai_api_key': 'sk-test'})
        conv = self._conv()
        seen = []

        def create(**kw):
            seen.append(kw['messages'])
            return response([block(type='text', text='Dạ vâng ạ.')])

        with patch.object(type(self.env['dmag.ai']), '_client', lambda s: fake_client(create)):
            conv.simulator_send('Chào')
            conv.simulator_send('Cho hỏi giờ mở cửa')
        roles = [m['role'] for m in seen[-1]]
        self.assertEqual(roles, ['user', 'assistant', 'user'])
