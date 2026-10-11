import json
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .common import AiCustomerCase, block, fake_client, response


@tagged('post_install', '-at_install')
class TestReplyScripts(AiCustomerCase):
    """AI-07 – trợ lý Zalo tự trả lời CHỈ theo kịch bản Giám đốc đã duyệt; còn lại chờ nhân viên duyệt / chuyển người."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.company.sudo().write({'dmag_ai_zalo_reply_mode': 'script', 'dmag_ai_script_threshold': 0.6})
        # Lịch làm việc cố định cho bài test (không phụ thuộc hôm nay là thứ mấy): mở cửa mọi ngày 08:00–20:00
        schedule = env['dmag.clinic.schedule']._get_for_company(cls.company)
        schedule.closure_ids.unlink()
        schedule.line_ids.unlink()
        schedule.write({'line_ids': [(0, 0, {'weekday': str(wd), 'hour_from': 8.0, 'hour_to': 20.0})
                                     for wd in range(7)]})
        Script = env['dmag.ai.reply.script']
        Script._load_samples(cls.company)
        from odoo.addons.dmag_ai_customer.models.reply_script_samples import SAMPLE_SCRIPTS
        # CSDL demo có thể đã duyệt sẵn – chỉ dùng đúng 12 kịch bản mẫu, kịch bản khác (đề xuất demo…) lưu trữ
        cls.scripts = Script.search([('company_id', '=', cls.company.id),
                                     ('code', 'in', [x['code'] for x in SAMPLE_SCRIPTS])])
        Script.search([('company_id', '=', cls.company.id), ('id', 'not in', cls.scripts.ids)]).write({'active': False})
        cls.scripts.filtered(lambda x: x.state == 'draft').action_approve()  # quyền hệ thống = Giám đốc
        cls.by_code = {s.code: s for s in cls.scripts}

        def user(login, group):
            return env['res.users'].with_context(no_reset_password=True).create({
                'name': login, 'login': login, 'email': '%s@dmag.test' % login, 'tz': 'Asia/Ho_Chi_Minh',
                'groups_id': [(6, 0, [env.ref(group).id])]})
        cls.receptionist = user('lt_script', 'dmag_dental_base.group_dmag_receptionist')
        cls.manager = user('ql_script', 'dmag_dental_base.group_dmag_manager')
        cls.director = user('gd_script', 'dmag_dental_base.group_dmag_director')

    def _sim(self):
        Conv = self.env['dmag.ai.conversation']
        return Conv.browse(Conv.simulator_start()['id'])

    def _last(self, conv, role=None):
        lines = conv.message_line_ids.sorted('id')
        if role:
            lines = lines.filtered(lambda m: m.role == role)
        return lines[-1:]

    # ------------------------------------------------------------------ giả lập
    def test_seeded_scripts(self):
        self.assertGreaterEqual(len(self.scripts), 12)
        for code in ('gia_dich_vu', 'gio_mo_cua', 'dia_chi_do_xe', 'dat_lich', 'doi_huy_lich', 'chuan_bi_kham',
                     'bao_hanh', 'tra_gop', 'dau_sau_nho_rang', 'nieng_rang', 'tay_trang', 'kham_tre_em'):
            self.assertIn(code, self.by_code)
            self.assertEqual(self.by_code[code].state, 'approved')

    def test_matched_script_auto_sends_template_with_real_data(self):
        used = self.by_code['gia_dich_vu'].usage_count
        conv = self._sim()
        thread = conv.simulator_send('Cạo vôi răng AI test giá bao nhiêu ạ?')
        bot = thread['messages'][-1]
        self.assertEqual(bot['decision'], 'script_auto')
        self.assertEqual(bot['script']['code'], 'gia_dich_vu')
        self.assertGreaterEqual(bot['confidence'], 60)
        self.assertEqual(bot['state'], 'ready')
        self.assertIn('345.000 đ', bot['body'], 'Ô {gia_dich_vu} điền từ bảng giá thật')
        self.assertNotIn('{', bot['body'])
        self.assertIn('search_services', [t['tool'] for t in bot['trace']])
        self.assertEqual(self.by_code['gia_dich_vu'].usage_count, used + 1)

        thread = conv.simulator_send('Phòng khám mở cửa mấy giờ vậy?')
        bot = thread['messages'][-1]
        self.assertEqual(bot['script']['code'], 'gio_mo_cua')
        self.assertIn('08:00–20:00', bot['body'], 'Giờ làm việc lấy từ Lịch làm việc phòng khám')
        self.assertIn('028 3999 9999', bot['body'])

        # Kênh Zalo thật: khớp kịch bản → gửi ngay (ZNS giả lập)
        zalo = self.env['dmag.ai.conversation']._get_or_create('zalo', external_user_id='u-script-1', name='Khách')
        zalo.receive_customer_message('Cho em xin địa chỉ phòng khám, có chỗ đậu ô tô không?')
        reply = self._last(zalo, 'bot')
        self.assertEqual(reply.decision, 'script_auto')
        self.assertEqual(reply.script_id, self.by_code['dia_chi_do_xe'])
        self.assertEqual(reply.state, 'mock_sent')

    def test_unmatched_or_medical_escalates_to_staff(self):
        zalo = self.env['dmag.ai.conversation']._get_or_create('zalo', external_user_id='u-script-2', name='Khách 2')
        zalo.receive_customer_message('Bên mình có xuất hóa đơn VAT cho công ty không ạ?')
        draft = self._last(zalo, 'bot')
        self.assertEqual(draft.state, 'pending', 'Không khớp kịch bản → nháp chờ nhân viên duyệt')
        self.assertIn(draft.decision, ('no_match', 'low_confidence'))
        self.assertTrue(draft.decision_note)
        tools = [t['tool'] for t in json.loads(draft.tool_trace or '[]')]
        self.assertNotIn('book_appointment', tools)
        ack = self._last(zalo, 'system')
        self.assertEqual(ack.decision, 'ack')
        self.assertEqual(ack.state, 'mock_sent', 'Khách nhận tin báo đã nhận (mẫu cố định)')
        self.assertEqual(zalo.pending_count, 1)
        self.assertEqual(zalo.state, 'bot')
        self.assertTrue(zalo.activity_ids)
        # Tin thứ hai cũng chưa có kịch bản: không gửi lặp tin báo đã nhận
        zalo.receive_customer_message('Có xuất hóa đơn đỏ không ạ?')
        self.assertEqual(len(zalo.message_line_ids.filtered(lambda m: m.decision == 'ack')), 1)

        conv = self._sim()
        thread = conv.simulator_send('Răng em bị ê buốt khi uống nước lạnh, có sao không ạ?')
        bot = [m for m in thread['messages'] if m['role'] == 'bot'][-1]
        self.assertEqual(bot['decision'], 'medical')
        self.assertEqual(bot['state'], 'pending')

    def test_safety_paths(self):
        conv = self._sim()
        thread = conv.simulator_send('Em mới nhổ răng, giờ chảy máu không cầm được')
        self.assertEqual(thread['state'], 'handoff')
        last = thread['messages'][-1]
        self.assertEqual(last['role'], 'system')
        self.assertEqual(last['decision'], 'emergency')
        self.assertIn('028 3999 9999', last['body'])

        conv = self._sim()
        thread = conv.simulator_send('Em mới nhổ răng khôn hôm qua giờ còn đau, có sao không ạ?')
        bot = thread['messages'][-1]
        self.assertEqual(bot['decision'], 'handoff_script')
        self.assertEqual(bot['script']['code'], 'dau_sau_nho_rang')
        self.assertEqual(bot['state'], 'ready', 'Mẫu an toàn đã duyệt gửi ngay')
        self.assertEqual(thread['state'], 'handoff')
        self.assertEqual(conv.handoff_reason, 'medical_question')

        conv = self._sim()
        thread = conv.simulator_send('Tôi rất thất vọng, thái độ lễ tân quá tệ, tôi muốn khiếu nại')
        self.assertEqual(thread['state'], 'handoff')
        self.assertEqual(thread['messages'][-1]['decision'], 'complaint')

    def test_booking_script_creates_draft_visit(self):
        conv = self._sim()
        thread = conv.simulator_send('Cho em đặt lịch cạo vôi răng AI test ngày mai buổi chiều')
        bot = thread['messages'][-1]
        self.assertEqual(bot['decision'], 'script_flow')
        self.assertEqual(bot['script']['code'], 'dat_lich')
        self.assertIn('get_free_slots', [t['tool'] for t in bot['trace']])
        slot = bot['quick'][0]
        conv.simulator_send(slot)
        conv.simulator_send('Tên em là Trần Văn Bình, sđt 0909 123 456')
        thread = conv.simulator_send('Đồng ý')
        bot = thread['messages'][-1]
        self.assertEqual(bot['decision'], 'script_flow', 'Các lượt sau tiếp tục luồng của kịch bản đặt lịch')
        self.assertIn('book_appointment', [t['tool'] for t in bot['trace']])
        self.assertEqual(len(thread['visits']), 1)
        visit = self.env['dmag.dental.visit'].browse(thread['visits'][0]['id'])
        self.assertEqual(visit.state, 'draft', 'Lịch NHÁP chờ lễ tân xác nhận')
        self.assertFalse(conv.script_id, 'Đặt xong → kết thúc luồng')
        # Không nêu ngày → gửi nguyên mẫu đã duyệt kèm giờ trống thật
        conv2 = self._sim()
        thread = conv2.simulator_send('Đặt hẹn khám răng giúp em')
        bot = thread['messages'][-1]
        self.assertEqual(bot['decision'], 'script_auto')
        self.assertIn('Giờ còn trống gần nhất', bot['body'])

    def test_unapproved_script_not_used(self):
        script = self.by_code['tra_gop']
        script.action_reset_draft()
        conv = self._sim()
        thread = conv.simulator_send('Có trả góp không ạ?')
        bot = [m for m in thread['messages'] if m['role'] == 'bot'][-1]
        self.assertEqual(bot['state'], 'pending', 'Kịch bản bị mở lại (nháp) → trợ lý không tự gửi')
        self.assertNotEqual(bot['decision'], 'script_auto')

    # ------------------------------------------------------------------ quyền & khóa
    def test_permissions_and_lock(self):
        Script = self.env['dmag.ai.reply.script']
        vals = {'name': 'Khám định kỳ công ty', 'code': 'kham_cong_ty', 'sample_questions': 'Khám cho công ty',
                'answer_template': 'Dạ phòng khám có gói khám cho doanh nghiệp, hotline {hotline} ạ.'}
        with self.assertRaises(AccessError):
            Script.with_user(self.receptionist).create(vals)
        script = Script.with_user(self.manager).create(vals)
        self.assertEqual(script.state, 'draft')
        with self.assertRaises(AccessError):
            script.with_user(self.manager).action_approve()
        with self.assertRaises(AccessError):
            script.with_user(self.manager).write({'state': 'approved'})
        script.with_user(self.director).action_approve()
        self.assertEqual(script.state, 'approved')
        self.assertEqual(script.approved_by_id, self.director)
        self.assertTrue(script.approved_at)
        with self.assertRaisesRegex(UserError, 'khóa'):
            script.with_user(self.manager).write({'answer_template': 'Sửa lén'})
        with self.assertRaisesRegex(UserError, 'khóa'):
            script.with_user(self.director).write({'answer_template': 'Sửa thẳng'})
        script.with_user(self.director).action_reset_draft()
        script.with_user(self.manager).write({'answer_template': 'Dạ có ạ, gọi {hotline}.'})
        # Ô dữ liệu cần công cụ chưa được phép → không duyệt được; ô lạ → không lưu được
        script.with_user(self.manager).write({'answer_template': 'Giờ trống: {gio_trong}'})
        with self.assertRaisesRegex(UserError, 'get_free_slots'):
            script.with_user(self.director).action_approve()
        with self.assertRaises(Exception):
            script.with_user(self.manager).write({'answer_template': 'Giá {gia_bi_mat}'})
        # "Tự động hoàn toàn" chỉ Giám đốc bật
        with self.assertRaises(AccessError):
            self.company.with_user(self.manager).write({'dmag_ai_zalo_reply_mode': 'auto'})

    # ------------------------------------------------------------------ huấn luyện từ hộp thư + thống kê
    def test_training_from_inbox_and_stats(self):
        zalo = self.env['dmag.ai.conversation']._get_or_create('zalo', external_user_id='u-train', name='Chị Vân')
        zalo.receive_customer_message('Bên mình có xuất hóa đơn VAT cho công ty không ạ?')
        draft = self._last(zalo, 'bot').with_user(self.receptionist)
        self.assertFalse(draft._is_promotable(), 'Chưa duyệt thì chưa đề xuất được')
        draft.approve_and_edit('Dạ có ạ, phòng khám xuất hóa đơn điện tử cho công ty khi thanh toán.')
        self.assertTrue(draft.edited)
        self.assertTrue(draft.original_body)
        ui = draft.read_for_ui()[0]
        self.assertTrue(ui['promotable'])
        res = draft.action_promote_to_script()
        script = self.env['dmag.ai.reply.script'].browse(res['id'])
        self.assertEqual(script.state, 'draft', 'Đề xuất là bản nháp – Giám đốc duyệt')
        self.assertIn('hóa đơn VAT', script.sample_questions)
        self.assertIn('xuất hóa đơn điện tử', script.answer_template)
        self.assertEqual(script.source_message_id, draft)
        self.assertEqual(script.proposed_by_id, self.receptionist)
        # Ví dụ hỏi – đáp cho kịch bản có sẵn → chỉ dùng khi Giám đốc duyệt
        conv = self._sim()
        conv.simulator_send('Thanh toán bằng thẻ tín dụng được không?')
        question = self._last(conv, 'customer')
        staff = conv.with_user(self.receptionist).staff_reply('Dạ được ạ, phòng khám nhận quẹt thẻ Visa/Master.')
        msg = self.env['dmag.ai.conversation.message'].browse(staff['id'])
        self.assertEqual(msg.question_id, question)
        ex = msg.with_user(self.receptionist).action_promote_to_example(self.by_code['tra_gop'].id)
        example = self.env['dmag.ai.reply.example'].browse(ex['id'])
        self.assertEqual(example.state, 'draft')
        with self.assertRaises(AccessError):
            example.with_user(self.manager).action_approve()
        example.with_user(self.director).action_approve()
        self.assertEqual(example.state, 'approved')
        self.assertIn('Thanh toán bằng thẻ tín dụng được không?', self.by_code['tra_gop']._samples())
        # Thống kê
        stats = self.env['dmag.ai.conversation'].get_script_stats(30)
        self.assertGreater(stats['total'], 0)
        self.assertGreater(stats['escalated'], 0)
        self.assertTrue(any('hóa đơn' in u['question'] for u in stats['top_unmatched']))
        self.assertGreaterEqual(stats['scripts_draft'], 1)

    # ------------------------------------------------------------------ Claude (client giả)
    def _live(self, create):
        self.company.sudo().write({'dmag_ai_mode': 'live', 'dmag_ai_api_key': 'sk-test'})
        return patch.object(type(self.env['dmag.ai']), '_client', lambda s: fake_client(create))

    def test_live_classifies_strictly_among_approved_scripts(self):
        price = self.by_code['gia_dich_vu']
        calls = []

        def create(**kw):
            calls.append(kw)
            self.assertNotIn('tool_choice', kw)
            if len(calls) == 1:
                schema = kw['output_config']['format']['schema']
                enum = schema['properties']['script_id']['enum']
                self.assertIn(str(price.id), enum)
                self.assertIn('none', enum)
                self.assertEqual(set(enum) - {'none'}, {str(s.id) for s in self.scripts})
                self.assertFalse(schema['additionalProperties'])
                self.assertNotIn('tools', kw, 'Bước phân loại không gọi công cụ')
                return response([block(type='text', text=json.dumps({
                    'script_id': str(price.id), 'confidence': 0.93, 'safety': 'normal',
                    'reason': 'Khách hỏi giá cạo vôi'}))])
            # Diễn đạt lại nhẹ (kịch bản cho phép) – giữ nguyên số liệu
            approved = kw['messages'][-1]['content']
            text = approved if isinstance(approved, str) else approved[0]['text']
            return response([block(type='text', text=json.dumps({'text': 'Dạ ' + text}))])

        conv = self._sim()
        with self._live(create):
            thread = conv.simulator_send('Cạo vôi răng AI test hết bao nhiêu tiền vậy ạ?')
        bot = thread['messages'][-1]
        self.assertEqual(len(calls), 2)
        self.assertEqual(bot['decision'], 'script_auto')
        self.assertEqual(bot['script']['id'], price.id)
        self.assertEqual(bot['confidence'], 93)
        self.assertIn('345.000 đ', bot['body'])
        self.assertTrue(bot['body'].startswith('Dạ Dạ'))
        self.assertFalse(bot['simulated'])

    def test_live_rephrase_changing_numbers_falls_back_to_template(self):
        price = self.by_code['gia_dich_vu']
        state = {'n': 0}

        def create(**kw):
            state['n'] += 1
            if state['n'] == 1:
                return response([block(type='text', text=json.dumps({
                    'script_id': str(price.id), 'confidence': 0.9, 'safety': 'normal', 'reason': 'giá'}))])
            return response([block(type='text', text=json.dumps({'text': 'Cạo vôi chỉ 99.000 đ thôi ạ!'}))])

        conv = self._sim()
        with self._live(create):
            thread = conv.simulator_send('Cạo vôi răng AI test giá sao ạ?')
        bot = thread['messages'][-1]
        self.assertIn('345.000 đ', bot['body'])
        self.assertNotIn('99.000', bot['body'])

    def test_live_low_confidence_or_none_goes_to_staff(self):
        calls = []

        def create(**kw):
            calls.append(kw)
            if len(calls) == 1:
                return response([block(type='text', text=json.dumps({
                    'script_id': 'none', 'confidence': 0.2, 'safety': 'normal', 'reason': 'Hỏi hóa đơn công ty'}))])
            names = {t['name'] for t in kw.get('tools', [])}
            self.assertNotIn('book_appointment', names, 'Soạn nháp chờ duyệt chỉ dùng công cụ đọc')
            self.assertNotIn('handoff_to_staff', names)
            return response([block(type='text', text='Dạ phòng khám có xuất hóa đơn ạ.')])

        conv = self._sim()
        with self._live(create):
            thread = conv.simulator_send('Bên mình xuất hóa đơn công ty được không?')
        bot = [m for m in thread['messages'] if m['role'] == 'bot'][-1]
        self.assertEqual(len(calls), 2)
        self.assertEqual(bot['state'], 'pending')
        self.assertEqual(bot['decision'], 'no_match')
        self.assertIn('Claude', bot['decision_note'])

        def create_emergency(**kw):
            return response([block(type='text', text=json.dumps({
                'script_id': 'none', 'confidence': 0.0, 'safety': 'emergency', 'reason': 'Sốt, sưng'}))])
        conv = self._sim()
        with self._live(create_emergency):
            thread = conv.simulator_send('Má em to lên và người hầm hập từ tối qua')
        self.assertEqual(thread['state'], 'handoff')
        self.assertEqual(thread['messages'][-1]['decision'], 'emergency')
