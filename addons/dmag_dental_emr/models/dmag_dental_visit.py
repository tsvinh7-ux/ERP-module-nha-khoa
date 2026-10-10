from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.dmag_dental_base.models.dmag_access import is_director, is_workflow

# Trường bệnh án RHM (16/BV1) bổ sung – khóa sau khi bác sĩ ký, như CLINICAL_FIELDS của lõi
EMR_FIELDS = {
    'referral_source', 'referral_facility', 'referral_diagnosis',
    'present_illness', 'personal_history', 'family_history',
    'pulse', 'temperature', 'bp_systolic', 'bp_diastolic', 'respiratory_rate', 'weight', 'height',
    'general_exam', 'organ_exam',
    'exam_extraoral', 'exam_intraoral', 'exam_occlusion', 'exam_soft_tissue', 'exam_periodontal',
    'paraclinical_summary', 'primary_diagnosis_id',
    'final_diagnosis_id', 'final_diagnosis', 'treatment_direction', 'treatment_from', 'treatment_to',
    'summary_course', 'summary_method', 'summary_status_end', 'summary_next_direction',
}
# Khóa giao diện bác sĩ (workspace) được phép lưu – liệt kê trong README
WORKSPACE_EMR_KEYS = EMR_FIELDS - {'primary_diagnosis_id', 'final_diagnosis_id'}
# Trường nghiệp vụ hồ sơ (không phải nội dung lâm sàng) được ghi tiếp sau khi ký
RECORD_ADMIN_FIELDS = {'outpatient_number', 'archive_number'}

REFERRAL_SOURCES = [
    ('self', 'Tự đến'),
    ('facility', 'Cơ quan y tế giới thiệu'),
    ('other', 'Khác'),
]


