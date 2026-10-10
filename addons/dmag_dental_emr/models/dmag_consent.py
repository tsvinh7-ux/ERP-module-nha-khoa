from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .dmag_record_access_log import _client_ip

CONSENT_TYPES = [
    ('procedure', 'Thực hiện thủ thuật'),
    ('treatment_plan', 'Kế hoạch điều trị'),
    ('anesthesia', 'Gây tê / gây mê'),
    ('other', 'Khác'),
]
SIGN_METHODS = [
    ('tablet', 'Ký trên máy tính bảng'),
    ('otp', 'Xác nhận bằng mã OTP'),
    ('paper', 'Ký giấy – bản quét'),
]
CONSENT_TEMPLATE = (
    'Tôi (hoặc người đại diện hợp pháp của người bệnh) đã được bác sĩ giải thích rõ về tình trạng bệnh, '
    'thủ thuật dự kiến thực hiện, các nguy cơ, tai biến có thể xảy ra, các phương pháp điều trị thay thế '
    'và chi phí dự kiến như nêu trên. Tôi đã được trả lời đầy đủ các câu hỏi, hiểu rõ và tự nguyện đồng ý '
    'thực hiện. Tôi cam kết thực hiện đúng hướng dẫn của bác sĩ trước, trong và sau khi điều trị.'
)


