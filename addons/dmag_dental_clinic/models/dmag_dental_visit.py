from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from odoo.addons.dmag_dental_base.models.dmag_access import check_director, is_director, is_manager, is_workflow
from odoo.addons.dmag_dental_base.models.dmag_clinic_schedule import WEEKDAY_SHORT, local_naive

ACTIVE_STATES = ('draft', 'confirmed', 'arrived', 'in_chair')
PAYMENT_METHODS = [('cash', 'Tiền mặt'), ('transfer', 'Chuyển khoản'), ('card', 'Quẹt thẻ')]

# Trường bệnh án: khóa sau khi bác sĩ ký
CLINICAL_FIELDS = {
    'chief_complaint', 'examination', 'assessment', 'diagnosis_ids',
    'treatment_note', 'advice',
}
# Trường bác sĩ được ghi tiếp khi bệnh án chưa ký (kể cả sau khi lượt khám hoàn tất)
RECORD_EDITABLE = CLINICAL_FIELDS | {'pain_score'}
# Sau khi khách đã đến, không đổi người bệnh / phòng khám
LOCK_AFTER_ARRIVAL = {'patient_id', 'company_id'}


class DmagDentalVisit(models.Model):
    """Lượt khám = một chặng trong hành trình khách hàng.

    Đặt lịch → Xác nhận → Đã đến (chờ) → Đang điều trị → Hoàn tất,
    kèm bệnh án của lượt khám (khóa sau khi ký) và các thủ thuật đã làm.
    """
    _name = 'dmag.dental.visit'
    _description = 'Lượt khám nha khoa'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'scheduled_start desc, id desc'

    name = fields.Char('Mã lượt khám', required=True, copy=False, readonly=True, default='/')
    company_id = fields.Many2one('res.company', string='Phòng khám', required=True,
                                 default=lambda self: self.env.company, index=True)
    patient_id = fields.Many2one('res.partner', string='Bệnh nhân', required=True, index=True,
                                 tracking=True, domain=[('is_patient', '=', True)],
                                 context={'default_is_patient': True, 'dmag_patient_search': True})
    patient_code = fields.Char(related='patient_id.patient_code', string='Mã BN')
    patient_phone = fields.Char(related='patient_id.mobile', string='Điện thoại')
    patient_alert_ids = fields.Many2many(related='patient_id.patient_alert_ids', string='Cảnh báo')
    is_new_patient = fields.Boolean('Khách mới', compute='_compute_is_new_patient', store=True)

    doctor_id = fields.Many2one('dmag.dental.practitioner', string='Bác sĩ', tracking=True,
                                domain=[('role', '=', 'doctor')], index=True)
    assistant_id = fields.Many2one('dmag.dental.practitioner', string='Phụ tá',
                                   domain=[('role', 'in', ('assistant', 'technician'))])
    chair_id = fields.Many2one('dmag.dental.chair', string='Ghế', tracking=True, index=True)
    service_ids = fields.Many2many('product.product', string='Dịch vụ dự kiến',
                                   domain=[('is_dental_service', '=', True)])
    reason = fields.Char('Lý do đến khám')
    source_id = fields.Many2one('dmag.customer.source', string='Nguồn đặt lịch')
    treatment_plan_id = fields.Many2one('dmag.treatment.plan', string='Theo kế hoạch điều trị')

    scheduled_start = fields.Datetime('Giờ hẹn', required=True, tracking=True,
                                      default=lambda self: fields.Datetime.now())
    duration = fields.Integer('Thời lượng (phút)', compute='_compute_duration', store=True, readonly=False)
    scheduled_end = fields.Datetime('Kết thúc dự kiến', compute='_compute_scheduled_end', store=True)
    is_heavy = fields.Boolean('Ca nặng', compute='_compute_is_heavy', store=True)

    state = fields.Selection([
        ('draft', 'Đã đặt lịch'),
        ('confirmed', 'Đã xác nhận'),
        ('arrived', 'Đã đến – đang chờ'),
        ('in_chair', 'Đang điều trị'),
        ('done', 'Hoàn tất'),
        ('cancel', 'Đã hủy'),
        ('no_show', 'Không đến'),
    ], string='Trạng thái', default='draft', required=True, tracking=True, index=True, copy=False)
    checkin_time = fields.Datetime('Giờ check-in', copy=False, readonly=True)
    chair_time = fields.Datetime('Giờ lên ghế', copy=False, readonly=True)
    done_time = fields.Datetime('Giờ hoàn tất', copy=False, readonly=True)
    wait_minutes = fields.Integer('Thời gian chờ (phút)', compute='_compute_wait_minutes')
    cancel_reason = fields.Char('Lý do hủy / không đến', copy=False)

    # Bệnh án của lượt khám
    chief_complaint = fields.Text('Lý do khám / triệu chứng (S)', tracking=True)
    examination = fields.Text('Khám lâm sàng (O)', tracking=True)
    diagnosis_ids = fields.Many2many('dmag.dental.diagnosis', string='Chẩn đoán (ICD-10)', tracking=True)
    assessment = fields.Text('Đánh giá / chẩn đoán (A)', tracking=True)
    treatment_note = fields.Text('Xử trí / thủ thuật đã làm (P)', tracking=True)
    advice = fields.Text('Lời dặn', tracking=True)
    pain_score = fields.Integer('Điểm đau sau thủ thuật (0–10)', tracking=True,
                                help='Phụ tá hỏi bệnh nhân trước khi rời ghế.')
    record_state = fields.Selection([
        ('draft', 'Đang ghi'),
        ('signed', 'Đã ký – khóa'),
    ], string='Bệnh án', default='draft', required=True, tracking=True, copy=False)
    signed_by_id = fields.Many2one('dmag.dental.practitioner', string='Bác sĩ ký', readonly=True, copy=False)
    signed_at = fields.Datetime('Thời điểm ký', readonly=True, copy=False)

    chart_entry_ids = fields.One2many('dmag.dental.chart.entry', 'visit_id', string='Ghi nhận sơ đồ răng')
    procedure_ids = fields.One2many('dmag.dental.procedure', 'visit_id', string='Thủ thuật đã làm')
    procedure_count = fields.Integer(compute='_compute_procedure_count')
    sale_order_id = fields.Many2one('sale.order', string='Đơn dịch vụ lẻ', copy=False, readonly=True,
                                    help='Đơn cho các thủ thuật không nằm trong kế hoạch điều trị.')
    invoice_ids = fields.Many2many('account.move', string='Hóa đơn', copy=False, readonly=True)
    amount_due = fields.Monetary('Phải thu lượt này', compute='_compute_payment_status',
                                 currency_field='currency_id')
    currency_id = fields.Many2one(related='company_id.currency_id')
    payment_status = fields.Selection([
        ('none', 'Không phát sinh'),
        ('to_invoice', 'Chờ lập hóa đơn'),
        ('to_pay', 'Chờ thanh toán'),
        ('paid', 'Đã thanh toán'),
    ], string='Thanh toán', compute='_compute_payment_status')
    schedule_warning = fields.Char('Cảnh báo lịch', compute='_compute_schedule_warning')
    color = fields.Integer(related='doctor_id.color')

    # ------------------------------------------------------------------ compute
    @api.depends('patient_id')
    def _compute_is_new_patient(self):
        for visit in self:
            if not visit.patient_id:
                visit.is_new_patient = False
                continue
            domain = [('patient_id', '=', visit.patient_id.id), ('state', '=', 'done')]
            if visit.id:
                domain.append(('id', '!=', visit.id))
            visit.is_new_patient = not self.search_count(domain, limit=1)

    @api.depends('service_ids.dental_duration')
    def _compute_duration(self):
        for visit in self:
            visit.duration = sum(visit.service_ids.mapped('dental_duration')) or visit.duration or 30

    @api.depends('scheduled_start', 'duration')
    def _compute_scheduled_end(self):
        for visit in self:
            visit.scheduled_end = (visit.scheduled_start + timedelta(minutes=visit.duration or 30)
                                   if visit.scheduled_start else False)

    @api.depends('service_ids.dental_complexity')
    def _compute_is_heavy(self):
        for visit in self:
            visit.is_heavy = any(c == 'heavy' for c in visit.service_ids.mapped('dental_complexity'))

    @api.depends('checkin_time', 'chair_time', 'state')
    def _compute_wait_minutes(self):
        now = fields.Datetime.now()
        for visit in self:
            if not visit.checkin_time:
                visit.wait_minutes = 0
                continue
            end = visit.chair_time or (now if visit.state == 'arrived' else visit.checkin_time)
            visit.wait_minutes = max(int((end - visit.checkin_time).total_seconds() // 60), 0)

    @api.depends('procedure_ids')
    def _compute_procedure_count(self):
        for visit in self:
            visit.procedure_count = len(visit.procedure_ids)

    @api.depends('procedure_ids.amount', 'invoice_ids.payment_state', 'invoice_ids.state',
                 'invoice_ids.amount_residual')
    def _compute_payment_status(self):
        for visit in self:
            posted = visit.sudo().invoice_ids.filtered(lambda m: m.state == 'posted')
            to_invoice = visit._get_lines_to_invoice()
            residual = sum(posted.mapped('amount_residual'))
            visit.amount_due = residual + sum(
                line.price_reduce_taxinc * line.qty_to_invoice for line in to_invoice)
            if to_invoice:
                visit.payment_status = 'to_invoice'
            elif posted and residual:
                visit.payment_status = 'to_pay'
            elif posted:
                visit.payment_status = 'paid'
            else:
                visit.payment_status = 'none'

    @api.depends('chair_id', 'doctor_id', 'scheduled_start', 'scheduled_end', 'is_heavy', 'state')
    def _compute_schedule_warning(self):
        for visit in self:
            messages = visit._get_schedule_conflicts(soft=True)
            hours_issue = visit._dmag_opening_issue() if visit.state in ('draft', 'confirmed') else None
            if hours_issue:
                messages.append(_('Ngoài lịch làm việc: %s.', hours_issue))
            visit.schedule_warning = '; '.join(messages) or False

    # ------------------------------------------------------------------ CRUD
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                seq = self.env['ir.sequence']
                if vals.get('company_id'):
                    seq = seq.with_company(vals['company_id'])
                vals['name'] = seq.next_by_code('dmag.dental.visit') or '/'
        notes = [self._dmag_check_opening_vals(vals) for vals in vals_list]
        visits = super().create(vals_list)
        for visit, note in zip(visits, notes):
            if note:
                visit.message_post(body=note)
        visits._dmag_journey_event('booked')
        return visits

    def write(self, vals):
        if not is_workflow(self.env) and not is_director(self.env):
            self._check_write_allowed(vals)
        if CLINICAL_FIELDS & set(vals) and not self.env.context.get('dmag_record_amend'):
            locked = self.filtered(lambda v: v.record_state == 'signed')
            if locked:
                raise UserError(_(
                    'Bệnh án lượt khám %s đã ký và bị khóa. Dùng "Bổ sung bệnh án" '
                    '(quyền Quản lý) để sửa có ghi vết.', ', '.join(locked.mapped('name'))))
        notes = {}
        if {'scheduled_start', 'doctor_id'} & set(vals):
            for visit in self:
                note = visit._dmag_check_opening_vals(dict(vals), visit)
                if note:
                    notes[visit.id] = note
        res = super().write(vals)
        for visit in self.filtered(lambda v: v.id in notes):
            visit.message_post(body=notes[visit.id])
        return res

    # ------------------------------------------------------------------ lịch làm việc phòng khám
    def _dmag_opening_issue(self, info=None):
        """Lý do lịch hẹn nằm ngoài Lịch làm việc phòng khám (nghỉ lễ, thứ nghỉ, ngoài ca, bác sĩ nghỉ) hoặc None."""
        self.ensure_one()
        if not self.scheduled_start:
            return None
        info = info or self.env['dmag.clinic.schedule'].get_info(self.company_id)
        start = local_naive(self.env, self.scheduled_start)
        end = local_naive(self.env, self.scheduled_end or self.scheduled_start + timedelta(minutes=30))
        reason = info.check_interval(start, end)
        if not reason and self.doctor_id and not self.doctor_id.works_on(start.date(), info):
            reason = _('bác sĩ %(doc)s không làm việc %(wd)s', doc=self.doctor_id.name,
                       wd=WEEKDAY_SHORT[start.weekday()])
        return reason

    def _dmag_check_opening_vals(self, vals, visit=None):
        """Đặt / dời lịch hẹn TƯƠNG LAI ngoài Lịch làm việc phòng khám (kiểm tra TRƯỚC khi ghi): nhân viên bị chặn;
        Quản lý trở lên (hoặc chế độ "chỉ cảnh báo") được đặt – trả nội dung ghi chú cho chatter. Lịch đã qua (khách
        vãng lai, nhập bù) không kiểm tra."""
        if self.env.context.get('dmag_skip_opening_hours'):
            return None
        visit = visit or self.browse()
        start = vals.get('scheduled_start', visit.scheduled_start)
        state = vals.get('state', visit.state or 'draft')
        if not start or state not in ('draft', 'confirmed'):
            return None
        start = fields.Datetime.to_datetime(start)
        if start <= fields.Datetime.now():
            return None
        services = visit.service_ids
        if 'service_ids' in vals:
            services = self.env['product.product'].browse(
                self.new({'service_ids': vals['service_ids']}).service_ids.ids)
        duration = vals.get('duration') or sum(services.mapped('dental_duration')) or visit.duration or 30
        company = self.env['res.company'].browse(vals.get('company_id')) if vals.get('company_id') else \
            (visit.company_id or self.env.company)
        doctor_id = vals.get('doctor_id', visit.doctor_id.id)
        doctor = self.env['dmag.dental.practitioner'].browse(doctor_id) if doctor_id else None
        info = self.env['dmag.clinic.schedule'].get_info(company)
        local_start = local_naive(self.env, start)
        reason = info.check_interval(local_start, local_start + timedelta(minutes=duration))
        if not reason and doctor and not doctor.works_on(local_start.date(), info):
            reason = _('bác sĩ %(doc)s không làm việc %(wd)s', doc=doctor.name, wd=WEEKDAY_SHORT[local_start.weekday()])
        if not reason:
            return None
        if info.enforce == 'block' and not is_manager(self.env):
            raise UserError(_('Không đặt được lịch hẹn: %(reason)s.\nChọn giờ trong lịch làm việc của phòng khám, hoặc '
                              'nhờ Quản lý / Giám đốc đặt ngoài giờ.', reason=reason))
        return _('Lịch hẹn ngoài lịch làm việc phòng khám (%(reason)s) – đặt bởi %(user)s.',
                 reason=reason, user=self.env.user.name)

    def _check_write_allowed(self, vals):
        """Tạo được – không sửa: chặn sửa lượt khám đã có hiệu lực."""
        fields_changed = set(vals)
        for visit in self:
            if visit.state in ('done', 'cancel', 'no_show'):
                if visit.state == 'done' and fields_changed <= RECORD_EDITABLE and visit.record_state == 'draft':
                    continue
                raise AccessError(_('Lượt khám %s đã kết thúc – chỉ Giám đốc / Quản lý cấp cao được sửa.', visit.name))
            if visit.state in ('arrived', 'in_chair') and fields_changed & LOCK_AFTER_ARRIVAL:
                raise AccessError(_('Bệnh nhân đã check-in – không đổi được người bệnh của lượt khám %s.', visit.name))

    def unlink(self):
        for visit in self:
            if visit.state not in ('draft', 'cancel', 'no_show') or visit.procedure_ids:
                raise UserError(_('Không xóa được lượt khám %s đã phát sinh khám / thủ thuật. Hãy hủy lịch.', visit.name))
        if not is_director(self.env):
            check_director(self.env, _('Chỉ Giám đốc / Quản lý cấp cao được xóa lịch hẹn. Hãy dùng "Hủy lịch".'))
        return super().unlink()

    def _workflow_write(self, vals):
        return self.with_context(dmag_workflow=True).write(vals)

    # ------------------------------------------------------------------ constraints
    def _get_schedule_conflicts(self, soft=False):
        """Xung đột lịch. soft=False: lỗi chặn; soft=True: cảnh báo hiển thị."""
        self.ensure_one()
        if self.state not in ACTIVE_STATES or not self.scheduled_start or not self.scheduled_end:
            return []
        overlap = [
            ('id', '!=', self.id or 0),
            ('state', 'in', ACTIVE_STATES),
            ('scheduled_start', '<', self.scheduled_end),
            ('scheduled_end', '>', self.scheduled_start),
        ]
        messages = []
        if self.chair_id and not soft:
            other = self.search(overlap + [('chair_id', '=', self.chair_id.id)], limit=1)
            if other:
                messages.append(_('%(chair)s đã có lịch %(visit)s (%(patient)s) trùng giờ.',
                                  chair=self.chair_id.name, visit=other.name, patient=other.patient_id.name))
        if self.doctor_id:
            others = self.search(overlap + [('doctor_id', '=', self.doctor_id.id)])
            if not soft and self.is_heavy and others.filtered('is_heavy'):
                messages.append(_('Bác sĩ %s đã có ca nặng khác trùng giờ – không xếp chồng 2 ca nặng.',
                                  self.doctor_id.name))
            elif soft and others:
                messages.append(_('Bác sĩ %(doc)s đang có %(n)s lịch khác trùng giờ.',
                                  doc=self.doctor_id.name, n=len(others)))
        return messages

    @api.constrains('chair_id', 'doctor_id', 'scheduled_start', 'duration', 'state', 'service_ids')
    def _check_schedule(self):
        for visit in self:
            conflicts = visit._get_schedule_conflicts()
            if conflicts:
                raise ValidationError('\n'.join(conflicts))

    @api.constrains('doctor_id', 'service_ids')
    def _check_doctor_scope(self):
        for visit in self.filtered(lambda v: v.doctor_id and v.service_ids and v.state in ACTIVE_STATES):
            visit.doctor_id.check_can_perform(visit.service_ids)

    @api.constrains('pain_score')
    def _check_pain_score(self):
        for visit in self:
            if not 0 <= visit.pain_score <= 10:
                raise ValidationError(_('Điểm đau phải từ 0 đến 10.'))

    # ------------------------------------------------------------------ journey
    def _dmag_journey_event(self, event):
        """Điểm móc cho hành trình khách hàng (Zalo ZNS, CSKH…).

        event: booked, confirmed, arrived, in_chair, done, cancelled, no_show, signed.
        Các module hành trình/loyalty kế thừa hàm này.
        """
        return True

    def action_confirm(self):
        self.filtered(lambda v: v.state == 'draft')._workflow_write({'state': 'confirmed'})
        self._dmag_journey_event('confirmed')
        return True

    def action_check_in(self):
        for visit in self:
            if visit.state not in ('draft', 'confirmed'):
                raise UserError(_('Lượt khám %s không ở trạng thái chờ đến.', visit.name))
        self._workflow_write({'state': 'arrived', 'checkin_time': fields.Datetime.now()})
        self._dmag_journey_event('arrived')
        return True

    def action_start(self, chair_id=False):
        for visit in self:
            if visit.state not in ('confirmed', 'arrived'):
                raise UserError(_('Bệnh nhân cần check-in trước khi lên ghế.'))
            vals = {'state': 'in_chair', 'chair_time': fields.Datetime.now()}
            if not visit.checkin_time:
                vals['checkin_time'] = vals['chair_time']
            if chair_id:
                vals['chair_id'] = chair_id
            if not (chair_id or visit.chair_id):
                raise UserError(_('Chọn ghế cho bệnh nhân %s.', visit.patient_id.name))
            if not visit.doctor_id:
                practitioner = self._current_practitioner()
                if practitioner.role == 'doctor':
                    vals['doctor_id'] = practitioner.id
            visit._workflow_write(vals)
        self._dmag_journey_event('in_chair')
        return True

    def action_done(self):
        for visit in self:
            if visit.state != 'in_chair':
                raise UserError(_('Chỉ hoàn tất được lượt khám đang điều trị.'))
        self._workflow_write({'state': 'done', 'done_time': fields.Datetime.now()})
        self._dmag_journey_event('done')
        return True

    def action_cancel(self):
        self.filtered(lambda v: v.state in ACTIVE_STATES)._workflow_write({'state': 'cancel'})
        self._dmag_journey_event('cancelled')
        return True

    def action_no_show(self):
        self.filtered(lambda v: v.state in ('draft', 'confirmed'))._workflow_write({'state': 'no_show'})
        self._dmag_journey_event('no_show')
        return True

    def action_reset(self):
        check_director(self.env, _('Chỉ Giám đốc / Quản lý cấp cao được khôi phục lịch đã hủy.'))
        self.filtered(lambda v: v.state in ('cancel', 'no_show'))._workflow_write({'state': 'draft', 'cancel_reason': False})
        return True

    # ------------------------------------------------------------------ medical record
    @api.model
    def _current_practitioner(self):
        return self.env['dmag.dental.practitioner'].search([
            ('user_id', '=', self.env.uid), ('company_id', 'in', self.env.companies.ids)], limit=1)

    def action_sign_record(self):
        """Bác sĩ ký bệnh án lượt khám → khóa. Chữ ký số (MySign) gắn qua module dmag_esign."""
        practitioner = self._current_practitioner()
        if not practitioner or practitioner.role != 'doctor':
            raise UserError(_('Chỉ bác sĩ (có hồ sơ nhân sự lâm sàng gắn tài khoản) mới được ký bệnh án.'))
        for visit in self:
            if visit.record_state == 'signed':
                continue
            if not (visit.chief_complaint or visit.examination or visit.assessment or visit.procedure_ids):
                raise UserError(_('Bệnh án %s chưa có nội dung để ký.', visit.name))
            visit._workflow_write({
                'record_state': 'signed',
                'signed_by_id': practitioner.id,
                'signed_at': fields.Datetime.now(),
            })
            visit._dmag_esign_request()
        self._dmag_journey_event('signed')
        return True

    def _dmag_esign_request(self):
        """Điểm móc ký số từ xa (Viettel MySign) – cài module dmag_esign để kích hoạt."""
        return True

    def action_amend_record(self):
        check_director(self.env, _('Chỉ Giám đốc / Quản lý cấp cao được mở bổ sung bệnh án đã ký.'))
        for visit in self:
            visit.message_post(body=_('Mở bổ sung bệnh án đã ký bởi %s.', self.env.user.name))
        self.with_context(dmag_record_amend=True, dmag_workflow=True).write({'record_state': 'draft'})
        return True

    # ------------------------------------------------------------------ billing
    def _get_lines_to_invoice(self):
        self.ensure_one()
        lines = self.sudo().procedure_ids.mapped('sale_line_id')
        return lines.filtered(lambda l: l.qty_to_invoice > 0 and l.state == 'sale')

    def _get_or_create_sale_order(self):
        self.ensure_one()
        if not self.sale_order_id:
            so = self.env['sale.order'].sudo().create({
                'partner_id': self.patient_id.id,
                'company_id': self.company_id.id,
                'dental_visit_id': self.id,
                'origin': self.name,
            })
            self._workflow_write({'sale_order_id': so.id})
        return self.sale_order_id.sudo()

    def _create_and_post_invoices(self):
        """Lập + ghi sổ hóa đơn phần đã làm (thu theo tiến độ). Chạy quyền hệ thống:
        lễ tân tạo được chứng từ nhưng không sửa được hóa đơn."""
        self.ensure_one()
        lines = self._get_lines_to_invoice()
        if not lines:
            return self.env['account.move']
        orders = lines.mapped('order_id').sudo()
        moves = orders._create_invoices()
        moves.action_post()
        self._workflow_write({'invoice_ids': [(4, m.id) for m in moves]})
        for move in moves:
            self.message_post(body=_('Lập hóa đơn %(name)s – %(amount)s', name=move.name,
                                     amount=move.amount_total))
        self._dmag_on_invoices_posted(moves)
        return moves

    def _dmag_on_invoices_posted(self, moves):
        """Điểm móc phát hành hóa đơn điện tử (Viettel S-Invoice / VNPT của Bizapps)."""
        return True

    def action_create_invoice(self):
        self.ensure_one()
        moves = self._create_and_post_invoices()
        if not moves:
            raise UserError(_('Không còn thủ thuật nào chờ lập hóa đơn trong lượt khám này.'))
        return True

    def _get_open_invoices(self):
        self.ensure_one()
        return self.sudo().invoice_ids.filtered(
            lambda m: m.state == 'posted' and m.payment_state not in ('paid', 'in_payment', 'reversed'))

    def register_payment(self, method, amount=False, reference=False):
        """Ghi nhận thu tiền tại quầy (tiền mặt / chuyển khoản / thẻ).

        Tạo chứng từ thanh toán bằng quyền hệ thống, đối trừ vào hóa đơn còn nợ.
        Nhân viên không sửa / hủy được – sai sót do Giám đốc xử lý.
        """
        self.ensure_one()
        if self.payment_status == 'to_invoice':
            self._create_and_post_invoices()
        invoices = self._get_open_invoices()
        if not invoices:
            raise UserError(_('Lượt khám %s không còn khoản phải thu.', self.name))
        journal = self._get_payment_journal(method)
        residual = sum(invoices.mapped('amount_residual'))
        amount = amount or residual
        if amount <= 0 or amount > residual + 0.5:
            raise UserError(_('Số tiền thu không hợp lệ (còn phải thu %s).', residual))
        wizard = self.env['account.payment.register'].sudo().with_context(
            active_model='account.move', active_ids=invoices.ids).create({
                'journal_id': journal.id,
                'amount': amount,
                'payment_date': fields.Date.context_today(self),
                'communication': reference or self.name,
                'group_payment': True,
            })
        payments = wizard._create_payments()
        self.message_post(body=_('Thu %(amount)s – %(method)s – người thu: %(user)s',
                                 amount=amount, method=dict(PAYMENT_METHODS)[method], user=self.env.user.name))
        self._dmag_journey_event('paid')
        return payments.ids

    def _get_payment_journal(self, method):
        Journal = self.env['account.journal'].sudo()
        jtype = 'cash' if method == 'cash' else 'bank'
        journal = Journal.search([('company_id', '=', self.company_id.id), ('type', '=', jtype)], limit=1)
        if not journal:
            raise UserError(_('Chưa cấu hình sổ nhật ký %s cho phòng khám.', jtype))
        return journal

    # ------------------------------------------------------------------ actions UI
    def action_open_procedures(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Thủ thuật – %s', self.name),
            'res_model': 'dmag.dental.procedure',
            'view_mode': 'tree,form',
            'domain': [('visit_id', '=', self.id)],
            'context': {'default_visit_id': self.id},
        }

    # ------------------------------------------------------------------ data for workspace
    def _workspace_card(self):
        self.ensure_one()
        return {
            'id': self.id,
            'name': self.name,
            'state': self.state,
            'patient_id': self.patient_id.id,
            'patient': self.patient_id.name,
            'patient_code': self.patient_id.patient_code or '',
            'phone': self.patient_id.mobile or self.patient_id.phone or '',
            'age': self.patient_id.age,
            'is_new': self.is_new_patient,
            'alerts': [{'name': a.name, 'severity': a.severity} for a in self.patient_id.patient_alert_ids],
            'doctor_id': self.doctor_id.id,
            'doctor': self.doctor_id.name or '',
            'chair_id': self.chair_id.id,
            'chair': self.chair_id.name or '',
            'services': self.service_ids.mapped('name'),
            'reason': self.reason or '',
            'start': fields.Datetime.to_string(self.scheduled_start),
            'end': fields.Datetime.to_string(self.scheduled_end),
            'checkin': fields.Datetime.to_string(self.checkin_time) if self.checkin_time else False,
            'chair_time': fields.Datetime.to_string(self.chair_time) if self.chair_time else False,
            'wait': self.wait_minutes,
            'payment_status': self.payment_status,
            'amount_due': self.amount_due,
            'record_state': self.record_state,
            'warning': self.schedule_warning or '',
        }

    @api.model
    def get_frontdesk_board(self, date=False):
        """Bảng điều phối lễ tân: lịch trong ngày + trạng thái ghế."""
        day = fields.Date.from_string(date) if date else fields.Date.context_today(self)
        start = fields.Datetime.to_datetime(day)
        tz_offset = self._tz_offset()
        start -= tz_offset
        end = start + timedelta(days=1)
        visits = self.search([
            ('company_id', 'in', self.env.companies.ids),
            '|', '&', ('scheduled_start', '>=', start), ('scheduled_start', '<', end),
            ('state', 'in', ('arrived', 'in_chair')),
        ], order='scheduled_start asc')
        chairs = self.env['dmag.dental.chair'].search([('company_id', 'in', self.env.companies.ids)])
        busy = {v.chair_id.id: v for v in visits if v.state == 'in_chair' and v.chair_id}
        return {
            'date': fields.Date.to_string(day),
            'visits': [v._workspace_card() for v in visits],
            'chairs': [{
                'id': c.id, 'name': c.name, 'room': c.room or '',
                'visit': busy[c.id]._workspace_card() if c.id in busy else False,
            } for c in chairs],
            'doctors': [{'id': d.id, 'name': d.name, 'color': d.color}
                        for d in self.env['dmag.dental.practitioner'].search([('role', '=', 'doctor')])],
            'currency': self.env.company.currency_id.symbol,
        }

    @api.model
    def _tz_offset(self):
        import pytz
        tz = pytz.timezone(self.env.user.tz or 'Asia/Ho_Chi_Minh')
        now = fields.Datetime.now()
        return tz.utcoffset(now)

    @api.model
    def get_doctor_desk(self, date=False):
        """Bàn làm việc bác sĩ: bệnh nhân của tôi hôm nay."""
        board = self.get_frontdesk_board(date)
        practitioner = self._current_practitioner()
        mine = [v for v in board['visits'] if not practitioner or v['doctor_id'] in (practitioner.id, False)]
        return {
            'practitioner': {'id': practitioner.id, 'name': practitioner.name,
                             'title': practitioner.title or ''} if practitioner else False,
            'visits': mine,
            'all_visits': board['visits'],
        }

    def get_visit_workspace(self):
        """Toàn bộ dữ liệu một lượt khám cho màn hình bác sĩ (1 lần gọi)."""
        self.ensure_one()
        patient = self.patient_id
        history = self.search([('patient_id', '=', patient.id), ('id', '!=', self.id),
                               ('state', '=', 'done')], limit=10)
        plans = self.env['dmag.treatment.plan'].search([('patient_id', '=', patient.id),
                                                       ('state', '!=', 'cancel')])
        return {
            'visit': dict(self._workspace_card(),
                          chief_complaint=self.chief_complaint or '',
                          examination=self.examination or '',
                          assessment=self.assessment or '',
                          treatment_note=self.treatment_note or '',
                          advice=self.advice or '',
                          pain_score=self.pain_score,
                          diagnoses=[{'id': d.id, 'name': d.display_name} for d in self.diagnosis_ids],
                          signed_by=self.signed_by_id.name or '',
                          signed_at=fields.Datetime.to_string(self.signed_at) if self.signed_at else False),
            'patient': {
                'id': patient.id, 'name': patient.name, 'code': patient.patient_code or '',
                'age': patient.age, 'gender': patient.gender or '', 'phone': patient.mobile or '',
                'allergy': patient.allergy or '', 'medical_history': patient.medical_history or '',
                'medication': patient.current_medication or '',
                'alerts': [{'name': a.name, 'severity': a.severity} for a in patient.patient_alert_ids],
                'primary_dentition': bool(patient.age and patient.age < 13),
            },
            'chart': self.env['dmag.dental.chart.entry'].get_patient_chart(patient.id),
            'procedures': [p._workspace_dict() for p in self.procedure_ids],
            'plans': [p._workspace_dict() for p in plans],
            'history': [{
                'id': h.id, 'name': h.name, 'date': fields.Datetime.to_string(h.scheduled_start),
                'doctor': h.doctor_id.name or '', 'assessment': h.assessment or '',
                'procedures': h.procedure_ids.mapped('display_name'),
            } for h in history],
        }

    def save_record_from_workspace(self, values):
        self.ensure_one()
        allowed = {'chief_complaint', 'examination', 'assessment', 'treatment_note', 'advice', 'pain_score'}
        vals = {k: v for k, v in values.items() if k in allowed}
        if 'diagnosis_ids' in values:
            vals['diagnosis_ids'] = [(6, 0, values['diagnosis_ids'])]
        self.write(vals)
        return True
