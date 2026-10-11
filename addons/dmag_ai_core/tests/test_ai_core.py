from types import SimpleNamespace
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.dmag_ai_core.models import dmag_ai_service
from odoo.addons.dmag_ai_core.models.dmag_ai_service import DmagAiPseudonymizer


def _block(**kw):
    return SimpleNamespace(**kw)


def _response(content, stop='end_turn', inp=1000, out=200):
    return SimpleNamespace(content=content, stop_reason=stop, model='claude-opus-5-5', _request_id='req_1',
                           usage=SimpleNamespace(input_tokens=inp, output_tokens=out,
                                                 cache_read_input_tokens=0, cache_creation_input_tokens=0))


@tagged('post_install', '-at_install')
class TestAiCore(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.patient = cls.env['res.partner'].create({
            'name': 'Nguyễn Thị Mai', 'is_patient': True, 'mobile': '0912345678',
            'citizen_id': '079090000123', 'dmag_ai_consent': True})
        cls.company = cls.env.company
        cls.company.write({'dmag_ai_mode': 'simulate', 'dmag_ai_monthly_budget': 5000000})

    def test_simulate_logs_estimate(self):
        res = self.env['dmag.ai'].run('AI-04', 'Tóm tắt hồ sơ.', 'Bệnh nhân Nguyễn Thị Mai, dị ứng Lidocaine.',
                                      patient=self.patient, simulate=lambda: {'text': 'Tóm tắt mẫu'})
        self.assertTrue(res['simulated'])
        self.assertEqual(res['text'], 'Tóm tắt mẫu')
        log = self.env['dmag.ai.log'].browse(res['log_id'])
        self.assertEqual(log.cost_vnd, 0)
        self.assertGreater(log.estimated_cost_vnd, 0)
        self.assertNotIn('Nguyễn Thị Mai', log.request_preview)
        self.assertIn('[BN_1]', log.request_preview)
        with self.assertRaises(AccessError):
            log.with_user(self.env.ref('base.user_demo') if self.env.ref('base.user_demo', False) else self.env.user).write({'cost_vnd': 1})

    def test_consent_required(self):
        self.patient.dmag_ai_consent = False
        with self.assertRaises(UserError):
            self.env['dmag.ai'].run('AI-04', 's', 'u', patient=self.patient)
        self.company.dmag_ai_require_consent = False
        self.env['dmag.ai'].run('AI-04', 's', 'u', patient=self.patient)

    def test_feature_off(self):
        self.env.ref('dmag_ai_core.feature_ai_04').active = False
        with self.assertRaises(UserError):
            self.env['dmag.ai'].run('AI-04', 's', 'u')

    def test_pseudonymizer_roundtrip(self):
        p = DmagAiPseudonymizer()
        p.add_partner(self.patient)
        masked = p.mask('Chị Nguyễn Thị Mai, SĐT 0912345678, CCCD 079090000123')
        self.assertNotIn('0912345678', masked)
        self.assertEqual(p.unmask(masked), 'Chị Nguyễn Thị Mai, SĐT 0912345678, CCCD 079090000123')
        self.assertEqual(p.unmask({'a': [masked]}), {'a': ['Chị Nguyễn Thị Mai, SĐT 0912345678, CCCD 079090000123']})

    def test_live_tool_loop_and_cost(self):
        self.company.sudo().write({'dmag_ai_mode': 'live', 'dmag_ai_api_key': 'sk-test'})
        calls = []

        def create(**kw):
            calls.append(kw)
            if len(calls) == 1:
                # AI nhận dữ liệu đã ẩn danh và gọi công cụ với mã [BN_1]
                self.assertNotIn('Nguyễn Thị Mai', str(kw['messages']))
                self.assertEqual(kw['fallbacks'], 'default')
                return _response([_block(type='tool_use', id='t1', name='get_slots', input={'patient': '[BN_1]'})],
                                 stop='tool_use')
            self.assertEqual(kw['messages'][-1]['content'][0]['type'], 'tool_result')
            return _response([_block(type='text', text='Đã đặt lịch cho [BN_1] lúc 14:00.')])

        fake = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
        seen = {}
        with patch.object(type(self.env['dmag.ai']), '_client', lambda self: fake):
            res = self.env['dmag.ai'].run(
                'AI-07', 'Đặt lịch', 'Tôi là Nguyễn Thị Mai muốn đặt lịch', patient=self.patient,
                tools=[{'name': 'get_slots', 'description': 'x', 'input_schema': {'type': 'object'}}],
                tool_handlers={'get_slots': lambda i: seen.update(i) or {'slots': ['14:00']}})
        self.assertEqual(seen['patient'], 'Nguyễn Thị Mai', 'Công cụ nhận lại giá trị thật')
        self.assertEqual(res['text'], 'Đã đặt lịch cho Nguyễn Thị Mai lúc 14:00.')
        log = self.env['dmag.ai.log'].browse(res['log_id'])
        self.assertEqual((log.input_tokens, log.output_tokens, log.tool_calls), (2000, 400, 1))
        self.assertAlmostEqual(log.cost_usd, (2000 * 4 + 400 * 20) / 1e6)

    def test_live_budget_and_refusal(self):
        self.company.sudo().write({'dmag_ai_mode': 'live', 'dmag_ai_api_key': 'sk-test'})
        fake = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(
            create=lambda **kw: _response([], stop='refusal'))))
        with patch.object(type(self.env['dmag.ai']), '_client', lambda self: fake):
            with self.assertRaises(UserError):
                self.env['dmag.ai'].run('AI-13', 's', 'u')
        self.company.dmag_ai_monthly_budget = 0.0001
        self.env['dmag.ai.log'].create({'feature_id': self.env.ref('dmag_ai_core.feature_ai_13').id,
                                        'mode': 'live', 'cost_vnd': 100})
        with self.assertRaises(UserError):
            self.env['dmag.ai'].run('AI-13', 's', 'u')
        self.assertTrue(dmag_ai_service.PRICES['claude-opus-5-5'])
