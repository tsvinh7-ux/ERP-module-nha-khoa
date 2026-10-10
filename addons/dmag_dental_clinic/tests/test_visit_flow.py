from datetime import timedelta

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import DentalCommon


@tagged('post_install', '-at_install')
class TestVisitFlow(DentalCommon):

    def test_journey_and_billing(self):
        visit = self._visit()
        self.assertTrue(visit.name.startswith('LK'))
        self.assertEqual(visit.duration, 30)
        self.assertTrue(visit.is_new_patient)
        visit.action_confirm()
        visit.action_check_in()
        self.assertEqual(visit.state, 'arrived')
        self.assertTrue(visit.checkin_time)
        visit.action_start()
        self.assertEqual(visit.state, 'in_chair')

        # Bệnh lý sâu răng 36 mặt nhai
        Entry = self.env['dmag.dental.chart.entry']
        entry_ids = Entry.add_from_chart(self.patient.id, ['36'], self.env.ref('dmag_dental_base.condition_caries').id,
                                         surfaces=['O'], visit_id=visit.id)
        self.assertEqual(len(entry_ids), 1)
        # Chạm lại cùng tình trạng trên cùng mặt răng không tạo bản ghi trùng
        again = Entry.add_from_chart(self.patient.id, ['36'], self.env.ref('dmag_dental_base.condition_caries').id,
                                     surfaces=['O'], visit_id=visit.id)
        self.assertEqual(again, [])

        proc = self.env['dmag.dental.procedure'].add_from_workspace(
            visit.id, self.svc_filling.id, teeth=['36'], surfaces=['O'])
        self.assertEqual(proc['state'], 'done')
        self.assertEqual(proc['amount'], 400000)

        chart = Entry.get_patient_chart(self.patient.id)
        conditions = {(c['tooth'], c['condition']) for c in chart}
        self.assertIn(('36', self.env.ref('dmag_dental_base.condition_filling').name), conditions)

        # Thu theo tiến độ
        self.assertEqual(visit.payment_status, 'to_invoice')
        self.assertEqual(visit.amount_due, 400000)
        visit.action_create_invoice()
        self.assertEqual(len(visit.invoice_ids), 1)
        self.assertEqual(visit.invoice_ids.amount_total, 400000)

        visit.action_done()
        self.assertEqual(visit.state, 'done')

        # Lượt sau không còn là khách mới
        visit2 = self._visit(scheduled_start=self.start + timedelta(days=7))
        self.assertFalse(visit2.is_new_patient)

    def test_chair_conflict(self):
        self._visit()
        with self.assertRaises(ValidationError):
            self._visit(doctor_id=self.doctor2.id, scheduled_start=self.start + timedelta(minutes=15))
        # Ghế khác thì được
        self._visit(doctor_id=self.doctor2.id, chair_id=self.chair2.id,
                    scheduled_start=self.start + timedelta(minutes=15))

    def test_two_heavy_cases_same_doctor(self):
        self._visit(service_ids=[(6, 0, self.svc_heavy.ids)])
        with self.assertRaises(ValidationError):
            self._visit(chair_id=self.chair2.id, service_ids=[(6, 0, self.svc_heavy.ids)],
                        scheduled_start=self.start + timedelta(minutes=30))
        # Ca nhẹ xen vào thì chỉ cảnh báo mềm
        light = self._visit(chair_id=self.chair2.id, scheduled_start=self.start + timedelta(minutes=30))
        self.assertTrue(light.schedule_warning)

    def test_scope_blocks_booking(self):
        with self.assertRaises(ValidationError):
            self._visit(doctor_id=self.doctor2.id, service_ids=[(6, 0, self.svc_crown.ids)])

    def test_record_lock(self):
        visit = self._visit()
        visit.action_check_in()
        visit.action_start()
        # Đủ thông tin pháp lý tối thiểu để ký (TT 13/2025: gắn số định danh; có khám, chẩn đoán ICD-10)
        self.patient.citizen_id = '079090000001'
        visit.save_record_from_workspace({
            'chief_complaint': 'Đau răng', 'examination': 'Lỗ sâu mặt nhai 36', 'assessment': 'Sâu ngà 36',
            'diagnosis_ids': self.env.ref('dmag_dental_base.diag_k02_1').ids})
        visit.action_sign_record()
        self.assertEqual(visit.record_state, 'signed')
        self.assertEqual(visit.signed_by_id, self.doctor)
        with self.assertRaises(UserError):
            visit.write({'assessment': 'Sửa sau khi ký'})
        # Quản lý mở bổ sung có ghi vết
        visit.action_amend_record()
        visit.write({'assessment': 'Bổ sung'})
        self.assertEqual(visit.assessment, 'Bổ sung')

    def test_cannot_start_without_checkin_state(self):
        visit = self._visit()
        with self.assertRaises(UserError):
            visit.action_done()
        visit.action_no_show()
        self.assertEqual(visit.state, 'no_show')

    def test_frontdesk_board(self):
        visit = self._visit()
        visit.action_check_in()
        board = self.env['dmag.dental.visit'].get_frontdesk_board()
        self.assertIn(visit.id, [v['id'] for v in board['visits']])
        self.assertTrue(board['chairs'])
        data = visit.get_visit_workspace()
        self.assertEqual(data['patient']['id'], self.patient.id)
