import re
import secrets
import threading
import string

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.dmag_dental_base.models.dmag_access import check_director, is_director, is_workflow

from .dmag_prescription_template import format_quantity

RX_TYPES = [
    ('c', 'Đơn thuốc thông thường (c)'),
    ('n', 'Đơn thuốc gây nghiện (n)'),
    ('h', 'Đơn thuốc hướng thần, tiền chất (h)'),
    ('y', 'Đơn thuốc y học cổ truyền (y)'),
]
STATES = [
    ('draft', 'Nháp'),
    ('issued', 'Đã phát hành – chờ liên thông'),
    ('sent', 'Đã liên thông'),
    ('send_error', 'Lỗi liên thông'),
    ('replaced', 'Đã thay thế'),
    ('cancelled', 'Đã hủy'),
]
ISSUED_STATES = ('issued', 'sent', 'send_error')
CODE_ALPHABET = string.digits + string.ascii_lowercase
CODE_RE = re.compile(r'^[0-9A-Za-z]{5}[0-9a-z]{7}-[cnhy]$')
MAX_DAYS = 30
MAX_DAYS_CHRONIC = 90
# Trường được ghi sau khi phát hành (không thuộc nội dung đơn) – chỉ Giám đốc
DIRECTOR_EDITABLE = {'internal_note', 'cancel_reason'}
GENDER_LABELS = {'male': 'Nam', 'female': 'Nữ', 'other': 'Khác'}


