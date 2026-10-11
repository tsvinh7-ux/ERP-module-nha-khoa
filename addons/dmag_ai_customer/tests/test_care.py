import base64
import json
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import HttpCase, tagged
from odoo.tools.misc import file_path

from odoo.addons.dmag_ai_customer.models.dmag_ai_feedback import classify_local
from odoo.addons.dmag_ai_customer.models.dmag_ai_followup import evaluate_local

from .common import AiCustomerCase, block, fake_client, response


@tagged('post_install', '-at_install')
class TestFeedback(AiCustomerCase):
    """AI-09 – phân loại phản hồi."""

    def test_local_classifier(self):
        res = classify_local('Chờ lâu quá gần 1 tiếng, lễ tân thái độ khó chịu. Tôi sẽ không quay lại nữa', score=2)
        self.assertEqual(res['sentiment'], 'negative')
        self.assertEqual(res['severity'], 'high')
        self.assertTrue(res['churn_risk'])
        self.assertIn(res['topic'], ('wait_time', 'staff_attitude'))
        res = classify_local('Bác sĩ nhẹ nhàng, nhổ răng không đau, rất hài lòng', score=10)
        self.assertEqual((res['topic'], res['sentiment'], res['severity']), ('praise', 'positive', 'low'))
        res = classify_local('Sau nhổ răng bị sưng to và sốt 39 độ')
        self.assertEqual(res['severity'], 'critical')
        self.assertTrue(res['red_flags'])
        self.assertIn('KHẨN', res['suggested_action'])

    def test_nps_submit_creates_sorted_feedback(self):
        visit = self._done_visit()
        Nps = self.env['dmag.nps.response']
        low = Nps._dmag_create_for_visit(visit)
        low.submit(3, 'Đợi lâu, tính tiền phát sinh không báo trước')
        fb = low.dmag_ai_feedback_ids
        self.assertTrue(fb)
        self.assertEqual(fb.method, 'simulate')
        self.assertEqual(fb.sentiment, 'negative')
        self.assertTrue(fb.activity_ids, 'Mức cao → giao việc')
        praise = self.env['dmag.ai.feedback']._create_from_text('Rất hài lòng, cảm ơn bác sĩ', 'manual', partner=self.patient)
        ordered = self.env['dmag.ai.feedback'].search([('id', 'in', (fb | praise).ids)])
        self.assertEqual(ordered[0], fb, 'Danh sách sắp theo mức độ nghiêm trọng')

    def test_no_consent_falls_back_local(self):
        self.patient.dmag_ai_consent = False
        fb = self.env['dmag.ai.feedback']._create_from_text('Răng sứ bị bong sau 2 tuần', 'manual', partner=self.patient)
        self.assertEqual(fb.method, 'local')
        self.assertIn('đồng ý', fb.method_note)
        self.assertEqual(fb.topic, 'result_quality')

    def test_live_schema(self):
        self.company.sudo().write({'dmag_ai_mode': 'live', 'dmag_ai_api_key': 'sk-test'})
        seen = {}

        def create(**kw):
            seen.update(kw)
            data = {'topic': 'pain', 'severity': 'high', 'sentiment': 'negative', 'churn_risk': False,
                    'summary': '[BN_1] còn đau', 'suggested_reply': 'Xin lỗi [BN_1]', 'suggested_action': 'BS gọi',
                    'red_flags': []}
            return response([block(type='text', text=json.dumps(data))])

        with patch.object(type(self.env['dmag.ai']), '_client', lambda s: fake_client(create)):
            fb = self.env['dmag.ai.feedback']._create_from_text('Lê Thị Hoa: còn đau nhiều', 'manual', partner=self.patient)
        fmt = seen['output_config']['format']
        self.assertEqual(fmt['type'], 'json_schema')
        self.assertFalse(fmt['schema']['additionalProperties'])
        self.assertNotIn('Lê Thị Hoa', json.dumps(seen['messages'], ensure_ascii=False), 'Ẩn danh trước khi gửi')
        self.assertEqual((fb.topic, fb.method), ('pain', 'live'))
        self.assertEqual(fb.suggested_reply, 'Xin lỗi Lê Thị Hoa')


