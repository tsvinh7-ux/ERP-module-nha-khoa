from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase


class DentalCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        ref = env.ref
        env.user.email = 'admin@dmag.test'
        cls.level1 = ref('dmag_dental_base.level_1')
        cls.level3 = ref('dmag_dental_base.level_3')
        cls.scope_general = ref('dmag_dental_base.scope_general')
        cls.scope_prostho = ref('dmag_dental_base.scope_prostho')
        cls.doctor = env['dmag.dental.practitioner'].create({
            'name': 'BS Một', 'role': 'doctor', 'user_id': env.user.id,
            'clinical_level_id': cls.level3.id,
            'scope_ids': [(6, 0, (cls.scope_general | cls.scope_prostho).ids)],
            'license_number': 'T-001',
        })
        cls.doctor_user2 = env['res.users'].create({
            'name': 'BS Hai', 'login': 'bs_hai_test', 'email': 'bshai@dmag.test',
            'groups_id': [(6, 0, [ref('dmag_dental_base.group_dmag_doctor').id])],
        })
        cls.doctor2 = env['dmag.dental.practitioner'].create({
            'name': 'BS Hai', 'role': 'doctor', 'user_id': cls.doctor_user2.id,
            'clinical_level_id': cls.level1.id,
            'scope_ids': [(6, 0, cls.scope_general.ids)],
            'license_number': 'T-002',
        })
        cls.chair1 = env['dmag.dental.chair'].create({'name': 'Ghế T1'})
        cls.chair2 = env['dmag.dental.chair'].create({'name': 'Ghế T2'})
        Product = env['product.product'].with_context(default_taxes_id=False)
        cls.svc_filling = Product.create({
            'name': 'Trám T', 'is_dental_service': True, 'list_price': 400000,
            'dental_duration': 30, 'practice_scope_id': cls.scope_general.id,
            'dental_result_condition_id': ref('dmag_dental_base.condition_filling').id,
        })
        cls.svc_heavy = Product.create({
            'name': 'Ca nặng T', 'is_dental_service': True, 'list_price': 2000000,
            'dental_duration': 60, 'dental_complexity': 'heavy', 'dental_requires_tooth': False,
        })
        cls.svc_crown = Product.create({
            'name': 'Sứ T', 'is_dental_service': True, 'list_price': 5000000,
            'practice_scope_id': cls.scope_prostho.id, 'requires_second_opinion': True,
            'dental_result_condition_id': ref('dmag_dental_base.condition_crown').id,
        })
        cls.patient = env['res.partner'].create({'name': 'BN Test', 'is_patient': True, 'mobile': '0900000001'})
        cls.tooth_36 = ref('dmag_dental_base.tooth_36')
        cls.surface_o = ref('dmag_dental_base.surface_o')
        cls.start = fields.Datetime.now().replace(microsecond=0) + timedelta(days=1)

    def _visit(self, **kw):
        vals = {
            'patient_id': self.patient.id,
            'doctor_id': self.doctor.id,
            'chair_id': self.chair1.id,
            'scheduled_start': self.start,
            'service_ids': [(6, 0, self.svc_filling.ids)],
        }
        vals.update(kw)
        return self.env['dmag.dental.visit'].create(vals)