class DmagPrescription(models.Model):
    """Đơn thuốc điện tử theo TT 26/2025/TT-BYT.

    Phát hành → khóa (không sửa); muốn đổi phải kê đơn mới thay thế (``replaced_id``).
    """
    _name = 'dmag.prescription'
    _description = 'Đơn thuốc'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char('Mã đơn thuốc', copy=False, readonly=True, index=True, tracking=True,
                       help='14 ký tự xxxxxyyyyyyy-z: mã cơ sở KCB (5) + 7 ký tự ngẫu nhiên + "-" + loại đơn.')
    company_id = fields.Many2one('res.company', string='Phòng khám', required=True, index=True,
                                 default=lambda self: self.env.company)
    visit_id = fields.Many2one('dmag.dental.visit', string='Lượt khám', index=True, ondelete='restrict')
    patient_id = fields.Many2one('res.partner', string='Bệnh nhân', required=True, index=True, tracking=True,
                                 domain=[('is_patient', '=', True)],
                                 context={'dmag_patient_search': True})
    doctor_id = fields.Many2one('dmag.dental.practitioner', string='Bác sĩ kê đơn', tracking=True,
                                domain=[('role', '=', 'doctor')])
    rx_type = fields.Selection(RX_TYPES, string='Loại đơn', required=True, default='c', tracking=True)
    date = fields.Datetime('Ngày giờ kê đơn', default=fields.Datetime.now, copy=False)
    state = fields.Selection(STATES, string='Trạng thái', default='draft', required=True, copy=False,
                             tracking=True, index=True)
    template_id = fields.Many2one('dmag.prescription.template', string='Đơn mẫu', copy=False)

    diagnosis_ids = fields.Many2many('dmag.dental.diagnosis', string='Chẩn đoán (ICD-10)')
    diagnosis_text = fields.Char('Chẩn đoán (diễn giải)')

    # Ảnh chụp thông tin người bệnh tại thời điểm phát hành
    patient_name = fields.Char('Họ tên người bệnh', compute='_compute_patient_snapshot', store=True, readonly=False)
    patient_birthdate = fields.Date('Ngày sinh', compute='_compute_patient_snapshot', store=True, readonly=False)
    patient_gender = fields.Selection([('male', 'Nam'), ('female', 'Nữ'), ('other', 'Khác')], string='Giới tính',
                                      compute='_compute_patient_snapshot', store=True, readonly=False)
    patient_identity = fields.Char('Số định danh cá nhân / CCCD', compute='_compute_patient_snapshot',
                                   store=True, readonly=False)
    patient_address = fields.Char('Nơi cư trú', compute='_compute_patient_snapshot', store=True, readonly=False)
    patient_phone = fields.Char('Điện thoại người bệnh', compute='_compute_patient_snapshot', store=True,
                                readonly=False)
    patient_bhyt = fields.Char('Số thẻ BHYT', compute='_compute_patient_snapshot', store=True, readonly=False)
    patient_age = fields.Integer('Tuổi', compute='_compute_age', store=True)
    patient_age_months = fields.Integer('Tháng tuổi', compute='_compute_age', store=True)
    is_under_72_months = fields.Boolean('Trẻ dưới 72 tháng', compute='_compute_age', store=True)
    weight = fields.Float('Cân nặng (kg)', digits=(5, 1))
    companion_name = fields.Char('Họ tên người đưa trẻ đến khám')
    identity_exemption_reason = fields.Char(
        'Lý do không có số định danh',
        help='Ví dụ: người nước ngoài (ghi số hộ chiếu), trẻ em chưa có số định danh… '
             'Bỏ trống thì bắt buộc có số định danh / CCCD khi phát hành.')

    line_ids = fields.One2many('dmag.prescription.line', 'prescription_id', string='Thuốc', copy=True)
    line_count = fields.Integer('Số khoản thuốc', compute='_compute_line_count')
    advice = fields.Text('Lời dặn')
    re_exam_date = fields.Date('Ngày tái khám')
    internal_note = fields.Text('Ghi chú nội bộ')

    replaced_id = fields.Many2one('dmag.prescription', string='Thay thế cho đơn', copy=False, readonly=True,
                                  index=True)
    replaced_by_id = fields.Many2one('dmag.prescription', string='Được thay thế bởi', copy=False, readonly=True)
    cancel_reason = fields.Char('Lý do hủy', copy=False)
    issued_uid = fields.Many2one('res.users', string='Người phát hành', copy=False, readonly=True)

    send_attempts = fields.Integer('Số lần gửi liên thông', copy=False, readonly=True)
    send_error = fields.Text('Lỗi liên thông gần nhất', copy=False, readonly=True)
    sent_at = fields.Datetime('Thời điểm liên thông', copy=False, readonly=True)
    send_log_ids = fields.One2many('dmag.rx.send.log', 'prescription_id', string='Nhật ký liên thông')

    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'Mã đơn thuốc đã tồn tại.'),
    ]

    # ------------------------------------------------------------------ compute
    @api.depends('patient_id')
    def _compute_patient_snapshot(self):
        for rx in self:
            rx.update(rx._patient_snapshot_values())

    def _patient_snapshot_values(self):
        self.ensure_one()
        partner = self.patient_id
        if not partner:
            return {}
        address = partner._display_address(without_company=True) or ''
        address = ', '.join(p.strip() for p in address.splitlines() if p.strip())
        return {
            'patient_name': partner.name,
            'patient_birthdate': partner.birthdate,
            'patient_gender': partner.gender,
            'patient_identity': partner.citizen_id,
            'patient_address': address,
            'patient_phone': partner.mobile or partner.phone,
            'patient_bhyt': partner.dmag_bhyt_number,
        }

    @api.depends('patient_birthdate', 'date')
    def _compute_age(self):
        for rx in self:
            if not rx.patient_birthdate:
                rx.patient_age = rx.patient_age_months = 0
                rx.is_under_72_months = False
                continue
            ref = fields.Date.to_date(rx.date) if rx.date else fields.Date.context_today(rx)
            delta = relativedelta(ref, rx.patient_birthdate)
            rx.patient_age = delta.years
            rx.patient_age_months = delta.years * 12 + delta.months
            rx.is_under_72_months = rx.patient_age_months < 72

    @api.depends('line_ids')
    def _compute_line_count(self):
        for rx in self:
            rx.line_count = len(rx.line_ids)

    @api.depends('name', 'patient_id')
    def _compute_display_name(self):
        for rx in self:
            code = rx.name or _('Đơn nháp #%s', rx.id or '')
            rx.display_name = f'{code} – {rx.patient_id.name}' if rx.patient_id else code

    # ------------------------------------------------------------------ CRUD
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('visit_id'):
                visit = self.env['dmag.dental.visit'].browse(vals['visit_id'])
                vals.setdefault('patient_id', visit.patient_id.id)
                vals.setdefault('company_id', visit.company_id.id)
                if not vals.get('doctor_id') and visit.doctor_id:
                    vals['doctor_id'] = visit.doctor_id.id
                if 'diagnosis_ids' not in vals and visit.diagnosis_ids:
                    vals['diagnosis_ids'] = [(6, 0, visit.diagnosis_ids.ids)]
                if not vals.get('diagnosis_text') and visit.assessment:
                    vals['diagnosis_text'] = visit.assessment.strip().splitlines()[0][:250]
            if not vals.get('doctor_id'):
                practitioner = self.env['dmag.dental.visit']._current_practitioner()
                if practitioner.role == 'doctor':
                    vals['doctor_id'] = practitioner.id
            if vals.get('state', 'draft') != 'draft' and not is_workflow(self.env):
                raise UserError(_('Đơn thuốc mới luôn ở trạng thái nháp.'))
        records = super().create(vals_list)
        for rx, vals in zip(records, vals_list):
            if vals.get('template_id') and not vals.get('line_ids'):
                rx._apply_template(rx.template_id)
        return records

    def write(self, vals):
        if not is_workflow(self.env):
            locked = self.filtered(lambda r: r.state != 'draft')
            if locked:
                keys = {k for k in vals if not k.startswith(('message_', 'activity_'))}
                content = keys - DIRECTOR_EDITABLE
                if content:
                    raise UserError(_(
                        'Đơn thuốc %s đã phát hành – không được sửa (TT 26/2025/TT-BYT). '
                        'Dùng "Kê đơn thay thế" để kê đơn mới.', ', '.join(locked.mapped('display_name'))))
                if keys:
                    check_director(self.env)
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda r: r.state != 'draft' or r.name):
            raise UserError(_('Chỉ xóa được đơn thuốc nháp. Đơn đã phát hành chỉ có thể hủy (Giám đốc).'))
        return super().unlink()

    def _workflow_write(self, vals):
        return self.with_context(dmag_workflow=True).write(vals)

    @api.onchange('visit_id')
    def _onchange_visit_id(self):
        visit = self.visit_id
        if visit:
            self.patient_id = visit.patient_id
            self.company_id = visit.company_id
            if visit.doctor_id:
                self.doctor_id = visit.doctor_id
            if visit.diagnosis_ids and not self.diagnosis_ids:
                self.diagnosis_ids = visit.diagnosis_ids

    @api.onchange('template_id')
    def _onchange_template_id(self):
        if self.template_id and self.state == 'draft':
            template = self.template_id
            self.line_ids = [(5, 0, 0)] + [(0, 0, line._line_values()) for line in template.line_ids]
            if template.advice:
                self.advice = template.advice
            if template.re_exam_days:
                self.re_exam_date = fields.Date.context_today(self) + relativedelta(days=template.re_exam_days)
            if template.diagnosis_ids and not self.diagnosis_ids:
                self.diagnosis_ids = template.diagnosis_ids

    # ------------------------------------------------------------------ business
    def _apply_template(self, template):
        """Áp đơn mẫu: thay toàn bộ dòng thuốc, lời dặn, ngày tái khám."""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Chỉ áp đơn mẫu cho đơn nháp.'))
        vals = {
            'template_id': template.id,
            'line_ids': [(5, 0, 0)] + [(0, 0, line._line_values()) for line in template.line_ids],
        }
        if template.advice:
            vals['advice'] = template.advice
        if template.re_exam_days:
            vals['re_exam_date'] = fields.Date.context_today(self) + relativedelta(days=template.re_exam_days)
        if template.diagnosis_ids and not self.diagnosis_ids:
            vals['diagnosis_ids'] = [(6, 0, template.diagnosis_ids.ids)]
        self.write(vals)
        return True

    def action_apply_template(self):
        for rx in self:
            if rx.template_id:
                rx._apply_template(rx.template_id)
        return True

    def _max_days(self, line):
        if line.is_chronic and self.company_id.dmag_rx_allow_90_days:
            return MAX_DAYS_CHRONIC
        return MAX_DAYS

    def _get_issue_errors(self):
        """Danh sách lý do chưa được phát hành (rỗng = hợp lệ)."""
        self.ensure_one()
        errors = []
        company = self.company_id
        facility = (company.dmag_facility_code or '').strip()
        if not re.fullmatch(r'[0-9A-Za-z]{5}', facility):
            errors.append(_('Phòng khám %s chưa khai báo "Mã cơ sở KCB" 5 ký tự (dùng sinh mã đơn thuốc).',
                            company.name))
        doctor = self.doctor_id
        if not doctor:
            errors.append(_('Chưa chọn bác sĩ kê đơn.'))
        else:
            if doctor.role != 'doctor':
                errors.append(_('%s không phải bác sĩ – không được kê đơn.', doctor.name))
            if not doctor.license_number:
                errors.append(_('Bác sĩ %s chưa khai báo số giấy phép hành nghề.', doctor.name))
            elif doctor.license_state == 'expired':
                errors.append(_('Giấy phép hành nghề của bác sĩ %s đã hết hạn.', doctor.name))
            if (doctor.user_id and doctor.user_id != self.env.user
                    and not is_director(self.env)):
                errors.append(_('Chỉ bác sĩ %s mới được phát hành đơn thuốc của mình.', doctor.name))
        if not self.line_ids:
            errors.append(_('Đơn thuốc chưa có thuốc.'))
        if not self.patient_name:
            errors.append(_('Thiếu họ tên người bệnh.'))
        if not self.patient_birthdate:
            errors.append(_('Thiếu ngày sinh người bệnh.'))
        if not self.patient_gender:
            errors.append(_('Thiếu giới tính người bệnh.'))
        if not (self.patient_identity or '').strip() and not (self.identity_exemption_reason or '').strip():
            errors.append(_('Thiếu số định danh cá nhân / CCCD của người bệnh (hoặc ghi lý do không có).'))
        if not self.diagnosis_ids and not (self.diagnosis_text or '').strip():
            errors.append(_('Thiếu chẩn đoán.'))
        if self.is_under_72_months:
            if not self.weight or self.weight <= 0:
                errors.append(_('Trẻ dưới 72 tháng tuổi: bắt buộc ghi cân nặng.'))
            if not (self.companion_name or '').strip():
                errors.append(_('Trẻ dưới 72 tháng tuổi: bắt buộc ghi họ tên người đưa trẻ đến khám.'))
        drugs = self.line_ids.mapped('drug_id')
        narcotic = drugs.filtered('is_narcotic')
        psycho = drugs.filtered(lambda d: d.is_psychotropic and not d.is_narcotic)
        if narcotic and self.rx_type != 'n':
            errors.append(_('Thuốc gây nghiện (%s) phải kê trên đơn "N".', ', '.join(narcotic.mapped('name'))))
        if psycho and self.rx_type not in ('h', 'n'):
            errors.append(_('Thuốc hướng thần / tiền chất (%s) phải kê trên đơn "H".',
                            ', '.join(psycho.mapped('name'))))
        if self.rx_type in ('n', 'h'):
            if not company.dmag_rx_allow_controlled:
                errors.append(_('Phòng khám chưa được cấu hình cho phép kê đơn thuốc gây nghiện / hướng thần.'))
            if doctor and not doctor.rx_controlled_allowed:
                errors.append(_('Bác sĩ %s không có phạm vi kê đơn thuốc gây nghiện / hướng thần.', doctor.name))
        for line in self.line_ids:
            errors.extend(line._get_line_errors())
        return errors

    def _generate_code(self):
        """Mã đơn 14 ký tự: mã cơ sở (5) + 7 ký tự [0-9a-z] duy nhất trong cơ sở + '-' + loại đơn."""
        self.ensure_one()
        facility = self.company_id.dmag_facility_code.strip()
        for _attempt in range(100):
            random_part = ''.join(secrets.choice(CODE_ALPHABET) for _i in range(7))
            prefix = f'{facility}{random_part}'
            if not self.sudo().with_context(active_test=False).search_count(
                    [('name', '=like', f'{prefix}-_')], limit=1):
                return f'{prefix}-{self.rx_type}'
        raise UserError(_('Không sinh được mã đơn thuốc duy nhất – vui lòng thử lại.'))

    def action_issue(self):
        """Phát hành đơn: kiểm tra TT 26, cấp mã, khóa đơn, ký số (móc), gửi liên thông."""
        for rx in self:
            if rx.state != 'draft':
                raise UserError(_('Đơn %s không ở trạng thái nháp.', rx.display_name))
            now = fields.Datetime.now()
            rx._workflow_write(dict(rx._patient_snapshot_values(), date=now))
            errors = rx._get_issue_errors()
            if errors:
                raise ValidationError(_('Chưa phát hành được đơn thuốc:\n- %s', '\n- '.join(errors)))
            rx._workflow_write({
                'name': rx._generate_code(),
                'state': 'issued',
                'issued_uid': self.env.uid,
            })
            rx._dmag_esign_prescription()
            if rx.replaced_id:
                old = rx.replaced_id
                was_sent = old.state == 'sent'
                old._workflow_write({'state': 'replaced', 'replaced_by_id': rx.id})
                old.message_post(body=_('Đơn được thay thế bởi đơn mới %s.', rx.name))
                if was_sent:
                    old._rx_cancel_national()
            rx.message_post(body=_('Đã phát hành đơn thuốc, mã %s.', rx.name))
        self._rx_send_national()
        return True

    def _dmag_esign_prescription(self):
        """Điểm móc ký số đơn thuốc (Viettel MySign) – module dmag_esign_mysign ghi đè."""
        return True

    def action_replace(self):
        """TT 26: không sửa đơn – kê đơn mới thay thế (đơn cũ chuyển 'Đã thay thế' khi đơn mới phát hành)."""
        self.ensure_one()
        if self.state not in ISSUED_STATES:
            raise UserError(_('Chỉ kê đơn thay thế cho đơn đã phát hành.'))
        new = self.search([('replaced_id', '=', self.id), ('state', '=', 'draft')], limit=1)
        if not new:
            new = self.copy({'replaced_id': self.id, 'template_id': False})
            new.message_post(body=_('Kê đơn thay thế cho đơn %s.', self.name))
        return {
            'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': new.id,
            'view_mode': 'form', 'target': 'current', 'name': _('Đơn thay thế'),
        }

    def action_cancel(self):
        for rx in self:
            if rx.state in ('replaced', 'cancelled'):
                raise UserError(_('Đơn %s đã thay thế / đã hủy.', rx.display_name))
            if rx.state != 'draft':
                check_director(self.env, _('Chỉ Giám đốc / Quản lý cấp cao được hủy đơn thuốc đã phát hành.'))
                if not (rx.cancel_reason or '').strip():
                    raise UserError(_('Ghi "Lý do hủy" trước khi hủy đơn đã phát hành.'))
            was_sent = rx.state == 'sent'
            rx._workflow_write({'state': 'cancelled'})
            if was_sent:
                rx._rx_cancel_national()
        return True

    # ------------------------------------------------------------------ national interconnection
    def _rx_send_national(self):
        """Gửi đơn lên Hệ thống đơn thuốc quốc gia. Trả về dict {id: 'sent'|'error'|'queued'}."""
        result = {}
        Config = self.env['dmag.rx.national.config']
        for rx in self:
            if rx.state not in ('issued', 'send_error'):
                continue
            config = Config._get_for_company(rx.company_id)
            if not config or not config.enabled:
                result[rx.id] = 'queued'
                continue
            ok, error = config._send_prescription(rx)
            if ok:
                rx._workflow_write({'state': 'sent', 'sent_at': fields.Datetime.now(), 'send_error': False,
                                    'send_attempts': rx.send_attempts + 1})
                result[rx.id] = 'sent'
            else:
                rx._workflow_write({'state': 'send_error', 'send_error': error,
                                    'send_attempts': rx.send_attempts + 1})
                result[rx.id] = 'error'
        return result

    def _rx_cancel_national(self):
        Config = self.env['dmag.rx.national.config']
        for rx in self:
            config = Config._get_for_company(rx.company_id)
            if config and config.enabled:
                config._cancel_prescription(rx)
        return True

    def action_resend(self):
        """Nút "Gửi lại"."""
        Config = self.env['dmag.rx.national.config']
        for rx in self:
            if rx.state not in ('issued', 'send_error'):
                raise UserError(_('Đơn %s không ở trạng thái chờ / lỗi liên thông.', rx.display_name))
            config = Config._get_for_company(rx.company_id)
            if not config or not config.enabled:
                raise UserError(_('Phòng khám chưa bật liên thông đơn thuốc quốc gia (Cấu hình → Liên thông đơn thuốc).'))
        self._rx_send_national()
        return True

    @api.model
    def _cron_send_pending(self, limit=50):
        """Hàng đợi: gửi đơn đã phát hành chưa liên thông / lỗi (chưa vượt số lần thử)."""
        configs = self.env['dmag.rx.national.config'].sudo().search([('enabled', '=', True)])
        for config in configs:
            pending = self.sudo().search([
                ('company_id', '=', config.company_id.id),
                ('state', 'in', ('issued', 'send_error')),
                ('send_attempts', '<', config.max_attempts),
            ], order='date asc', limit=limit)
            for rx in pending:
                rx._rx_send_national()
                if not getattr(threading.current_thread(), 'testing', False):
                    self.env.cr.commit()  # giữ kết quả từng đơn nếu đơn sau lỗi
        return True

    # ------------------------------------------------------------------ patient-facing helpers
    def get_patient_message(self):
        """Tin nhắn mã đơn thuốc gửi người bệnh (module Zalo / SMS dùng lại)."""
        self.ensure_one()
        company = self.company_id
        date_text = fields.Datetime.context_timestamp(self, self.date).strftime('%d/%m/%Y') if self.date else ''
        lines = [
            _('%(clinic)s: Mã đơn thuốc của %(patient)s ngày %(date)s là %(code)s.',
              clinic=company.name, patient=self.patient_name or self.patient_id.name, date=date_text,
              code=self.name or ''),
            _('Vui lòng đưa mã đơn thuốc này cho nhà thuốc khi mua thuốc.'),
        ]
        if self.re_exam_date:
            lines.append(_('Ngày tái khám: %s.', self.re_exam_date.strftime('%d/%m/%Y')))
        if company.phone:
            lines.append(_('Điện thoại phòng khám: %s.', company.phone))
        return '\n'.join(lines)

    def _report_age_text(self):
        self.ensure_one()
        if not self.patient_birthdate:
            return ''
        if self.is_under_72_months:
            return _('%s tháng tuổi', self.patient_age_months)
        return _('%s tuổi', self.patient_age)

    def _report_gender_text(self):
        return GENDER_LABELS.get(self.patient_gender, '')

    def _report_date_text(self):
        self.ensure_one()
        if not self.date:
            return ''
        local = fields.Datetime.context_timestamp(self, self.date)
        return _('Ngày %(d)s tháng %(m)s năm %(y)s', d=f'{local.day:02d}', m=f'{local.month:02d}', y=local.year)

    def _workspace_dict(self):
        self.ensure_one()
        return {
            'id': self.id, 'code': self.name or '', 'state': self.state,
            'state_label': dict(STATES).get(self.state), 'rx_type': self.rx_type,
            'date': fields.Datetime.to_string(self.date) if self.date else False,
            'doctor': self.doctor_id.name or '', 'doctor_id': self.doctor_id.id,
            'diagnoses': [{'id': d.id, 'name': d.display_name} for d in self.diagnosis_ids],
            'diagnosis_text': self.diagnosis_text or '', 'advice': self.advice or '',
            're_exam_date': fields.Date.to_string(self.re_exam_date) if self.re_exam_date else False,
            'weight': self.weight, 'companion_name': self.companion_name or '',
            'identity_exemption_reason': self.identity_exemption_reason or '',
            'is_under_72_months': self.is_under_72_months,
            'send_error': self.send_error or '',
            'replaced_id': self.replaced_id.id, 'replaced_by_id': self.replaced_by_id.id,
            'can_edit': self.state == 'draft',
            'print_url': f'/report/pdf/dmag_dental_prescription.report_prescription/{self.id}',
            'lines': [line._workspace_dict() for line in self.line_ids],
        }


