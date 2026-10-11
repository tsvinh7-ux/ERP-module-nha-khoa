from datetime import date, datetime

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, tagged

from odoo.addons.dmag_dental_goals.models.dmag_goal_dashboard import GoalBoard
from odoo.addons.dmag_dental_goals.models.dmag_goal_metrics import period_bounds, working_days

# Kỳ cố định trong quá khứ – không lẫn với dữ liệu demo (sinh quanh ngày hôm nay)
D_FROM, D_TO = date(2025, 3, 1), date(2025, 3, 31)


@tagged('post_install', '-at_install')
class TestGoalEngine(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env(context=dict(cls.env.context, tz='Asia/Ho_Chi_Minh', tracking_disable=True))
        cls.env = env
        env.user.tz = 'Asia/Ho_Chi_Minh'
        cls.company = env.company
        cls.engine = env['dmag.goal.engine']
        cls.chair = env['dmag.dental.chair'].create({'name': 'Ghế mục tiêu'})
        cls.chair2 = env['dmag.dental.chair'].create({'name': 'Ghế mục tiêu 2'})
        level3 = env.ref('dmag_dental_base.level_3')
        level2 = env.ref('dmag_dental_base.level_2', raise_if_not_found=False) or level3
        scopes = env['dmag.practice.scope'].search([])
        cls.doc_a = env['dmag.dental.practitioner'].create({
            'name': 'BS Mục tiêu A', 'role': 'doctor', 'license_number': 'GOAL-A',
            'scope_ids': [(6, 0, scopes.ids)], 'clinical_level_id': level3.id})
        cls.doc_b = env['dmag.dental.practitioner'].create({
            'name': 'BS Mục tiêu B', 'role': 'doctor', 'license_number': 'GOAL-B',
            'scope_ids': [(6, 0, scopes.ids)], 'clinical_level_id': level2.id})
        Product = env['product.product']
        cls.svc_exam = Product.create({'name': 'Khám (mục tiêu)', 'is_dental_service': True, 'dental_duration': 30,
                                       'dental_requires_tooth': False, 'list_price': 200000,
                                       'dental_category': 'exam'})
        cls.svc_implant = Product.create({'name': 'Implant (mục tiêu)', 'is_dental_service': True,
                                          'dental_duration': 60, 'dental_requires_tooth': False,
                                          'list_price': 15000000, 'dental_category': 'implant'})
        cls.svc_ortho = Product.create({'name': 'Niềng (mục tiêu)', 'is_dental_service': True, 'dental_duration': 30,
                                        'dental_requires_tooth': False, 'list_price': 30000000,
                                        'dental_category': 'orthodontic'})
        Partner = env['res.partner']
        cls.p1 = Partner.create({'name': 'BN mục tiêu 1', 'is_patient': True})
        cls.p2 = Partner.create({'name': 'BN mục tiêu 2', 'is_patient': True})
        cls.p3 = Partner.create({'name': 'BN mục tiêu 3', 'is_patient': True})

        # 3 lượt hoàn tất (2 BS A, 1 BS B) + 1 không đến + 1 hủy, giờ địa phương 09:00 (= 02:00 UTC)
        cls.v1 = cls._done_visit(datetime(2025, 3, 3, 2, 0), cls.p1, cls.doc_a, cls.chair, [cls.svc_exam, cls.svc_implant])
        cls.v2 = cls._done_visit(datetime(2025, 3, 4, 2, 0), cls.p2, cls.doc_b, cls.chair, [cls.svc_exam])
        cls.v3 = cls._done_visit(datetime(2025, 3, 10, 2, 0), cls.p1, cls.doc_a, cls.chair2, [cls.svc_ortho])
        cls.v4 = env['dmag.dental.visit'].create({'patient_id': cls.p3.id, 'doctor_id': cls.doc_b.id,
                                                  'chair_id': cls.chair.id,
                                                  'scheduled_start': datetime(2025, 3, 11, 2, 0)})
        cls.v4.action_no_show()
        cls.v5 = env['dmag.dental.visit'].create({'patient_id': cls.p3.id, 'doctor_id': cls.doc_b.id,
                                                  'chair_id': cls.chair.id,
                                                  'scheduled_start': datetime(2025, 3, 12, 2, 0)})
        cls.v5.action_cancel()
        # Kế hoạch: 2 đã tư vấn (1 đồng ý), 1 nháp (không tính)
        Plan = env['dmag.treatment.plan'].with_context(dmag_workflow=True)
        cls.plan_ok = Plan.create({'patient_id': cls.p1.id, 'doctor_id': cls.doc_a.id, 'date': date(2025, 3, 3)})
        cls.plan_ok.write({'state': 'accepted'})
        cls.plan_wait = Plan.create({'patient_id': cls.p2.id, 'doctor_id': cls.doc_b.id, 'date': date(2025, 3, 4)})
        cls.plan_wait.write({'state': 'presented'})
        Plan.create({'patient_id': cls.p3.id, 'doctor_id': cls.doc_b.id, 'date': date(2025, 3, 5)})

    @classmethod
    def _done_visit(cls, start, patient, doctor, chair, services):
        visit = cls.env['dmag.dental.visit'].create({'patient_id': patient.id, 'doctor_id': doctor.id,
                                                     'chair_id': chair.id, 'scheduled_start': start})
        visit.flush_recordset()  # "khách mới" tính ngay lúc đặt lịch như khi chạy thật
        visit.action_check_in()
        visit.action_start()
        for svc in services:
            cls.env['dmag.dental.procedure'].add_from_workspace(visit.id, svc.id)
        visit.procedure_ids.with_context(dmag_workflow=True).write({'doctor_id': doctor.id})
        visit.action_done()
        visit.procedure_ids.filtered(lambda p: p.state != 'done').with_context(dmag_workflow=True).write(
            {'state': 'done'})
        return visit

    def scope(self, doctor=None):
        return self.engine._scope(D_FROM, D_TO, self.company, doctor, today=date(2025, 4, 5))

    def metric(self, key, doctor=None):
        return self.engine.compute_metric(key, self.scope(doctor))

    # ------------------------------------------------------------------ engine
    def test_period_helpers(self):
        self.assertEqual(period_bounds('quarter', date(2026, 11, 20)), (date(2026, 10, 1), date(2026, 12, 31)))
        self.assertEqual(period_bounds('year', date(2026, 5, 2)), (date(2026, 1, 1), date(2026, 12, 31)))
        # Tháng 3/2025: 31 ngày, 5 Chủ nhật → 26 ngày làm việc
        self.assertEqual(working_days(D_FROM, D_TO), 26)
        self.assertEqual(working_days(D_FROM, date(2025, 3, 15)), 13)

    def test_sum_metrics(self):
        amounts = {v: sum(v.procedure_ids.mapped('amount')) for v in (self.v1, self.v2, self.v3)}
        self.assertTrue(all(amounts.values()))
        self.assertAlmostEqual(self.metric('revenue'), sum(amounts.values()))
        self.assertAlmostEqual(self.metric('revenue', self.doc_a), amounts[self.v1] + amounts[self.v3])
        self.assertAlmostEqual(self.metric('revenue', self.doc_b), amounts[self.v2])
        self.assertEqual(self.metric('new_patients'), 2.0)  # p1 lần đầu + p2; lượt 2 của p1 không tính
        self.assertEqual(self.metric('implant_cases'), 1.0)
        self.assertEqual(self.metric('ortho_new'), 1.0)
        self.assertEqual(self.metric('booked'), 4.0)  # 3 hoàn tất + 1 không đến; lịch hủy không tính
        s = self.scope()
        expected_gp = self.metric('revenue') - (s.material_cost() or 0) - (s.lab_cost() or 0) \
            - (s.commission_cost() or 0)
        self.assertAlmostEqual(self.metric('gross_profit'), expected_gp)
        # Vật tư đúng định nghĩa của dmag.material.usage.get_material_kpis (nếu module kho đã cài)
        if 'dmag.material.usage' in self.env and self.env.company == self.company:
            kpis = self.env['dmag.material.usage'].get_material_kpis(D_FROM, D_TO, self.company.id)
            self.assertAlmostEqual(s.material_cost(), kpis['material_cost'], places=0)

    def test_rate_metrics(self):
        self.assertAlmostEqual(self.metric('show_up_rate'), 75.0)  # 3 đến / (3 + 1 không đến)
        self.assertAlmostEqual(self.metric('plan_acceptance'), 50.0)  # 1 đồng ý / 2 đã tư vấn
        self.assertAlmostEqual(self.metric('plan_acceptance', self.doc_a), 100.0)
        self.assertAlmostEqual(self.metric('consult_rate'), 100.0)  # p1, p2 đã đến và đều được tư vấn
        self.assertAlmostEqual(self.metric('completion_rate'), 0.0)
        # 4 thủ thuật, 1 do BS B (bậc 2 nếu có danh mục bậc 2)
        expected = 25.0 if self.doc_b.clinical_level_id.level < 3 else 0.0
        self.assertAlmostEqual(self.metric('associate_share'), expected)
        self.assertIsNotNone(self.metric('avg_wait'))
        self.assertGreater(self.metric('chair_util_am'), 0.0)
        self.assertEqual(self.metric('chair_util_pm'), 0.0)

    # ------------------------------------------------------------------ targets & status
    def _target(self, metric, value, period_type='month', d_from=D_FROM, doctor=None, user=None, **kw):
        Target = self.env['dmag.business.target'].with_user(user) if user else self.env['dmag.business.target']
        target = Target.create(dict({'metric': metric, 'target_value': value, 'period_type': period_type,
                                     'date_from': d_from, 'company_id': self.company.id,
                                     'practitioner_id': doctor.id if doctor else False}, **kw))
        target.sudo().action_confirm()
        return target

    def test_pace_and_status(self):
        revenue = self.metric('revenue')
        self._target('revenue', revenue * 4)
        board = GoalBoard(self.env, 'month', D_FROM, D_TO, self.company, date(2025, 3, 15))
        self.assertEqual((board.wd_total, board.wd_elapsed, board.wd_left), (26, 13, 13))
        card = board.card('revenue', trend=False)
        self.assertEqual(card['target_source'], 'target')
        self.assertAlmostEqual(card['achieved_pct'], 25.0)
        self.assertAlmostEqual(card['forecast'], revenue * 2)  # nhịp 13/26 ngày → ×2
        self.assertAlmostEqual(card['forecast_pct'], 50.0)
        self.assertEqual(card['status'], 'at_risk')
        self.assertAlmostEqual(card['per_day'], revenue * 3 / 13)
        res = board.evaluate('revenue', 95.0, 180.0)  # dự báo 190 ≥ 180 → đúng tiến độ
        self.assertEqual(res['status'], 'on_track')
        self.assertEqual(board.evaluate('revenue', 85.0, 180.0)['status'], 'behind')  # 170/180 = 94%
        self.assertEqual(board.evaluate('avg_wait', 12.0, 15.0)['status'], 'on_track')
        self.assertEqual(board.evaluate('avg_wait', 25.0, 15.0)['status'], 'at_risk')
        self.assertEqual(board.evaluate('nps', 45.0, 50.0)['status'], 'behind')
        # Kỳ đã qua: Đạt / Không đạt
        past = GoalBoard(self.env, 'month', D_FROM, D_TO, self.company, date(2025, 5, 1))
        self.assertEqual(past.card('revenue', trend=False)['status'], 'missed')
        # Không có mục tiêu: chỉ số có chuẩn DMAG dùng chuẩn, chỉ số khác "Chưa đặt mục tiêu"
        plan = board.card('plan_acceptance', trend=False)
        self.assertEqual((plan['target'], plan['target_source']), (60.0, 'dmag'))
        self.assertEqual(board.card('implant_cases', trend=False)['status'], 'no_target')

    def test_doctor_target_and_derived_quarter(self):
        self._target('revenue', 1000000, doctor=self.doc_a)
        for month in (1, 2, 3):
            self._target('new_patients', 10, d_from=date(2025, month, 1))
        board = GoalBoard(self.env, 'quarter', date(2025, 1, 1), date(2025, 3, 31), self.company, date(2025, 3, 15))
        card = board.card('new_patients', trend=False)
        self.assertEqual((card['target'], card['target_source']), (30.0, 'derived'))
        month = GoalBoard(self.env, 'month', D_FROM, D_TO, self.company, date(2025, 3, 15))
        doc_card = month.card('revenue', self.doc_a, trend=False)
        self.assertEqual(doc_card['target'], 1000000)
        self.assertIsNone(month.card('revenue', self.doc_b, trend=False)['target'])

    def test_dashboard_payload(self):
        self._target('revenue', 50000000, objective='Tăng trưởng doanh thu')
        self._target('plan_acceptance', 70, objective='Tăng trưởng doanh thu')
        data = self.env['dmag.goal.dashboard'].get_goal_dashboard('month', '2025-03-20')
        self.assertEqual(data['period']['label'], 'Tháng 3/2025')
        self.assertEqual([c['metric'] for c in data['north_star']][:2], ['revenue', 'collected'])
        revenue = data['north_star'][0]
        self.assertEqual(revenue['target'], 50000000)
        self.assertEqual(len(revenue['spark']), 6)
        self.assertEqual(revenue['action']['res_model'], 'dmag.dental.procedure')
        self.assertEqual(data['okr']['target_objectives'][0]['name'], 'Tăng trưởng doanh thu')
        self.assertEqual(len(data['okr']['target_objectives'][0]['krs']), 2)
        self.assertEqual([s['count'] for s in data['funnel']['steps']][:2], [4, 3])
        self.assertTrue(any(d['id'] == self.doc_a.id for d in data['people']['doctors']))
        self.assertEqual(data['finance']['waterfall'][0]['value'], self.metric('revenue'))
        self.assertTrue(all(a['todo'] for a in data['alerts']))
        self.assertEqual(self.env.ref('dmag_clinic_workspace.action_dmag_owner_cockpit').tag, 'dmag_goal_dashboard')


@tagged('post_install', '-at_install')
class TestGoalAccess(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        def user(login, group):
            return cls.env['res.users'].with_context(no_reset_password=True).create({
                'name': login, 'login': login, 'company_id': cls.env.company.id,
                'company_ids': [(6, 0, cls.env.company.ids)],
                'groups_id': [(6, 0, [cls.env.ref('dmag_dental_base.%s' % group).id])]})
        cls.receptionist = user('goal_lt', 'group_dmag_receptionist')
        cls.doctor = user('goal_bs', 'group_dmag_doctor')
        cls.manager = user('goal_ql', 'group_dmag_manager')
        cls.director = user('goal_gd', 'group_dmag_director')

    def test_staff_denied(self):
        for staff in (self.receptionist, self.doctor):
            with self.assertRaises(AccessError):
                self.env['dmag.goal.dashboard'].with_user(staff).get_goal_dashboard('month')
            with self.assertRaises(AccessError):
                self.env['dmag.business.target'].with_user(staff).search([])
        data = self.env['dmag.goal.dashboard'].with_user(self.manager).get_goal_dashboard('quarter')
        self.assertIn('north_star', data)
        self.assertFalse(data['can_edit_targets'])

    def test_create_but_not_edit_after_confirm(self):
        Target = self.env['dmag.business.target']
        draft = Target.with_user(self.manager).create({'metric': 'revenue', 'target_value': 100000000,
                                                       'period_type': 'quarter', 'date_from': '2026-11-15'})
        self.assertEqual(str(draft.date_from), '2026-10-01')  # đưa về đầu quý
        self.assertEqual(str(draft.date_to), '2026-12-31')
        draft.write({'target_value': 120000000})  # đề xuất còn sửa được
        with self.assertRaises(AccessError):
            draft.action_confirm()  # quản lý không chốt
        draft.with_user(self.director).action_confirm()
        self.assertEqual(draft.state, 'confirmed')
        with self.assertRaises(AccessError):
            draft.with_user(self.manager).write({'target_value': 1})
        with self.assertRaises(AccessError):
            draft.with_user(self.manager).unlink()
        draft.with_user(self.director).write({'target_value': 150000000})
        self.assertEqual(draft.target_value, 150000000)
        with self.assertRaises(ValidationError):
            Target.with_user(self.director).create({'metric': 'revenue', 'target_value': 1,
                                                    'period_type': 'quarter', 'date_from': '2026-10-01'})
        with self.assertRaises(ValidationError):
            Target.with_user(self.director).create({'metric': 'plan_acceptance', 'target_value': 120})
