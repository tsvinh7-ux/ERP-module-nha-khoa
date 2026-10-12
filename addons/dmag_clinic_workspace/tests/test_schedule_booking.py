from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestScheduleBooking(TransactionCase):
    """Lịch làm việc phòng khám áp vào giờ trống đặt lịch và kiểm tra đặt lịch ngoài giờ."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.ws = env['dmag.workspace']
        cls.schedule = env['dmag.clinic.schedule']._get_for_company(env.company)
        cls.schedule.closure_ids.unlink()
        cls.chair = env['dmag.dental.chair'].create({'name': 'Ghế lịch làm việc'})
        cls.doctor = env['dmag.dental.practitioner'].create({'name': 'BS Lịch', 'role': 'doctor'})
        cls.doctor_all = env['dmag.dental.practitioner'].create({'name': 'BS Cả tuần', 'role': 'doctor'})
        env['dmag.staff.rotation'].search([('company_id', '=', env.company.id)]).unlink()
        cls.receptionist = env['res.users'].create({
            'name': 'Lễ tân lịch', 'login': 'lt_schedule', 'email': 'lt_schedule@dmag.test', 'tz': 'Asia/Ho_Chi_Minh',
            'groups_id': [(6, 0, [env.ref('dmag_dental_base.group_dmag_receptionist').id])]})
        cls.manager = env['res.users'].create({
            'name': 'Quản lý lịch', 'login': 'ql_schedule', 'email': 'ql_schedule@dmag.test', 'tz': 'Asia/Ho_Chi_Minh',
            'groups_id': [(6, 0, [env.ref('dmag_dental_base.group_dmag_manager').id])]})
        cls.patient = env['res.partner'].create({'name': 'BN lịch làm việc', 'is_patient': True})
        today = fields.Date.context_today(cls.ws)
        cls.monday = today + timedelta(days=7 - today.weekday())
        cls.sunday = cls.monday + timedelta(days=6)

    def _book(self, user, day, time):
        return self.ws.with_user(user).quick_book({
            'patient_id': self.patient.id, 'chair_id': self.chair.id, 'date': day.isoformat(), 'time': time})

    def test_free_slots_follow_shifts(self):
        slots = self.ws.get_free_slots(self.monday.isoformat(), False, 30)
        times = [s['time'] for s in slots]
        self.assertEqual(times[0], '08:00')
        self.assertIn('11:30', times)
        self.assertNotIn('11:45', times, 'Không vắt qua giờ nghỉ trưa (ca sáng kết thúc 12:00)')
        self.assertFalse([t for t in times if '12:00' <= t < '13:30'], 'Giờ nghỉ trưa không có khung trống')
        self.assertIn('13:30', times)
        self.assertEqual(times[-1], '19:30')
        sunday = [s['time'] for s in self.ws.get_free_slots(self.sunday.isoformat(), False, 30)]
        self.assertEqual(sunday, times, 'Chủ nhật làm như ngày thường (mặc định mở cửa cả tuần)')
        self.schedule.line_ids.filtered(lambda l: l.weekday == '6').unlink()
        self.assertFalse(self.ws.get_free_slots(self.sunday.isoformat(), False, 30), 'Chủ nhật nghỉ khi bỏ ca')
        # Ngày nghỉ đột xuất
        self.schedule.write({'closure_ids': [(0, 0, {'name': 'Đào tạo nội bộ', 'kind': 'closure',
                                                     'date_from': self.monday, 'date_to': self.monday})]})
        self.assertFalse(self.ws.get_free_slots(self.monday.isoformat(), False, 30))
        info = self.ws.get_day_info(self.monday.isoformat())
        self.assertFalse(info['open'])
        self.assertEqual(info['closure'], 'Đào tạo nội bộ')

    def test_custom_schedule_and_doctor_days(self):
        self.schedule.line_ids.unlink()
        self.schedule.write({'slot_step': 30, 'line_ids': [
            (0, 0, {'weekday': str(wd), 'hour_from': 9.0, 'hour_to': 11.0}) for wd in range(7)]})
        times = [s['time'] for s in self.ws.get_free_slots(self.sunday.isoformat(), False, 60)]
        self.assertEqual(times, ['09:00', '09:30', '10:00'])
        self.doctor.work_weekday_ids = [(6, 0, self.env.ref('dmag_dental_base.weekday_2').ids)]  # chỉ Thứ 4
        slots = self.ws.get_free_slots(self.monday.isoformat(), self.doctor.id, 30)
        self.assertTrue(slots)
        self.assertFalse(any(s['doctor_free'] for s in slots), 'Bác sĩ không làm Thứ 2')

    def test_booking_outside_hours_blocked_unless_manager(self):
        self.schedule.line_ids.filtered(lambda l: l.weekday == '6').unlink()  # thử với Chủ nhật nghỉ
        with self.assertRaisesRegex(UserError, 'ngoài giờ'):
            self._book(self.receptionist, self.monday, '12:30')
        with self.assertRaisesRegex(UserError, 'không làm việc'):
            self._book(self.receptionist, self.sunday, '09:00')
        ok = self._book(self.receptionist, self.monday, '09:00')
        self.assertTrue(ok['id'])
        # Quản lý trở lên được đặt ngoài giờ – có ghi chú trên lịch hẹn
        res = self._book(self.manager, self.sunday, '09:00')
        visit = self.env['dmag.dental.visit'].browse(res['id'])
        self.assertIn('ngoài lịch làm việc', ' '.join(visit.message_ids.mapped('body')))
        self.assertIn('Ngoài lịch làm việc', visit.schedule_warning or '')
        # Lễ tân dời lịch hợp lệ sang ngoài giờ cũng bị chặn
        valid = self.env['dmag.dental.visit'].browse(ok['id'])
        with self.assertRaises(UserError):
            valid.with_user(self.receptionist).write({
                'scheduled_start': self.ws._local_to_utc(self.monday, 21, 0)})
        # Chế độ chỉ cảnh báo
        self.schedule.enforce = 'warn'
        res = self._book(self.receptionist, self.monday, '12:30')
        self.assertTrue(res['id'])

    def test_rotation_day_off_slots_and_booking_warning(self):
        """Bác sĩ nghỉ luân phiên: không có giờ trống cho bác sĩ đó; đặt lịch vẫn được nhưng CẢNH BÁO; ngày không bác
        sĩ nào trực → không có giờ trống."""
        Rot = self.env['dmag.staff.rotation']
        tuesday = self.env.ref('dmag_dental_base.weekday_1')
        Rot.create([{'name': 'BS Lịch', 'role': 'doctor', 'practitioner_id': self.doctor.id,
                     'off_weekday_ids': [(6, 0, tuesday.ids)]},
                    {'name': 'BS Cả tuần', 'role': 'doctor', 'practitioner_id': self.doctor_all.id}])
        tue = self.monday + timedelta(days=1)
        slots = self.ws.get_free_slots(tue.isoformat(), self.doctor.id, 30)
        self.assertTrue(slots)
        self.assertFalse(any(s['doctor_free'] for s in slots), 'Bác sĩ nghỉ luân phiên Thứ 3')
        self.assertTrue(all(s['doctor_free'] for s in self.ws.get_free_slots(tue.isoformat(), self.doctor_all.id, 30)))
        info = self.ws.get_day_info(tue.isoformat())
        off = [d for d in info['doctors'] if not d['on_duty']]
        self.assertEqual([d['id'] for d in off], [self.doctor.id])
        self.assertIn('nghỉ luân phiên', off[0]['off_reason'])
        # đặt lịch bác sĩ ngày nghỉ: không chặn, cảnh báo + chatter
        res = self.ws.with_user(self.receptionist).quick_book({
            'patient_id': self.patient.id, 'chair_id': self.chair.id, 'doctor_id': self.doctor.id,
            'date': tue.isoformat(), 'time': '09:00'})
        visit = self.env['dmag.dental.visit'].browse(res['id'])
        self.assertIn('nghỉ luân phiên', visit.schedule_warning or '')
        self.assertIn('Bác sĩ không trực', visit.schedule_warning)
        self.assertIn('cần xác nhận lại với bác sĩ', ' '.join(visit.message_ids.mapped('body')))
        # mọi bác sĩ nghỉ Thứ 3 → không có giờ trống
        Rot.search([('practitioner_id', '=', self.doctor_all.id)]).off_weekday_ids = tuesday
        self.env['dmag.dental.practitioner'].search([('role', '=', 'doctor'), (
            'id', 'not in', (self.doctor | self.doctor_all).ids)]).write({'active': False})
        self.assertFalse(self.ws.get_free_slots(tue.isoformat(), False, 30))
