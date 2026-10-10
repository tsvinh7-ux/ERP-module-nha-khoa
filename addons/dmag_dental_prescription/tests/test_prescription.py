from unittest.mock import patch

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from odoo.addons.dmag_dental_prescription.models import dmag_prescription as rx_module

from .common import RxCommon


@tagged('post_install', '-at_install')
class TestPrescription(RxCommon):

    def test_drug_display_name_tt26(self):
        self.assertEqual(self.amox.name, 'Amoxicillin 500 mg')
        self.assertEqual(self.para.name, 'Paracetamol 500 mg (Efferalgan)')
        self.assertEqual(self.augmentin.name, 'Augmentin 500 mg + 125 mg')

    def test_usage_and_quantity(self):
        rx = self._rx(lines=[
            {'drug_id': self.amox.id, 'dose_per_time': 1, 'times_per_day': 2, 'days': 4},
            {'drug_id': self.chx.id, 'dose_per_time': 10, 'times_per_day': 2, 'days': 7},
        ])
        amox_line, chx_line = rx.line_ids
        self.assertEqual(amox_line.usage, 'Uống ngày 2 lần, mỗi lần 1 viên, sau ăn')
        self.assertEqual(amox_line.quantity, 8)
        self.assertEqual(amox_line.quantity_display, '08 Viên')
        self.assertEqual(chx_line.usage, 'Súc miệng ngày 2 lần, mỗi lần 10 ml, sau khi chải răng')
        self.assertEqual(chx_line.quantity_display, '01 Chai')
        amox_line.quantity = 12
        self.assertEqual(amox_line.quantity_display, '12 Viên')

    def test_code_format_and_uniqueness(self):
        rx1 = self._rx()
        rx1.action_issue()
        self.assertEqual(len(rx1.name), 14)
        self.assertRegex(rx1.name, rx_module.CODE_RE)
        self.assertTrue(rx1.name.startswith('79001'))
        self.assertTrue(rx1.name.endswith('-c'))
        # Va chạm mã ngẫu nhiên → sinh lại
        random_part = rx1.name[5:12]
        other = 'zzzzzzz' if random_part != 'zzzzzzz' else 'yyyyyyy'
        rx2 = self._rx()
        with patch.object(rx_module.secrets, 'choice', side_effect=list(random_part) + list(other)):
            rx2.action_issue()
        self.assertEqual(rx2.name, f'79001{other}-c')

    def test_facility_code_required(self):
        self.company.dmag_facility_code = False
        rx = self._rx()
        with self.assertRaisesRegex(ValidationError, 'Mã cơ sở KCB'):
            rx.action_issue()

    def test_day_limit(self):
        with self.assertRaisesRegex(ValidationError, 'tối đa 30 ngày'):
            self._rx(lines=[{'drug_id': self.amox.id, 'days': 31}])
        # Bệnh mạn tính: chỉ khi phòng khám bật cấu hình
        with self.assertRaises(ValidationError):
            self._rx(lines=[{'drug_id': self.amox.id, 'days': 60, 'is_chronic': True}])
        self.company.dmag_rx_allow_90_days = True
        rx = self._rx(lines=[{'drug_id': self.amox.id, 'days': 90, 'is_chronic': True}])
        self.assertEqual(rx.line_ids.days, 90)
        with self.assertRaises(ValidationError):
            self._rx(lines=[{'drug_id': self.amox.id, 'days': 91, 'is_chronic': True}])
        with self.assertRaises(ValidationError):
            self._rx(lines=[{'drug_id': self.amox.id, 'days': 31}])

    def test_quantity_positive(self):
        with self.assertRaisesRegex(ValidationError, 'số lượng'):
            self._rx(lines=[{'drug_id': self.amox.id, 'quantity': 0, 'days': 5}])

    def test_supplement_blocked(self):
        with self.assertRaisesRegex(ValidationError, 'thực phẩm chức năng'):
            self._rx(lines=[{'drug_id': self.supplement.id}])

    def test_identity_required(self):
        self.patient.citizen_id = False
        rx = self._rx()
        with self.assertRaisesRegex(ValidationError, 'định danh'):
            rx.action_issue()
        rx.identity_exemption_reason = 'Người nước ngoài – hộ chiếu B1234567'
        rx.action_issue()
        self.assertEqual(rx.state, 'sent')

    def test_under_72_months(self):
        rx = self._rx(patient=self.child)
        self.assertTrue(rx.is_under_72_months)
        with self.assertRaisesRegex(ValidationError, 'cân nặng'):
            rx.action_issue()
        rx.write({'weight': 14.5})
        with self.assertRaisesRegex(ValidationError, 'người đưa trẻ'):
            rx.action_issue()
        rx.write({'companion_name': 'Trần Văn Bố'})
        rx.action_issue()
        self.assertTrue(rx.name)
        self.assertGreaterEqual(rx.patient_age_months, 35)
        html = self.env['ir.actions.report']._render_qweb_html(
            'dmag_dental_prescription.report_prescription', rx.ids)[0].decode()
        self.assertIn('Họ tên người đưa trẻ đến khám', html)

    def test_doctor_license(self):
        self.doctor.license_expiry_date = '2020-01-01'
        self.doctor.license_issue_date = '2015-01-01'
        rx = self._rx()
        with self.assertRaisesRegex(ValidationError, 'hết hạn'):
            rx.action_issue()

    def test_controlled_drugs(self):
        rx = self._rx(lines=[{'drug_id': self.morphine.id, 'days': 1, 'times_per_day': 1}])
        with self.assertRaisesRegex(ValidationError, 'đơn "N"'):
            rx.action_issue()
        rx.rx_type = 'n'
        with self.assertRaisesRegex(ValidationError, 'chưa được cấu hình'):
            rx.action_issue()
        self.company.dmag_rx_allow_controlled = True
        with self.assertRaisesRegex(ValidationError, 'phạm vi kê đơn'):
            rx.action_issue()
        self.doctor.rx_controlled_allowed = True
        rx.action_issue()
        self.assertTrue(rx.name.endswith('-n'))

    def test_issued_is_locked(self):
        rx = self._rx(advice='Ăn mềm')
        rx.action_issue()
        self.assertEqual(rx.patient_identity, '079090000111')
        self.assertIn('Lê Lợi', rx.patient_address)
        with self.assertRaises(UserError):
            rx.advice = 'Sửa lời dặn'
        with self.assertRaises(UserError):
            rx.line_ids.days = 3
        with self.assertRaises(UserError):
            rx.write({'line_ids': [(0, 0, {'drug_id': self.para.id})]})
        with self.assertRaises(UserError):
            rx.unlink()
        # Thông tin bệnh nhân đổi sau phát hành không ảnh hưởng đơn
        self.patient.with_context(dmag_workflow=True).citizen_id = '079090000999'
        self.assertEqual(rx.patient_identity, '079090000111')

    def test_replace_flow(self):
        rx = self._rx()
        rx.action_issue()
        action = rx.action_replace()
        new = self.env['dmag.prescription'].browse(action['res_id'])
        self.assertEqual(new.state, 'draft')
        self.assertEqual(new.replaced_id, rx)
        self.assertEqual(len(new.line_ids), 1)
        self.assertFalse(new.name)
        # Gọi lại trả về cùng đơn nháp
        self.assertEqual(rx.action_replace()['res_id'], new.id)
        new.line_ids.days = 7
        new.action_issue()
        self.assertEqual(rx.state, 'replaced')
        self.assertEqual(rx.replaced_by_id, new)
        self.assertNotEqual(rx.name, new.name)
        cancel_logs = rx.send_log_ids.filtered(lambda log: log.operation == 'cancel')
        self.assertTrue(cancel_logs)

    def test_cancel_director_only(self):
        rx = self._rx()
        rx.action_issue()
        with self.assertRaises(AccessError):
            rx.with_user(self.doctor_user).action_cancel()
        with self.assertRaises(UserError):
            rx.action_cancel()  # thiếu lý do
        rx.cancel_reason = 'Kê nhầm bệnh nhân'
        rx.action_cancel()
        self.assertEqual(rx.state, 'cancelled')
        # Đơn nháp: bác sĩ tự hủy được
        draft = self._rx(doctor_id=self.doctor2.id)
        draft.with_user(self.doctor_user).action_cancel()
        self.assertEqual(draft.state, 'cancelled')

    def test_only_own_doctor_issues(self):
        rx = self._rx()
        with self.assertRaisesRegex(ValidationError, 'Chỉ bác sĩ'):
            rx.with_user(self.doctor_user).action_issue()
        own = self._rx(doctor_id=self.doctor2.id)
        own.with_user(self.doctor_user).action_issue()
        self.assertTrue(own.name)

    def test_template_apply_and_message(self):
        template = self.env['dmag.prescription.template'].create({
            'name': 'Sau nhổ răng khôn (test)', 'advice': 'Chườm lạnh', 're_exam_days': 7,
            'line_ids': [(0, 0, {'drug_id': self.augmentin.id, 'dose_per_time': 1, 'times_per_day': 2, 'days': 5}),
                         (0, 0, {'drug_id': self.para.id, 'dose_per_time': 1, 'times_per_day': 3,
                                 'days': 3, 'timing': 'when_pain'})],
        })
        rx = self._rx(lines=[])
        rx._apply_template(template)
        self.assertEqual(rx.line_ids.mapped('drug_id'), self.augmentin | self.para)
        self.assertEqual(rx.advice, 'Chườm lạnh')
        self.assertTrue(rx.re_exam_date)
        self.assertEqual(rx.line_ids[1].usage, 'Uống khi đau, mỗi lần 1 viên, tối đa 3 lần mỗi ngày')
        rx.action_issue()
        message = rx.get_patient_message()
        self.assertIn(rx.name, message)
        self.assertIn('0281234567', message)
        html = self.env['ir.actions.report']._render_qweb_html(
            'dmag_dental_prescription.report_prescription', rx.ids)[0].decode()
        self.assertIn('ĐƠN THUỐC', html)
        self.assertIn('Augmentin 500 mg + 125 mg', html)
        self.assertIn('10 Viên', html)
        self.assertIn('Bác sĩ / Y sĩ khám bệnh', html)
        self.assertIn('Khám lại xin mang theo đơn này', html)
