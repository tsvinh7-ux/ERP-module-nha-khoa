"""Lịch nghỉ luân phiên của nhân sự ("Lịch nghỉ luân phiên").

Quyết định của chủ phòng khám (11/10/2026): *"Chủ nhật vẫn làm, nghỉ luân phiên nhau vào ngày trong tuần vì Chủ nhật
khách hàng đi khám đông"* → phòng khám mở cửa cả tuần, mỗi nhân sự (bác sĩ, phụ tá, lễ tân) có ngày nghỉ hằng tuần vào
ngày thường; bộ xếp lịch tự động chia ngày nghỉ xoay vòng giữ số người trực tối thiểu theo vai trò; nghỉ phép / đổi ca
đột xuất do Quản lý duyệt.

* ``dmag.staff.rotation`` – một người trong lịch luân phiên: vai trò, hồ sơ lâm sàng / tài khoản / nhân viên, ngày nghỉ
  hằng tuần.
* ``dmag.staff.leave`` – nghỉ phép một hoặc nhiều ngày, hoặc đổi ngày nghỉ (nghỉ ngày A, đi làm bù ngày nghỉ cố định B);
  nhân viên tạo yêu cầu, Quản lý duyệt; đã duyệt chỉ Giám đốc sửa.
* ``RosterInfo`` – ảnh chụp thuần Python (gắn vào ``ScheduleInfo.roster``) để mọi nơi hỏi "ai trực ngày nào": giờ trống,
  kiểm tra đặt lịch, gợi ý xếp lịch AI-11, trợ lý Zalo AI-07, nhịp mục tiêu từng bác sĩ, dữ liệu demo, người nhận
  thông báo của trợ lý.
"""
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .dmag_access import check_director, is_director, is_manager, is_workflow
from .dmag_clinic_schedule import WEEKDAY_SHORT

ROLES = [
    ('doctor', 'Bác sĩ'),
    ('assistant', 'Phụ tá / Điều dưỡng'),
    ('receptionist', 'Lễ tân / Tư vấn'),
    ('other', 'Khác'),
]
ROLE_SHORT = {'doctor': 'BS', 'assistant': 'PT', 'receptionist': 'LT', 'other': 'NV'}
COVER_ROLES = ('doctor', 'assistant', 'receptionist')
ROTATION_ANCHOR = date(2026, 1, 5)  # một Thứ Hai – mốc đếm tuần khi xoay vòng ngày nghỉ


class RosterInfo:
    """Ảnh chụp lịch luân phiên (không truy vấn lại CSDL).

    * ``members``: {id: {'id', 'name', 'role', 'off': set(thứ), 'practitioner_id', 'user_id'}}
    * ``leaves``: [(member_id, từ ngày, đến ngày, kind, nhãn)] – chỉ yêu cầu ĐÃ DUYỆT
    * ``extra_work``: {member_id: {ngày: nhãn}} – ngày đi làm bù khi đổi ca
    """

    def __init__(self, members, leaves=(), extra_work=None, rotate_weekly=False, allowed=(0, 1, 2, 3, 4),
                 requirements=None):
        self.members = members
        self.leaves = list(leaves)
        self.extra_work = extra_work or {}
        self.rotate_weekly = rotate_weekly
        self.allowed = [wd for wd in allowed]
        self.requirements = requirements or {}
        self.by_practitioner = {m['practitioner_id']: mid for mid, m in members.items() if m.get('practitioner_id')}
        self.by_user = {}
        for mid, m in members.items():
            if m.get('user_id'):
                self.by_user.setdefault(m['user_id'], mid)

    def weekly_off(self, member, day):
        """Các thứ nghỉ hằng tuần của ``member`` trong tuần chứa ``day`` (xoay vòng nếu bật)."""
        offs = set(member.get('off') or ())
        if not self.rotate_weekly or not offs or not self.allowed:
            return offs
        week = (day - ROTATION_ANCHOR).days // 7
        out = set()
        for wd in offs:
            if wd in self.allowed:
                idx = self.allowed.index(wd)
                out.add(self.allowed[(idx + week) % len(self.allowed)])
            else:
                out.add(wd)
        return out

    def status(self, member_id, day):
        """(trực?, loại, nhãn) – loại: on | weekly_off | leave | swap_off | swap_work."""
        member = self.members.get(member_id)
        if not member:
            return True, 'on', ''
        for mid, d_from, d_to, kind, label in self.leaves:
            if mid == member_id and d_from <= day <= d_to:
                return False, 'swap_off' if kind == 'swap' else 'leave', label
        if day in self.extra_work.get(member_id, {}):
            return True, 'swap_work', self.extra_work[member_id][day]
        if day.weekday() in self.weekly_off(member, day):
            return False, 'weekly_off', _('nghỉ luân phiên %s', WEEKDAY_SHORT[day.weekday()])
        return True, 'on', ''

    def is_on_duty(self, member_id, day):
        return self.status(member_id, day)[0]

    def practitioner_off_reason(self, practitioner_id, day):
        mid = self.by_practitioner.get(practitioner_id)
        if not mid:
            return None
        on, _kind, label = self.status(mid, day)
        return None if on else label

    def user_on_duty(self, user_id, day):
        mid = self.by_user.get(user_id)
        return True if not mid else self.is_on_duty(mid, day)

    def on_duty(self, day, role=None):
        return [m for mid, m in self.members.items()
                if (not role or m['role'] == role) and self.is_on_duty(mid, day)]

    def coverage(self, day):
        counts = {role: 0 for role in COVER_ROLES}
        for m in self.on_duty(day):
            if m['role'] in counts:
                counts[m['role']] += 1
        return counts

    def shortages(self, day, requirements=None):
        """[(vai trò, đang trực, tối thiểu)] còn thiếu người – chỉ vai trò có người trong lịch luân phiên."""
        req = requirements or self.requirements
        present = {m['role'] for m in self.members.values()}
        cov = self.coverage(day)
        return [(role, cov.get(role, 0), req[role]) for role in COVER_ROLES
                if role in present and req.get(role) and cov.get(role, 0) < req[role]]

    def duty_days(self, member_id, days):
        return [d for d in days if self.is_on_duty(member_id, d)]


