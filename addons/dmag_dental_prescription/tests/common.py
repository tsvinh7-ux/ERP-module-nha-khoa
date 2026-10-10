from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.tests import TransactionCase


class RxCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.company = env.company
        cls.company.write({'dmag_facility_code': '79001', 'phone': '0281234567',
                           'dmag_health_department': 'SỞ Y TẾ THÀNH PHỐ HỒ CHÍ MINH'})
        cls.doctor = env['dmag.dental.practitioner'].create({
            'name': 'BS Kê Đơn', 'role': 'doctor', 'user_id': env.user.id, 'title': 'BSCKI',
            'license_number': 'GPHN-001', 'rx_link_code': 'BS001', 'rx_link_password': 'secret',
        })
        cls.doctor_user = env['res.users'].create({
            'name': 'BS Thường', 'login': 'bs_rx_test', 'email': 'bsrx@dmag.test',
            'groups_id': [(6, 0, [env.ref('dmag_dental_base.group_dmag_doctor').id])],
        })
        cls.doctor2 = env['dmag.dental.practitioner'].create({
            'name': 'BS Thường', 'role': 'doctor', 'user_id': cls.doctor_user.id,
            'license_number': 'GPHN-002',
        })
        today = fields.Date.today()
        cls.patient = env['res.partner'].create({
            'name': 'Nguyễn Văn An', 'is_patient': True, 'mobile': '0900000111',
            'birthdate': today - relativedelta(years=30), 'gender': 'male',
            'citizen_id': '079090000111', 'street': '12 Lê Lợi', 'city': 'Thành phố Hồ Chí Minh',
            'dmag_bhyt_number': 'DN4797900000111',
        })
        cls.child = env['res.partner'].create({
            'name': 'Trần Bé Na', 'is_patient': True, 'birthdate': today - relativedelta(years=3),
            'gender': 'female', 'citizen_id': '079223000999',
        })
        Drug = env['dmag.drug']
        cls.amox = Drug.create({'inn_name': 'Amoxicillin', 'strength': '500 mg', 'unit': 'Viên',
                                'default_dose_per_time': 1, 'default_times_per_day': 2, 'default_days': 5})
        cls.augmentin = Drug.create({'inn_name': 'Amoxicillin + Acid clavulanic', 'strength': '500 mg + 125 mg',
                                     'brand_name': 'Augmentin', 'multi_ingredient': True, 'unit': 'Viên'})
        cls.para = Drug.create({'inn_name': 'Paracetamol', 'strength': '500 mg', 'unit': 'Viên',
                                'brand_name': 'Efferalgan'})
        cls.chx = Drug.create({'inn_name': 'Chlorhexidin', 'strength': '0,12%', 'unit': 'Chai', 'dose_unit': 'ml',
                               'route': 'mouthwash', 'default_timing': 'after_brushing'})
        cls.supplement = Drug.create({'inn_name': 'Vitamin C', 'strength': '500 mg', 'unit': 'Viên',
                                      'is_supplement': True})
        cls.morphine = Drug.create({'inn_name': 'Morphin', 'strength': '10 mg', 'unit': 'Ống',
                                    'route': 'injection', 'is_narcotic': True})
        cls.diag = env.ref('dmag_dental_base.diag_k04_0')
        Config = env['dmag.rx.national.config']
        cls.config = Config._get_for_company(cls.company) or Config.create({'company_id': cls.company.id})
        cls.config.write({'enabled': True, 'mode': 'mock', 'mock_fail': False,
                          'facility_link_code': 'CS79001', 'facility_password': 'pw',
                          'facility_token': False, 'facility_token_expiry': False})

    def _visit(self, patient=None):
        return self.env['dmag.dental.visit'].create({
            'patient_id': (patient or self.patient).id,
            'doctor_id': self.doctor.id,
            'diagnosis_ids': [(6, 0, self.diag.ids)],
        })

    def _rx(self, patient=None, lines=None, **kw):
        vals = {
            'patient_id': (patient or self.patient).id,
            'doctor_id': self.doctor.id,
            'diagnosis_ids': [(6, 0, self.diag.ids)],
            'line_ids': [(0, 0, line) for line in (lines or [
                {'drug_id': self.amox.id, 'dose_per_time': 1, 'times_per_day': 2, 'days': 5},
            ])],
        }
        vals.update(kw)
        return self.env['dmag.prescription'].create(vals)
