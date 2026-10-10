from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCompliance(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        # Phòng khám riêng để không lẫn dữ liệu demo
        cls.company = env['res.company'].create({'name': 'PK Pháp chế T'})
        env.user.company_ids |= cls.company
        cls.env = env(context=dict(env.context, allowed_company_ids=[cls.company.id]))
        cls.Doc = cls.env['dmag.compliance.doc'].with_company(cls.company)
        cls.today = fields.Date.context_today(cls.Doc)
        cls.type_facility = env.ref('dmag_dental_compliance.doc_type_facility_license')
        cls.type_waste = env.ref('dmag_dental_compliance.doc_type_waste_contract')
        cls.type_xray = env.ref('dmag_dental_compliance.doc_type_xray_inspection')
        cls.assistant_user = env['res.users'].create({
            'name': 'Phụ tá KSNK', 'login': 'pt_ksnk_test', 'email': 'ptksnk@dmag.test',
            'company_id': cls.company.id, 'company_ids': [(6, 0, cls.company.ids)],
            'groups_id': [(6, 0, [env.ref('dmag_dental_base.group_dmag_assistant').id])],
        })

    def _doc(self, dtype, expiry, **kw):
        vals = {'name': dtype.name, 'type_id': dtype.id, 'company_id': self.company.id,
                'issue_date': self.today - relativedelta(years=1), 'expiry_date': expiry}
        vals.update(kw)
        return self.Doc.create(vals)

    def test_doc_states_and_search(self):
        valid = self._doc(self.type_facility, False, no_expiry=True)
        expiring = self._doc(self.type_waste, self.today + timedelta(days=10))  # cảnh báo 30 ngày
        expired = self._doc(self.type_waste, self.today - timedelta(days=1), name='HĐ cũ')
        self.assertEqual(valid.state, 'valid')
        self.assertEqual(expiring.state, 'expiring')
        self.assertEqual(expiring.days_left, 10)
        self.assertEqual(expired.state, 'expired')
        domain = [('company_id', '=', self.company.id)]
        self.assertEqual(self.Doc.search(domain + [('state', '=', 'expired')]), expired)
        self.assertEqual(self.Doc.search(domain + [('state', 'in', ('expiring', 'expired'))]), expiring | expired)
        self.assertEqual(self.Doc.search(domain + [('state', '!=', 'valid')]), expiring | expired)
        # Gia hạn: hồ sơ mới thay thế, hồ sơ cũ lưu trữ
        ctx = expired.action_renew()['context']
        new = self.Doc.with_context(**ctx).create({'expiry_date': self.today + relativedelta(years=1),
                                                   'issue_date': self.today})
        self.assertEqual(new.type_id, self.type_waste)
        self.assertFalse(expired.active)
        self.assertEqual(new.state, 'valid')

    def test_compliance_status_and_cron(self):
        Equipment = self.env['dmag.equipment'].with_company(self.company)
        cbct = Equipment.create({'name': 'CBCT T', 'category': 'cbct', 'company_id': self.company.id})
        self.assertTrue(cbct.is_radiation)
        self.assertEqual(cbct.inspection_status, 'overdue')  # chưa có kiểm định
        self._doc(self.type_facility, False, no_expiry=True)
        waste = self._doc(self.type_waste, self.today + timedelta(days=10))
        status = self.Doc.get_compliance_status(self.company.id)
        self.assertFalse(status['ready'])
        self.assertEqual(status['documents'], {'valid': 1, 'expiring': 1, 'expired': 0})
        self.assertEqual(status['equipment']['overdue'], 1)
        red_names = [i['name'] for i in status['red_items']]
        self.assertIn(cbct.name, red_names)
        missing_types = {i['type'] for i in status['red_items'] if i['kind'] == 'missing'}
        self.assertIn(self.env.ref('dmag_dental_compliance.doc_type_radiation_license').name, missing_types)
        self.assertIn(self.type_xray.name, missing_types)  # CBCT chưa có chứng thư kiểm định
        self.assertEqual(status['counts']['expiring'], 1)
        self.assertTrue(status['counts']['missing'] >= 4)
        self.assertEqual([i['id'] for i in status['expiring_items']], [waste.id])

        # Kiểm định đạt → thiết bị hết quá hạn
        self.env['dmag.equipment.log'].with_user(self.assistant_user).create({
            'equipment_id': cbct.id, 'log_type': 'inspection', 'result': 'pass',
            'date': self.today - timedelta(days=5)})
        self.assertEqual(cbct.last_inspection_date, self.today - timedelta(days=5))
        self.assertEqual(cbct.next_inspection_date, self.today - timedelta(days=5) + relativedelta(months=12))
        self.assertEqual(cbct.inspection_status, 'ok')
        self._doc(self.type_xray, self.today + relativedelta(months=11), equipment_id=cbct.id)
        status = self.Doc.get_compliance_status(self.company.id)
        self.assertNotIn(cbct.name, [i['name'] for i in status['red_items']])
        self.assertNotIn(self.type_xray.name, {i['type'] for i in status['red_items'] if i['kind'] == 'missing'})

        # Cron: việc nhắc, không trùng
        self.Doc._cron_compliance_alerts()
        self.assertEqual(len(waste.activity_ids), 1)
        self.Doc._cron_compliance_alerts()
        self.assertEqual(len(waste.activity_ids), 1)

    def test_sterilization_batch(self):
        Equipment = self.env['dmag.equipment'].with_company(self.company)
        autoclave = Equipment.create({'name': 'Nồi hấp T', 'category': 'autoclave', 'company_id': self.company.id})
        Batch = self.env['dmag.sterilization.batch'].with_user(self.assistant_user)
        batch = Batch.create({'autoclave_id': autoclave.id, 'company_id': self.company.id, 'cycle_number': '101',
                              'biological_result': 'pending'})
        self.assertTrue(batch.name.startswith('TK'))
        with self.assertRaises(UserError):
            batch.action_release()  # chỉ thị hóa học chưa đạt
        batch.chemical_result = 'pass'
        batch.action_release()
        self.assertEqual(batch.state, 'released')
        self.assertTrue(batch.expiry_date)
        with self.assertRaises(AccessError):
            batch.write({'cycle_number': '999'})
        # Gắn mẻ vào lượt khám
        patient = self.env['res.partner'].create({'name': 'BN KSNK', 'is_patient': True})
        visit = self.env['dmag.dental.visit'].create({
            'patient_id': patient.id, 'company_id': self.company.id,
            'scheduled_start': fields.Datetime.now() + timedelta(days=2)})
        visit.sterilization_batch_ids = [(4, batch.id)]
        self.assertEqual(batch.visit_ids, visit)
        # Chỉ thị sinh học không đạt → thu hồi + việc rà soát
        batch.write({'biological_result': 'fail'})
        self.assertEqual(batch.state, 'recalled')
        self.assertTrue(batch.sudo().activity_ids)
        status = self.env['dmag.compliance.doc'].get_compliance_status(self.company.id)
        self.assertEqual(status['sterilization']['failed_30d'], 1)
        self.assertIn('sterilization', [i['kind'] for i in status['red_items']])