def plan_rotation(members_by_role, allowed, requirements, role_order=COVER_ROLES):
    """Bộ xếp lịch nghỉ luân phiên (hàm thuần, xác định).

    :param members_by_role: {vai trò: [mã người theo thứ tự]}
    :param allowed: các thứ được xếp nghỉ (vd. [0, 1, 2, 3, 4])
    :param requirements: {vai trò: số người trực tối thiểu}
    :return: ({mã người: thứ nghỉ hoặc None}, [cảnh báo])

    Mỗi người một ngày nghỉ / tuần; chia vòng tròn qua các ngày được phép, mỗi ngày không quá ``n − tối thiểu`` người
    cùng vai trò nghỉ → luôn đủ người trực. Vai trò sau lệch pha với vai trò trước để ngày nghỉ của cả phòng khám rải
    đều trong tuần.
    """
    plan, warnings = {}, []
    allowed = sorted(set(allowed))
    offset = 0
    for role in list(role_order) + sorted(r for r in members_by_role if r not in role_order):
        people = members_by_role.get(role) or []
        if not people:
            continue
        need = requirements.get(role, 0)
        capacity = len(people) - need
        label = dict(ROLES).get(role, role)
        if not allowed:
            warnings.append(_('Chưa chọn ngày được nghỉ luân phiên – không xếp nghỉ cho %s.', label))
            plan.update({p: None for p in people})
            continue
        if capacity <= 0:
            warnings.append(_('%(role)s: chỉ có %(n)s người, cần tối thiểu %(need)s người trực mỗi ngày – không thể '
                              'xếp nghỉ luân phiên (cần thêm người hoặc giảm mức tối thiểu).',
                              role=label, n=len(people), need=need))
            plan.update({p: None for p in people})
            continue
        counts = {wd: 0 for wd in allowed}
        for i, person in enumerate(people):
            order = [allowed[(offset + i + k) % len(allowed)] for k in range(len(allowed))]
            candidates = [wd for wd in order if counts[wd] < capacity]
            if not candidates:
                plan[person] = None
                warnings.append(_('%s: không đủ ngày để xếp nghỉ cho mọi người.', label))
                continue
            best = min(candidates, key=lambda wd: (counts[wd], order.index(wd)))
            counts[best] += 1
            plan[person] = best
        offset += len(people)
    return plan, warnings


