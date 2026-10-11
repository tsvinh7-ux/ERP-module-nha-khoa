from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestWorkspace(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.email = 'admin@dmag.test'
        cls.ws = cls.env['dmag.workspace']
        cls.chair = cls.env['dmag.dental.chair'].create({'name': 'Ghế WS'})
        cls.doctor = cls.env['dmag.dental.practitioner'].create({
            'name': 'BS WS', 'role': 'doctor', 'user_id': cls.env.user.id, 'license_number': 'WS-1',
            'scope_ids': [(6, 0, cls.env.ref('dmag_dental_base.scope_general').ids)],
            'clinical_level_id': cls.env.ref('dmag_dental_base.level_3').id})
        cls.svc = cls.env['product.product'].create({
            'name': 'Khám WS', 'is_dental_service': True, 'dental_duration': 30, 'dental_requires_tooth': False,
            'list_price': 100000})

    def test_quick_patient_requires_consent_and_detects_duplicate(self):
        with self.assertRaises(UserError):
            self.ws.quick_create_patient({'name': 'A', 'phone': '0912000111'})
        res = self.ws.quick_create_patient({'name': 'Nguyễn A', 'phone': '0912 000 111', 'consent': True})
        self.assertTrue(res['code'])
        dup = self.ws.quick_create_patient({'name': 'Nguyễn A2', 'phone': '0912000111', 'consent': True})
        self.assertEqual(dup['duplicate']['id'], res['id'])
        self.assertTrue(self.ws.search_patients('0912000'))

    def test_slots_and_booking(self):
        patient = self.env['res.partner'].create({'name': 'BN slot', 'is_patient': True})
        day = (fields.Date.context_today(self.ws) + timedelta(days=1)).isoformat()
        slots = self.ws.get_free_slots(day, self.doctor.id, 30)
        self.assertTrue(slots)
        first = slots[0]
        res = self.ws.quick_book({'patient_id': patient.id, 'doctor_id': self.doctor.id, 'chair_id': self.chair.id,
                                  'service_ids': self.svc.ids, 'date': day, 'time': first['time'], 'confirm': True})
        visit = self.env['dmag.dental.visit'].browse(res['id'])
        self.assertEqual(visit.state, 'confirmed')
        after = self.ws.get_free_slots(day, self.doctor.id, 30)
        same = [s for s in after if s['time'] == first['time']]
        self.assertTrue(not same or self.chair.id not in same[0]['chairs'])

    def test_goal_dashboard_action_kept(self):
        """Hành động cũ (xml id ``action_dmag_owner_cockpit``) mở Bảng điều hành mục tiêu; không còn "Buồng lái"."""
        action = self.env.ref('dmag_clinic_workspace.action_dmag_owner_cockpit')
        self.assertEqual(action.tag, 'dmag_goal_dashboard')
        self.assertEqual(action.name, 'Bảng điều hành mục tiêu')
        self.assertFalse(hasattr(self.ws, 'get_owner_cockpit'))
        menus = self.env['ir.ui.menu'].sudo().search([('name', 'ilike', 'Buồng lái')])
        self.assertFalse(menus, 'Không còn dùng tên "Buồng lái" trên menu')

    def test_payment_panel(self):
        patient = self.env['res.partner'].create({'name': 'BN pay', 'is_patient': True})
        visit = self.env['dmag.dental.visit'].create({
            'patient_id': patient.id, 'doctor_id': self.doctor.id, 'chair_id': self.chair.id,
            'scheduled_start': fields.Datetime.now() + timedelta(hours=1)})
        visit.action_check_in()
        visit.action_start()
        self.env['dmag.dental.procedure'].add_from_workspace(visit.id, self.svc.id)
        panel = self.ws.get_payment_panel(visit.id)
        self.assertEqual(panel['amount_due'], 100000)
        visit.register_payment('cash')
        self.assertEqual(self.ws.get_payment_panel(visit.id)['payment_status'], 'paid')
        html = self.env['ir.actions.report']._render_qweb_html(
            'dmag_clinic_workspace.report_payment_receipt', visit.ids)[0]
        self.assertIn('PHIẾU THU', html.decode())
