from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from odoo.addons.dmag_dental_clinic.tests.common import DentalCommon


@tagged('post_install', '-at_install')
class TestOkrDental(DentalCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        today = fields.Date.context_today(cls.env.user)
        cls.cycle = cls.env['okr.scale.cycle'].create({
            'name': 'Quý test', 'date_start': today - timedelta(days=30),
            'date_end': today + timedelta(days=60), 'state': 'open'})
        cls.objective = cls.env['okr.scale.objective'].create({
            'name': 'Trải nghiệm không đau, không chờ',
            'cycle_id': cls.cycle.id, 'level': 'company', 'owner_id': cls.env.user.id,
        })
        KR = cls.env['okr.scale.key.result']
        cls.kr_wait = KR.create({'objective_id': cls.objective.id, 'name': 'Chờ ≤ 10 phút',
                                 'progress_method': 'dmag_wait_time', 'start_value': 30, 'target_value': 10})
        cls.kr_accept = KR.create({'objective_id': cls.objective.id, 'name': 'Tỷ lệ chốt 50%',
                                   'progress_method': 'dmag_plan_acceptance', 'start_value': 0, 'target_value': 50})
        cls.kr_assoc = KR.create({'objective_id': cls.objective.id, 'name': '40% ca do BS phụ',
                                  'progress_method': 'dmag_associate_share', 'start_value': 0, 'target_value': 40})
        cls.doctor2.dmag_is_associate = True
        # Chỉ đo trên bác sĩ của test để không lẫn dữ liệu demo
        (cls.kr_wait | cls.kr_accept | cls.kr_assoc).write({
            'dmag_doctor_ids': [(6, 0, (cls.doctor | cls.doctor2).ids)]})

    def _visit_in_chair(self, doctor, start, wait):
        visit = self._visit(doctor_id=doctor.id, scheduled_start=start)
        checkin = fields.Datetime.now() - timedelta(minutes=60)
        visit._workflow_write({'state': 'in_chair', 'checkin_time': checkin,
                               'chair_time': checkin + timedelta(minutes=wait)})
        return visit

    def test_wait_time_and_associate_share(self):
        v1 = self._visit_in_chair(self.doctor, self.start, 10)
        v2 = self._visit_in_chair(self.doctor2, self.start + timedelta(hours=2), 20)
        Procedure = self.env['dmag.dental.procedure']
        Procedure.add_from_workspace(v1.id, self.svc_filling.id, teeth=['36'])
        Procedure.add_from_workspace(v2.id, self.svc_filling.id, teeth=['46'])

        self.assertEqual(self.kr_wait._dmag_compute_value(), 15)
        self.kr_wait.action_dmag_refresh()
        self.assertEqual(self.kr_wait.current_value, 15)
        self.assertAlmostEqual(self.kr_wait.progress, 75.0)

        self.assertEqual(self.kr_assoc._dmag_compute_value(), 50)
        self.kr_assoc.action_dmag_refresh()
        self.assertEqual(self.kr_assoc.progress, 100.0)

        # Lọc theo bác sĩ
        self.kr_wait.dmag_doctor_ids = self.doctor2
        self.assertEqual(self.kr_wait._dmag_compute_value(), 20)

    def test_plan_acceptance(self):
        Plan = self.env['dmag.treatment.plan']
        states = ['accepted', 'presented', 'cancel', 'draft']
        for state in states:
            plan = Plan.create({'patient_id': self.patient.id, 'doctor_id': self.doctor.id})
            plan._workflow_write({'state': state})
        self.assertAlmostEqual(self.kr_accept._dmag_compute_value(), 33.3)
        self.kr_accept.action_dmag_refresh()
        self.assertAlmostEqual(self.kr_accept.progress, 66.6, places=0)

    def test_no_data_keeps_manual_value(self):
        self.kr_wait.dmag_doctor_ids = self.doctor2
        self.assertIsNone(self.kr_wait._dmag_compute_value())
        self.kr_wait.action_dmag_refresh()
        self.assertEqual(self.kr_wait.progress, 0.0)
        self.assertTrue(self.kr_wait.dmag_value_date)

    def test_guardrail_turns_kr_red(self):
        self.kr_assoc.write({'current_value': 40})
        guard = self.env.ref('dmag_okr_dental.guardrail_low_reviews')
        guard.write({'key_result_ids': [(6, 0, self.kr_assoc.ids)], 'manual_value': 2})
        guard.action_check()
        self.assertFalse(guard.breached)
        self.assertNotEqual(self.kr_assoc.status, 'off_track')
        guard.manual_value = 5
        guard.action_check()
        self.assertTrue(guard.breached)
        self.assertTrue(self.kr_assoc.dmag_guardrail_breached)
        self.assertEqual(self.kr_assoc.status, 'off_track')
        # Cầu chì tự đo: hủy hợp đồng niềng – không có dữ liệu → 0%
        ortho = self.env.ref('dmag_okr_dental.guardrail_ortho_cancel')
        ortho.action_check()
        self.assertTrue(ortho.is_auto)
        self.assertFalse(ortho.breached)