class DmagPrescriptionLine(models.Model):
    _name = 'dmag.prescription.line'
    _inherit = 'dmag.rx.line.mixin'
    _description = 'Dòng đơn thuốc'
    _order = 'sequence, id'

    prescription_id = fields.Many2one('dmag.prescription', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='prescription_id.company_id', store=True, index=True)
    state = fields.Selection(related='prescription_id.state')
    is_chronic = fields.Boolean('Bệnh mạn tính (Phụ lục VII)',
                                help='Được kê tối đa 90 ngày nếu phòng khám bật cấu hình tương ứng.')
    quantity_display = fields.Char('Số lượng (in)', compute='_compute_quantity_display')
    drug_name = fields.Char(related='drug_id.name', string='Tên thuốc')

    @api.depends('quantity', 'unit')
    def _compute_quantity_display(self):
        for line in self:
            line.quantity_display = f'{format_quantity(line.quantity)} {line.unit or ""}'.strip()

    def _get_line_errors(self):
        self.ensure_one()
        errors = []
        name = self.drug_id.name or ''
        if self.drug_id.is_supplement:
            errors.append(_('%s là thực phẩm chức năng – không được kê trong đơn thuốc (Luật KCB 2023 Đ63).', name))
        if not self.quantity or self.quantity <= 0:
            errors.append(_('%s: số lượng phải lớn hơn 0.', name))
        if self.dose_per_time <= 0 or self.times_per_day <= 0:
            errors.append(_('%s: liều mỗi lần và số lần mỗi ngày phải lớn hơn 0.', name))
        max_days = self.prescription_id._max_days(self) if self.prescription_id else MAX_DAYS
        if not self.days or self.days <= 0:
            errors.append(_('%s: số ngày dùng phải lớn hơn 0.', name))
        elif self.days > max_days:
            errors.append(_('%(drug)s: kê tối đa %(max)s ngày (đang kê %(days)s ngày).',
                            drug=name, max=max_days, days=self.days))
        return errors

    @api.constrains('drug_id', 'quantity', 'days', 'dose_per_time', 'times_per_day', 'is_chronic')
    def _check_line(self):
        for line in self:
            errors = line._get_line_errors()
            if errors:
                raise ValidationError('\n'.join(errors))

    def _check_prescription_draft(self, prescriptions):
        if is_workflow(self.env):
            return
        if prescriptions.filtered(lambda r: r.state != 'draft'):
            raise UserError(_('Đơn thuốc đã phát hành – không được thêm / sửa / xóa thuốc. '
                              'Dùng "Kê đơn thay thế".'))

    @api.model_create_multi
    def create(self, vals_list):
        ids = {v.get('prescription_id') for v in vals_list if v.get('prescription_id')}
        self._check_prescription_draft(self.env['dmag.prescription'].browse(list(ids)))
        return super().create(vals_list)

    def write(self, vals):
        self._check_prescription_draft(self.mapped('prescription_id'))
        return super().write(vals)

    def unlink(self):
        self._check_prescription_draft(self.mapped('prescription_id'))
        return super().unlink()

    def _workspace_dict(self):
        self.ensure_one()
        return dict(self._line_values(), id=self.id, drug_name=self.drug_id.name,
                    quantity_display=self.quantity_display, is_chronic=self.is_chronic)