@tagged('post_install', '-at_install')
class TestCareAndFollowup(AiCustomerCase):
    """AI-12 nội dung chăm sóc, AI-18 theo dõi sau điều trị."""

    def test_care_draft_simulate_and_send(self):
        visit = self._done_visit()
        action = visit.action_dmag_ai_care_draft()
        draft = self.env['dmag.ai.care.draft'].browse(action['res_id'])
        self.assertEqual(draft.mode, 'simulate')
        self.assertIn('Hoa', draft.call_script)
        self.assertIn('Nhổ răng khôn AI test', draft.call_script)
        self.assertIn('chườm lạnh', draft.call_script.lower() + draft.key_points.lower())
        self.assertIn('028 3999 9999', draft.oa_message)
        self.assertGreater(draft.estimated_cost_vnd, 0)
        draft.oa_message = draft.oa_message + '\nNV Lan'
        draft.action_approve_send()
        self.assertEqual(draft.state, 'sent')
        self.assertEqual(draft.approved_by_id, self.env.user)
        draft.call_pain = 3
        draft.action_log_call()
        self.assertEqual(visit.pain_score_24h, 3)

    def test_care_requires_consent(self):
        self.patient.dmag_ai_consent = False
        visit = self._done_visit()
        with self.assertRaises(UserError):
            visit.action_dmag_ai_care_draft()

    def test_followups_created_and_evaluated(self):
        visit = self._done_visit()
        fus = visit.dmag_ai_followup_ids
        self.assertEqual(sorted(fus.mapped('checkpoint')), ['24h', '72h'])
        fu24 = fus.filtered(lambda f: f.checkpoint == '24h')
        fu24.action_send()
        self.assertEqual(fu24.state, 'sent')
        fu24.submit_answers(2, 'none', 'mild', False, 'Ăn uống được, hơi ê')
        self.assertEqual(fu24.level, 'normal')
        self.assertEqual(fu24.state, 'answered')
        fu72 = fus - fu24
        fu72.submit_answers(5, 'none', 'none', False, 'Có mùi hôi và hơi sốt về chiều')
        self.assertEqual(fu72.level, 'urgent', 'AI đọc mô tả tự do bắt được dấu hiệu')
        self.assertEqual(fu72.local_level, 'urgent', 'Đau tăng 2 → 5 ở mốc 72h')
        self.assertEqual(fu72.state, 'alert')
        self.assertTrue(fu72.activity_ids)
        with self.assertRaises(UserError):
            fu72.submit_answers(1, 'none', 'none', False)

    def test_local_thresholds(self):
        self.assertEqual(evaluate_local({'pain': 8, 'bleeding': 'none', 'swelling': 'none'})[0], 'urgent')
        self.assertEqual(evaluate_local({'pain': 3, 'bleeding': 'heavy', 'swelling': 'none'})[0], 'urgent')
        self.assertEqual(evaluate_local({'pain': 3, 'bleeding': 'none', 'swelling': 'mild'}, '72h')[0], 'watch')
        self.assertEqual(evaluate_local({'pain': 2, 'bleeding': 'light', 'swelling': 'mild'}, '24h')[0], 'normal')
        self.assertEqual(evaluate_local({'pain': 1, 'fever': True})[0], 'urgent')

    def test_light_visit_has_no_followup(self):
        visit = self._done_visit(product=self.scaling)
        self.assertFalse(visit.dmag_ai_followup_ids)

    def test_smile_simulate_and_live_vision(self):
        image = base64.b64encode(open(file_path('dmag_ai_customer/static/img/demo_smile.jpg'), 'rb').read())
        smile = self.env['dmag.ai.smile'].create({'patient_id': self.patient.id, 'image_before': image})
        smile.action_generate()
        self.assertEqual(smile.state, 'done')
        self.assertTrue(smile.image_result)
        self.assertTrue(smile.shade_now)
        self.assertIn('Giả lập', smile.mode)
        self.assertIn('minh họa', smile.caution.lower())
        self.company.sudo().write({'dmag_ai_mode': 'live', 'dmag_ai_api_key': 'sk-test'})
        seen = {}

        def create(**kw):
            seen.update(kw)
            data = {'observations': ['Màu răng hơi ngả vàng'], 'options': [{'service': 'Cạo vôi răng AI test', 'why': 'Làm sạch'}],
                    'caution': 'Chỉ minh họa'}
            return response([block(type='text', text=json.dumps(data, ensure_ascii=False))])

        with patch.object(type(self.env['dmag.ai']), '_client', lambda s: fake_client(create)):
            smile.action_generate()
        content = seen['messages'][-1]['content']
        self.assertEqual(content[0]['type'], 'image')
        self.assertEqual(content[0]['source']['media_type'], 'image/jpeg')
        self.assertIn('Claude', smile.mode)
        self.assertIn('345.000 đ', smile.options, 'Giá lấy từ bảng giá, không do AI nêu')


