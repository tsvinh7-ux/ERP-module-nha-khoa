import logging
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)

VISIT_EVENTS = [
    ('booked', 'Đặt lịch thành công'),
    ('confirmed', 'Xác nhận lịch'),
    ('arrived', 'Check-in'),
    ('in_chair', 'Lên ghế'),
    ('done', 'Hoàn tất lượt khám'),
    ('cancelled', 'Hủy lịch'),
    ('no_show', 'Không đến'),
    ('signed', 'Ký bệnh án'),
    ('paid', 'Thanh toán'),
]
TIME_TRIGGERS = ('before_start', 'after_done', 'recall', 'birthday', 'warranty')
INVASIVE_CATEGORIES = ('surgery', 'implant')
EXAM_CATEGORIES = ('exam', 'imaging')
ACTIVE_VISIT_STATES = ('draft', 'confirmed', 'arrived', 'in_chair', 'done')


class DmagJourneyRule(models.Model):
    """Luật điểm chạm hành trình khách hàng: khi nào → điều kiện → gửi ZNS và/hoặc giao việc CSKH."""
    _name = 'dmag.journey.rule'
    _description = 'Luật hành trình khách hàng'
    _order = 'stage_sequence, sequence, id'

    name = fields.Char('Điểm chạm', required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Phòng khám', index=True,
                                 help='Để trống = áp dụng cho mọi phòng khám.')
    stage = fields.Selection([
        ('before', 'Trước khi đến'),
        ('during', 'Trong khi ở phòng khám'),
        ('after', 'Sau khi về'),
    ], string='Giai đoạn', required=True, default='before')
    stage_sequence = fields.Integer(compute='_compute_stage_sequence', store=True)

    trigger = fields.Selection([
        ('event', 'Sự kiện lượt khám'),
        ('before_start', 'Trước giờ hẹn X giờ'),
        ('after_done', 'Sau khi hoàn tất X giờ'),
        ('recall', 'Đến hạn tái khám (theo dịch vụ)'),
        ('birthday', 'Sinh nhật'),
        ('warranty', 'Sắp hết hạn bảo hành'),
    ], string='Kích hoạt', required=True, default='event')
    event = fields.Selection(VISIT_EVENTS, string='Sự kiện')
    offset_hours = fields.Float('Số giờ', help='Trước giờ hẹn / sau khi hoàn tất.')
    offset_days = fields.Integer('Số ngày báo trước',
                                 help='Tái khám / sinh nhật / bảo hành: gửi trước ngày đến hạn bao nhiêu ngày.')
    lookback_days = fields.Integer(
        'Bỏ qua nếu trễ quá (ngày)', default=3,
        help='Không xử lý các mốc đã qua quá số ngày này (tránh gửi bù hàng loạt khi mới bật luật).')
    skip_if_booked_late = fields.Boolean(
        'Bỏ qua nếu đặt lịch sát giờ', default=True,
        help='Nhắc trước giờ hẹn: không gửi nếu lịch được đặt sau thời điểm nhắc (đã có tin xác nhận).')

    # Điều kiện
    domain = fields.Char('Điều kiện lượt khám (domain)', default='[]')
    service_scope = fields.Selection([
        ('all', 'Mọi lượt khám'),
        ('procedure', 'Có dịch vụ thủ thuật'),
        ('exam_only', 'Chỉ khám / chụp phim'),
    ], string='Phạm vi dịch vụ', default='all', required=True)
    invasive_only = fields.Boolean('Chỉ ca xâm lấn',
                                   help='Ca nặng hoặc có dịch vụ nhóm Phẫu thuật / Implant.')
    new_patient_only = fields.Boolean('Chỉ khách mới')

    # Hành động
    action = fields.Selection([
        ('zns', 'Gửi Zalo ZNS'),
        ('activity', 'Giao việc gọi CSKH'),
        ('both', 'Gửi ZNS + giao việc CSKH'),
    ], string='Hành động', required=True, default='zns')
    template_id = fields.Many2one('dmag.zns.template', string='Mẫu ZNS')
    create_nps = fields.Boolean('Tạo phiếu khảo sát NPS',
                                help='Tạo link khảo sát NPS (biến nps.url) để gửi kèm tin.')
    expire_on_start = fields.Boolean('Hủy tin nếu đã qua giờ hẹn', default=False)
    activity_type_id = fields.Many2one('mail.activity.type', string='Loại việc',
                                       default=lambda self: self.env.ref(
                                           'dmag_dental_journey.activity_type_cskh_call', raise_if_not_found=False))
    activity_role = fields.Selection([
        ('cskh', 'Nhân viên CSKH'),
        ('cskh_lead', 'Trưởng CSKH'),
        ('doctor', 'Bác sĩ phụ trách'),
        ('booker', 'Người đặt lịch'),
    ], string='Giao cho', default='cskh')
    activity_summary = fields.Char('Tiêu đề việc')
    activity_note = fields.Html('Kịch bản / ghi chú')
    activity_deadline_days = fields.Integer('Hạn xử lý (ngày)', default=0)
    note = fields.Text('Mô tả')

    execution_count = fields.Integer('Số lần chạy', compute='_compute_execution_count')

    @api.depends('stage')
    def _compute_stage_sequence(self):
        order = {'before': 1, 'during': 2, 'after': 3}
        for rule in self:
            rule.stage_sequence = order.get(rule.stage, 9)

    def _compute_execution_count(self):
        data = self.env['dmag.journey.execution']._read_group(
            [('rule_id', 'in', self.ids)], ['rule_id'], ['__count'])
        counts = {rule.id: count for rule, count in data}
        for rule in self:
            rule.execution_count = counts.get(rule.id, 0)

    @api.constrains('trigger', 'event', 'action', 'template_id', 'domain')
    def _check_rule(self):
        for rule in self:
            if rule.trigger == 'event' and not rule.event:
                raise ValidationError(_('Luật "%s": chọn sự kiện lượt khám.', rule.name))
            if rule.action in ('zns', 'both') and not rule.template_id:
                raise ValidationError(_('Luật "%s": chọn mẫu ZNS.', rule.name))
            try:
                domain = safe_eval(rule.domain or '[]')
                assert isinstance(domain, (list, tuple))
            except Exception as exc:
                raise ValidationError(_('Luật "%s": điều kiện domain không hợp lệ.', rule.name)) from exc

    def action_open_executions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Nhật ký – %s', self.name),
            'res_model': 'dmag.journey.execution',
            'view_mode': 'tree,form',
            'domain': [('rule_id', '=', self.id)],
        }

    # ------------------------------------------------------------------ conditions
    def _dmag_rules_for_company(self, company):
        return self.filtered(lambda r: not r.company_id or r.company_id == company)

    def _dmag_match_visit(self, visit):
        self.ensure_one()
        if self.company_id and self.company_id != visit.company_id:
            return False
        if self.new_patient_only and not visit.is_new_patient:
            return False
        products = visit._dmag_journey_products()
        categories = set(products.mapped('dental_category'))
        if self.service_scope == 'procedure' and not (categories - set(EXAM_CATEGORIES) - {False}):
            return False
        if self.service_scope == 'exam_only' and categories - set(EXAM_CATEGORIES) - {False}:
            return False
        if self.invasive_only and not (
                visit.is_heavy or categories & set(INVASIVE_CATEGORIES)
                or 'heavy' in products.mapped('dental_complexity')):
            return False
        domain = safe_eval(self.domain or '[]')
        if domain and not visit.filtered_domain(domain):
            return False
        return True

    # ------------------------------------------------------------------ execution
    def _dmag_run(self, key, visit=None, partner=None, record=None, variables=None, expire_at=False,
                  note=False):
        """Chạy luật một lần cho một đối tượng (idempotent theo ``key``). Trả về execution hoặc False."""
        self.ensure_one()
        Execution = self.env['dmag.journey.execution'].sudo()
        if Execution.search_count([('rule_id', '=', self.id), ('dedupe_key', '=', key)], limit=1):
            return False
        visit = visit or self.env['dmag.dental.visit']
        partner = partner or visit.patient_id
        record = record or visit or partner
        company = self.company_id or (visit and visit.company_id) or self.env.company
        vals = {
            'rule_id': self.id, 'dedupe_key': key, 'visit_id': visit.id, 'partner_id': partner.id,
            'company_id': company.id, 'note': note,
        }
        try:
            with self.env.cr.savepoint():
                result = self._dmag_perform(visit, partner, record, company, variables or {}, expire_at)
            vals.update(result, state='done')
            if result.get('message_id'):
                message = self.env['dmag.zns.message'].sudo().browse(result['message_id'])
                if message.state == 'skipped':
                    vals['state'] = 'skipped'
                    vals['note'] = message.error
        except Exception as exc:  # không chặn nghiệp vụ phòng khám
            _logger.exception('Journey rule %s failed for %s', self.id, key)
            vals.update(state='error', note=str(exc)[:500])
        return Execution.create(vals)

    def _dmag_perform(self, visit, partner, record, company, variables, expire_at):
        result = {}
        if self.create_nps and visit:
            nps = self.env['dmag.nps.response'].sudo()._dmag_create_for_visit(visit, channel='zns')
            variables = dict(variables, nps=nps)
            result['nps_response_id'] = nps.id
        if self.action in ('zns', 'both'):
            message = self.env['dmag.zns.message'].sudo().send(
                self.template_id, partner, record=record, variables=variables, company=company,
                expire_at=expire_at or (self.expire_on_start and visit and visit.scheduled_start) or False,
                origin=self.name)
            result['message_id'] = message.id
        if self.action in ('activity', 'both'):
            activity = self._dmag_schedule_activity(visit, partner, record, company, variables)
            result['activity_id'] = activity.id
        return result

    def _dmag_schedule_activity(self, visit, partner, record, company, variables):
        target = visit or partner
        user = self._dmag_responsible_user(self.activity_role, visit, company)
        summary = self.activity_summary or self.name
        if variables.get('service'):
            summary = '%s – %s' % (summary, variables['service'].display_name)
        activity_type = self.activity_type_id or self.env.ref('dmag_dental_journey.activity_type_cskh_call')
        return target.sudo().activity_schedule(
            activity_type_id=activity_type.id,
            date_deadline=fields.Date.context_today(self) + timedelta(days=self.activity_deadline_days),
            summary=summary,
            note=self.activity_note or '',
            user_id=user.id,
        )

    @api.model
    def _dmag_responsible_user(self, role, visit=None, company=None):
        company = company or (visit and visit.company_id) or self.env.company
        users = self.env['res.users']
        candidates = []
        if role == 'doctor' and visit:
            candidates.append(visit.doctor_id.user_id)
        if role == 'booker' and visit:
            candidates.append(visit.create_uid)
        if role in ('cskh', 'booker', 'doctor'):
            candidates.append(company.dmag_cskh_user_id)
        candidates.append(company.dmag_cskh_lead_user_id)
        manager_group = self.env.ref('dmag_dental_base.group_dmag_manager')
        candidates.append(manager_group.users.filtered(
            lambda u: u.active and not u.share and company in u.company_ids
            and u.id not in (self.env.ref('base.user_root').id,))[:1])
        candidates.append(self.env.ref('base.user_admin', raise_if_not_found=False) or users)
        for user in candidates:
            if user and user.active and not user._is_public() and user.id != self.env.ref('base.user_root').id:
                return user
        return self.env.user

    # ------------------------------------------------------------------ event hook
    @api.model
    def _dmag_on_visit_event(self, visits, event):
        rules = self.sudo().search([('trigger', '=', 'event'), ('event', '=', event)])
        for visit in visits.sudo():
            for rule in rules._dmag_rules_for_company(visit.company_id):
                if rule._dmag_match_visit(visit):
                    rule._dmag_run('visit:%s' % visit.id, visit=visit)
        if event in ('cancelled', 'no_show'):
            queued = self.env['dmag.zns.message'].sudo().search([
                ('res_model', '=', 'dmag.dental.visit'), ('res_id', 'in', visits.ids), ('state', '=', 'queued')])
            queued.write({'state': 'cancel', 'error': _('Lịch hẹn đã hủy / khách không đến.')})
        return True

    # ------------------------------------------------------------------ time-based (cron)
    @api.model
    def _cron_run_time_rules(self):
        rules = self.sudo().search([('trigger', 'in', TIME_TRIGGERS)])
        for rule in rules:
            try:
                getattr(rule, '_dmag_cron_%s' % rule.trigger)()
            except Exception:
                _logger.exception('Journey cron failed for rule %s', rule.id)
        return True

    def _dmag_company_domain(self, field='company_id'):
        return [(field, '=', self.company_id.id)] if self.company_id else []

    def _dmag_cron_before_start(self):
        now = fields.Datetime.now()
        offset = timedelta(hours=self.offset_hours)
        visits = self.env['dmag.dental.visit'].sudo().search([
            ('state', 'in', ('draft', 'confirmed')),
            ('scheduled_start', '>', now),
            ('scheduled_start', '<=', now + offset),
        ] + self._dmag_company_domain())
        for visit in visits:
            due = visit.scheduled_start - offset
            if self.skip_if_booked_late and visit.create_date and visit.create_date > due:
                continue
            if self._dmag_match_visit(visit):
                self._dmag_run('visit:%s:%s' % (visit.id, fields.Datetime.to_string(visit.scheduled_start)),
                               visit=visit, expire_at=visit.scheduled_start)

    def _dmag_cron_after_done(self):
        now = fields.Datetime.now()
        offset = timedelta(hours=self.offset_hours)
        visits = self.env['dmag.dental.visit'].sudo().search([
            ('state', '=', 'done'),
            ('done_time', '<=', now - offset),
            ('done_time', '>=', now - offset - timedelta(days=max(self.lookback_days, 1))),
        ] + self._dmag_company_domain())
        for visit in visits:
            if self._dmag_match_visit(visit):
                self._dmag_run('visit:%s' % visit.id, visit=visit)

    def _dmag_cron_recall(self):
        today = fields.Date.context_today(self)
        Visit = self.env['dmag.dental.visit'].sudo()
        companies = self.company_id or self.env['res.company'].sudo().search([])
        for item in Visit._dmag_recall_due(days_ahead=self.offset_days, companies=companies,
                                          lookback_days=self.lookback_days or 30, today=today):
            visit, product, due = item['visit'], item['product'], item['due_date']
            if not self._dmag_match_visit(visit):
                continue
            self._dmag_run('recall:%s:%s' % (visit.id, product.id), visit=visit,
                           variables={'service': product, 'due_date': due},
                           note=_('%(service)s – đến hạn %(due)s', service=product.display_name,
                                  due=due.strftime('%d/%m/%Y')))

    def _dmag_cron_birthday(self):
        target = fields.Date.context_today(self) + timedelta(days=self.offset_days)
        query = """
            SELECT id FROM res_partner
             WHERE is_patient AND active AND birthdate IS NOT NULL
               AND EXTRACT(MONTH FROM birthdate) = %s AND EXTRACT(DAY FROM birthdate) = %s
        """
        self.env.cr.execute(query, (target.month, target.day))
        partners = self.env['res.partner'].sudo().browse([r[0] for r in self.env.cr.fetchall()])
        Visit = self.env['dmag.dental.visit'].sudo()
        for partner in partners:
            last = Visit.search([('patient_id', '=', partner.id), ('state', '=', 'done')]
                                + self._dmag_company_domain(), order='scheduled_start desc', limit=1)
            if not last:
                continue
            self._dmag_run('birthday:%s:%s' % (partner.id, target.year), visit=last, partner=partner,
                           record=partner)

    def _dmag_cron_warranty(self):
        today = fields.Date.context_today(self)
        for item in self.env['dmag.dental.visit'].sudo()._dmag_warranty_due(
                days_ahead=self.offset_days, companies=self.company_id or None, today=today):
            visit = item['visit']
            if not self._dmag_match_visit(visit):
                continue
            self._dmag_run(item['key'], visit=visit,
                           variables={'service': item['product'], 'expiry_date': item['expiry_date']},
                           note=_('%(service)s – hết bảo hành %(date)s', service=item['product'].display_name,
                                  date=item['expiry_date'].strftime('%d/%m/%Y')))

    def action_run_now(self):
        """Chạy thử ngay các luật theo thời gian (Quản lý)."""
        for rule in self.filtered(lambda r: r.trigger in TIME_TRIGGERS):
            getattr(rule.sudo(), '_dmag_cron_%s' % rule.trigger)()
        return True


def months_after(date, months):
    return date + relativedelta(months=months)
