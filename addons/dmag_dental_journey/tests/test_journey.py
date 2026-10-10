import json
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import JourneyCommon


@tagged('post_install', '-at_install')
class TestJourney(JourneyCommon):

    def test_booking_sends_confirmation_once(self):
        visit = self._visit()
        execs = self._execs('rule_booking_confirm', visit_id=visit.id)
        self.assertEqual(len(execs), 1)
        self.assertEqual(execs.state, 'done')
        message = self._messages(visit, 'booking_confirm')
        self.assertEqual(len(message), 1)
        self.assertEqual(message.phone, '84912345678')
        self.assertTrue(message.transactional)
        data = json.loads(message.params_json)
        self.assertEqual(data['customer_name'], self.patient.name)
        self.assertEqual(data['booking_code'], visit.name)
        self.assertRegex(data['booking_time'], r'^\d{2}:\d{2}$')
        self.Message._cron_send_queue()
        self.assertEqual(message.state, 'sent')
        # Idempotent: sự kiện lặp lại không gửi lần hai
        visit._dmag_journey_event('booked')
        self.assertEqual(len(self._execs('rule_booking_confirm', visit_id=visit.id)), 1)
        self.assertEqual(len(self._messages(visit, 'booking_confirm')), 1)

    def test_checkin_welcome_and_done_thank_you(self):
        visit = self._done_visit()
        welcome = self._messages(visit, 'welcome_checkin')
        self.assertEqual(len(welcome), 1)
        thanks = self._messages(visit, 'visit_thank_you')
        self.assertEqual(len(thanks), 1)
        self.assertTrue(json.loads(thanks.params_json)['visit_url'])

    def test_reminder_d1_cron(self):
        start = self._now() + timedelta(hours=20)
        visit = self._visit(scheduled_start=start)
        late = self._visit(scheduled_start=start + timedelta(hours=2), chair_id=self.chair2.id)
        self._shift(visit, create_date=self._ago(days=3))
        surgery = self.env['product.product'].create({
            'name': 'Nhổ răng khôn T', 'is_dental_service': True, 'dental_category': 'surgery',
            'dental_requires_tooth': False})
        proc_visit = self._visit(scheduled_start=start + timedelta(minutes=30), chair_id=self.chair2.id,
                                 doctor_id=self.doctor2.id, service_ids=[(6, 0, surgery.ids)])
        self._shift(proc_visit, create_date=self._ago(days=3))

        self.Rule._cron_run_time_rules()
        self.assertEqual(len(self._messages(visit, 'reminder_d1')), 1)
        self.assertFalse(self._messages(visit, 'reminder_d1_video'))
        self.assertEqual(len(self._messages(proc_visit, 'reminder_d1_video')), 1)
        self.assertFalse(self._messages(proc_visit, 'reminder_d1'))
        # Đặt lịch sát giờ → đã có tin xác nhận, không nhắc D-1
        self.assertFalse(self._messages(late, 'reminder_d1'))
        # Còn 20 giờ → chưa nhắc H-2
        self.assertFalse(self._messages(visit, 'reminder_h2'))
        reminder = self._messages(visit, 'reminder_d1')
        self.assertEqual(reminder.expire_at, visit.scheduled_start)
        # Chạy lại cron: không gửi trùng
        self.Rule._cron_run_time_rules()
        self.assertEqual(len(self._messages(visit, 'reminder_d1')), 1)
        # Hủy lịch → tin còn chờ bị hủy
        self._set_quiet_now()
        visit.action_cancel()
        self.assertEqual(reminder.state, 'cancel')

    def test_reschedule_sends_new_reminder(self):
        visit = self._visit(scheduled_start=self._now() + timedelta(hours=1))
        self._shift(visit, create_date=self._ago(days=3))
        self.Rule._cron_run_time_rules()
        self.assertEqual(len(self._messages(visit, 'reminder_h2')), 1)
        visit.write({'scheduled_start': self._now() + timedelta(hours=1, minutes=30)})
        self.Rule._cron_run_time_rules()
        self.assertEqual(len(self._messages(visit, 'reminder_h2')), 2)

    def test_quiet_hours(self):
        self._set_quiet_now()
        visit = self._visit()
        confirm = self._messages(visit, 'booking_confirm')
        self.assertLessEqual(confirm.next_try, fields.Datetime.now())  # tin giao dịch
        self._shift(visit, scheduled_start=self._now() + timedelta(hours=10), create_date=self._ago(days=3))
        self.Rule._cron_run_time_rules()
        reminder = self._messages(visit, 'reminder_d1')
        self.assertEqual(reminder.state, 'queued')
        self.assertGreater(reminder.next_try, fields.Datetime.now())
        self.Message._cron_send_queue()
        self.assertEqual(confirm.state, 'sent')
        self.assertEqual(reminder.state, 'queued')

    def test_no_show_call_task(self):
        visit = self._visit()
        visit.action_no_show()
        execution = self._execs('rule_no_show_call', visit_id=visit.id)
        self.assertEqual(len(execution), 1)
        activity = execution.activity_id
        self.assertEqual(activity.activity_type_id, self.env.ref('dmag_dental_journey.activity_type_cskh_call'))
        self.assertEqual(activity.user_id, self.cskh_user)
        self.assertEqual(activity.res_id, visit.id)
        self.assertIn('buổi chiều', activity.summary)

    def test_followup_24h_pain_and_nps_48h(self):
        heavy = self._done_visit(service_ids=[(6, 0, self.svc_heavy.ids)], doctor_id=self.doctor2.id)
        light = self._done_visit(scheduled_start=self.start + timedelta(hours=3), chair_id=self.chair2.id)
        self._shift(heavy, done_time=self._ago(hours=25))
        self._shift(light, done_time=self._ago(hours=25))
        self.Rule._cron_run_time_rules()
        call = self._execs('rule_followup_24h', visit_id=heavy.id)
        self.assertEqual(len(call), 1)
        self.assertFalse(self._execs('rule_followup_24h', visit_id=light.id), 'Ca không xâm lấn: không gọi')
        self.assertFalse(self._execs('rule_nps_48h', visit_id=heavy.id), 'Chưa đủ 48h')

        heavy.with_user(self.cskh_user).record_pain_score_24h(8, 'Sưng nhẹ')
        self.assertEqual(heavy.pain_score_24h, 8)
        self.assertTrue(heavy.pain_score_24h_date)
        doctor_task = heavy.activity_ids.filtered(lambda a: a.user_id == self.doctor_user2)
        self.assertTrue(doctor_task)
        with self.assertRaises(ValidationError):
            heavy.record_pain_score_24h(11)

        self._shift(light, done_time=self._ago(hours=49))
        self.Rule._cron_run_time_rules()
        nps_exec = self._execs('rule_nps_48h', visit_id=light.id)
        self.assertEqual(len(nps_exec), 1)
        response = nps_exec.nps_response_id
        self.assertEqual(response.state, 'pending')
        message = self._messages(light, 'nps_survey')
        self.assertIn('/dmag/nps/%s' % response.sudo().token, json.loads(message.params_json)['survey_url'])

    def test_nps_low_score_creates_complaint(self):
        visit = self._done_visit()
        response = self.env['dmag.nps.response']._dmag_create_for_visit(visit)
        response.submit(4, 'Chờ lâu')
        self.assertEqual(response.category, 'detractor')
        self.assertTrue(response.is_complaint)
        activity = response.activity_ids
        self.assertEqual(len(activity), 1)
        self.assertEqual(activity.activity_type_id, self.env.ref('dmag_dental_journey.activity_type_complaint'))
        self.assertEqual(activity.user_id, self.lead_user)
        with self.assertRaises(UserError):
            response.submit(10)
        with self.assertRaises(ValidationError):
            self.env['dmag.nps.response']._dmag_create_for_visit(visit).submit(11)
        # Khách hài lòng: không mở phàn nàn
        visit2 = self._done_visit(scheduled_start=self.start + timedelta(hours=3))
        happy = self.env['dmag.nps.response']._dmag_create_for_visit(visit2)
        happy.submit(10)
        self.assertEqual(happy.category, 'promoter')
        self.assertFalse(happy.is_complaint)
        dashboard = self.env['dmag.dental.visit'].get_journey_dashboard()
        self.assertGreaterEqual(dashboard['nps']['responses'], 2)
        self.assertGreaterEqual(dashboard['nps']['complaints_open'], 1)

    def test_recall_due_generation(self):
        scaling = self.env['product.product'].create({
            'name': 'Cạo vôi T', 'is_dental_service': True, 'dental_category': 'hygiene',
            'recall_months': 6, 'dental_requires_tooth': False})
        visit = self._done_visit(service_ids=[(6, 0, scaling.ids)])
        past = fields.Datetime.now() - relativedelta(months=6) + timedelta(days=3)
        self._shift(visit, done_time=past, scheduled_start=past - timedelta(hours=1),
                    scheduled_end=past - timedelta(minutes=30))
        due = self.env['dmag.dental.visit']._dmag_recall_due(days_ahead=7)
        items = [i for i in due if i['visit'] == visit]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['product'], scaling)

        self.Rule._cron_run_time_rules()
        execution = self._execs('rule_recall', visit_id=visit.id)
        self.assertEqual(len(execution), 1)
        self.assertTrue(execution.message_id)
        self.assertEqual(json.loads(execution.message_id.params_json)['service_name'], 'Cạo vôi T')
        self.assertEqual(execution.activity_id.user_id, self.cskh_user)
        self.Rule._cron_run_time_rules()
        self.assertEqual(len(self._execs('rule_recall', visit_id=visit.id)), 1)
        # Khách đã đặt lịch mới → không còn trong danh sách đến hạn
        self._visit(scheduled_start=self.start + timedelta(days=2))
        due = self.env['dmag.dental.visit']._dmag_recall_due(days_ahead=7)
        self.assertFalse([i for i in due if i['visit'] == visit])

    def test_opt_out_respected(self):
        self.patient.zns_opt_out = True
        visit = self._visit()
        execution = self._execs('rule_booking_confirm', visit_id=visit.id)
        self.assertEqual(execution.state, 'skipped')
        message = self._messages(visit, 'booking_confirm')
        self.assertEqual(message.state, 'skipped')
        self.Message._cron_send_queue()
        self.assertEqual(message.state, 'skipped')
        # Opt-out sau khi tin đã xếp hàng → không gửi
        self.patient.zns_opt_out = False
        visit2 = self._visit(scheduled_start=self.start + timedelta(hours=3))
        queued = self._messages(visit2, 'booking_confirm')
        self.patient.zns_opt_out = True
        self.Message._cron_send_queue()
        self.assertEqual(queued.state, 'skipped')

    def test_birthday_and_warranty(self):
        today = fields.Date.context_today(self.env['res.partner'])
        crown = self.env['product.product'].create({
            'name': 'Bọc sứ BH', 'is_dental_service': True, 'warranty_months': 12, 'dental_requires_tooth': False})
        visit = self._done_visit()
        self.env['dmag.dental.procedure'].create({'visit_id': visit.id, 'product_id': crown.id,
                                                  'price_unit': 1000, 'state': 'draft'})
        proc = visit.procedure_ids.filtered(lambda p: p.product_id == crown)
        proc.write({'state': 'done'})
        self._shift(visit, done_time=fields.Datetime.now() - relativedelta(months=12) + timedelta(days=10))
        self.patient.birthdate = today - relativedelta(years=30)
        self.Rule._cron_run_time_rules()
        birthday = self._execs('rule_birthday', partner_id=self.patient.id)
        self.assertEqual(len(birthday), 1)
        self.assertEqual(birthday.message_id.template_id.code, 'birthday_wish')
        warranty = self._execs('rule_warranty', visit_id=visit.id)
        self.assertEqual(len(warranty), 1)
        self.assertEqual(json.loads(warranty.message_id.params_json)['service_name'], 'Bọc sứ BH')

    def test_dashboard_shape(self):
        visit = self._visit()
        visit.action_no_show()
        self._done_visit(scheduled_start=self.start + timedelta(hours=3))
        data = self.env['dmag.dental.visit'].get_journey_dashboard(
            fields.Date.to_string(fields.Date.today() - timedelta(days=1)),
            fields.Date.to_string(fields.Date.today() + timedelta(days=3)))
        for key in ('period', 'visits', 'show_up_rate', 'no_show_rate', 'nps', 'recall_due', 'messages',
                    'call_tasks'):
            self.assertIn(key, data)
        self.assertGreaterEqual(data['visits']['no_show'], 1)
        self.assertGreater(data['no_show_rate'], 0)
        self.assertGreaterEqual(data['call_tasks']['today'], 1)
        self.assertGreaterEqual(data['messages']['total'], 1)
        # Lễ tân xem được bảng điều khiển
        self.env['dmag.dental.visit'].with_user(self.cskh_user).get_journey_dashboard()

    def test_logs_read_only(self):
        visit = self._visit()
        execution = self._execs('rule_booking_confirm', visit_id=visit.id)
        from odoo.exceptions import AccessError
        with self.assertRaises(AccessError):
            execution.with_user(self.lead_user).write({'note': 'x'})
        with self.assertRaises(AccessError):
            execution.with_user(self.lead_user).unlink()