class DmagStaffRotation(models.Model):
    _name = 'dmag.staff.rotation'
    _description = 'Nhân sự trong lịch nghỉ luân phiên'
    _inherit = ['mail.thread']
    _order = 'role_sequence, sequence, name, id'

    name = fields.Char('Họ tên', required=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Phòng khám', required=True, index=True,
                                 default=lambda self: self.env.company)
    role = fields.Selection(ROLES, string='Vai trò', required=True, default='doctor', tracking=True)
    role_sequence = fields.Integer(compute='_compute_role_sequence', store=True)
    practitioner_id = fields.Many2one('dmag.dental.practitioner', string='Hồ sơ lâm sàng', index=True,
                                      help='Bác sĩ / phụ tá: giờ trống, đặt lịch, gợi ý xếp lịch dùng ngày trực của hồ sơ này.')
    user_id = fields.Many2one('res.users', string='Tài khoản', index=True,
                              help='Lễ tân: trợ lý Zalo báo câu hỏi ngoài dữ liệu cho người đang trực theo tài khoản này.')
    employee_id = fields.Many2one('hr.employee', string='Hồ sơ nhân viên', groups='hr.group_hr_user')
    off_weekday_ids = fields.Many2many('dmag.weekday', 'dmag_staff_rotation_off_weekday_rel', 'rotation_id', 'weekday_id',
                                       string='Ngày nghỉ hằng tuần', tracking=True)
    off_text = fields.Char('Nghỉ hằng tuần', compute='_compute_off_text')
    note = fields.Char('Ghi chú')
    leave_ids = fields.One2many('dmag.staff.leave', 'member_id', string='Nghỉ phép / đổi ca')

    _sql_constraints = [
        ('practitioner_uniq', 'unique(practitioner_id, company_id)', 'Hồ sơ lâm sàng này đã có trong lịch luân phiên.'),
        ('user_uniq', 'unique(user_id, company_id)', 'Tài khoản này đã có trong lịch luân phiên.'),
    ]

    @api.depends('role')
    def _compute_role_sequence(self):
        order = {code: i for i, (code, _label) in enumerate(ROLES)}
        for member in self:
            member.role_sequence = order.get(member.role, 9)

    @api.depends('off_weekday_ids')
    def _compute_off_text(self):
        for member in self:
            days = member.off_weekday_ids.sorted('code')
            member.off_text = ', '.join(days.mapped('name')) if days else _('Không nghỉ cố định')

    @api.onchange('practitioner_id')
    def _onchange_practitioner(self):
        prac = self.practitioner_id
        if prac:
            self.name = self.name or prac.name
            self.role = 'doctor' if prac.role == 'doctor' else 'assistant'
            if prac.user_id and not self.user_id:
                self.user_id = prac.user_id

    @api.onchange('user_id')
    def _onchange_user(self):
        if self.user_id and not self.name:
            self.name = self.user_id.name

    @api.constrains('off_weekday_ids', 'company_id')
    def _check_sunday(self):
        for member in self:
            if 6 in member.off_weekday_ids.mapped('code'):
                schedule = self.env['dmag.clinic.schedule'].sudo()._get_for_company(member.company_id)
                if not schedule.rotation_allow_sunday:
                    raise ValidationError(_('%s: Chủ nhật là ngày đông khách nhất – phòng khám không cho nghỉ hằng tuần '
                                            'vào Chủ nhật (bật "Cho phép nghỉ Chủ nhật" trong Lịch làm việc nếu cần).',
                                            member.name))

    def write(self, vals):
        if 'off_weekday_ids' in vals and not is_workflow(self.env) and not is_manager(self.env):
            raise UserError(_('Chỉ Quản lý phòng khám đổi ngày nghỉ hằng tuần. Nhân viên tạo yêu cầu "Nghỉ phép / đổi ca".'))
        return super().write(vals)

    # ------------------------------------------------------------------ snapshot
    @api.model
    def _roster_info(self, schedule):
        """``RosterInfo`` của phòng khám của ``schedule`` (None nếu chưa ai trong lịch luân phiên)."""
        members = self.sudo().search([('company_id', '=', schedule.company_id.id)])
        if not members:
            return None
        data = {m.id: {'id': m.id, 'name': m.name, 'role': m.role, 'off': set(m.off_weekday_ids.mapped('code')),
                       'practitioner_id': m.practitioner_id.id, 'user_id': m.user_id.id} for m in members}
        leaves, extra = [], {}
        for leave in self.env['dmag.staff.leave'].sudo().search([('member_id', 'in', members.ids),
                                                                ('state', '=', 'approved')]):
            label = leave._short_label()
            leaves.append((leave.member_id.id, leave.date_from, leave.date_to or leave.date_from, leave.kind, label))
            if leave.kind == 'swap' and leave.swap_date:
                extra.setdefault(leave.member_id.id, {})[leave.swap_date] = _('đi làm bù (đổi ca %s)',
                                                                             leave.date_from.strftime('%d/%m'))
        allowed = sorted(schedule.rotation_weekday_ids.mapped('code')) or [0, 1, 2, 3, 4]
        return RosterInfo(data, leaves, extra, schedule.rotation_rotate_weekly, allowed, schedule._requirements())

    @api.model
    def _info(self, company=None):
        return self.env['dmag.clinic.schedule'].get_info(company or self.env.company)

    @api.model
    def on_duty_users(self, day=None, role='receptionist', company=None):
        """Tài khoản đang trực ngày ``day`` theo vai trò (lễ tân trực nhận thông báo của trợ lý)."""
        company = company or self.env.company
        day = day or fields.Date.context_today(self)
        info = self._info(company)
        members = self.sudo().search([('company_id', '=', company.id), ('role', '=', role), ('user_id', '!=', False)])
        if not info.roster:
            return members.mapped('user_id')
        return members.filtered(lambda m: info.is_open_day(day) and info.roster.is_on_duty(m.id, day)).mapped('user_id')

    # ------------------------------------------------------------------ bộ xếp lịch
    @api.model
    def action_generate_rotation(self, company=None):
        """Nút "Xếp lịch nghỉ luân phiên tự động": chia ngày nghỉ hằng tuần vòng tròn theo vai trò, giữ số người trực
        tối thiểu. Chỉ Quản lý trở lên."""
        if not is_manager(self.env):
            raise UserError(_('Chỉ Quản lý phòng khám được xếp lịch nghỉ luân phiên.'))
        company = company or self.env.company
        schedule = self.env['dmag.clinic.schedule'].sudo()._get_for_company(company)
        members = self.sudo().search([('company_id', '=', company.id)])
        by_role = {}
        for member in members:
            by_role.setdefault(member.role, []).append(member.id)
        info = schedule._info()
        allowed = [wd for wd in (schedule.rotation_weekday_ids.mapped('code') or [0, 1, 2, 3, 4])
                   if info.weekly.get(wd) and (wd != 6 or schedule.rotation_allow_sunday)]
        req = schedule._requirements()
        req['other'] = 0
        plan, warnings = plan_rotation(by_role, allowed, req)
        Weekday = self.env['dmag.weekday']
        for member in members:
            wd = plan.get(member.id)
            day = Weekday.search([('code', '=', wd)], limit=1) if wd is not None else Weekday
            member.with_context(dmag_workflow=True).write({'off_weekday_ids': [(6, 0, day.ids)]})
        body = _('Xếp lịch nghỉ luân phiên tự động (%(user)s): %(lines)s',
                 user=self.env.user.name,
                 lines='; '.join('%s – %s' % (m.name, m.off_text) for m in members))
        schedule.message_post(body=body + ('<br/>' + '<br/>'.join(warnings) if warnings else ''))
        return {'plan': {m.id: plan.get(m.id) for m in members}, 'warnings': warnings}

    # ------------------------------------------------------------------ màn hình lịch tháng
    @api.model
    def get_month_roster(self, month=False, company_id=False):
        """Dữ liệu màn hình "Lịch nghỉ luân phiên": lịch tháng (tuần × 7 ngày), ai trực / nghỉ, đủ người hay thiếu."""
        company = self.env['res.company'].browse(company_id) if company_id else self.env.company
        today = fields.Date.context_today(self)
        start = fields.Date.to_date(month) if month else today
        start = start.replace(day=1)
        end = start + relativedelta(months=1) - timedelta(days=1)
        schedule = self.env['dmag.clinic.schedule'].sudo()._get_for_company(company)
        info = schedule._info()
        roster = info.roster
        req = schedule._requirements()
        members = self.sudo().search([('company_id', '=', company.id)])
        grid_start = start - timedelta(days=start.weekday())
        grid_end = end + timedelta(days=6 - end.weekday())
        role_labels = dict(ROLES)
        present_roles = [r for r in COVER_ROLES if members.filtered(lambda m, r=r: m.role == r)]
        days, weeks, shortage_days = {}, [], 0
        day = grid_start
        week = []
        while day <= grid_end:
            closure = info.closure(day)
            is_open = info.is_open_day(day)
            on, off = {r: [] for r in present_roles}, []
            cov = {}
            if is_open and roster:
                for member in members:
                    on_duty, kind, label = roster.status(member.id, day)
                    if on_duty:
                        if member.role in on:
                            on[member.role].append({'id': member.id, 'name': member.name,
                                                    'swap': kind == 'swap_work', 'label': label})
                    else:
                        off.append({'id': member.id, 'name': member.name, 'role': member.role,
                                    'short': ROLE_SHORT.get(member.role, ''), 'kind': kind, 'label': label})
                for role in present_roles:
                    n = len(on[role])
                    cov[role] = {'n': n, 'min': req.get(role, 0), 'ok': n >= req.get(role, 0),
                                 'label': role_labels[role], 'short': ROLE_SHORT[role]}
            ok = all(c['ok'] for c in cov.values())
            in_month = start <= day <= end
            if in_month and is_open and not ok:
                shortage_days += 1
            item = {'date': fields.Date.to_string(day), 'day': day.day, 'in_month': in_month,
                    'weekday': WEEKDAY_SHORT[day.weekday()], 'is_sunday': day.weekday() == 6,
                    'is_today': day == today, 'open': is_open, 'closure': closure or '',
                    'on': on, 'off': off, 'coverage': cov, 'ok': ok}
            days[item['date']] = item
            week.append(item)
            if len(week) == 7:
                weeks.append(week)
                week = []
            day += timedelta(days=1)
        leaves = self.env['dmag.staff.leave'].sudo().search([
            ('company_id', '=', company.id), ('state', '=', 'draft')], order='date_from')
        recent = self.env['dmag.staff.leave'].sudo().search([
            ('company_id', '=', company.id), ('state', '=', 'approved'), ('date_to', '>=', start),
            ('date_from', '<=', end)], order='date_from')
        weekly = []
        for wd in range(7):
            if not info.weekly.get(wd):
                weekly.append({'weekday': WEEKDAY_SHORT[wd], 'open': False, 'off': []})
                continue
            names = [m.name for m in members if wd in m.off_weekday_ids.mapped('code')]
            weekly.append({'weekday': WEEKDAY_SHORT[wd], 'open': True, 'off': names, 'is_sunday': wd == 6})
        return {
            'month': fields.Date.to_string(start), 'label': _('Tháng %s/%s', start.month, start.year),
            'prev': fields.Date.to_string(start - relativedelta(months=1)),
            'next': fields.Date.to_string(start + relativedelta(months=1)),
            'weeks': weeks, 'roles': [{'code': r, 'label': role_labels[r], 'short': ROLE_SHORT[r], 'min': req.get(r, 0)}
                                      for r in present_roles],
            'members': [{'id': m.id, 'name': m.name, 'role': m.role, 'role_label': role_labels.get(m.role, ''),
                         'off_text': m.off_text, 'user_id': m.user_id.id} for m in members],
            'weekly': weekly, 'shortage_days': shortage_days,
            'pending': [leave._card() for leave in leaves],
            'approved': [leave._card() for leave in recent],
            'hours': info.weekly_text(),
            'rotate_weekly': schedule.rotation_rotate_weekly,
            'can_manage': is_manager(self.env),
            'schedule_id': schedule.id,
            'empty': not members,
        }


