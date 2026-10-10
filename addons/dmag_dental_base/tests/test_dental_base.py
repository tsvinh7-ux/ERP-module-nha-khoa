from datetime import timedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestDentalBase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.level1 = cls.env.ref('dmag_dental_base.level_1')
        cls.level2 = cls.env.ref('dmag_dental_base.level_2')
        cls.scope_general = cls.env.ref('dmag_dental_base.scope_general')
        cls.scope_implant = cls.env.ref('dmag_dental_base.scope_implant')
        cls.doctor = cls.env['dmag.dental.practitioner'].create({
            'name': 'BS Test', 'role': 'doctor',
            'clinical_level_id': cls.level1.id,
            'scope_ids': [(6, 0, cls.scope_general.ids)],
            'license_number': 'TEST-1',
        })
        cls.filling = cls.env['product.product'].create({
            'name': 'Trám test', 'detailed_type': 'service', 'is_dental_service': True,
            'practice_scope_id': cls.scope_general.id, 'min_clinical_level_id': cls.level1.id,
        })
        cls.implant = cls.env['product.product'].create({
            'name': 'Implant test', 'detailed_type': 'service', 'is_dental_service': True,
            'practice_scope_id': cls.scope_implant.id, 'min_clinical_level_id': cls.level2.id,
        })

    def test_tooth_catalog(self):
        teeth = self.env['dmag.dental.tooth'].search([])
        self.assertEqual(len(teeth), 52)
        self.assertEqual(len(teeth.filtered(lambda t: t.dentition == 'primary')), 20)
        self.assertEqual(self.env.ref('dmag_dental_base.tooth_36').arch, 'lower')
        self.assertEqual(self.env.ref('dmag_dental_base.tooth_55').arch, 'upper')

    def test_patient_code_and_age(self):
        patient = self.env['res.partner'].create({
            'name': 'BN Test', 'is_patient': True,
            'birthdate': fields.Date.today() - timedelta(days=365 * 30 + 10),
        })
        self.assertTrue(patient.patient_code.startswith('BN'))
        self.assertEqual(patient.age, 30)
        other = self.env['res.partner'].create({'name': 'Liên hệ thường'})
        self.assertFalse(other.patient_code)
        other.is_patient = True
        self.assertTrue(other.patient_code)
        self.assertNotEqual(other.patient_code, patient.patient_code)

    def test_patient_search_by_phone(self):
        patient = self.env['res.partner'].create({'name': 'Tìm SĐT', 'is_patient': True, 'mobile': '0911222333'})
        found = self.env['res.partner'].with_context(dmag_patient_search=True).name_search('0911222')
        self.assertIn(patient.id, [r[0] for r in found])

    def test_scope_and_level_blockers(self):
        self.assertTrue(self.doctor.check_can_perform(self.filling))
        with self.assertRaises(ValidationError):
            self.doctor.check_can_perform(self.implant)
        reasons = self.doctor._get_service_blockers(self.implant)
        self.assertEqual(len(reasons), 2)

    def test_expired_license_blocks(self):
        self.doctor.license_expiry_date = fields.Date.today() - timedelta(days=1)
        self.assertEqual(self.doctor.license_state, 'expired')
        with self.assertRaises(ValidationError):
            self.doctor.check_can_perform(self.filling)

    def test_license_dates_constraint(self):
        with self.assertRaises(ValidationError):
            self.doctor.write({'license_issue_date': '2026-01-10', 'license_expiry_date': '2025-01-10'})