@tagged('post_install', '-at_install')
class TestPortalAssistant(AiCustomerCase):
    """AI-17 – phạm vi dữ liệu: người dùng cổng chỉ thấy dữ liệu của mình."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.visit_a = cls._done_visit()
        cls.other = cls.env['res.partner'].create({'name': 'Người Khác', 'is_patient': True, 'dmag_ai_consent': True})
        cls.visit_b = cls._done_visit(patient=cls.other)
        cls.portal_user = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': cls.patient.name, 'login': 'hoa.portal@example.com', 'partner_id': cls.patient.id,
            'groups_id': [(6, 0, [cls.env.ref('base.group_portal').id])]})

    def test_scope(self):
        Assistant = self.env['dmag.ai.portal.assistant'].with_user(self.portal_user).sudo()
        detail = Assistant.tool_get_visit_detail(self.patient, self.visit_a.id)
        self.assertEqual(detail['id'], self.visit_a.id)
        with self.assertRaises(AccessError):
            Assistant.tool_get_visit_detail(self.patient, self.visit_b.id)
        visits = Assistant.tool_list_my_visits(self.patient, 10)
        self.assertNotIn(self.visit_b.id, [v['id'] for v in visits['recent']])
        with self.assertRaises(AccessError):
            self.env['dmag.ai.feedback'].with_user(self.portal_user).search([])

    def test_ask_simulate_and_consent(self):
        Assistant = self.env['dmag.ai.portal.assistant'].with_user(self.portal_user).sudo()
        res = Assistant.ask(self.patient, 'Sau buổi khám vừa rồi tôi cần chăm sóc thế nào?')
        self.assertTrue(res['simulated'])
        self.assertIn('chườm lạnh', res['answer'].lower())
        self.assertIn('get_visit_detail', res['tools'])
        res = Assistant.ask(self.patient, 'Tôi bị sưng to và sốt')
        self.assertIn('028 3999 9999', res['answer'])
        self.patient.dmag_ai_consent = False
        self.assertTrue(Assistant.ask(self.patient, 'Kế hoạch của tôi?').get('need_consent'))

    def test_live_tools_scoped(self):
        self.company.sudo().write({'dmag_ai_mode': 'live', 'dmag_ai_api_key': 'sk-test'})
        calls = []

        def create(**kw):
            calls.append(kw)
            if len(calls) == 1:
                # AI cố đọc lượt khám của người khác → công cụ trả lỗi quyền, không lộ dữ liệu
                return response([block(type='tool_use', id='x', name='get_visit_detail', input={'visit_id': self.visit_b.id})],
                                stop='tool_use')
            result = kw['messages'][-1]['content'][0]
            self.assertTrue(result['is_error'])
            self.assertNotIn('Người Khác', result['content'])
            return response([block(type='text', text='Mình chỉ xem được hồ sơ của bạn.')])

        Assistant = self.env['dmag.ai.portal.assistant'].with_user(self.portal_user).sudo()
        with patch.object(type(self.env['dmag.ai']), '_client', lambda s: fake_client(create)):
            res = Assistant.ask(self.patient, 'Cho xem lượt khám %s' % self.visit_b.id)
        self.assertEqual(res['answer'], 'Mình chỉ xem được hồ sơ của bạn.')
        self.assertTrue(all(t['strict'] for t in calls[0]['tools']))


@tagged('post_install', '-at_install')
class TestHttp(HttpCase):
    """Trang công khai AI-18 và JSON trợ lý cổng AI-17."""

    def test_followup_page_and_assistant_json(self):
        env = self.env(context=dict(self.env.context, tracking_disable=True))
        patient = env['res.partner'].create({'name': 'Vũ Thị Lan', 'is_patient': True, 'dmag_ai_consent': True,
                                             'email': 'lan.portal@example.com'})
        env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Vũ Thị Lan', 'login': 'lan.portal', 'password': 'lan.portal.123', 'partner_id': patient.id,
            'groups_id': [(6, 0, [env.ref('base.group_portal').id])]})
        product = env['product.product'].create({'name': 'Nhổ răng HTTP', 'is_dental_service': True,
                                                 'dental_category': 'surgery', 'dental_requires_tooth': False,
                                                 'type': 'service', 'lst_price': 1000000})
        chair = env['dmag.dental.chair'].search([], limit=1) or env['dmag.dental.chair'].create({'name': 'Ghế HTTP'})
        visit = env['dmag.dental.visit'].create({'patient_id': patient.id, 'chair_id': chair.id,
                                                 'service_ids': [(6, 0, product.ids)]})
        visit.action_check_in()
        visit.action_start(chair_id=chair.id)
        env['dmag.dental.procedure'].create({'visit_id': visit.id, 'product_id': product.id}).action_done()
        visit.action_done()
        fu = visit.dmag_ai_followup_ids[:1].sudo()
        self.assertTrue(fu)
        page = self.url_open('/dmag/followup/%s' % fu.token)
        self.assertEqual(page.status_code, 200)
        self.assertIn('Bạn cảm thấy thế nào', page.text)
        self.assertEqual(self.url_open('/dmag/followup/not-a-token').status_code, 404)

        self.authenticate('lan.portal', 'lan.portal.123')
        res = self.url_open('/my/dental/assistant/ask', data=json.dumps({
            'jsonrpc': '2.0', 'method': 'call', 'params': {'question': 'Lịch hẹn tiếp theo của tôi?'}}),
            headers={'Content-Type': 'application/json'})
        result = res.json()['result']
        self.assertTrue(result['simulated'])
        self.assertIn('list_my_visits', result['tools'])
        home = self.url_open('/my/dental')
        self.assertIn('dmag_ai_assistant', home.text)
