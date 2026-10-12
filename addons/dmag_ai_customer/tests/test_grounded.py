import json
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .common import AiCustomerCase, block, fake_client, response


@tagged('post_install', '-at_install')
class TestGroundedMode(AiCustomerCase):
    """Chế độ "Tự động – chỉ trả lời từ dữ liệu đã nạp": trả lời có nguồn; ngoài dữ liệu → tin giữ chỗ + báo lễ tân
    đang trực + báo Quản lý khi quá hạn; số liệu không có trong nguồn bị chặn; kho tri thức: bộ nạp, duyệt, khóa."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.company.sudo().write({'dmag_ai_zalo_reply_mode': 'grounded', 'dmag_ai_script_threshold': 0.6,
                                  'dmag_ai_escalation_minutes': 15})
        schedule = env['dmag.clinic.schedule']._get_for_company(cls.company)
        schedule.closure_ids.unlink()
        schedule.line_ids.unlink()
        schedule.write({'line_ids': [(0, 0, {'weekday': str(wd), 'hour_from': 8.0, 'hour_to': 20.0}) for wd in range(7)],
                        'rotation_allow_sunday': True, 'min_doctors': 1, 'min_receptionists': 1})
        Script = env['dmag.ai.reply.script']
        Script._load_samples(cls.company)
        from odoo.addons.dmag_ai_customer.models.reply_script_samples import SAMPLE_SCRIPTS
        cls.scripts = Script.search([('company_id', '=', cls.company.id),
                                     ('code', 'in', [x['code'] for x in SAMPLE_SCRIPTS])])
        Script.search([('company_id', '=', cls.company.id), ('id', 'not in', cls.scripts.ids)]).write({'active': False})
        cls.scripts.filtered(lambda x: x.state == 'draft').action_approve()
        cls.by_code = {s.code: s for s in cls.scripts}
        # Kho tri thức: chỉ dữ liệu của bài test
        env['dmag.ai.knowledge'].with_context(active_test=False, dmag_workflow=True).search(
            [('company_id', '=', cls.company.id)]).unlink()
        cls.scaling.warranty_months = 0
        cls.extraction.warranty_months = 0

        def user(login, group, name=None):
            return env['res.users'].with_context(no_reset_password=True).create({
                'name': name or login, 'login': login, 'email': '%s@dmag.test' % login, 'tz': 'Asia/Ho_Chi_Minh',
                'groups_id': [(6, 0, [env.ref(group).id])]})
        cls.lt_off = user('lt_grounded_off', 'dmag_dental_base.group_dmag_receptionist', 'Lễ tân Nghỉ Hôm Nay')
        cls.lt_on = user('lt_grounded_on', 'dmag_dental_base.group_dmag_receptionist', 'Lê Thị Ngọc Ánh Test')
        cls.manager = user('ql_grounded', 'dmag_dental_base.group_dmag_manager', 'Quản lý Trực')
        cls.director = user('gd_grounded', 'dmag_dental_base.group_dmag_director')
        cls.company.sudo().write({'dmag_ai_escalation_user_id': cls.manager.id, 'dmag_ai_duty_line_ids': [
            (5, 0, 0), (0, 0, {'user_id': cls.lt_off.id, 'sequence': 1}), (0, 0, {'user_id': cls.lt_on.id, 'sequence': 2})]})
        today = fields.Date.context_today(env['res.partner'])
        cls.today = today
        Rot = env['dmag.staff.rotation']
        Rot.search([('company_id', '=', cls.company.id)]).unlink()
        wd_today = env['dmag.weekday'].search([('code', '=', today.weekday())])
        wd_tomorrow = env['dmag.weekday'].search([('code', '=', (today + timedelta(days=1)).weekday())])
        Rot.create([
            {'name': cls.lt_off.name, 'role': 'receptionist', 'user_id': cls.lt_off.id,
             'off_weekday_ids': [(6, 0, wd_today.ids)]},
            {'name': cls.lt_on.name, 'role': 'receptionist', 'user_id': cls.lt_on.id},
            {'name': cls.doctor.name, 'role': 'doctor', 'practitioner_id': cls.doctor.id,
             'off_weekday_ids': [(6, 0, wd_tomorrow.ids)]},
            {'name': cls.doctor2.name, 'role': 'doctor', 'practitioner_id': cls.doctor2.id},
        ])
        KB = env['dmag.ai.knowledge']
        KB.load_master_data(cls.company)
        KB.load_scripts(cls.company)
        cls.company.sudo().dmag_ai_kb_refreshed_at = fields.Datetime.now()
        cls.vat = KB.create({
            'name': 'Xuất hóa đơn VAT cho công ty', 'category': 'faq', 'company_id': cls.company.id,
            'question_variants': 'có xuất hóa đơn VAT không\nxuất hóa đơn đỏ cho công ty',
            'content': 'Phòng khám xuất hóa đơn điện tử (VAT) cho công ty trong vòng 3 ngày làm việc; anh/chị gửi tên '
                       'công ty, mã số thuế và email nhận hóa đơn qua Zalo này.',
            'tags': 'hóa đơn, VAT, công ty, mã số thuế', 'state': 'approved'})

    def _sim(self):
        Conv = self.env['dmag.ai.conversation']
        return Conv.browse(Conv.simulator_start()['id'])

    def _bots(self, thread):
        return [m for m in thread['messages'] if m['role'] in ('bot', 'system')]

    # ------------------------------------------------------------------ trả lời có nguồn
    def test_default_mode_is_grounded(self):
        field = self.env['res.company']._fields['dmag_ai_zalo_reply_mode']
        self.assertEqual(field.default(self.env['res.company']), 'grounded')
        self.assertEqual({k for k, _v in field.selection}, {'grounded', 'script', 'approve', 'auto'})

    def test_grounded_answer_from_script_and_kb(self):
        conv = self._sim()
        thread = conv.simulator_send('Cạo vôi răng AI test giá bao nhiêu ạ?')
        bot = self._bots(thread)[-1]
        self.assertEqual(bot['decision'], 'grounded')
        self.assertEqual(bot['state'], 'ready')
        self.assertIn('345.000 đ', bot['body'])
        labels = [s['label'] for s in bot['sources']]
        self.assertIn("Kịch bản 'Giá dịch vụ'", labels)
        self.assertIn('Bảng giá', labels)
        self.assertIn('Trả lời từ:', bot['decision_note'])
        # Câu hỏi có trong kho tri thức (hỏi – đáp đã duyệt)
        used = self.vat.usage_count
        thread = conv.simulator_send('Bên mình có xuất hóa đơn VAT cho công ty không ạ?')
        bot = self._bots(thread)[-1]
        self.assertEqual(bot['decision'], 'grounded', bot['decision_note'])
        self.assertIn('3 ngày làm việc', bot['body'])
        self.assertEqual(bot['sources'][0]['id'], self.vat.id)
        self.assertEqual(self.vat.usage_count, used + 1)
        # Giờ làm việc (mở cả tuần) + lịch trực bác sĩ (nghỉ luân phiên)
        thread = conv.simulator_send('Chủ nhật phòng khám có làm việc không ạ?')
        bot = self._bots(thread)[-1]
        self.assertEqual(bot['decision'], 'grounded')
        self.assertIn('08:00–20:00', bot['body'])
        thread = conv.simulator_send('Lịch làm việc của bác sĩ thế nào ạ?')
        bot = self._bots(thread)[-1]
        self.assertEqual(bot['decision'], 'grounded')
        self.assertIn('nghỉ luân phiên', bot['body'])
        self.assertIn('Lịch nghỉ luân phiên', [s['label'] for s in bot['sources']])

    def test_out_of_data_notifies_on_duty_receptionist_and_escalates(self):
        zalo = self.env['dmag.ai.conversation']._get_or_create('zalo', external_user_id='u-grounded-1', name='Khách BH')
        sent = []
        Bus = type(self.env['bus.bus'])
        with patch.object(Bus, '_sendone', lambda _self, target, kind, message: sent.append((target, kind, message))):
            zalo.receive_customer_message('Phòng khám có nhận bảo hiểm Bảo Việt không ạ?')
        hold = zalo.message_line_ids.sorted('id')[-1]
        self.assertEqual(hold.decision, 'out_of_data')
        self.assertEqual(hold.role, 'system')
        self.assertEqual(hold.state, 'mock_sent', 'Khách nhận tin giữ chỗ (mẫu cố định)')
        self.assertIn('lễ tân đang trực', hold.body)
        self.assertFalse(zalo.message_line_ids.filtered(lambda m: m.role == 'bot'), 'Không tự trả lời bừa')
        gap = zalo.gap_ids
        self.assertEqual(len(gap), 1)
        self.assertEqual(gap.state, 'open')
        self.assertEqual(gap.assigned_user_id, self.lt_on, 'Báo lễ tân ĐANG TRỰC (người kia nghỉ luân phiên hôm nay)')
        self.assertIn(self.lt_on.name, hold.decision_note)
        self.assertTrue(zalo.activity_ids.filtered(lambda a: a.user_id == self.lt_on))
        self.assertEqual(zalo.state, 'bot', 'Trợ lý vẫn trả lời các câu khác')
        self.assertTrue([m for t, k, m in sent if k == 'simple_notification' and t == self.lt_on.partner_id
                         and 'Trợ lý Zalo cần bạn trả lời' in m['title']], 'Thông báo nổi cho lễ tân đang trực')
        inbox = self.env['dmag.ai.conversation'].get_inbox('gaps')
        self.assertIn(zalo.id, [c['id'] for c in inbox['conversations']])
        self.assertGreaterEqual(inbox['counts']['gaps'], 1)
        # câu ngoài dữ liệu thứ hai: không gửi lặp tin giữ chỗ
        zalo.receive_customer_message('Thế còn bảo hiểm Prudential thì sao?')
        self.assertEqual(len(zalo.message_line_ids.filtered(lambda m: m.decision == 'out_of_data'
                                                            and m.state == 'mock_sent')), 1)
        self.assertEqual(len(zalo.gap_ids), 2)
        # quá 15 phút chưa trả lời → báo Quản lý
        gap.notified_at = fields.Datetime.now() - timedelta(minutes=20)
        second = zalo.gap_ids - gap
        second.write({'notified_at': fields.Datetime.now()})
        self.env['dmag.ai.kb.gap']._cron_escalate()
        self.assertTrue(gap.escalated_at)
        self.assertEqual(gap.escalated_user_id, self.manager)
        self.assertFalse(second.escalated_at, 'Câu mới chưa quá hạn')
        self.assertTrue(zalo.activity_ids.filtered(lambda a: a.user_id == self.manager))
        # lễ tân trả lời → một chạm nạp vào kho tri thức (nháp) → Giám đốc duyệt → lần sau trợ lý tự trả lời
        zalo.with_user(self.lt_on).staff_reply('Dạ hiện phòng khám chưa liên kết bảo hiểm Bảo Việt; anh/chị thanh toán '
                                               'trước, phòng khám xuất hóa đơn để anh/chị tự yêu cầu bảo hiểm hoàn tiền ạ.')
        self.assertTrue(all(g.state == 'answered' for g in zalo.gap_ids))
        card = gap.with_user(self.lt_on).action_learn()
        entry = self.env['dmag.ai.knowledge'].browse(card['id'])
        self.assertEqual((entry.state, entry.source_type), ('draft', 'inbox'))
        with self.assertRaises(AccessError):
            entry.with_user(self.lt_on).action_approve()
        with self.assertRaises(AccessError):
            entry.with_user(self.manager).action_approve()
        entry.with_user(self.director).action_approve()
        self.assertEqual(gap.state, 'learned')
        conv = self._sim()
        thread = conv.simulator_send('Có nhận bảo hiểm Bảo Việt không ạ?')
        bot = self._bots(thread)[-1]
        self.assertEqual(bot['decision'], 'grounded', bot['decision_note'])
        self.assertIn('chưa liên kết bảo hiểm', bot['body'])

    def test_safety_rules_unchanged(self):
        conv = self._sim()
        thread = conv.simulator_send('Răng em sưng to và chảy máu không cầm')
        self.assertEqual(thread['state'], 'handoff')
        self.assertEqual(thread['messages'][-1]['decision'], 'emergency')
        conv = self._sim()
        thread = conv.simulator_send('Răng em bị ê buốt khi uống nước lạnh, có sao không ạ?')
        last = thread['messages'][-1]
        self.assertEqual(last['decision'], 'out_of_data')
        self.assertEqual(conv.gap_ids.reason, 'medical', 'Không chẩn đoán – chuyển nhân viên / bác sĩ')
        conv = self._sim()
        thread = conv.simulator_send('Em mới nhổ răng khôn hôm qua giờ còn đau')
        last = self._bots(thread)[-1]
        self.assertEqual(last['decision'], 'handoff_script')
        self.assertEqual(thread['state'], 'handoff')

    def test_booking_uses_only_doctors_on_duty(self):
        conv = self._sim()
        thread = conv.simulator_send('Cho em đặt lịch cạo vôi ngày mai')
        bot = self._bots(thread)[-1]
        self.assertEqual(bot['decision'], 'grounded')
        self.assertIn('get_free_slots', [t['tool'] for t in bot['trace']])
        slots = [t for t in bot['trace'] if t['tool'] == 'get_free_slots'][-1]['output']['slots']
        self.assertTrue(slots)
        self.assertNotIn(self.doctor.id, [s['doctor_id'] for s in slots], 'Bác sĩ nghỉ luân phiên ngày mai')
        self.assertIn('Giờ trống', [s['label'] for s in bot['sources']])

    # ------------------------------------------------------------------ kiểm tra phía máy chủ
    def test_numbers_not_in_sources_are_blocked(self):
        conv = self._sim()
        trace = [{'tool': 'search_services', 'input': {'query': 'cạo vôi'},
                  'output': {'services': [{'name': 'Cạo vôi', 'price_vnd': 345000, 'price_text': '345.000 đ'}]}}]
        sources, problem = conv._verify_grounded('Dạ cạo vôi giá 345.000 đ ạ', ['search_services'], trace, '')
        self.assertFalse(problem)
        self.assertEqual(sources[0]['label'], 'Bảng giá')
        _s, problem = conv._verify_grounded('Dạ cạo vôi giá 299.000 đ ạ', ['search_services'], trace, '')
        self.assertIn('299000', problem)
        _s, problem = conv._verify_grounded('Dạ cạo vôi giá 345.000 đ', [], trace, '')
        self.assertTrue(problem, 'Không nêu nguồn → chặn')
        _s, problem = conv._verify_grounded('Dạ có ạ', ['kb:%s' % self.vat.id], trace, '')
        self.assertTrue(problem, 'Mục tri thức không có trong kết quả tra cứu của lượt → chặn')
        _s, problem = conv._verify_grounded('Dạ có ạ', ['get_free_slots'], trace, '')
        self.assertTrue(problem, 'Công cụ không được gọi → chặn')

    def test_live_claude_grounded_and_blocked(self):
        self.company.sudo().write({'dmag_ai_mode': 'live', 'dmag_ai_api_key': 'sk-test'})
        state = {'answer': 'Dạ cạo vôi giá 345.000 đ ạ.'}

        def create(**kwargs):
            tool_names = {t['name'] for t in kwargs.get('tools') or []}
            self.assertTrue({'search_knowledge', 'search_services', 'book_appointment', 'handoff_to_staff'} <= tool_names)
            self.assertEqual(kwargs['output_config']['format']['schema']['required'],
                             ['answer', 'grounded', 'sources', 'needs_staff', 'reason'])
            if kwargs['messages'][-1]['role'] == 'user' and isinstance(kwargs['messages'][-1]['content'], str):
                return response([block(type='tool_use', id='t1', name='search_services',
                                       input={'query': 'Cạo vôi răng AI test'})], stop='tool_use')
            return response([block(type='text', text=json.dumps({
                'answer': state['answer'], 'grounded': True, 'sources': ['search_services'], 'needs_staff': False,
                'reason': ''}))])
        with patch.object(type(self.env['dmag.ai']), '_client', lambda s: fake_client(create)):
            conv = self._sim()
            thread = conv.simulator_send('Cạo vôi răng AI test giá bao nhiêu?')
            bot = self._bots(thread)[-1]
            self.assertEqual(bot['decision'], 'grounded')
            self.assertIn('345.000 đ', bot['body'])
            # Claude "bịa" giá → không gửi; nháp chờ nhân viên + tin giữ chỗ + báo lễ tân
            state['answer'] = 'Dạ cạo vôi chỉ 199.000 đ thôi ạ.'
            thread = conv.simulator_send('Cạo vôi răng AI test giá bao nhiêu vậy?')
            msgs = thread['messages']
            self.assertEqual(msgs[-1]['decision'], 'out_of_data')
            blocked = [m for m in msgs if m['decision'] == 'blocked_unverified']
            self.assertTrue(blocked and blocked[-1]['state'] == 'pending')
            self.assertIn('199000', blocked[-1]['decision_note'])
            self.assertEqual(conv.gap_ids[-1:].reason, 'unverified')

    # ------------------------------------------------------------------ kho tri thức
    def test_kb_loaders_and_approval_locks(self):
        KB = self.env['dmag.ai.knowledge']
        price = KB.search([('source_type', '=', 'pricelist'), ('source_ref', '=', 'product.product,%s' % self.scaling.id)])
        self.assertEqual(price.state, 'approved')
        self.assertTrue(price.auto_managed)
        self.assertIn('345.000 đ', price.content)
        hours = KB.search([('source_type', '=', 'schedule'), ('name', '=', 'Giờ làm việc')])
        self.assertIn('Thứ 2 – Chủ nhật', hours.content)
        doc_entry = KB.search([('source_type', '=', 'rotation'),
                               ('source_ref', '=', 'dmag.dental.practitioner,%s' % self.doctor.id)])
        self.assertIn('nghỉ luân phiên', doc_entry.content)
        scripts = KB.search([('source_type', '=', 'script')])
        self.assertEqual(len(scripts), len(self.scripts))
        # giá đổi → nội dung trả lời dùng giá mới ngay; nạp lại cập nhật mục
        self.scaling.lst_price = 365000
        self.assertIn('365.000 đ', price._live_content())
        KB.load_master_data(self.company)
        self.assertIn('365.000 đ', price.content)
        # khóa: đã duyệt không sửa được (kể cả Quản lý); Quản lý soạn nháp, chỉ Giám đốc duyệt
        with self.assertRaises(UserError):
            self.vat.with_user(self.manager).write({'content': 'Sửa'})
        draft = KB.with_user(self.manager).create({'name': 'Gửi xe đạp điện', 'content': 'Có chỗ sạc xe đạp điện.',
                                                   'question_variants': 'có chỗ sạc xe đạp điện không'})
        self.assertEqual(draft.state, 'draft')
        self.assertFalse([h for h in KB.search_knowledge('có chỗ sạc xe đạp điện không') if h['id'] == draft.id],
                         'Nháp chưa duyệt không được dùng')
        with self.assertRaises(AccessError):
            draft.with_user(self.manager).action_approve()
        with self.assertRaises(AccessError):
            KB.with_user(self.manager).create({'name': 'X', 'content': 'Y', 'state': 'approved'})
        draft.with_user(self.director).action_approve()
        self.assertTrue([h for h in KB.search_knowledge('có chỗ sạc xe đạp điện không') if h['id'] == draft.id])
        # tài liệu: trích văn bản, tách đoạn (nháp) → Giám đốc duyệt tài liệu
        import base64
        md = ('# Chính sách hủy lịch\nKhách hủy lịch trước 24 giờ không mất phí giữ chỗ. Đặt cọc niềng răng được hoàn '
              'nếu hủy trước khi gắn mắc cài.\n\n# Khám cho người cao tuổi\nPhòng khám có ghế nâng hạ và hỗ trợ xe lăn '
              'tại tầng trệt.')
        doc = self.env['dmag.ai.knowledge.document'].with_user(self.manager).create({
            'name': 'Cẩm nang khách hàng', 'filename': 'cam-nang.md', 'datas': base64.b64encode(md.encode())})
        doc.with_user(self.manager).action_extract()
        self.assertEqual(doc.chunk_count, 2)
        self.assertEqual(set(doc.chunk_ids.mapped('state')), {'draft'})
        self.assertEqual(doc.chunk_ids[0].name, 'Chính sách hủy lịch')
        with self.assertRaises(AccessError):
            doc.with_user(self.manager).action_approve()
        doc.with_user(self.director).action_approve()
        hit = KB.search_knowledge('hủy lịch có mất phí không')[0]
        self.assertTrue(hit['grounded'])
        self.assertEqual(hit['source_label'], "Tài liệu 'Cẩm nang khách hàng'")
        overview = KB.get_kb_overview()
        self.assertTrue(any(g['code'] == 'pricelist' and g['approved'] for g in overview['groups']))
        self.assertTrue(KB.try_question('Chủ nhật có làm việc không')['grounded'])
        self.assertFalse(KB.try_question('Có nhận bảo hiểm Bảo Việt không')['grounded'])

    def test_retrieval_accent_insensitive(self):
        KB = self.env['dmag.ai.knowledge']
        with_accents = KB.search_knowledge('Có xuất hóa đơn VAT cho công ty không?')
        without = KB.search_knowledge('co xuat hoa don vat cho cong ty khong')
        self.assertEqual(with_accents[0]['id'], self.vat.id)
        self.assertEqual(without[0]['id'], self.vat.id)
        self.assertTrue(without[0]['grounded'])

    def test_sample_scripts_render_new_placeholders(self):
        self.scaling.warranty_months = 0
        self.extraction.warranty_months = 0
        crown = self.env['product.product'].create({
            'name': 'Mão sứ Zirconia AI test', 'is_dental_service': True, 'dental_category': 'prosthodontic',
            'lst_price': 5000000, 'warranty_months': 120, 'type': 'service', 'dental_requires_tooth': False})
        Reception = self.env['dmag.ai.reception']
        conv = self._sim()
        text = Reception._render_script(self.by_code['bao_hanh'], conv, 'Mão sứ Zirconia AI test bảo hành bao lâu?')['text']
        self.assertIn('120 tháng (10 năm)', text)
        self.assertIn(crown.name, text)
        rendered = Reception._render_script(self.by_code['lich_bac_si'], conv, '')
        self.assertIn(self.doctor.name, rendered['text'])
        self.assertIn('nghỉ luân phiên', rendered['text'])
        self.assertIn('Lịch nghỉ luân phiên', rendered['source_labels'])
        hours = Reception._render_script(self.by_code['gio_mo_cua'], conv, '')['text']
        self.assertIn('Thứ 2 – Chủ nhật', hours)
