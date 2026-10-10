from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from odoo.addons.dmag_dental_clinic.tests.common import DentalCommon


@tagged('post_install', '-at_install')
class TestWarranty(DentalCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.svc_crown_w = cls.env['product.product'].create({
            'name': 'Sứ BH T', 'is_dental_service': True, 'list_price': 5000000,
            'warranty_months': 60, 'warranty_conditions': 'Tái khám 12 tháng/lần.',
            'dental_result_condition_id': cls.env.ref('dmag_dental_base.condition_crown').id,
        })
        cls.receptionist = cls.env['res.users'].create({
            'name': 'Lễ tân BH', 'login': 'lt_bh_test', 'email': 'ltbh@dmag.test',
            'groups_id': [(6, 0, [cls.env.ref('dmag_dental_base.group_dmag_receptionist').id])],
        })
        cls.today = fields.Date.context_today(cls.env.user)

    def _done_procedure(self, product):
        visit = self._visit(scheduled_start=fields.Datetime.now())
        visit.action_check_in()
        visit.action_start()
        res = self.env['dmag.dental.procedure'].add_from_workspace(visit.id, product.id, teeth=['36'])
        return self.env['dmag.dental.procedure'].browse(res['id'])

    def test_auto_card_on_done(self):
        proc = self._done_procedure(self.svc_crown_w)
        card = proc.warranty_card_ids
        self.assertEqual(len(card), 1)
        self.assertTrue(card.name.startswith('BH'))
        self.assertEqual(card.patient_id, self.patient)
        self.assertEqual(card.tooth_ids, self.tooth_36)
        self.assertEqual(card.start_date, self.today)
        self.assertEqual(card.end_date, self.today + relativedelta(months=60))
        self.assertEqual(card.conditions, 'Tái khám 12 tháng/lần.')
        self.assertEqual(card.state, 'active')
        # Dịch vụ không bảo hành → không có thẻ
        res = self.env['dmag.dental.procedure'].add_from_workspace(proc.visit_id.id, self.svc_filling.id, teeth=['37'])
        self.assertFalse(self.env['dmag.dental.procedure'].browse(res['id']).warranty_card_ids)
        # In thẻ (HTML)
        html, _fmt = self.env['ir.actions.report']._render_qweb_html(
            'dmag_dental_warranty.action_report_warranty_card', card.ids)
        self.assertIn(card.name.encode(), html)

    def test_card_locked_and_void(self):
        card = self._done_procedure(self.svc_crown_w).warranty_card_ids
        card_rec = card.with_user(self.receptionist)
        with self.assertRaises(AccessError):
            card_rec.write({'end_date': self.today + relativedelta(years=20)})
        with self.assertRaises(AccessError):
            card_rec.action_void()
        admin = self.env.ref('base.user_admin')
        card_admin = card.with_user(admin)
        with self.assertRaises(UserError):
            card_admin.action_void()
        card_admin.write({'void_reason': 'Lập nhầm'})
        card_admin.action_void()
        self.assertEqual(card.state, 'void')

    def test_claim_and_expiry(self):
        card = self._done_procedure(self.svc_crown_w).warranty_card_ids
        claim = self.env['dmag.warranty.claim'].with_user(self.receptionist).create({
            'card_id': card.id, 'issue': 'Mẻ sứ rìa cắn'})
        self.assertEqual(claim.decision, 'pending')
        with self.assertRaises(AccessError):
            claim.write({'decision': 'covered'})
        with self.assertRaises(AccessError):
            claim.action_cover()  # lễ tân không kết luận
        claim.with_user(self.doctor_user2).action_cover()
        self.assertEqual(claim.decision, 'covered')
        self.assertEqual(card.state, 'claimed')
        action = claim.with_user(self.receptionist).action_create_visit()
        self.assertTrue(claim.visit_id)
        self.assertEqual(action['res_id'], claim.visit_id.id)
        with self.assertRaises(AccessError):
            claim.with_user(self.receptionist).write({'issue': 'Sửa'})

        # Sắp hết hạn / hết hạn
        Card = self.env['dmag.warranty.card']
        soon = Card.create({'patient_id': self.patient.id, 'product_id': self.svc_crown_w.id, 'months': 12,
                            'start_date': self.today - relativedelta(months=12) + timedelta(days=10)})
        old = Card.create({'patient_id': self.patient.id, 'product_id': self.svc_crown_w.id, 'months': 12,
                           'start_date': self.today - relativedelta(months=13)})
        expiring = Card._dmag_warranty_expiring(30)
        self.assertIn(soon, expiring)
        self.assertNotIn(card, expiring)
        self.assertNotIn(old, expiring)
        Card._cron_warranty_expiry(30)
        self.assertEqual(old.state, 'expired')
        self.assertEqual(len(soon.activity_ids), 1)
        Card._cron_warranty_expiry(30)
        self.assertEqual(len(soon.activity_ids), 1)
