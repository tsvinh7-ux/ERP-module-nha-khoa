from datetime import date, timedelta

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged

from odoo.addons.dmag_dental_base.models.dmag_staff_rotation import plan_rotation


@tagged('post_install', '-at_install')
class TestStaffRotation(TransactionCase):
    """Lịch nghỉ luân phiên: bộ xếp lịch giữ số người trực tối thiểu, nghỉ phép / đổi ca có duyệt, Chủ nhật đông khách."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.company = env.company
        cls.schedule = env['dmag.clinic.schedule']._get_for_company(cls.company)
        cls.schedule.closure_ids.unlink()
        cls.schedule.write({'min_doctors': 2, 'min_receptionists': 1, 'min_assistants': 1, 'chairs_per_group': 4,
                            'rotation_allow_sunday': False, 'rotation_rotate_weekly': False})
        env['dmag.staff.rotation'].search([('company_id', '=', cls.company.id)]).unlink()
        Prac = env['dmag.dental.practitioner']
        cls.docs = Prac.create([{'name': 'BS Luân %s' % i, 'role': 'doctor'} for i in range(1, 4)])
        cls.assistants = Prac.create([{'name': 'PT Luân %s' % i, 'role': 'assistant'} for i in range(1, 3)])

        def user(login, group):
            return env['res.users'].with_context(no_reset_password=True).create({
                'name': login, 'login': login, 'email': '%s@dmag.test' % login, 'tz': 'Asia/Ho_Chi_Minh',
                'groups_id': [(6, 0, [env.ref(group).id])]})
        cls.lt1 = user('lt_rot1', 'dmag_dental_base.group_dmag_receptionist')
        cls.lt2 = user('lt_rot2', 'dmag_dental_base.group_dmag_receptionist')
        cls.manager = user('ql_rot', 'dmag_dental_base.group_dmag_manager')
        Rot = env['dmag.staff.rotation']
        cls.members = Rot.create(
            [{'name': d.name, 'role': 'doctor', 'practitioner_id': d.id} for d in cls.docs]
            + [{'name': a.name, 'role': 'assistant', 'practitioner_id': a.id} for a in cls.assistants]
            + [{'name': u.name, 'role': 'receptionist', 'user_id': u.id} for u in (cls.lt1, cls.lt2)])
        cls.monday = date(2026, 10, 12)
        cls.week = [cls.monday + timedelta(days=i) for i in range(7)]

    def _info(self):
        return self.env['dmag.clinic.schedule'].get_info(self.company)

    def test_plan_rotation_respects_minimums(self):
        plan, warnings = plan_rotation({'doctor': [1, 2, 3], 'receptionist': [4, 5], 'assistant': [6]},
                                       [0, 1, 2, 3, 4], {'doctor': 2, 'receptionist': 1, 'assistant': 1})
        self.assertEqual(len({plan[1], plan[2], plan[3]}), 3, 'Mỗi bác sĩ nghỉ một ngày khác nhau')
        self.assertNotEqual(plan[4], plan[5])
        self.assertIsNone(plan[6], 'Chỉ 1 phụ tá, cần 1 trực → không xếp nghỉ')
        self.assertTrue(warnings)
        for wd in range(7):
            self.assertGreaterEqual(sum(1 for p in (1, 2, 3) if plan[p] != wd), 2)
            self.assertGreaterEqual(sum(1 for p in (4, 5) if plan[p] != wd), 1)
        # nhiều người hơn số ngày: tối đa (n − tối thiểu) người cùng nghỉ một ngày
        plan, _w = plan_rotation({'doctor': list(range(10, 18))}, [0, 1, 2], {'doctor': 5})
        for wd in (0, 1, 2):
            self.assertLessEqual(sum(1 for p in range(10, 18) if plan[p] == wd), 3)

    def test_generate_rotation_and_coverage(self):
        with self.assertRaises(UserError):
            self.env['dmag.staff.rotation'].with_user(self.lt1).action_generate_rotation()
        res = self.env['dmag.staff.rotation'].with_user(self.manager).action_generate_rotation()
        self.assertFalse(res['warnings'])
        info = self._info()
        roster = info.roster
        for day in self.week:
            self.assertFalse(roster.shortages(day), 'Đủ người trực %s' % day)
        sunday = self.week[6]
        self.assertEqual(len(roster.on_duty(sunday)), len(self.members), 'Chủ nhật đông khách – không ai nghỉ')
        for member in self.members:
            self.assertNotIn(6, member.off_weekday_ids.mapped('code'))
            self.assertIn(member.off_weekday_ids.code, (0, 1, 2, 3, 4))
        # bác sĩ nghỉ luân phiên → không trực, có lý do
        doc_member = self.members.filtered(lambda m: m.practitioner_id == self.docs[0])
        off_day = self.monday + timedelta(days=doc_member.off_weekday_ids.code)
        self.assertFalse(self.docs[0].works_on(off_day))
        self.assertIn('nghỉ luân phiên', self.docs[0].off_reason(off_day))
        self.assertTrue(self.docs[0].works_on(sunday))
        self.assertEqual(len(self.docs[0].duty_days(self.monday, sunday)), 6)
        self.assertIn('nghỉ luân phiên', self.docs[0].duty_text())
        # lễ tân trực hôm đó
        lt_member = self.members.filtered(lambda m: m.user_id == self.lt1)
        lt_off = self.monday + timedelta(days=lt_member.off_weekday_ids.code)
        on_duty = self.env['dmag.staff.rotation'].on_duty_users(lt_off, 'receptionist')
        self.assertEqual(on_duty, self.lt2)

    def test_sunday_off_not_allowed_by_default(self):
        with self.assertRaises(ValidationError):
            self.members[0].write({'off_weekday_ids': [(6, 0, self.env.ref('dmag_dental_base.weekday_6').ids)]})
        self.schedule.rotation_allow_sunday = True
        self.members[0].write({'off_weekday_ids': [(6, 0, self.env.ref('dmag_dental_base.weekday_6').ids)]})
        # nhân viên không tự đổi ngày nghỉ hằng tuần
        with self.assertRaises(UserError):
            self.members[1].with_user(self.lt1).write({'off_weekday_ids': [(5, 0, 0)]})

    def test_leave_and_swap_with_approval(self):
        Rot = self.env['dmag.staff.rotation']
        Rot.with_user(self.manager).action_generate_rotation()
        doc_members = self.members.filtered(lambda m: m.role == 'doctor')
        a, b = doc_members[0], doc_members[1]
        # ngày b nghỉ luân phiên: nếu a cũng nghỉ phép → chỉ còn 1/2 bác sĩ
        b_off = self.monday + timedelta(days=b.off_weekday_ids.code)
        Leave = self.env['dmag.staff.leave']
        lt_member = self.members.filtered(lambda m: m.user_id == self.lt1)
        with self.assertRaises(UserError):  # lễ tân không tạo yêu cầu cho người khác
            Leave.with_user(self.lt1).request_leave({'member_id': a.id, 'date_from': str(b_off)})
        own = Leave.with_user(self.lt1).request_leave({'member_id': lt_member.id, 'date_from': str(self.week[5]),
                                                       'reason': 'Việc gia đình'})
        self.assertEqual(own['state'], 'draft')
        with self.assertRaises(UserError):
            Leave.browse(own['id']).with_user(self.lt1).action_approve()
        leave = Leave.create({'member_id': a.id, 'date_from': b_off, 'date_to': b_off, 'reason': 'Hội thảo'})
        self.assertIn('1/2', leave.coverage_warning or '', 'Cảnh báo thiếu bác sĩ trước khi duyệt')
        self.assertTrue(a.practitioner_id.works_on(b_off), 'Chưa duyệt → vẫn trực')
        leave.with_user(self.manager).action_approve()
        self.assertEqual(leave.state, 'approved')
        self.assertFalse(a.practitioner_id.works_on(b_off))
        self.assertIn('nghỉ phép', a.practitioner_id.off_reason(b_off))
        roster = self._info().roster
        self.assertEqual(roster.shortages(b_off), [('doctor', 1, 2)])
        with self.assertRaises(UserError):  # đã duyệt: chỉ Giám đốc sửa
            leave.with_user(self.manager).write({'reason': 'Sửa'})
        # đổi ca: nghỉ Chủ nhật, đi làm bù ngày nghỉ cố định
        c = doc_members[2]
        c_off = self.monday + timedelta(days=c.off_weekday_ids.code)
        swap = Leave.create({'member_id': c.id, 'kind': 'swap', 'date_from': self.week[6], 'swap_date': c_off})
        swap.with_user(self.manager).action_approve()
        self.assertTrue(c.practitioner_id.works_on(c_off), 'Đi làm bù ngày nghỉ cố định')
        self.assertFalse(c.practitioner_id.works_on(self.week[6]))

        data = Rot.with_user(self.manager).get_month_roster('2026-10-01')
        day = next(d for w in data['weeks'] for d in w if d['date'] == str(b_off))
        self.assertFalse(day['ok'])
        self.assertFalse(day['coverage']['doctor']['ok'])
        self.assertGreaterEqual(data['shortage_days'], 1)
        self.assertTrue(data['pending'])
        self.assertEqual(len(data['weeks'][0]), 7)

    def test_rotate_weekly(self):
        self.env['dmag.staff.rotation'].with_user(self.manager).action_generate_rotation()
        self.schedule.rotation_rotate_weekly = True
        roster = self._info().roster
        member = self.members[0]
        wd = member.off_weekday_ids.code
        this_week = self.monday + timedelta(days=wd)
        offs = roster.weekly_off(roster.members[member.id], this_week)
        next_offs = roster.weekly_off(roster.members[member.id], this_week + timedelta(days=7))
        self.assertNotEqual(offs, next_offs, 'Ngày nghỉ lùi sang thứ kế tiếp mỗi tuần')
        for day in self.week + [d + timedelta(days=7) for d in self.week]:
            self.assertFalse(roster.shortages(day))
