from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import RxCommon


@tagged('post_install', '-at_install')
class TestRxWorkspace(RxCommon):

    def test_workspace_flow(self):
        visit = self._visit()
        Visit = self.env['dmag.dental.visit']
        catalog = Visit.get_rx_catalog()
        drug_ids = [d['id'] for d in catalog['drugs']]
        self.assertIn(self.amox.id, drug_ids)
        self.assertNotIn(self.supplement.id, drug_ids)
        self.assertIn('templates', catalog)
        self.assertEqual(catalog['max_days'], 30)

        ws = visit.get_visit_workspace()
        self.assertEqual(ws['prescriptions'], [])

        data = visit.save_prescription_from_workspace({
            'advice': 'Ăn mềm', 're_exam_date': '2030-01-01',
            'lines': [{'drug_id': self.amox.id, 'dose_per_time': 1, 'times_per_day': 2, 'days': 5,
                       'timing': 'after_meal'}],
        })
        self.assertEqual(data['state'], 'draft')
        self.assertEqual(data['diagnoses'][0]['id'], self.diag.id)  # mặc định từ lượt khám
        self.assertEqual(data['lines'][0]['usage'], 'Uống ngày 2 lần, mỗi lần 1 viên, sau ăn')
        self.assertEqual(data['lines'][0]['quantity'], 10)
        self.assertEqual(data['lines'][0]['quantity_display'], '10 Viên')

        # Cập nhật nháp: thay dòng thuốc
        data = visit.save_prescription_from_workspace({
            'id': data['id'],
            'lines': [{'drug_id': self.amox.id, 'dose_per_time': 1, 'times_per_day': 2, 'days': 5},
                      {'drug_id': self.para.id, 'dose_per_time': 1, 'times_per_day': 3, 'days': 2,
                       'quantity': 6}],
        })
        self.assertEqual(len(data['lines']), 2)
        self.assertEqual(data['advice'], 'Ăn mềm')

        ws = visit.get_visit_workspace()
        self.assertEqual(len(ws['prescriptions']), 1)

        result = visit.issue_prescription(data['id'])
        self.assertEqual(result['state'], 'sent')
        self.assertEqual(result['send_status'], 'sent')
        self.assertEqual(len(result['code']), 14)
        self.assertIn(result['code'], result['patient_message'])

        with self.assertRaises(UserError):
            visit.save_prescription_from_workspace({'id': data['id'], 'advice': 'Sửa'})
        other_visit = self._visit()
        with self.assertRaises(UserError):
            other_visit.issue_prescription(data['id'])

    def test_workspace_template(self):
        visit = self._visit()
        template = self.env['dmag.prescription.template'].create({
            'name': 'Viêm tủy cấp (test)', 'advice': 'Tránh nhai bên đau',
            'line_ids': [(0, 0, {'drug_id': self.amox.id, 'dose_per_time': 1, 'times_per_day': 3, 'days': 5})],
        })
        data = visit.save_prescription_from_workspace({'template_id': template.id})
        self.assertEqual(data['lines'][0]['quantity'], 15)
        self.assertEqual(data['advice'], 'Tránh nhai bên đau')
