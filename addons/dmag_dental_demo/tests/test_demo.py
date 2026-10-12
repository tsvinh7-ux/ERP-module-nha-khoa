import json
import re

from odoo.exceptions import AccessError
from odoo.tests import HttpCase, TransactionCase, tagged

from odoo.addons.dmag_dental_demo.generator import data as D

GROUPS = {
    'letan.demo': 'dmag_dental_base.group_dmag_receptionist',
    'tuvan.demo': 'dmag_dental_base.group_dmag_receptionist',
    'phuta.demo': 'dmag_dental_base.group_dmag_assistant',
    'bacsi.demo': 'dmag_dental_base.group_dmag_doctor',
    'bacsi2.demo': 'dmag_dental_base.group_dmag_doctor',
    'bacsi3.demo': 'dmag_dental_base.group_dmag_doctor',
    'phuta2.demo': 'dmag_dental_base.group_dmag_assistant',
    'quanly.demo': 'dmag_dental_base.group_dmag_manager',
    'giamdoc.demo': 'dmag_dental_base.group_dmag_director',
}
MIN_DONE_PAID = 40


def demo_user(env, login):
    return env['res.users'].search([('login', '=', login)], limit=1)


@tagged('post_install', '-at_install')
class TestDemoData(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.Visit = cls.env['dmag.dental.visit']

    def test_01_hook_ran_and_users(self):
        self.assertEqual(self.env['ir.config_parameter'].sudo().get_param('dmag.demo_mode'), '1')
        for login, group in GROUPS.items():
            user = demo_user(self.env, login)
            self.assertTrue(user, 'Thiếu người dùng demo %s' % login)
            self.assertTrue(user.has_group(group), '%s phải thuộc nhóm %s' % (login, group))
        self.assertFalse(demo_user(self.env, 'letan.demo').has_group('dmag_dental_base.group_dmag_doctor'))
        self.assertFalse(demo_user(self.env, 'bacsi.demo').has_group('dmag_dental_base.group_dmag_manager'))
        doctor = self.env['dmag.dental.practitioner'].search(
            [('user_id', '=', demo_user(self.env, 'bacsi.demo').id)])
        self.assertEqual(doctor.role, 'doctor')
        self.assertTrue(doctor.license_number and doctor.scope_ids and doctor.clinical_level_id)
        self.assertTrue(doctor.sudo().employee_id)
        portal = demo_user(self.env, D.PORTAL_LOGIN)
        self.assertTrue(portal and portal.has_group('base.group_portal'))

    def test_02_integrations_are_simulated(self):
        company = self.company
        self.assertEqual(company.dmag_zns_mode, 'mock')
        rx_config = self.env['dmag.rx.national.config']._get_for_company(company)
        self.assertTrue(rx_config.enabled)
        self.assertEqual(rx_config.mode, 'mock')
        provider = self.env['dmag.esign.provider']._dmag_get_provider(company)
        self.assertEqual(provider.provider_type, 'mock')
        sepay = self.env['dmag.sepay.config']._get_for_company(company)
        self.assertEqual(sepay.bank_code, 'MBBank')
        self.assertEqual(sepay.account_number, '0000000000')
        self.assertEqual(sepay.account_name, 'NHA KHOA DMAG DEMO')
        self.assertTrue(sepay.sudo().api_key)
        if 'demo_mode' in sepay._fields:
            self.assertTrue(sepay.demo_mode)
        self.assertEqual(company.dmag_facility_code and len(company.dmag_facility_code), 5)
        self.assertTrue(company.dmag_license_number and company.dmag_professional_director)
        self.assertEqual(company.dmag_max_discount, 10.0)

    def test_03_catalog_and_policies(self):
        services = self.env['product.product'].search([('is_dental_service', '=', True),
                                                       ('default_code', '=like', 'DM-%')])
        self.assertGreaterEqual(len(services), 25)
        whitening = services.filtered(lambda p: p.default_code == 'DM-WHITENING')
        self.assertEqual(whitening.dental_vat_regime, 'taxable')
        filling = services.filtered(lambda p: p.default_code == 'DM-FILLING')
        self.assertEqual(filling.dental_vat_regime, 'exempt')
        self.assertTrue(filling.warranty_months)
        rules = self.env['dmag.commission.rule'].search([('name', 'like', '(mẫu)')])
        self.assertEqual(set(rules.mapped('role')), {'doctor', 'assistant', 'consultant', 'receptionist',
                                                      'referrer'})
        self.assertTrue(all(rules.mapped('active')))
        self.assertEqual(len(self.env['dmag.dental.chair'].search([('name', 'like', '(demo)')])), 4)
        docs = self.env['dmag.compliance.doc'].search([('name', 'like', '(mẫu)')])
        self.assertIn('expired', docs.mapped('state'))
        self.assertIn('expiring', docs.mapped('state'))
        self.assertTrue(self.env['dmag.care.plan'].search([('name', 'like', '(mẫu)')]))

    def test_04_patients(self):
        patients = self.env['res.partner'].search([('is_patient', '=', True), ('citizen_id', '!=', False),
                                                   ('data_consent', '=', True)])
        demo = patients.filtered(lambda p: p.name in {spec[1] for spec in D.PATIENTS})
        self.assertGreaterEqual(len(demo), 40)
        self.assertTrue(all(len(p.citizen_id) == 12 and p.citizen_id.isdigit() for p in demo))
        self.assertTrue(demo.filtered(lambda p: p.age < 6 and p.guardian_id))
        self.assertTrue(demo.filtered('has_danger_alert'))
        self.assertTrue(demo.filtered('referrer_id'))
        self.assertTrue(demo.mapped('dental_family_id.head_id'))

    def test_05_today_board(self):
        receptionist = demo_user(self.env, 'letan.demo')
        board = self.Visit.with_user(receptionist).get_frontdesk_board()
        states = {v['state'] for v in board['visits']}
        self.assertGreaterEqual(len(board['visits']), 6)
        self.assertTrue(states & {'arrived', 'in_chair'}, states)
        self.assertTrue(states & {'confirmed', 'draft'}, states)
        self.assertTrue([c for c in board['chairs'] if c['visit']], 'Phải có ghế đang điều trị')

    def test_06_history_done_paid_with_kct(self):
        done = self.Visit.search([('state', '=', 'done'), ('record_state', '=', 'signed')])
        paid = done.filtered(lambda v: v.payment_status == 'paid')
        self.assertGreaterEqual(len(paid), MIN_DONE_PAID)
        lines = paid.sudo().mapped('invoice_ids.invoice_line_ids').filtered(
            lambda l: l.product_id.dental_vat_regime == 'exempt')
        self.assertTrue(lines)
        self.assertTrue(all('KCT' in l.tax_ids.mapped('description') for l in lines))
        self.assertTrue(done.filtered(lambda v: v.payment_status == 'to_pay'), 'Cần có ca thu một phần')
        self.assertTrue(self.Visit.search_count([('state', '=', 'no_show')]))
        self.assertTrue(self.Visit.search_count([('state', '=', 'cancel')]))
        self.assertTrue(self.env['dmag.payment.log'].search_count([('source', '=', 'sepay')]))
        self.assertTrue(self.env['dmag.loyalty.ledger'].search_count([]))
        self.assertTrue(self.env['dmag.commission.line'].search_count([('state', '=', 'valid')]))
        self.assertTrue(self.env['dmag.warranty.card'].search_count([]))
        self.assertTrue(self.env['dmag.material.usage'].search_count([]))
        self.assertTrue(self.env['dmag.lab.order'].search_count([]))
        self.assertTrue(self.env['dmag.nps.response'].search_count([('state', '=', 'answered')]))
        plans = self.env['dmag.treatment.plan'].search([])
        self.assertTrue(plans.filtered(lambda p: len(p.option_ids) >= 2 and p.accepted_option_id))
        self.assertTrue(plans.filtered(lambda p: p.state == 'presented'))
        self.assertTrue(done.filtered(lambda v: v.esign_state == 'signed'))
        sheets = self.env['dmag.pay3p.sheet'].search([])
        self.assertIn('approved', sheets.mapped('state'))
        self.assertIn('draft', sheets.mapped('state'))
        self.assertTrue(self.env['dmag.commission.statement'].search([('state', '=', 'confirmed')]))

    def test_07_prescription_code(self):
        rx = self.env['dmag.prescription'].search([('state', 'in', ('issued', 'sent'))])
        self.assertTrue(rx)
        for code in rx.mapped('name'):
            self.assertEqual(len(code), 14)
            self.assertTrue(re.fullmatch(r'[0-9A-Za-z]{5}[0-9a-z]{7}-[cnhy]', code), code)
        self.assertIn('sent', rx.mapped('state'))

    def test_08_doctor_desk(self):
        doctor = demo_user(self.env, 'bacsi.demo')
        Visit = self.Visit.with_user(doctor)
        desk = Visit.get_doctor_desk()
        self.assertEqual(desk['practitioner']['name'], doctor.name)
        visit = Visit.search([('doctor_id.user_id', '=', doctor.id), ('state', '=', 'done')], limit=1)
        data = visit.get_visit_workspace()
        self.assertTrue(data['procedures'])
        self.assertIn('emr', data)
        assistant = demo_user(self.env, 'phuta.demo')
        self.assertTrue(self.Visit.with_user(assistant).get_frontdesk_board()['visits'])

    def test_10_ai_demo(self):
        """Trợ lý AI: giả lập, ~90 % bệnh nhân đồng ý, nhật ký / bản tin / cảnh báo sinh bằng hàm AI thật."""
        if 'dmag.ai.log' not in self.env:
            self.skipTest('Chưa cài dmag_ai_core')
        self.assertEqual(self.company.dmag_ai_mode, 'simulate')
        names = {spec[1] for spec in D.PATIENTS}
        demo = self.env['res.partner'].search([('is_patient', '=', True)]).filtered(lambda p: p.name in names)
        ratio = len(demo.filtered('dmag_ai_consent')) / len(demo)
        self.assertGreaterEqual(ratio, 0.85)
        self.assertLess(ratio, 1.0)
        hai = demo.filtered(lambda p: p.name == 'Nghiêm Văn Hải')
        self.assertIn('Warfarin', hai.current_medication or '')
        self.assertTrue(demo.filtered('is_pregnant'))
        visits = self.Visit.search([('state', 'in', ('done', 'no_show'))])
        rate = len(visits.filtered(lambda v: v.state == 'no_show')) / len(visits)
        self.assertGreater(rate, 0.08, 'Lịch sử demo cần đủ lượt không đến cho AI-08')
        if 'dmag.ai.noshow.model' in self.env:
            self.assertTrue(self.env['dmag.ai.noshow.model'].search_count([]))
        Log = self.env['dmag.ai.log']
        self.assertGreaterEqual(Log.search_count([('feature_id.code', '=', 'AI-13')]), 5)
        self.assertTrue(Log.search_count([('feature_id.code', '=', 'AI-16')]))
        if 'dmag.ai.brief' in self.env:
            brief = self.env['dmag.ai.brief'].search([], limit=1)
            self.assertTrue(brief and brief.state == 'sent' and brief.trigger == 'cron')
            anomalies = self.env['dmag.ai.anomaly'].search([])
            kinds = set(anomalies.mapped('kind'))
            self.assertIn('discount_staff', kinds)
            self.assertIn('refund', kinds)
            self.assertIn('review', anomalies.mapped('state'))
            self.assertTrue(anomalies.filtered('ai_narrative'))
            hub = self.env['dmag.ai.hub'].get_hub()
            self.assertEqual(len(hub['features']), 20)
            self.assertGreater(hub['estimated'], 0)
            for model in ('dmag.ai.log', 'dmag.ai.brief', 'dmag.ai.anomaly'):
                self.assertTrue(self.env['ir.model.data'].search_count([
                    ('module', '=', 'dmag_dental_demo'), ('model', '=', model)]),
                    'Dữ liệu AI demo phải gắn xmlid để gỡ module là xóa sạch (%s)' % model)

    def test_11_rotation_and_sunday(self):
        """Mở cửa 7 ngày; Chủ nhật đông nhất; lịch sử tôn trọng ngày nghỉ luân phiên của từng bác sĩ; lịch luân phiên
        có ô thiếu người (nghỉ phép đã duyệt) và yêu cầu chờ duyệt."""
        from datetime import timedelta
        from collections import Counter
        from odoo import fields
        schedule = self.env['dmag.clinic.schedule'].get_info(self.company)
        self.assertEqual(sorted(schedule.open_weekdays()), list(range(7)))
        roster = schedule.roster
        self.assertTrue(roster)
        members = self.env['dmag.staff.rotation'].search([('company_id', '=', self.company.id)])
        self.assertGreaterEqual(len(members), 7)
        self.assertFalse(members.filtered(lambda m: 6 in m.off_weekday_ids.mapped('code')), 'Không ai nghỉ Chủ nhật')
        today = fields.Date.context_today(self.Visit)
        shortages = [d for d in (today + timedelta(days=i) for i in range(1, 29)) if roster.shortages(d)]
        self.assertGreaterEqual(len(shortages), 1, 'Có một ngày thiếu bác sĩ (nghỉ phép đã duyệt) để demo cảnh báo')
        self.assertLessEqual(len(shortages), 3)
        self.assertTrue(self.env['dmag.staff.leave'].search_count([('state', '=', 'draft')]))
        # lịch sử: bác sĩ không có ca vào ngày nghỉ luân phiên / nghỉ phép
        done = self.Visit.search([('state', '=', 'done'), ('company_id', '=', self.company.id),
                                  ('scheduled_start', '<', fields.Datetime.now() - timedelta(days=1))])
        tz = 'Asia/Ho_Chi_Minh'
        bad = [v for v in done if v.doctor_id and v.doctor_id.off_reason(
            fields.Datetime.context_timestamp(v.with_context(tz=tz), v.scheduled_start).date(), schedule)]
        self.assertFalse(bad, 'Lượt khám vào ngày bác sĩ nghỉ: %s' % [v.name for v in bad[:5]])
        per_day = Counter(fields.Datetime.context_timestamp(v.with_context(tz=tz), v.scheduled_start).date()
                          for v in self.Visit.search([('company_id', '=', self.company.id),
                                                      ('scheduled_start', '<', fields.Datetime.now() - timedelta(days=1)),
                                                      ('state', 'in', ('done', 'no_show', 'cancel'))]))
        sundays = [n for d, n in per_day.items() if d.weekday() == 6]
        weekdays = [n for d, n in per_day.items() if d.weekday() != 6]
        self.assertTrue(sundays and weekdays)
        self.assertGreater(sum(sundays) / len(sundays), 1.3 * sum(weekdays) / len(weekdays), 'Chủ nhật đông nhất')

    def test_12_grounded_assistant_demo(self):
        """Trợ lý Zalo: chế độ chỉ trả lời từ dữ liệu đã nạp, kho tri thức đã nạp, đề xuất kịch bản của lễ tân,
        câu hỏi ngoài dữ liệu (đã trả lời / nạp kho / quá hạn báo Quản lý)."""
        if 'dmag.ai.knowledge' not in self.env:
            self.skipTest('Chưa cài dmag_ai_customer')
        self.assertEqual(self.company.dmag_ai_zalo_reply_mode, 'grounded')
        KB = self.env['dmag.ai.knowledge']
        self.assertGreaterEqual(KB.search_count([('state', '=', 'approved'), ('source_type', '=', 'pricelist')]), 20)
        self.assertTrue(KB.search_count([('source_type', '=', 'document'), ('state', '=', 'approved')]))
        self.assertTrue(KB.search_count([('source_type', '=', 'inbox'), ('state', '=', 'approved')]))
        self.assertTrue(KB.search_count([('source_type', '=', 'inbox'), ('state', '=', 'draft')]))
        Script = self.env['dmag.ai.reply.script']
        self.assertGreaterEqual(Script.search_count([('origin', '=', 'sample'), ('state', '=', 'approved')]), 14)
        self.assertGreaterEqual(Script.search_count([('origin', '=', 'proposal'), ('state', '=', 'draft')]), 2)
        self.assertTrue(Script.search_count([('origin', '=', 'proposal'), ('state', '=', 'approved')]))
        Gap = self.env['dmag.ai.kb.gap']
        self.assertTrue(Gap.search_count([('state', '=', 'open'), ('escalated_at', '!=', False)]))
        self.assertTrue(Gap.search_count([('state', '=', 'learned')]))
        self.assertTrue(Gap.search_count([('state', '=', 'open'), ('assigned_user_id', '!=', False)]))
        grounded = self.env['dmag.ai.conversation.message'].search_count([('decision', '=', 'grounded')])
        self.assertGreaterEqual(grounded, 3)

    def test_09_regenerate(self):
        receptionist = demo_user(self.env, 'letan.demo')
        with self.assertRaises(AccessError):
            self.env['dmag.demo'].with_user(receptionist).action_regenerate()

        def counts():
            env = self.env
            return {
                'visits': env['dmag.dental.visit'].search_count([]),
                'patients': env['res.partner'].search_count([('is_patient', '=', True)]),
                'plans': env['dmag.treatment.plan'].search_count([]),
                'rx': env['dmag.prescription'].search_count([]),
                'users': env['res.users'].search_count([('login', 'in', list(GROUPS))]),
                'services': env['product.product'].search_count([('default_code', '=like', 'DM-%')]),
            }
        before = counts()
        manager = demo_user(self.env, 'quanly.demo')
        result = self.env['dmag.demo'].with_user(manager).action_regenerate()
        self.assertEqual(result['tag'], 'display_notification')
        self.env.invalidate_all()
        after = counts()
        self.assertEqual(before, after)
        self.assertEqual(self.env['ir.config_parameter'].sudo().get_param('dmag.demo_mode'), '1')
        # một nhân viên chỉ một tài khoản, không bản ghi demo nào bị nhân đôi
        for login in GROUPS:
            self.assertEqual(self.env['res.users'].search_count([('login', '=', login)]), 1)
        status = self.env['dmag.demo'].with_user(receptionist).get_demo_status()
        self.assertTrue(status['active'])
        self.assertFalse(status['can_manage'])


@tagged('post_install', '-at_install')
class TestDemoLogin(HttpCase):

    def _call(self, model, method, args=None, kwargs=None):
        payload = {'jsonrpc': '2.0', 'method': 'call', 'id': 1,
                   'params': {'model': model, 'method': method, 'args': args or [], 'kwargs': kwargs or {}}}
        res = self.url_open('/web/dataset/call_kw/%s/%s' % (model, method), data=json.dumps(payload),
                            headers={'Content-Type': 'application/json'})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertNotIn('error', body, body.get('error'))
        return body['result']

    def test_receptionist_frontdesk_rpc(self):
        self.authenticate('letan.demo', D.PASSWORD)
        board = self._call('dmag.dental.visit', 'get_frontdesk_board')
        self.assertTrue(board['visits'])
        status = self._call('dmag.demo', 'get_demo_status')
        self.assertTrue(status['active'])

    def test_doctor_desk_rpc(self):
        self.authenticate('bacsi2.demo', D.PASSWORD)
        desk = self._call('dmag.dental.visit', 'get_doctor_desk')
        self.assertTrue(desk['practitioner'])
        self.assertTrue(desk['all_visits'])

    def test_director_goal_dashboard_rpc(self):
        """Giám đốc demo mở Bảng điều hành mục tiêu: có mục tiêu đã chốt, Objective, mục tiêu theo bác sĩ."""
        Target = self.env['dmag.business.target']
        self.assertTrue(Target.search_count([('state', '=', 'confirmed'), ('practitioner_id', '!=', False)]))
        self.assertTrue(Target.search_count([('state', '=', 'draft')]))
        self.assertTrue(self.env['ir.model.data'].search_count([
            ('module', '=', 'dmag_dental_demo'), ('model', '=', 'dmag.business.target')]),
            'Mục tiêu demo phải gắn xmlid để gỡ module là xóa sạch')
        self.authenticate('giamdoc.demo', D.PASSWORD)
        data = self._call('dmag.goal.dashboard', 'get_goal_dashboard', ['month'])
        self.assertTrue(data['can_edit_targets'])
        revenue = data['north_star'][0]
        self.assertEqual(revenue['target_source'], 'target')
        self.assertGreater(revenue['actual'], 0)
        self.assertEqual(len(data['okr']['target_objectives']), 3)
        self.assertTrue(any(d['revenue']['target'] for d in data['people']['doctors']))
        quarter = self._call('dmag.goal.dashboard', 'get_goal_dashboard', ['quarter'])
        self.assertEqual(quarter['north_star'][0]['target_source'], 'target')
