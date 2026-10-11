from datetime import date, datetime

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged

from odoo.addons.dmag_dental_base.models.dmag_clinic_schedule import ScheduleInfo


@tagged('post_install', '-at_install')
class TestClinicSchedule(TransactionCase):
    """Lịch làm việc phòng khám: mặc định, ca, ngày nghỉ, ngày làm việc riêng của bác sĩ."""

    def setUp(self):
        super().setUp()
        self.Schedule = self.env['dmag.clinic.schedule']
        self.schedule = self.Schedule._get_for_company(self.env.company)

    def test_default_schedule_matches_previous_behaviour(self):
        info = ScheduleInfo.default()
        monday, sunday = date(2026, 10, 12), date(2026, 10, 18)
        self.assertEqual(info.shifts(monday), [(480, 720), (810, 1200)])
        self.assertFalse(info.is_open_day(sunday))
        # cùng số ngày làm việc Thứ 2 – Thứ 7 như trước đây
        self.assertEqual(info.count_open_days(date(2025, 3, 1), date(2025, 3, 31)), 26)
        self.assertIn('Thứ 2 – Thứ 7: 08:00–12:00, 13:30–20:00', info.weekly_text())
        self.assertIn('Chủ nhật: nghỉ', info.weekly_text())
        # lịch tự tạo của công ty có cùng ca + ngày lễ mẫu 2026 đánh dấu cần xác minh
        company_info = self.schedule._info()
        self.assertEqual(company_info.weekly, info.weekly)
        self.assertTrue(self.schedule.closure_ids.filtered('to_verify'))
        self.assertTrue(all('[CẦN XÁC MINH]' in c.name for c in self.schedule.closure_ids))
        self.assertFalse(company_info.is_open_day(date(2026, 9, 2)), 'Quốc khánh (mẫu) nghỉ')

    def test_check_interval_and_capacity(self):
        info = ScheduleInfo.default()
        day = date(2026, 10, 13)
        self.assertIsNone(info.check_interval(datetime(2026, 10, 13, 9, 0), datetime(2026, 10, 13, 9, 30)))
        self.assertIn('ngoài giờ', info.check_interval(datetime(2026, 10, 13, 11, 45), datetime(2026, 10, 13, 12, 15)))
        self.assertIn('ngoài giờ', info.check_interval(datetime(2026, 10, 13, 20, 0), datetime(2026, 10, 13, 20, 30)))
        self.assertIn('không làm việc', info.check_interval(datetime(2026, 10, 18, 9, 0), datetime(2026, 10, 18, 9, 30)))
        # công suất: 1 lịch 60 phút / (240 phút sáng × 1 ghế)
        util = info.chair_utilization([day], 1, [(datetime(2026, 10, 13, 9, 0), datetime(2026, 10, 13, 10, 0))],
                                      (0, 720))
        self.assertEqual(util, 25.0)
        # giờ nghỉ trưa không tính
        self.assertEqual(info.busy_minutes(day, datetime(2026, 10, 13, 11, 30), datetime(2026, 10, 13, 14, 0)), 60)

    def test_closures_and_custom_shifts(self):
        self.schedule.line_ids.filtered(lambda l: l.weekday == '6').unlink()
        self.schedule.write({'line_ids': [(0, 0, {'weekday': '6', 'hour_from': 8.0, 'hour_to': 12.0})],
                             'closure_ids': [(0, 0, {'name': 'Bảo trì máy CBCT', 'kind': 'closure',
                                                     'date_from': '2026-10-21', 'date_to': '2026-10-21'})]})
        info = self.Schedule.get_info()
        self.assertEqual(info.shifts(date(2026, 10, 18)), [(480, 720)], 'Chủ nhật mở buổi sáng')
        self.assertFalse(info.is_open_day(date(2026, 10, 21)))
        self.assertEqual(info.closure(date(2026, 10, 21)), 'Bảo trì máy CBCT')
        day_info = self.Schedule.get_day_info('2026-10-21')
        self.assertFalse(day_info['open'])
        self.assertIn('Bảo trì', day_info['text'])
        with self.assertRaises(ValidationError):
            self.schedule.write({'line_ids': [(0, 0, {'weekday': '0', 'hour_from': 11.0, 'hour_to': 14.0})]})
        with self.assertRaises(ValidationError):
            self.schedule.write({'line_ids': [(0, 0, {'weekday': '1', 'hour_from': 21.0, 'hour_to': 20.0})]})

    def test_doctor_working_days(self):
        doctor = self.env['dmag.dental.practitioner'].create({
            'name': 'BS Thứ 2-4-6', 'role': 'doctor',
            'work_weekday_ids': [(6, 0, [self.env.ref('dmag_dental_base.weekday_%s' % d).id for d in (0, 2, 4)])]})
        self.assertTrue(doctor.works_on(date(2026, 10, 12)))
        self.assertFalse(doctor.works_on(date(2026, 10, 13)), 'Thứ 3 bác sĩ nghỉ')
        free = self.env['dmag.dental.practitioner'].create({'name': 'BS cả tuần', 'role': 'doctor'})
        self.assertTrue(free.works_on(date(2026, 10, 13)))
        self.assertFalse(free.works_on(date(2026, 10, 18)), 'Phòng khám nghỉ Chủ nhật')