class DmagDentalVisit(models.Model):
    _inherit = 'dmag.dental.visit'

    # Số hồ sơ
    outpatient_number = fields.Char('Số ngoại trú', copy=False, readonly=True, index=True,
                                    help='Cấp tự động khi bác sĩ ký bệnh án.')
    archive_number = fields.Char('Số lưu trữ', copy=False, tracking=True)

    # I. Hành chính – nơi giới thiệu
    referral_source = fields.Selection(REFERRAL_SOURCES, string='Nơi giới thiệu', default='self', tracking=True)
    referral_facility = fields.Char('Tên cơ sở giới thiệu', tracking=True)
    referral_diagnosis = fields.Text('Chẩn đoán của nơi giới thiệu', tracking=True)

    # III. Hỏi bệnh
    present_illness = fields.Text('Quá trình bệnh lý (bệnh sử)', tracking=True)
    personal_history = fields.Text('Tiền sử bản thân', tracking=True,
                                   compute='_compute_history_defaults', store=True, readonly=False)
    family_history = fields.Text('Tiền sử gia đình', tracking=True,
                                 compute='_compute_history_defaults', store=True, readonly=False)

    # IV. Khám bệnh – toàn thân
    pulse = fields.Integer('Mạch (lần/phút)', tracking=True)
    temperature = fields.Float('Nhiệt độ (°C)', digits=(4, 1), tracking=True)
    bp_systolic = fields.Integer('Huyết áp tâm thu (mmHg)', tracking=True)
    bp_diastolic = fields.Integer('Huyết áp tâm trương (mmHg)', tracking=True)
    respiratory_rate = fields.Integer('Nhịp thở (lần/phút)', tracking=True)
    weight = fields.Float('Cân nặng (kg)', digits=(5, 1), tracking=True)
    height = fields.Float('Chiều cao (cm)', digits=(5, 1), tracking=True)
    bmi = fields.Float('Chỉ số khối cơ thể', digits=(4, 1), compute='_compute_bmi')
    general_exam = fields.Text('Toàn thân', tracking=True)
    organ_exam = fields.Text('Các bộ phận', tracking=True)

    # IV. Khám chuyên khoa Răng Hàm Mặt
    exam_extraoral = fields.Text('Khám ngoài mặt', tracking=True)
    exam_intraoral = fields.Text('Khám trong miệng', tracking=True)
    exam_occlusion = fields.Text('Khớp cắn', tracking=True)
    exam_soft_tissue = fields.Text('Mô mềm', tracking=True)
    exam_periodontal = fields.Text('Nha chu', tracking=True)

    # V. Cận lâm sàng
    paraclinical_summary = fields.Text('Tóm tắt kết quả cận lâm sàng (X-quang, xét nghiệm)', tracking=True)

    # VI. Chẩn đoán ban đầu
    primary_diagnosis_id = fields.Many2one('dmag.dental.diagnosis', string='Bệnh chính (ICD-10)', tracking=True)
    secondary_diagnosis_ids = fields.Many2many('dmag.dental.diagnosis', string='Bệnh kèm theo (ICD-10)',
                                               compute='_compute_secondary_diagnosis_ids')

    # VIII–IX. Kết thúc điều trị
    final_diagnosis_id = fields.Many2one('dmag.dental.diagnosis', string='Chẩn đoán khi kết thúc (ICD-10)',
                                         tracking=True)
    final_diagnosis = fields.Text('Chẩn đoán khi kết thúc – mô tả', tracking=True)
    treatment_direction = fields.Text('Hướng điều trị', tracking=True)
    treatment_from = fields.Date('Điều trị ngoại trú từ ngày', tracking=True)
    treatment_to = fields.Date('Điều trị ngoại trú đến ngày', tracking=True)

    # Tổng kết bệnh án
    summary_course = fields.Text('Quá trình bệnh lý và diễn biến lâm sàng', tracking=True)
    summary_method = fields.Text('Phương pháp điều trị', tracking=True)
    summary_status_end = fields.Text('Tình trạng người bệnh khi kết thúc điều trị', tracking=True)
    summary_next_direction = fields.Text('Hướng điều trị và các chế độ tiếp theo', tracking=True)

    # Lưu trữ / đồng ý
    retention_until = fields.Date('Lưu trữ đến ngày', compute='_compute_retention_until')
    consent_ids = fields.One2many('dmag.consent', 'visit_id', string='Cam kết / đồng ý')
    consent_count = fields.Integer(compute='_compute_consent_count', string='Số phiếu đồng ý')
    identity_exemption_reason = fields.Char(related='patient_id.identity_exemption_reason')
    patient_citizen_id = fields.Char(related='patient_id.citizen_id', string='Số định danh cá nhân')

    # ------------------------------------------------------------------ compute
    @api.depends('patient_id')
    def _compute_history_defaults(self):
        for visit in self:
            patient = visit.patient_id
            if not visit.personal_history and patient:
                parts = []
                if patient.medical_history:
                    parts.append(_('Toàn thân: %s', patient.medical_history))
                if patient.dental_history:
                    parts.append(_('Răng miệng: %s', patient.dental_history))
                if patient.allergy:
                    parts.append(_('Dị ứng: %s', patient.allergy))
                if patient.current_medication:
                    parts.append(_('Thuốc đang dùng: %s', patient.current_medication))
                visit.personal_history = '\n'.join(parts) or False
            if not visit.family_history and patient:
                visit.family_history = patient.family_history or False

    @api.depends('weight', 'height')
    def _compute_bmi(self):
        for visit in self:
            visit.bmi = visit.weight / ((visit.height / 100.0) ** 2) if visit.weight and visit.height else 0.0

    @api.depends('diagnosis_ids', 'primary_diagnosis_id')
    def _compute_secondary_diagnosis_ids(self):
        for visit in self:
            visit.secondary_diagnosis_ids = visit.diagnosis_ids - visit.primary_diagnosis_id

    @api.depends('done_time', 'signed_at', 'scheduled_start', 'treatment_to', 'company_id.dmag_record_retention_years')
    def _compute_retention_until(self):
        for visit in self:
            base = visit.treatment_to or (visit.done_time or visit.signed_at or visit.scheduled_start)
            if not base:
                visit.retention_until = False
                continue
            base = fields.Date.to_date(base)
            years = visit.company_id.dmag_record_retention_years or 10
            visit.retention_until = base + relativedelta(years=years)

    def _compute_consent_count(self):
        for visit in self:
            visit.consent_count = len(visit.consent_ids)

    @api.onchange('diagnosis_ids')
    def _onchange_diagnosis_primary(self):
        if self.diagnosis_ids and self.primary_diagnosis_id not in self.diagnosis_ids:
            self.primary_diagnosis_id = self.diagnosis_ids[:1]

    @api.onchange('primary_diagnosis_id')
    def _onchange_primary_diagnosis(self):
        if self.primary_diagnosis_id and self.primary_diagnosis_id not in self.diagnosis_ids:
            self.diagnosis_ids = [(4, self.primary_diagnosis_id.id)]

    # ------------------------------------------------------------------ lock
    def write(self, vals):
        if EMR_FIELDS & set(vals) and not self.env.context.get('dmag_record_amend'):
            locked = self.filtered(lambda v: v.record_state == 'signed')
            if locked:
                raise UserError(_(
                    'Bệnh án lượt khám %s đã ký và bị khóa. Dùng "Bổ sung bệnh án" '
                    '(quyền Giám đốc / Quản lý cấp cao) để sửa có ghi vết.', ', '.join(locked.mapped('name'))))
        return super().write(vals)

    def _check_write_allowed(self, vals):
        """Bác sĩ ghi tiếp các mục bệnh án RHM khi bệnh án chưa ký, kể cả sau khi lượt khám hoàn tất."""
        extra = (EMR_FIELDS | RECORD_ADMIN_FIELDS) & set(vals)
        if extra:
            for visit in self:
                if visit.state in ('cancel', 'no_show'):
                    raise AccessError(_('Lượt khám %s đã hủy / không đến – không ghi bệnh án.', visit.name))
                if visit.state == 'done' and visit.record_state == 'signed' and extra - RECORD_ADMIN_FIELDS:
                    raise AccessError(_('Lượt khám %s đã kết thúc và bệnh án đã ký.', visit.name))
            vals = {k: v for k, v in vals.items() if k not in extra}
            if not vals:
                return None
        return super()._check_write_allowed(vals)

    # ------------------------------------------------------------------ retention
    def _emr_has_record(self):
        self.ensure_one()
        return bool(self.state in ('in_chair', 'done') or self.record_state == 'signed' or self.procedure_ids
                    or self.chief_complaint or self.examination or self.diagnosis_ids
                    or self.present_illness or self.exam_intraoral)

    def unlink(self):
        today = fields.Date.context_today(self)
        for visit in self:
            if visit._emr_has_record() and visit.retention_until and visit.retention_until > today:
                raise UserError(_(
                    'Bệnh án lượt khám %(name)s phải được lưu trữ đến ngày %(date)s '
                    '(%(years)s năm theo cấu hình lưu trữ hồ sơ bệnh án – Thông tư 33/2025/TT-BYT). '
                    'Không ai, kể cả Giám đốc, được xóa trước thời hạn.',
                    name=visit.name, date=visit.retention_until.strftime('%d/%m/%Y'),
                    years=visit.company_id.dmag_record_retention_years or 10))
        return super().unlink()

    # ------------------------------------------------------------------ signing
    def _emr_missing_for_signature(self):
        """Danh sách mục bắt buộc còn thiếu trước khi ký (tiếng Việt)."""
        self.ensure_one()
        missing = []
        patient = self.patient_id
        if not (patient.citizen_id or patient.identity_exemption_reason):
            missing.append(_('Số định danh cá nhân / căn cước của người bệnh (TT 13/2025/TT-BYT) – '
                             'hoặc ghi rõ "Lý do chưa có số định danh" trong hồ sơ người bệnh'))
        if not (self.chief_complaint or self.reason):
            missing.append(_('Lý do đến khám'))
        if not (self.diagnosis_ids or self.primary_diagnosis_id):
            missing.append(_('Chẩn đoán có mã ICD-10 (ít nhất một bệnh chính)'))
        if not (self.examination or self.general_exam or self.exam_extraoral or self.exam_intraoral
                or self.exam_periodontal or self.exam_soft_tissue or self.exam_occlusion):
            missing.append(_('Kết quả khám bệnh (toàn thân hoặc khám chuyên khoa Răng Hàm Mặt)'))
        return missing

    def action_sign_record(self):
        errors = []
        for visit in self.filtered(lambda v: v.record_state == 'draft'):
            missing = visit._emr_missing_for_signature()
            if missing:
                errors.append(_('Bệnh án %(name)s – %(patient)s còn thiếu:\n%(items)s',
                                name=visit.name, patient=visit.patient_id.name,
                                items='\n'.join('  • ' + m for m in missing)))
        if errors:
            raise UserError(_('Chưa ký được bệnh án.\n\n%s', '\n\n'.join(errors)))
        to_sign = self.filtered(lambda v: v.record_state == 'draft')
        for visit in to_sign:
            vals = {}
            if not visit.primary_diagnosis_id:
                vals['primary_diagnosis_id'] = visit.diagnosis_ids[:1].id
            elif visit.primary_diagnosis_id not in visit.diagnosis_ids:
                vals['diagnosis_ids'] = [(4, visit.primary_diagnosis_id.id)]
            if not visit.treatment_from:
                vals['treatment_from'] = fields.Date.to_date(visit.chair_time or visit.scheduled_start)
            if vals:
                visit._workflow_write(vals)
        res = super().action_sign_record()
        for visit in to_sign.filtered(lambda v: v.record_state == 'signed' and not v.outpatient_number):
            seq = self.env['ir.sequence'].with_company(visit.company_id)
            visit._workflow_write({'outpatient_number': seq.next_by_code('dmag.outpatient.record') or '/'})
        return res

    # ------------------------------------------------------------------ reports helpers
    def _emr_period_visits(self):
        """Các lượt khám thuộc cùng đợt điều trị (phiếu điều trị)."""
        self.ensure_one()
        domain = [('patient_id', '=', self.patient_id.id), ('state', 'in', ('in_chair', 'done'))]
        if self.treatment_plan_id:
            domain.append(('treatment_plan_id', '=', self.treatment_plan_id.id))
        elif self.treatment_from:
            start = fields.Datetime.to_datetime(self.treatment_from)
            end = fields.Datetime.to_datetime(self.treatment_to or fields.Date.context_today(self)) \
                + relativedelta(days=1)
            domain += [('scheduled_start', '>=', start), ('scheduled_start', '<', end)]
        else:
            domain = [('id', '=', self.id)]
        visits = self.search(domain, order='scheduled_start asc, id asc')
        return visits | self if self not in visits else visits

    def _emr_tooth_chart(self):
        """Dữ liệu sơ đồ răng FDI cho bản in: hàng răng + chú giải tình trạng."""
        self.ensure_one()
        Entry = self.env['dmag.dental.chart.entry'].with_context(active_test=False)
        entries = Entry.search([
            ('patient_id', '=', self.patient_id.id),
            '|', ('active', '=', True), ('visit_id', '=', self.id),
        ], order='date asc, id asc')
        if self.signed_at:
            entries = entries.filtered(lambda e: e.date <= self.signed_at)
        legend = {}
        by_tooth = {}
        for entry in entries:
            cond = entry.condition_id
            if cond.id not in legend:
                numbered = sum(1 for lg in legend.values() if lg['symbol'] != 'cross')
                legend[cond.id] = {'key': 'X' if cond.symbol == 'cross' else str(numbered + 1), 'name': cond.name,
                                   'color': cond.color or '#178BEC', 'symbol': cond.symbol,
                                   'category': cond.category}
            mark = dict(legend[cond.id], layer=entry.layer,
                        surfaces=', '.join(entry.surface_ids.mapped('code')))
            by_tooth.setdefault(entry.tooth_id.code, []).append(mark)
        rows = {
            'upper_permanent': [str(c) for c in list(range(18, 10, -1)) + list(range(21, 29))],
            'lower_permanent': [str(c) for c in list(range(48, 40, -1)) + list(range(31, 39))],
            'upper_primary': [str(c) for c in list(range(55, 50, -1)) + list(range(61, 66))],
            'lower_primary': [str(c) for c in list(range(85, 80, -1)) + list(range(71, 76))],
        }
        return {'rows': rows, 'teeth': by_tooth, 'legend': list(legend.values()), 'entries': entries}

    @api.model
    def _emr_fmt_dt(self, value, with_time=True):
        """Ngày giờ theo múi giờ người dùng, dạng dd/mm/yyyy hh:mm."""
        if not value:
            return ''
        if isinstance(value, str):
            value = fields.Datetime.to_datetime(value)
        if hasattr(value, 'hour'):
            local = fields.Datetime.context_timestamp(self, value)
            return local.strftime('%H giờ %M phút, ngày %d/%m/%Y') if with_time else local.strftime('%d/%m/%Y')
        return value.strftime('%d/%m/%Y')

    # ------------------------------------------------------------------ actions
    def action_open_consents(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Cam kết / đồng ý – %s', self.name),
            'res_model': 'dmag.consent',
            'view_mode': 'tree,form',
            'domain': [('visit_id', '=', self.id)],
            'context': {'default_visit_id': self.id, 'default_patient_id': self.patient_id.id,
                        'default_plan_id': self.treatment_plan_id.id},
        }

    # ------------------------------------------------------------------ workspace
    def _emr_workspace_dict(self):
        self.ensure_one()
        data = {key: (self[key] or ('' if self._fields[key].type in ('text', 'char') else self[key]))
                for key in sorted(WORKSPACE_EMR_KEYS)}
        for key in ('treatment_from', 'treatment_to'):
            data[key] = fields.Date.to_string(self[key]) if self[key] else False
        data.update({
            'referral_source': self.referral_source or '',
            'bmi': round(self.bmi, 1),
            'primary_diagnosis_id': self.primary_diagnosis_id.id or False,
            'primary_diagnosis': self.primary_diagnosis_id.display_name or '',
            'secondary_diagnoses': [{'id': d.id, 'name': d.display_name} for d in self.secondary_diagnosis_ids],
            'final_diagnosis_id': self.final_diagnosis_id.id or False,
            'final_diagnosis_name': self.final_diagnosis_id.display_name or '',
            'outpatient_number': self.outpatient_number or '',
            'archive_number': self.archive_number or '',
            'vitals': {
                'pulse': self.pulse, 'temperature': self.temperature,
                'bp_systolic': self.bp_systolic, 'bp_diastolic': self.bp_diastolic,
                'respiratory_rate': self.respiratory_rate, 'weight': self.weight, 'height': self.height,
                'bmi': round(self.bmi, 1),
            },
            'missing_for_signature': self._emr_missing_for_signature() if self.record_state == 'draft' else [],
            'consents': [{'id': c.id, 'name': c.name, 'type': c.consent_type, 'state': c.state}
                         for c in self.consent_ids],
            'patient_admin': self._emr_patient_admin(),
        })
        return data

    def _emr_patient_admin(self):
        patient = self.patient_id
        return {
            'identity_type': patient.identity_type or '',
            'citizen_id': patient.citizen_id or '',
            'identity_exemption_reason': patient.identity_exemption_reason or '',
            'ethnicity': patient.ethnicity or '',
            'nationality': patient.nationality_id.name or '',
            'workplace': patient.workplace or '',
            'patient_category': patient.patient_category or '',
            'bhyt_number': patient.bhyt_number or '',
            'bhyt_valid_to': fields.Date.to_string(patient.bhyt_valid_to) if patient.bhyt_valid_to else False,
            'emergency_contact_name': patient.emergency_contact_name or '',
            'emergency_contact_phone': patient.emergency_contact_phone or '',
        }

    def get_visit_workspace(self):
        res = super().get_visit_workspace()
        self.env['dmag.record.access.log']._log(self, 'workspace', document='get_visit_workspace',
                                                dedupe_minutes=10)
        res['emr'] = self._emr_workspace_dict()
        return res

    def save_record_from_workspace(self, values):
        self.ensure_one()
        values = dict(values or {})
        nested = values.pop('emr', None) or {}
        values.update(nested)
        res = super().save_record_from_workspace(values)
        vals = {k: values[k] for k in WORKSPACE_EMR_KEYS if k in values}
        for key in ('primary_diagnosis_id', 'final_diagnosis_id'):
            if key in values:
                vals[key] = values[key] or False
        for key in ('treatment_from', 'treatment_to'):
            if key in vals and not vals[key]:
                vals[key] = False
        if vals:
            self.write(vals)
        return res
