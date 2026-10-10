from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_patient = fields.Boolean('Là bệnh nhân', index=True)
    patient_code = fields.Char('Mã bệnh nhân', copy=False, index=True, readonly=True)
    birthdate = fields.Date('Ngày sinh')
    age = fields.Integer('Tuổi', compute='_compute_age')
    gender = fields.Selection([
        ('male', 'Nam'),
        ('female', 'Nữ'),
        ('other', 'Khác'),
    ], string='Giới tính')
    citizen_id = fields.Char('Số CCCD / Hộ chiếu', copy=False)
    occupation = fields.Char('Nghề nghiệp')
    guardian_id = fields.Many2one('res.partner', string='Người giám hộ',
                                  help='Bắt buộc với bệnh nhân dưới 18 tuổi.')
    guardian_relation = fields.Char('Quan hệ với bệnh nhân')

    dental_family_id = fields.Many2one('dmag.patient.family', string='Nhóm gia đình', index=True)
    customer_source_id = fields.Many2one('dmag.customer.source', string='Nguồn khách')
    referrer_id = fields.Many2one('res.partner', string='Người giới thiệu')

    patient_alert_ids = fields.Many2many('dmag.patient.alert', string='Cảnh báo y khoa')
    has_danger_alert = fields.Boolean(compute='_compute_has_danger_alert')
    medical_history = fields.Text('Tiền sử bệnh toàn thân')
    dental_history = fields.Text('Tiền sử nha khoa')
    allergy = fields.Text('Dị ứng (thuốc, vật liệu…)')
    current_medication = fields.Text('Thuốc đang dùng')
    is_pregnant = fields.Boolean('Đang mang thai')

    data_consent = fields.Boolean('Đồng ý xử lý dữ liệu cá nhân')
    data_consent_date = fields.Datetime('Thời điểm đồng ý', readonly=True)
    zalo_phone = fields.Char('SĐT Zalo', help='Để trống nếu trùng số di động.')

    _sql_constraints = [
        ('patient_code_company_uniq', 'unique(patient_code, company_id)',
         'Mã bệnh nhân đã tồn tại.'),
    ]

    @api.depends('birthdate')
    def _compute_age(self):
        today = fields.Date.context_today(self)
        for partner in self:
            partner.age = relativedelta(today, partner.birthdate).years if partner.birthdate else 0

    @api.depends('patient_alert_ids.severity')
    def _compute_has_danger_alert(self):
        for partner in self:
            partner.has_danger_alert = any(a.severity == 'danger' for a in partner.patient_alert_ids)

    @api.constrains('birthdate')
    def _check_birthdate(self):
        today = fields.Date.context_today(self)
        for partner in self:
            if partner.birthdate and partner.birthdate > today:
                raise ValidationError(_('Ngày sinh không được ở tương lai.'))

    @api.constrains('customer_source_id', 'referrer_id')
    def _check_referrer(self):
        for partner in self:
            if partner.customer_source_id.is_referral and partner.referrer_id == partner:
                raise ValidationError(_('Bệnh nhân không thể tự giới thiệu chính mình.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('is_patient') and not vals.get('patient_code'):
                vals['patient_code'] = self._next_patient_code(vals.get('company_id'))
            if vals.get('data_consent') and not vals.get('data_consent_date'):
                vals['data_consent_date'] = fields.Datetime.now()
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('data_consent'):
            vals.setdefault('data_consent_date', fields.Datetime.now())
        res = super().write(vals)
        if vals.get('is_patient'):
            for partner in self.filtered(lambda p: not p.patient_code):
                partner.patient_code = self._next_patient_code(partner.company_id.id)
        return res

    @api.model
    def _next_patient_code(self, company_id=False):
        sequence = self.env['ir.sequence']
        if company_id:
            sequence = sequence.with_company(company_id)
        return sequence.next_by_code('dmag.patient') or '/'

    @api.depends('patient_code')
    def _compute_display_name(self):
        super()._compute_display_name()
        if self.env.context.get('dmag_show_patient_code'):
            for partner in self.filtered('patient_code'):
                partner.display_name = f'[{partner.patient_code}] {partner.display_name}'

    @api.model
    def _name_search(self, name, domain=None, operator='ilike', limit=None, order=None):
        if name and operator in ('ilike', 'like', '=', '=ilike') and self.env.context.get('dmag_patient_search'):
            domain = list(domain or [])
            domain += ['|', '|', '|',
                       ('name', operator, name),
                       ('patient_code', '=ilike', name + '%'),
                       ('phone', 'ilike', name),
                       ('mobile', 'ilike', name)]
            return self._search(domain, limit=limit, order=order)
        return super()._name_search(name, domain, operator, limit, order)
