from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from odoo.addons.dmag_dental_clinic.tests.common import DentalCommon


@tagged('post_install', '-at_install')
class TestLoyalty(DentalCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ref = cls.env.ref
        cls.company = cls.env.company
        cls.company.write({
            'dmag_loyalty_amount_per_point': 10000,
            'dmag_loyalty_referrer_points': 200,
            'dmag_loyalty_referee_points': 100,
            'dmag_loyalty_point_value': 1000,
            'dmag_loyalty_min_redeem': 50,
            'dmag_loyalty_approval_points': 1000,
            'dmag_loyalty_family_pool': True,
            'dmag_max_discount': 10,
        })
        Users = cls.env['res.users'].with_context(no_reset_password=True)
        cls.recep = Users.create({
            'name': 'Lễ tân L', 'login': 'recep_loyalty', 'email': 'recep_l@dmag.test',
            'groups_id': [(6, 0, [ref('dmag_dental_base.group_dmag_receptionist').id])],
        })
        cls.director = Users.create({
            'name': 'Giám đốc L', 'login': 'director_loyalty', 'email': 'gd_l@dmag.test',
            'groups_id': [(6, 0, [ref('dmag_dental_base.group_dmag_director').id])],
        })
        cls.Ledger = cls.env['dmag.loyalty.ledger']
        cls._n = 0

    def _paid_visit(self, patient, pay=True, amount=False):
        """Lượt khám có 1 thủ thuật trám (400.000 ₫), hoàn tất, thu tiền."""
        type(self)._n += 1
        visit = self._visit(patient_id=patient.id, scheduled_start=self.start + timedelta(hours=2 * self._n))
        visit.action_check_in()
        visit.action_start()
        self.env['dmag.dental.procedure'].add_from_workspace(visit.id, self.svc_filling.id, teeth=['36'],
                                                              surfaces=['O'])
        visit.action_done()
        if pay:
            visit.with_user(self.recep).register_payment('cash', amount=amount)
        return visit

    def _points(self, partner, reason=None):
        domain = [('partner_id', '=', partner.id)]
        if reason:
            domain.append(('reason', '=', reason))
        return sum(self.Ledger.search(domain).mapped('points'))

    # ------------------------------------------------------------------ earning
    def test_points_on_payment_idempotent(self):
        visit = self._paid_visit(self.patient)
        self.assertEqual(self._points(self.patient, 'payment'), 40)
        # Sự kiện 'paid' bắn lại (ví dụ module khác gọi lại) không cộng trùng
        visit._dmag_journey_event('paid')
        visit._dmag_journey_event('paid')
        self.assertEqual(self._points(self.patient, 'payment'), 40)
        self.assertEqual(self.patient.dmag_points_balance, 40)

        # Thu 2 lần: mỗi khoản thu được tích điểm đúng một lần
        visit2 = self._paid_visit(self.patient, amount=150000)
        self.assertEqual(self._points(self.patient, 'payment'), 55)
        visit2.with_user(self.recep).register_payment('transfer')
        self.assertEqual(self._points(self.patient, 'payment'), 80)
        self.assertEqual(self.Ledger.search_count([('partner_id', '=', self.patient.id),
                                                   ('reason', '=', 'payment')]), 3)
        self.assertEqual(self.patient.dmag_paid_12m, 800000)

    def test_referral_rewarded_once(self):
        referee = self.env['res.partner'].create({'name': 'BN Được GT', 'is_patient': True,
                                                  'referrer_id': self.patient.id})
        # Thanh toán một phần: chưa thưởng giới thiệu
        visit = self._paid_visit(referee, amount=100000)
        self.assertEqual(self._points(self.patient, 'referral'), 0)
        visit.with_user(self.recep).register_payment('cash')
        self.assertEqual(self._points(self.patient, 'referral'), 200)
        self.assertEqual(self._points(referee, 'referral'), 100)
        # Lượt khám sau: không thưởng lại
        self._paid_visit(referee)
        visit._dmag_journey_event('paid')
        self.assertEqual(self._points(self.patient, 'referral'), 200)
        self.assertEqual(self._points(referee, 'referral'), 100)

    def test_tier_recompute_family_pool(self):
        silver = self.env.ref('dmag_dental_loyalty.tier_silver')
        member_tier = self.env.ref('dmag_dental_loyalty.tier_member')
        silver.write({'min_paid_12m': 700000, 'min_engagement_points': 0})
        family = self.env['dmag.patient.family'].create({'name': 'Gia đình Test', 'head_id': self.patient.id})
        child = self.env['res.partner'].create({'name': 'Con Test', 'is_patient': True})
        (self.patient | child).write({'dental_family_id': family.id})

        self._paid_visit(self.patient)
        self.assertEqual(self.patient.dmag_tier_id, member_tier)
        self._paid_visit(child)
        # Gộp gia đình: 800.000 ≥ 700.000 → cả nhà lên Bạc
        self.assertEqual(self.patient.dmag_tier_id, silver)
        self.assertEqual(child.dmag_tier_id, silver)
        self.assertEqual(self.patient.dmag_points_balance, 80)
        self.assertEqual(child.dmag_own_points, 40)
        summary = self.env['res.partner'].get_loyalty_summary(child.id)
        self.assertTrue(summary['pooled'])
        self.assertEqual(summary['points'], 80)
        self.assertEqual(len(summary['members']), 2)
        self.assertEqual(summary['tier']['id'], silver.id)
        self.assertTrue(summary['next_tier'])

        # Tắt ví gia đình → xét riêng từng người (cron hằng đêm)
        self.company.dmag_loyalty_family_pool = False
        self.env['res.partner']._cron_dmag_loyalty_recompute()
        self.assertEqual(self.patient.dmag_tier_id, member_tier)
        self.assertEqual(child.dmag_points_balance, 40)

    def test_engagement_tier_and_recall(self):
        gold = self.env.ref('dmag_dental_loyalty.tier_gold')
        gold.write({'min_paid_12m': 0, 'min_engagement_points': 100})
        self.svc_filling.recall_months = 6
        first = self._paid_visit(self.patient)
        # Lượt tái khám đúng hẹn (6 tháng sau)
        first.sudo().with_context(dmag_workflow=True).write({'done_time': fields.Datetime.now() - timedelta(days=183)})
        first.with_context(dmag_workflow=True).write({'scheduled_start': fields.Datetime.now() - timedelta(days=183)})
        recall = self._visit(scheduled_start=fields.Datetime.now() + timedelta(minutes=5), chair_id=self.chair2.id)
        recall.action_check_in()
        recall.action_start()
        recall.action_done()
        self.assertEqual(self._points(self.patient, 'recall'), 50)
        recall._dmag_journey_event('done')
        self.assertEqual(self._points(self.patient, 'recall'), 50)
        self.patient.dmag_loyalty_award_survey(source=recall)
        self.patient.dmag_loyalty_award_survey(source=recall)
        self.assertEqual(self._points(self.patient, 'survey'), 20)
        self.Ledger.create({'partner_id': self.patient.id, 'points': 30, 'reason': 'adjustment', 'note': 'test'})
        self.patient._dmag_loyalty_recompute()
        self.assertEqual(self.patient.dmag_engagement_12m, 70)
        self.assertNotEqual(self.patient.dmag_tier_id, gold)
        self.patient.with_user(self.recep).dmag_loyalty_award_survey(key='nps:extra')
        self.Ledger.sudo()._dmag_earn(self.patient, 'referral', 30, key='manual-ref')
        self.patient._dmag_loyalty_recompute()
        self.assertEqual(self.patient.dmag_tier_id, gold)

    # ------------------------------------------------------------------ ledger security
    def test_ledger_read_only(self):
        entry = self.Ledger.create({'partner_id': self.patient.id, 'points': 10, 'reason': 'adjustment',
                                    'note': 'Giám đốc'})
        with self.assertRaises(UserError):
            entry.write({'points': 1000})
        with self.assertRaises(UserError):
            entry.unlink()
        with self.assertRaises(AccessError):
            self.Ledger.with_user(self.recep).create({'partner_id': self.patient.id, 'points': 10,
                                                      'reason': 'adjustment'})
        with self.assertRaises(AccessError):
            self.Ledger.with_user(self.director).create({'partner_id': self.patient.id, 'points': 10,
                                                         'reason': 'payment'})
        self.Ledger.with_user(self.director).create({'partner_id': self.patient.id, 'points': 10,
                                                     'reason': 'adjustment', 'note': 'OK'})
        self.assertEqual(self.patient.dmag_points_balance, 20)

    # ------------------------------------------------------------------ vouchers
    def test_voucher_min_validity(self):
        Voucher = self.env['dmag.loyalty.voucher']
        today = fields.Date.context_today(Voucher)
        with self.assertRaises(ValidationError):
            Voucher.create({'partner_id': self.patient.id, 'value': 50000, 'valid_from': today,
                            'valid_to': today + timedelta(days=3)})
        voucher = Voucher.create({'partner_id': self.patient.id, 'value': 50000})
        self.assertGreaterEqual((voucher.valid_to - voucher.valid_from).days, 7)
        self.assertEqual(voucher.state, 'to_approve')
        with self.assertRaises(AccessError):
            Voucher.with_user(self.recep).create({'partner_id': self.patient.id, 'value': 50000})

    def test_voucher_redeem_single_use(self):
        self.Ledger.create({'partner_id': self.patient.id, 'points': 500, 'reason': 'adjustment', 'note': 'Tặng'})
        Voucher = self.env['dmag.loyalty.voucher'].with_user(self.recep)
        with self.assertRaises(UserError):
            Voucher.create_from_points(self.patient.id, 600)
        voucher = Voucher.create_from_points(self.patient.id, 100)
        self.assertEqual(voucher.state, 'active')
        self.assertEqual(voucher.value, 100000)
        self.assertEqual(self.patient.dmag_points_balance, 400)
        with self.assertRaises(AccessError):
            voucher.write({'value': 999999})

        visit = self._paid_visit(self.patient, pay=False)
        res = visit.with_user(self.recep).dmag_apply_voucher(voucher.name)
        self.assertEqual(res['amount'], 100000)
        visit.invalidate_recordset()
        self.assertEqual(visit.amount_due, 300000)
        self.assertEqual(voucher.state, 'used')
        visit2 = self._paid_visit(self.patient, pay=False)
        with self.assertRaises(UserError):
            visit2.with_user(self.recep).dmag_apply_voucher(voucher.name)
        visit.with_user(self.recep).register_payment('cash')
        invoice = visit.sudo().invoice_ids
        self.assertEqual(invoice.amount_total, 300000)
        self.assertEqual(self._points(self.patient, 'payment'), 30)

    def test_voucher_approval_and_refund(self):
        self.Ledger.create({'partner_id': self.patient.id, 'points': 2000, 'reason': 'adjustment', 'note': 'Tặng'})
        voucher = self.env['dmag.loyalty.voucher'].with_user(self.recep).create_from_points(self.patient.id, 1500)
        self.assertEqual(voucher.state, 'to_approve')
        self.assertEqual(self.patient.dmag_points_balance, 500)
        with self.assertRaises(AccessError):
            voucher.with_user(self.recep).action_approve()
        voucher.action_reject()
        self.assertEqual(voucher.state, 'cancel')
        self.assertEqual(self.patient.dmag_points_balance, 2000)
        # Không ai dùng được voucher của người khác (ngoài gia đình)
        other = self.env['res.partner'].create({'name': 'BN Khác', 'is_patient': True})
        v2 = self.env['dmag.loyalty.voucher'].create_from_points(self.patient.id, 1500)
        self.assertEqual(v2.state, 'active', 'Quản lý đổi điểm không cần duyệt')
        visit = self._paid_visit(other, pay=False)
        with self.assertRaises(UserError):
            visit.dmag_apply_voucher(v2.name)

    # ------------------------------------------------------------------ care plan
    def test_care_plan_entitlement(self):
        plan = self.env['dmag.care.plan'].create({
            'name': 'Gói năm T', 'price': 1000000, 'duration_months': 12,
            'line_ids': [(0, 0, {'product_id': self.svc_filling.id, 'quantity': 1})],
        })
        sub = self.env['dmag.care.subscription'].with_user(self.recep).create({
            'partner_id': self.patient.id, 'plan_id': plan.id})
        sub.action_activate()
        self.assertEqual(sub.state, 'active')
        self.assertEqual(sub.amount_due, 1000000)
        with self.assertRaises(AccessError):
            sub.with_user(self.recep).write({'start_date': fields.Date.today() - timedelta(days=30)})
        sub.with_user(self.recep).register_payment('transfer')
        self.assertEqual(self._points(self.patient, 'payment'), 100)
        sub.invalidate_recordset()
        self.assertEqual(sub.amount_due, 0)

        visit = self._paid_visit(self.patient, pay=False)
        proc = visit.procedure_ids
        res = visit.with_user(self.recep).dmag_use_care_entitlement(proc.id)
        self.assertEqual(res['remaining'], 0)
        self.assertEqual(proc.price_unit, 0)
        visit.invalidate_recordset()
        self.assertEqual(visit.amount_due, 0)
        with self.assertRaises(UserError):
            visit.dmag_use_care_entitlement(proc.id)
        visit2 = self._paid_visit(self.patient, pay=False)
        with self.assertRaises(UserError):
            visit2.dmag_use_care_entitlement(visit2.procedure_ids.id)
        summary = self.env['res.partner'].get_loyalty_summary(self.patient.id)
        self.assertEqual(summary['subscriptions'][0]['entitlements'][0]['remaining'], 0)