class DmagStaffLeave(models.Model):
    _name = 'dmag.staff.leave'
    _description = 'Nghỉ phép / đổi ca (lịch luân phiên)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_from desc, id desc'

    name = fields.Char('Mô tả', compute='_compute_name', store=True)
    member_id = fields.Many2one('dmag.staff.rotation', string='Nhân sự', required=True, index=True, ondelete='cascade',
                                tracking=True)
    company_id = fields.Many2one(related='member_id.company_id', store=True, index=True)
    role = fields.Selection(related='member_id.role', store=True)
    kind = fields.Selection([('leave', 'Nghỉ phép / nghỉ đột xuất'), ('swap', 'Đổi ngày nghỉ (đổi ca)')],
                            string='Loại', required=True, default='leave', tracking=True)
    date_from = fields.Date('Nghỉ từ ngày', required=True, tracking=True)
    date_to = fields.Date('Đến ngày', tracking=True)
    swap_date = fields.Date('Đi làm bù ngày', tracking=True,
                            help='Đổi ca: ngày nghỉ cố định mà người này sẽ đi làm thay cho ngày nghỉ mới.')
    reason = fields.Char('Lý do')
    state = fields.Selection([('draft', 'Chờ Quản lý duyệt'), ('approved', 'Đã duyệt'), ('refused', 'Từ chối'),
                              ('cancel', 'Đã hủy')], string='Trạng thái', default='draft', required=True,
                             tracking=True, index=True, copy=False)
    requested_by_id = fields.Many2one('res.users', string='Người tạo yêu cầu', readonly=True,
                                      default=lambda self: self.env.user)
    approved_by_id = fields.Many2one('res.users', string='Người duyệt', readonly=True, copy=False)
    approved_at = fields.Datetime('Duyệt lúc', readonly=True, copy=False)
    coverage_warning = fields.Char('Cảnh báo thiếu người', compute='_compute_coverage_warning')

    @api.depends('member_id', 'kind', 'date_from', 'date_to', 'swap_date')
    def _compute_name(self):
        for leave in self:
            leave.name = '%s – %s' % (leave.member_id.name or '', leave._short_label())

    def _short_label(self):
        self.ensure_one()
        if not self.date_from:
            return ''
        if self.kind == 'swap':
            return _('đổi ca: nghỉ %(off)s, làm bù %(work)s', off=self.date_from.strftime('%d/%m'),
                     work=self.swap_date.strftime('%d/%m') if self.swap_date else '?')
        end = self.date_to or self.date_from
        if end != self.date_from:
            return _('nghỉ phép %(a)s–%(b)s', a=self.date_from.strftime('%d/%m'), b=end.strftime('%d/%m'))
        return _('nghỉ phép %s', self.date_from.strftime('%d/%m'))

    @api.onchange('date_from')
    def _onchange_date_from(self):
        if self.date_from and (not self.date_to or self.date_to < self.date_from):
            self.date_to = self.date_from

    @api.constrains('date_from', 'date_to', 'kind', 'swap_date')
    def _check_dates(self):
        for leave in self:
            if leave.date_to and leave.date_to < leave.date_from:
                raise ValidationError(_('Ngày kết thúc phải sau ngày bắt đầu.'))
            if leave.kind == 'swap' and not leave.swap_date:
                raise ValidationError(_('Đổi ca: cần chọn ngày đi làm bù.'))

    def _days(self):
        self.ensure_one()
        end = self.date_to or self.date_from
        return [self.date_from + timedelta(days=i) for i in range((end - self.date_from).days + 1)] \
            if self.kind == 'leave' else [self.date_from]

    def _compute_coverage_warning(self):
        for leave in self:
            leave.coverage_warning = leave._coverage_issue() if leave.member_id and leave.date_from else False

    def _coverage_issue(self):
        """Nếu duyệt yêu cầu này: những ngày thiếu người trực (mô phỏng trên ảnh chụp lịch luân phiên)."""
        self.ensure_one()
        info = self.env['dmag.clinic.schedule'].sudo().get_info(self.company_id or self.env.company)
        roster = info.roster
        if not roster or self.member_id.id not in roster.members:
            return False
        extra = (self.member_id.id, self.date_from, self.date_to or self.date_from, self.kind, self._short_label())
        trial = RosterInfo(roster.members, roster.leaves + ([extra] if self.state != 'approved' else []),
                           roster.extra_work, roster.rotate_weekly, roster.allowed, roster.requirements)
        role_labels = dict(ROLES)
        issues = []
        for day in self._days():
            if not info.is_open_day(day):
                continue
            for role, n, need in trial.shortages(day):
                if role == self.member_id.role:
                    issues.append(_('%(day)s chỉ còn %(n)s/%(need)s %(role)s', day=day.strftime('%d/%m'), n=n,
                                    need=need, role=role_labels[role].lower()))
        return '; '.join(issues) or False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('state') == 'approved' and not is_workflow(self.env) and not is_manager(self.env):
                raise UserError(_('Chỉ Quản lý phòng khám duyệt nghỉ phép / đổi ca.'))
        leaves = super().create(vals_list)
        for leave in leaves.filtered(lambda l: l.state == 'draft'):
            leave._notify_managers()
        return leaves

    def write(self, vals):
        if not is_workflow(self.env):
            if 'state' in vals or {'approved_by_id', 'approved_at'} & set(vals):
                if vals.get('state') == 'cancel' and all(l.state == 'draft' for l in self):
                    pass  # người tạo tự hủy yêu cầu chưa duyệt
                elif not is_manager(self.env):
                    raise UserError(_('Chỉ Quản lý phòng khám duyệt / từ chối nghỉ phép, đổi ca.'))
            locked = self.filtered(lambda l: l.state in ('approved', 'refused'))
            if locked and not is_director(self.env) and set(vals) - {'state'}:
                raise UserError(_('Yêu cầu "%s" đã được xử lý – chỉ Giám đốc được sửa.', locked[0].name))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda l: l.state == 'approved') and not is_director(self.env):
            raise UserError(_('Nghỉ phép / đổi ca đã duyệt chỉ Giám đốc được xóa – hãy hủy.'))
        return super().unlink()

    def _notify_managers(self):
        group = self.env.ref('dmag_dental_base.group_dmag_manager', raise_if_not_found=False)
        director_group = self.env.ref('dmag_dental_base.group_dmag_director', raise_if_not_found=False)
        root = self.env.ref('base.user_root')
        for leave in self:
            users = group.users.filtered(lambda u: leave.company_id in u.company_ids and not u.share and u != root
                                         and u not in (director_group.users if director_group else u.browse()))
            for user in users[:1]:
                leave.sudo().activity_schedule('mail.mail_activity_data_todo', summary=_('Duyệt: %s', leave.name),
                                               user_id=user.id, note=leave.reason or '')

    def action_approve(self):
        if not is_manager(self.env):
            raise UserError(_('Chỉ Quản lý phòng khám duyệt nghỉ phép / đổi ca.'))
        for leave in self.filtered(lambda l: l.state == 'draft'):
            issue = leave._coverage_issue()
            leave.with_context(dmag_workflow=True).write({
                'state': 'approved', 'approved_by_id': self.env.uid, 'approved_at': fields.Datetime.now()})
            leave.message_post(body=_('%(user)s duyệt %(name)s.%(warn)s', user=self.env.user.name, name=leave.name,
                                      warn=(_(' Lưu ý thiếu người trực: %s.', issue) if issue else '')))
            leave.activity_ids.action_feedback(feedback=_('Đã duyệt'))
        return True

    def action_refuse(self):
        if not is_manager(self.env):
            raise UserError(_('Chỉ Quản lý phòng khám từ chối nghỉ phép / đổi ca.'))
        self.filtered(lambda l: l.state == 'draft').with_context(dmag_workflow=True).write({'state': 'refused'})
        self.activity_ids.action_feedback(feedback=_('Từ chối'))
        return True

    def action_cancel(self):
        for leave in self:
            if leave.state == 'approved' and not is_manager(self.env):
                raise UserError(_('Chỉ Quản lý hủy nghỉ phép đã duyệt.'))
        self.with_context(dmag_workflow=True).write({'state': 'cancel'})
        self.activity_ids.unlink()
        return True

    def _card(self):
        self.ensure_one()
        return {'id': self.id, 'name': self.member_id.name, 'role': dict(ROLES).get(self.role, ''),
                'label': self._short_label(), 'reason': self.reason or '', 'state': self.state,
                'kind': self.kind, 'requested_by': self.requested_by_id.name or '',
                'warning': self.coverage_warning or ''}

    @api.model
    def request_leave(self, vals):
        """Tạo yêu cầu từ màn hình lịch (nhân viên tạo cho mình; Quản lý tạo cho bất kỳ ai và có thể duyệt ngay)."""
        member = self.env['dmag.staff.rotation'].browse(int(vals['member_id']))
        if not is_manager(self.env) and member.user_id != self.env.user:
            raise UserError(_('Nhân viên chỉ tạo yêu cầu nghỉ / đổi ca cho chính mình.'))
        leave = self.sudo().create({
            'member_id': member.id, 'kind': vals.get('kind') or 'leave', 'date_from': vals['date_from'],
            'date_to': vals.get('date_to') or vals['date_from'], 'swap_date': vals.get('swap_date') or False,
            'reason': vals.get('reason') or False, 'requested_by_id': self.env.uid})
        if vals.get('approve') and is_manager(self.env):
            leave.action_approve()
        return leave._card()