class DmagConsent(models.Model):
    """Giấy cam kết / đồng ý thực hiện thủ thuật – khóa sau khi người bệnh ký."""
    _name = 'dmag.consent'
    _description = 'Cam kết / đồng ý của người bệnh'
    _inherit = ['mail.thread']
    _order = 'create_date desc, id desc'

    name = fields.Char('Số phiếu', required=True, readonly=True, copy=False, default='/')
    company_id = fields.Many2one('res.company', string='Phòng khám', required=True,
                                 default=lambda self: self.env.company, index=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    patient_id = fields.Many2one('res.partner', string='Người bệnh', required=True, index=True, tracking=True,
                                 domain=[('is_patient', '=', True)])
    visit_id = fields.Many2one('dmag.dental.visit', string='Lượt khám', index=True, tracking=True,
                               domain="[('patient_id', '=', patient_id)]")
    plan_id = fields.Many2one('dmag.treatment.plan', string='Kế hoạch điều trị', tracking=True,
                              domain="[('patient_id', '=', patient_id)]")
    consent_type = fields.Selection(CONSENT_TYPES, string='Loại cam kết', required=True, default='procedure',
                                    tracking=True)
    product_id = fields.Many2one('product.product', string='Dịch vụ', domain=[('is_dental_service', '=', True)])
    procedure_name = fields.Char('Thủ thuật / kỹ thuật', required=True, tracking=True)
    tooth_ids = fields.Many2many('dmag.dental.tooth', string='Răng')
    diagnosis = fields.Char('Chẩn đoán')
    risks = fields.Text('Nguy cơ, tai biến có thể xảy ra', tracking=True)
    alternatives = fields.Text('Phương pháp điều trị thay thế', tracking=True)
    expected_cost = fields.Monetary('Chi phí dự kiến', currency_field='currency_id', tracking=True)
    consent_text = fields.Text('Nội dung cam kết (bản lưu tại thời điểm ký)', default=CONSENT_TEMPLATE)
    doctor_id = fields.Many2one('dmag.dental.practitioner', string='Bác sĩ giải thích',
                                domain=[('role', '=', 'doctor')], tracking=True)

    signer_name = fields.Char('Người ký (họ và tên)', tracking=True)
    guardian_name = fields.Char('Người đại diện hợp pháp / người giám hộ')
    guardian_relation = fields.Char('Quan hệ với người bệnh')
    guardian_identity = fields.Char('Số định danh của người đại diện')
    sign_method = fields.Selection(SIGN_METHODS, string='Hình thức ký', default='tablet', tracking=True)
    signature = fields.Binary('Chữ ký', attachment=True, copy=False)
    otp_reference = fields.Char('Mã giao dịch OTP', copy=False)
    scan_file = fields.Binary('Bản quét giấy đã ký', attachment=True, copy=False)
    scan_filename = fields.Char('Tên tệp')
    signed_at = fields.Datetime('Thời điểm ký', readonly=True, copy=False, tracking=True)
    signed_ip = fields.Char('Địa chỉ IP khi ký', readonly=True, copy=False)
    recorded_by_id = fields.Many2one('res.users', string='Người ghi nhận', readonly=True, copy=False)
    state = fields.Selection([('draft', 'Chờ ký'), ('signed', 'Đã ký – khóa')], string='Trạng thái',
                             default='draft', required=True, tracking=True, copy=False)
    patient_age = fields.Integer(related='patient_id.age', string='Tuổi')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('dmag.consent') or '/'
            if vals.get('visit_id') and not vals.get('patient_id'):
                vals['patient_id'] = self.env['dmag.dental.visit'].browse(vals['visit_id']).patient_id.id
        return super().create(vals_list)

    @api.onchange('patient_id')
    def _onchange_patient(self):
        patient = self.patient_id
        if patient and not self.signer_name:
            if patient.age and patient.age < 18 and patient.guardian_id:
                self.guardian_name = patient.guardian_id.name
                self.guardian_relation = patient.guardian_relation
                self.signer_name = patient.guardian_id.name
            else:
                self.signer_name = patient.name

    @api.onchange('visit_id')
    def _onchange_visit(self):
        if self.visit_id:
            self.patient_id = self.visit_id.patient_id
            self.doctor_id = self.doctor_id or self.visit_id.doctor_id
            self.plan_id = self.plan_id or self.visit_id.treatment_plan_id
            if not self.diagnosis and self.visit_id.diagnosis_ids:
                self.diagnosis = ', '.join(self.visit_id.diagnosis_ids.mapped('display_name'))

    @api.onchange('product_id')
    def _onchange_product(self):
        if self.product_id:
            self.procedure_name = self.product_id.name
            self.expected_cost = self.product_id.lst_price

    @api.onchange('plan_id')
    def _onchange_plan(self):
        plan = self.plan_id
        if plan:
            self.consent_type = 'treatment_plan' if self.consent_type == 'procedure' and not self.product_id else self.consent_type
            option = plan.accepted_option_id or plan.option_ids.filtered('is_recommended')[:1] or plan.option_ids[:1]
            if not self.procedure_name:
                self.procedure_name = plan.title or ', '.join(option.line_ids.mapped('product_id.name'))
            if option and not self.expected_cost:
                self.expected_cost = option.amount_total
            if option and not self.tooth_ids:
                self.tooth_ids = option.line_ids.mapped('tooth_ids')
            self.doctor_id = self.doctor_id or plan.doctor_id

    # ------------------------------------------------------------------ lock
    def write(self, vals):
        if not self.env.context.get('dmag_consent_sign') and not self.env.context.get('dmag_record_amend'):
            locked = self.filtered(lambda c: c.state == 'signed')
            if locked and set(vals) - {'message_main_attachment_id'}:
                raise UserError(_('Phiếu cam kết %s đã ký và bị khóa – không sửa được. '
                                  'Nếu cần thay đổi, lập phiếu cam kết mới.', ', '.join(locked.mapped('name'))))
        return super().write(vals)

    def unlink(self):
        for consent in self:
            if consent.state == 'signed':
                raise UserError(_('Phiếu cam kết %s đã ký là một phần hồ sơ bệnh án – không được xóa.', consent.name))
        return super().unlink()

    @api.constrains('sign_method', 'state', 'signature', 'otp_reference', 'scan_file')
    def _check_signed_evidence(self):
        for consent in self.filtered(lambda c: c.state == 'signed'):
            missing = consent._missing_evidence()
            if missing:
                raise ValidationError(missing)

    def _missing_evidence(self):
        self.ensure_one()
        if self.sign_method == 'tablet' and not self.signature:
            return _('Người bệnh chưa ký trên máy tính bảng.')
        if self.sign_method == 'otp' and not self.otp_reference:
            return _('Chưa có mã giao dịch OTP xác nhận.')
        if self.sign_method == 'paper' and not self.scan_file:
            return _('Chưa đính kèm bản quét giấy cam kết đã ký.')
        return False

    def action_sign(self):
        for consent in self:
            if consent.state == 'signed':
                continue
            errors = []
            if not consent.signer_name:
                errors.append(_('Họ và tên người ký'))
            if consent.patient_id.age and consent.patient_id.age < 18 and not consent.guardian_name:
                errors.append(_('Người đại diện hợp pháp (người bệnh dưới 18 tuổi)'))
            if not consent.doctor_id:
                errors.append(_('Bác sĩ giải thích'))
            if not consent.risks:
                errors.append(_('Nguy cơ, tai biến có thể xảy ra'))
            evidence = consent._missing_evidence()
            if evidence:
                errors.append(evidence)
            if errors:
                raise UserError(_('Phiếu %(name)s chưa ký được, còn thiếu:\n%(items)s', name=consent.name,
                                  items='\n'.join('  • ' + e for e in errors)))
            consent.with_context(dmag_consent_sign=True).write({
                'state': 'signed',
                'signed_at': fields.Datetime.now(),
                'signed_ip': _client_ip() or False,
                'recorded_by_id': self.env.uid,
                'consent_text': consent.consent_text or CONSENT_TEMPLATE,
            })
            consent.message_post(body=_('Người bệnh / người đại diện %(signer)s đã ký (%(method)s).',
                                        signer=consent.signer_name,
                                        method=dict(SIGN_METHODS)[consent.sign_method]))
        return True
