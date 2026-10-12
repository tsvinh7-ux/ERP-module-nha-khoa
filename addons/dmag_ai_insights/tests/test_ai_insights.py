import json
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.dmag_ai_insights.models import forecast_math as fm
from odoo.addons.dmag_ai_insights.models.ai_anomaly import AnomalyDetector
from odoo.addons.dmag_ai_insights.models.ai_common import resolve_period
from odoo.addons.dmag_ai_insights.models.ai_qa import TOOLS, _route

# Kỳ cố định trong quá khứ – không lẫn với dữ liệu demo (sinh quanh ngày hôm nay)
D_FROM, D_TO = date(2025, 3, 1), date(2025, 3, 31)


def _block(**kw):
    return SimpleNamespace(**kw)


def _response(content, stop='end_turn', inp=900, out=150):
    return SimpleNamespace(content=content, stop_reason=stop, model='claude-opus-5-5', _request_id='req_x',
                           usage=SimpleNamespace(input_tokens=inp, output_tokens=out, cache_read_input_tokens=0,
                                                 cache_creation_input_tokens=0))


@tagged('post_install', '-at_install')
class TestAiInsights(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env(context=dict(cls.env.context, tz='Asia/Ho_Chi_Minh', tracking_disable=True,
                                   mail_create_nosubscribe=True, mail_notrack=True))
        cls.env = env
        env.user.tz = 'Asia/Ho_Chi_Minh'
        cls.company = env.company
        cls.company.write({'dmag_ai_mode': 'simulate', 'dmag_ai_monthly_budget': 5000000})
        level = env.ref('dmag_dental_base.level_3')
        scopes = env['dmag.practice.scope'].search([])
        Prac = env['dmag.dental.practitioner']
        cls.doc_a = Prac.create({'name': 'BS Kiểm thử Xuân', 'role': 'doctor', 'license_number': 'AI-A',
                                 'scope_ids': [(6, 0, scopes.ids)], 'clinical_level_id': level.id})
        cls.doc_b = Prac.create({'name': 'BS Kiểm thử Thu', 'role': 'doctor', 'license_number': 'AI-B',
                                 'scope_ids': [(6, 0, scopes.ids)], 'clinical_level_id': level.id})
        cls.chair = env['dmag.dental.chair'].create({'name': 'Ghế kiểm thử AI'})
        cls.svc = env['product.product'].create({
            'name': 'Trám (kiểm thử AI)', 'is_dental_service': True, 'dental_duration': 30,
            'dental_requires_tooth': False, 'list_price': 1000000, 'dental_category': 'restorative'})
        Partner = env['res.partner']
        cls.patients = Partner.create([{'name': 'BN AI %s' % i, 'is_patient': True} for i in range(20)])
        # 10 lượt mỗi bác sĩ trong tháng 3/2025; BS Thu giảm 10 % mọi thủ thuật, BS Xuân không giảm
        for i in range(10):
            for doctor, disc, pat in ((cls.doc_a, 0.0, cls.patients[i]), (cls.doc_b, 10.0, cls.patients[10 + i])):
                start = datetime(2025, 3, 3 + i, 2 if doctor == cls.doc_a else 4, 0)
                cls._done_visit(start, pat, doctor, disc)

    @classmethod
    def _done_visit(cls, start, patient, doctor, discount):
        visit = cls.env['dmag.dental.visit'].create({'patient_id': patient.id, 'doctor_id': doctor.id,
                                                     'chair_id': cls.chair.id, 'scheduled_start': start})
        visit.flush_recordset()
        visit.action_check_in()
        visit.action_start()
        cls.env['dmag.dental.procedure'].add_from_workspace(visit.id, cls.svc.id)
        visit.procedure_ids.with_context(dmag_workflow=True).write({'doctor_id': doctor.id, 'discount': discount})
        visit.action_done()
        visit.procedure_ids.filtered(lambda p: p.state != 'done').with_context(dmag_workflow=True).write(
            {'state': 'done'})
        return visit

    def _director(self):
        return self.env['res.users'].create({
            'name': 'GĐ kiểm thử AI', 'login': 'gd_ai_test', 'email': 'gd_ai@test.vn',
            'groups_id': [(6, 0, [self.env.ref('dmag_dental_base.group_dmag_director').id,
                                  self.env.ref('base.group_user').id])]})

    def _user(self, login, group):
        return self.env['res.users'].create({
            'name': login, 'login': login, 'groups_id': [(6, 0, [self.env.ref(group).id,
                                                                 self.env.ref('base.group_user').id])]})

    # ------------------------------------------------------------------ AI-13 hỏi đáp
    def test_router(self):
        r = _route('Bác sĩ nào chốt kế hoạch thấp nhất quý này?')
        self.assertEqual((r['intent'], r['metric'], r['entity'], r['order'], r['period']),
                         ('top', 'plan_acceptance', 'doctor', 'asc', 'this_quarter'))
        r = _route('NPS tuần này so với tuần trước?')
        self.assertEqual((r['metric'], r['period'], r['period_b'], r['intent']), ('nps', 'this_week', 'last_week',
                                                                                   'compare'))
        r = _route('Vì sao doanh thu tháng này chậm?')
        self.assertEqual((r['intent'], r['metric'], r['period']), ('why', 'revenue', 'this_month'))
        self.assertEqual(_route('Thực thu tháng trước?')['metric'], 'collected')
        self.assertEqual(_route('Tỷ lệ khách không đến?')['metric'], 'show_up_rate')

    def test_qa_simulate_equals_engine(self):
        qa = self.env['dmag.ai.qa']
        an = self.env['dmag.ai.analysis']
        today = an._today()
        res = qa.ask('Doanh thu tháng này thế nào?')
        self.assertTrue(res['simulated'])
        d_from, d_to, _label = resolve_period('this_month', today)
        expected = an._value('revenue', d_from, d_to)
        fact = next(f for f in res['data']['facts'] if f['metric'] == 'revenue')
        self.assertAlmostEqual(fact['value'], expected)
        self.assertTrue(res['links'], 'Câu trả lời phải có nút "Mở danh sách"')
        self.assertIn('metric', [t['tool'] for t in res['tool_trace']])
        log = self.env['dmag.ai.log'].search([('feature_id.code', '=', 'AI-13')], limit=1)
        self.assertEqual(log.mode, 'simulate')
        self.assertGreater(log.estimated_cost_vnd, 0)
        self.assertEqual(log.tool_calls, len(res['tool_trace']))
        # Thực thu tháng trước
        res = qa.ask('Thực thu tháng trước bao nhiêu?')
        d_from, d_to, _label = resolve_period('last_month', today)
        fact = res['data']['facts'][0]
        self.assertEqual(fact['metric'], 'collected')
        self.assertAlmostEqual(fact['value'] or 0.0, an._value('collected', d_from, d_to) or 0.0)
        # Xếp hạng bác sĩ theo doanh thu trong một kỳ có tên → giống bộ máy chỉ số
        box_top = an._top('doctor', 'revenue', D_FROM, D_TO)
        rows = {r['name']: r['value'] for r in box_top['rows']}
        self.assertAlmostEqual(rows[self.doc_a.name], an._value('revenue', D_FROM, D_TO, self.doc_a))
        self.assertAlmostEqual(rows[self.doc_a.name], 10 * 1000000)
        self.assertAlmostEqual(rows[self.doc_b.name], 10 * 900000)
        help_res = qa.ask('xin chào')
        self.assertEqual(help_res['data']['intent'], 'help')

    def test_qa_tools_are_strict(self):
        for tool in TOOLS:
            self.assertTrue(tool['strict'])
            schema = tool['input_schema']
            self.assertFalse(schema['additionalProperties'])
            self.assertEqual(sorted(schema['required']), sorted(schema['properties']))

    def test_qa_live_tool_loop(self):
        self.company.sudo().write({'dmag_ai_mode': 'live', 'dmag_ai_api_key': 'sk-test'})
        calls = []

        def create(**kw):
            calls.append(kw)
            self.assertNotIn('tool_choice', kw, 'Không ép AI chọn công cụ')
            self.assertEqual(kw['model'], 'claude-opus-5-5')
            if len(calls) == 1:
                return _response([
                    _block(type='tool_use', id='t1', name='metric', input={
                        'key': 'revenue', 'date_from': '2025-03-01', 'date_to': '2025-03-31',
                        'doctor': 'BS Kiểm thử Thu'}),
                    _block(type='tool_use', id='t2', name='drill_records', input={
                        'key': 'revenue', 'period': 'this_month', 'doctor': None})], stop='tool_use')
            results = kw['messages'][-1]['content']
            self.assertEqual([r['type'] for r in results], ['tool_result', 'tool_result'])
            out = json.loads(results[0]['content'])
            return _response([_block(type='text', text='Doanh thu của BS Thu tháng 3/2025: **%s**.' % out['text'])])

        fake = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
        with patch.object(type(self.env['dmag.ai']), '_client', lambda self: fake):
            res = self.env['dmag.ai.qa'].ask('Doanh thu BS Thu tháng 3/2025?')
        self.assertFalse(res['simulated'])
        self.assertEqual(len(calls), 2)
        self.assertEqual([t['tool'] for t in res['tool_trace']], ['metric', 'drill_records'])
        self.assertIn('9,0 tr', res['text'])
        self.assertEqual(len(res['links']), 2)
        self.assertEqual(res['links'][0]['action']['res_model'], 'dmag.dental.procedure')
        log = self.env['dmag.ai.log'].browse(self.env['dmag.ai.log'].search([], limit=1).id)
        self.assertEqual((log.mode, log.tool_calls, log.input_tokens), ('live', 2, 1800))

    def test_qa_requires_manager(self):
        receptionist = self._user('letan_ai_test', 'dmag_dental_base.group_dmag_receptionist')
        with self.assertRaises(AccessError):
            self.env['dmag.ai.qa'].with_user(receptionist).ask('Doanh thu tháng này?')

    # ------------------------------------------------------------------ AI-14 bản tin
    def test_brief_simulate_and_live(self):
        director = self._director()
        brief = self.env['dmag.ai.brief']._generate(trigger='cron')
        data = json.loads(brief.data_json)
        self.assertEqual(set(data), {'headline', 'summary', 'off_track', 'causes', 'actions', 'highlights'})
        self.assertLessEqual(len(data['actions']), 3)
        self.assertTrue(data['actions'])
        self.assertEqual(brief.state, 'sent')
        self.assertEqual(brief.trigger, 'cron')
        self.assertIn(director.partner_id, brief.message_follower_ids.partner_id)
        self.assertTrue(brief.message_ids.filtered(lambda m: director.partner_id in m.partner_ids))
        self.assertIn('3 việc nên làm', brief.body_html)
        # Claude API: một lần gọi, có JSON schema, không công cụ
        self.company.sudo().write({'dmag_ai_mode': 'live', 'dmag_ai_api_key': 'sk-test'})
        payload = {'headline': 'Doanh thu chậm', 'summary': 'Tóm tắt.', 'off_track': [
            {'metric': 'Doanh thu', 'detail': 'Thực tế 1 tr / mục tiêu 2 tr'}], 'causes': ['Ít lượt khám.'],
            'actions': [{'title': 'Gọi lại khách', 'detail': '5 khách', 'owner': 'Tư vấn viên'}] * 3,
            'highlights': ['NPS tốt.']}
        seen = {}

        def create(**kw):
            seen.update(kw)
            return _response([_block(type='text', text=json.dumps(payload, ensure_ascii=False))])

        fake = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
        with patch.object(type(self.env['dmag.ai']), '_client', lambda self: fake):
            live = self.env['dmag.ai.brief']._generate()
        self.assertEqual(seen['output_config']['format']['type'], 'json_schema')
        self.assertNotIn('tools', seen)
        self.assertEqual(live.mode, 'live')
        self.assertEqual(live.headline, 'Doanh thu chậm')

    def test_brief_cron(self):
        before = self.env['dmag.ai.brief'].search_count([])
        self.env['dmag.ai.brief']._cron_weekly_brief()
        self.assertGreater(self.env['dmag.ai.brief'].search_count([]), before)
        cron = self.env.ref('dmag_ai_insights.cron_dmag_ai_weekly_brief')
        self.assertEqual(cron.interval_type, 'weeks')

    # ------------------------------------------------------------------ AI-15 bất thường
    def test_anomaly_detection_fixtures(self):
        Anomaly = self.env['dmag.ai.anomaly']
        det = AnomalyDetector(self.env, D_TO)
        found = det.discount_staff()
        mine = [f for f in found if f['practitioner_id'] == self.doc_b.id]
        self.assertEqual(len(mine), 1, found)
        self.assertGreaterEqual(mine[0]['score'], 3)
        self.assertAlmostEqual(mine[0]['amount'], 10 * 100000)
        self.assertFalse([f for f in found if f['practitioner_id'] == self.doc_a.id])
        # Hoa hồng tăng đột biến: 10 tuần ~1 tr/tuần, tuần cuối 6 tr
        if 'dmag.commission.line' in self.env:
            Line = self.env['dmag.commission.line'].with_context(dmag_workflow=True)
            user = self._user('hoahong_ai_test', 'dmag_dental_base.group_dmag_doctor')
            for w in range(10):
                Line.create({'name': 'HH tuần %s' % w, 'company_id': self.company.id, 'role': 'doctor',
                             'user_id': user.id, 'amount': 1000000 + 20000 * (w % 3),
                             'date': D_TO - timedelta(days=7 * (11 - w)), 'state': 'valid'})
            Line.create({'name': 'HH đột biến', 'company_id': self.company.id, 'role': 'doctor',
                         'user_id': user.id, 'amount': 6000000, 'date': D_TO - timedelta(days=1), 'state': 'valid'})
            spikes = [f for f in det.commission_spike() if f['user_id'] == user.id]
            self.assertTrue(spikes)
            self.assertEqual(spikes[0]['severity'], 'high')
        # Ghi nhận + luồng xử lý
        records = Anomaly._detect(today=D_TO)
        rec = records.filtered(lambda a: a.kind == 'discount_staff' and a.practitioner_id == self.doc_b)
        self.assertEqual(len(rec), 1)
        self.assertEqual(rec.doc_count, 10)
        self.assertEqual(rec.action_view_documents()['res_model'], 'dmag.dental.procedure')
        again = Anomaly._detect(today=D_TO)
        self.assertEqual(len(again.filtered(lambda a: a.kind == 'discount_staff' and a.practitioner_id == self.doc_b)),
                         1, 'Quét lại không nhân đôi cảnh báo')
        manager = self._user('quanly_ai_test', 'dmag_dental_base.group_dmag_manager')
        with self.assertRaises(UserError):
            rec.with_user(manager).action_review()  # phải ghi giải trình
        rec.with_user(manager).write({'manager_note': 'Chương trình tri ân khách cũ'})
        rec.with_user(manager).action_review()
        self.assertEqual(rec.state, 'review')
        with self.assertRaises(AccessError):
            rec.with_user(manager).action_close()
        director = self._director()
        rec.with_user(director).write({'director_note': 'Chấp nhận'})
        rec.with_user(director).action_close()
        self.assertEqual(rec.state, 'closed')
        rec.action_ai_narrative()  # giả lập
        self.assertIn('z', rec.explanation)
        self.assertTrue(rec.ai_narrative)

    def test_refund_anomaly(self):
        journal = self.env['account.journal'].search([('type', '=', 'sale'), ('company_id', '=', self.company.id)],
                                                     limit=1)
        if not journal:
            self.skipTest('Chưa có hệ thống tài khoản')
        partner = self.patients[0]
        moves = self.env['account.move'].create([{
            'move_type': 'out_invoice', 'partner_id': partner.id, 'invoice_date': date(2025, 3, 5),
            'date': date(2025, 3, 5), 'journal_id': journal.id,
            'invoice_line_ids': [(0, 0, {'name': 'Dịch vụ', 'quantity': 1, 'price_unit': price, 'tax_ids': [(6, 0, [])]})],
        } for price in (1000000, 1200000, 900000)])
        moves.action_post()
        refund = moves[0]._reverse_moves([{'date': date(2025, 3, 20), 'invoice_date': date(2025, 3, 20),
                                           'ref': 'Hoàn tiền kiểm thử'}])
        refund.action_post()
        found = AnomalyDetector(self.env, D_TO).refunds()
        mine = [f for f in found if f['res_ids'] == refund.ids]
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0]['kind'], 'refund')

    # ------------------------------------------------------------------ AI-16 dự báo
    def test_forecast_math_deterministic(self):
        season = [10, 12, 9, 11, 14, 20]
        series = [season[i % 6] + 0.2 * i for i in range(48)]
        a = fm.holt_winters(series, 12)
        b = fm.holt_winters(series, 12)
        self.assertEqual(a, b)
        self.assertEqual(a['method'], 'holt_winters')
        # bắt được mùa vụ: ngày thứ Bảy (vị trí 5) cao nhất trong chu kỳ dự báo
        week = a['forecast'][:6]
        self.assertEqual(week.index(max(week)), (5 - 48) % 6)
        self.assertLess(abs(a['forecast'][0] - (season[0] + 0.2 * 48)), 3)
        capped, rate, var, cap = fm.split_spikes([1, 2, 1, 2, 1, 2, 1, 2, 1, 50])
        self.assertLess(max(capped), 50)
        self.assertAlmostEqual(sum(capped) / 10 + rate, sum([1, 2, 1, 2, 1, 2, 1, 2, 1, 50]) / 10)
        self.assertGreater(fm.robust_z(50, [1, 2, 1, 2, 1, 2]), 10)
        self.assertEqual(fm.holt_winters([], 3)['forecast'], [0.0, 0.0, 0.0])

    def test_forecast_sunday_seasonality(self):
        """Phòng khám mở 7 ngày, Chủ nhật đông nhất → dự báo bắt được mùa vụ theo thứ (Chủ nhật cao nhất)."""
        F = self.env['dmag.ai.forecast']
        today = date(2025, 3, 10)
        hist = [today - timedelta(days=i) for i in range(56, 0, -1)]
        series = [(18000000.0 if d.weekday() == 6 else 10000000.0) + (i % 3) * 200000 for i, d in enumerate(hist)]
        profile = fm.weekday_profile(hist, series)
        self.assertGreater(profile[6][1], 1.4)
        scope = self.env['dmag.goal.engine']._scope(hist[0], hist[-1], self.env.companies, today=today)

        def fake_history(_self, d_from, d_to):
            return hist, list(series), scope
        with patch.object(type(F), '_daily_history', fake_history):
            res = F._revenue_forecast(month_from=date(2025, 3, 1), today=today)
        model = res['model']
        self.assertEqual(model['peak_weekday'], 'Chủ nhật')
        sunday = next(w for w in model['weekday_profile'] if w['weekday'] == 6)
        self.assertGreater(sunday['index'], 1.4)
        self.assertEqual(len(model['weekday_profile']), 7)
        rows = res['days']
        sun = [r['value'] for r in rows if fields.Date.to_date(r['date']).weekday() == 6]
        other = [r['value'] for r in rows if fields.Date.to_date(r['date']).weekday() != 6]
        self.assertEqual(len(rows), 22, 'Mọi ngày còn lại của tháng (kể cả Chủ nhật) đều là ngày làm việc')
        self.assertGreater(sum(sun) / len(sun), 1.3 * sum(other) / len(other))

    def test_forecast_rpc(self):
        F = self.env['dmag.ai.forecast']
        one = F._revenue_forecast(month_from=date(2025, 3, 1), today=date(2025, 3, 15))
        two = F._revenue_forecast(month_from=date(2025, 3, 1), today=date(2025, 3, 15))
        self.assertEqual(one['total'], two['total'])
        self.assertLessEqual(one['low'], one['total'])
        self.assertGreaterEqual(one['high'], one['total'])
        self.assertAlmostEqual(one['actual_to_date'],
                               self.env['dmag.ai.analysis']._value('revenue', date(2025, 3, 1), date(2025, 3, 14)))
        res = F.get_forecast()
        self.assertIn('materials', res)
        self.assertTrue(res['revenue']['cumulative'])
        self.assertTrue(self.env['dmag.ai.log'].search_count([('feature_id.code', '=', 'AI-16')]))

    # ------------------------------------------------------------------ Trung tâm AI
    def test_hub(self):
        hub = self.env['dmag.ai.hub'].get_hub()
        codes = [f['code'] for f in hub['features']]
        self.assertEqual(codes, ['AI-%02d' % i for i in range(20)])
        by = {f['code']: f for f in hub['features']}
        self.assertEqual(by['AI-13']['state'], 'simulate')
        self.assertEqual(by['AI-15']['state'], 'local')
        self.assertTrue(by['AI-13']['target'])
        self.assertTrue(all(f['what'] and f['example'] for f in hub['features']))
        self.env.ref('dmag_ai_core.feature_ai_14').active = False
        self.company.dmag_ai_mode = 'live'
        by = {f['code']: f for f in self.env['dmag.ai.hub'].get_hub()['features']}
        self.assertEqual(by['AI-14']['state'], 'off')
        self.assertEqual(by['AI-13']['state'], 'live')
        receptionist = self._user('letan_hub_test', 'dmag_dental_base.group_dmag_receptionist')
        rhub = self.env['dmag.ai.hub'].with_user(receptionist).get_hub()
        visible = {f['audience'] for f in rhub['features'] if f['visible']}
        self.assertEqual(visible, {'front', 'patient', 'platform'})
        self.assertFalse(rhub['is_manager'])
        action = self.env['dmag.ai.hub'].open_target('AI-16')
        self.assertEqual(action['tag'], 'dmag_ai_forecast')
        panel = self.env['dmag.ai.hub'].get_goal_panel()
        self.assertIn('anomalies', panel)
