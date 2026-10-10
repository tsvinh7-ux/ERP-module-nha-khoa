import base64
import csv
import io

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestPay3p(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        ref = cls.env.ref
        cls.job = ref('dmag_hr_3p.job_reception')
        cls.profile = ref('dmag_hr_3p.profile_reception')
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Lễ tân Test', 'job_id': cls.job.id, 'barcode': 'LT001'})
        cls.manager = new_test_user(cls.env, 'qlpk_3p', groups='dmag_dental_base.group_dmag_manager')
        cls.month = '2025-01-01'

    def _assess(self):
        assessment = self.env['dmag.competency.assessment'].create({
            'employee_id': self.employee.id, 'date': self.month, 'name': 'Đánh giá Q4'})
        assessment.action_prefill()
        self.assertEqual(len(assessment.line_ids), 3)
        scores = {'C_SCHEDULE': 4, 'C_SERVICE': 4, 'C_DATA': 3}
        for line in assessment.line_ids:
            line.score = scores[line.competency_id.code]
        assessment.action_confirm()
        return assessment

    def _sheet(self):
        self._assess()
        sheet = self.env['dmag.pay3p.sheet'].create({'date_from': self.month})
        sheet.action_generate_lines()
        line = sheet.line_ids.filtered(lambda l: l.employee_id == self.employee)
        self.assertEqual(len(line), 1)
        actuals = {1: 98, 2: 15, 3: 30, 4: 20000000, 5: 70}
        for result in sheet.kpi_result_ids.filtered(lambda r: r.employee_id == self.employee):
            seq = int(result.kpi_id.code.split('_K')[1])
            result.write({'actual': actuals[seq]})
        sheet.action_compute()
        return sheet, line

    def test_sample_framework(self):
        self.assertTrue(self.profile.is_sample)
        self.assertEqual(self.profile.kpi_weight_total, 100)
        self.assertEqual(sorted(self.profile.kpi_ids.mapped('weight')), [15, 20, 20, 20, 25])
        self.assertEqual(self.employee.dmag_profile_id, self.profile)
        self.assertEqual(self.employee.dmag_grade_id.code, 'P2')
        self.assertEqual(self.employee.dmag_p1_amount, 9500000)
        with self.assertRaises(ValidationError):
            self.employee.dmag_p1_amount = 50000000
        with self.assertRaises(ValidationError):
            self.env['dmag.job.grade'].create({'code': 'P9', 'name': 'Sai', 'track': 'P', 'level': 9})

    def test_3p_computation(self):
        sheet, line = self._sheet()
        self.assertAlmostEqual(line.p2_coefficient, 1.27)
        self.assertEqual(line.p2_amount, 2540000)
        # 20 + 20 + 25 * 50% + 20 + 15 = 87.5
        self.assertAlmostEqual(line.kpi_score, 87.5)
        self.assertEqual(line.p3_kpi_amount, 2625000)
        self.assertEqual(line.total, 9500000 + 2540000 + 2625000 + line.commission_amount + line.okr_bonus)

    def test_approval_lock_and_export(self):
        sheet, line = self._sheet()
        with self.assertRaises(UserError):
            sheet.action_export_csv()
        sheet.with_user(self.manager).action_review()
        self.assertEqual(sheet.state, 'reviewed')
        with self.assertRaises(AccessError):
            sheet.with_user(self.manager).action_approve()
        sheet.action_approve()
        self.assertEqual(sheet.state, 'approved')
        with self.assertRaises(AccessError):
            line.with_user(self.manager).write({'adjustment': 100000})
        with self.assertRaises(AccessError):
            sheet.with_user(self.manager).action_reset_draft()
        # Giám đốc vẫn điều chỉnh được sau duyệt
        line.write({'adjustment': -100000, 'adjustment_note': 'Vi phạm cầu chì y đức'})
        self.assertEqual(line.p3_amount, 2625000 - 100000 + line.commission_amount + line.okr_bonus)

        action = sheet.with_user(self.manager).action_export_csv()
        self.assertEqual(sheet.state, 'exported')
        attachment = self.env['ir.attachment'].browse(int(action['url'].split('/')[3].split('?')[0]))
        content = base64.b64decode(attachment.datas).decode('utf-8-sig')
        rows = list(csv.reader(io.StringIO(content)))
        self.assertEqual(rows[0][:4], ['PERIOD', 'COMPANY', 'EMP_CODE', 'EMP_NAME'])
        self.assertIn('DMAG_P1', rows[0])
        row = next(r for r in rows[1:] if r[2] == 'LT001')
        self.assertEqual(row[0], '2025-01')
        self.assertEqual(float(row[rows[0].index('DMAG_P1')]), 9500000)
        self.assertEqual(float(row[rows[0].index('DMAG_3P_TOTAL')]), line.total)
        xlsx = sheet._export_file('xlsx')
        self.assertTrue(xlsx.datas)
        with self.assertRaises(AccessError):
            line.with_user(self.manager).write({'p1_amount': 1})
