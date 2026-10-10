from odoo import api, fields, models


class DmagDentalTooth(models.Model):
    _name = 'dmag.dental.tooth'
    _description = 'Răng (FDI)'
    _order = 'sequence, code'
    _rec_name = 'code'

    code = fields.Char('Số răng (FDI)', required=True, size=2)
    name = fields.Char('Tên răng', required=True, translate=True)
    sequence = fields.Integer(default=10)
    dentition = fields.Selection(
        [('permanent', 'Răng vĩnh viễn'), ('primary', 'Răng sữa')],
        string='Bộ răng', required=True)
    quadrant = fields.Integer('Cung phần tư', required=True,
                              help='1–4 cho răng vĩnh viễn, 5–8 cho răng sữa')
    position = fields.Integer('Vị trí', required=True,
                              help='Thứ tự răng tính từ đường giữa (1 = răng cửa giữa)')
    arch = fields.Selection([('upper', 'Hàm trên'), ('lower', 'Hàm dưới')],
                            string='Hàm', compute='_compute_arch', store=True)
    tooth_type = fields.Selection([
        ('incisor', 'Răng cửa'),
        ('canine', 'Răng nanh'),
        ('premolar', 'Răng hàm nhỏ'),
        ('molar', 'Răng hàm lớn'),
    ], string='Nhóm răng', required=True)

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'Số răng FDI phải là duy nhất.'),
    ]

    @api.depends('quadrant')
    def _compute_arch(self):
        for tooth in self:
            tooth.arch = 'upper' if tooth.quadrant in (1, 2, 5, 6) else 'lower'

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for tooth in self:
            tooth.display_name = f'{tooth.code} – {tooth.name}' if tooth.name else tooth.code


class DmagDentalSurface(models.Model):
    _name = 'dmag.dental.surface'
    _description = 'Mặt răng'
    _order = 'sequence, id'

    code = fields.Char('Ký hiệu', required=True, size=2)
    name = fields.Char('Tên mặt răng', required=True, translate=True)
    sequence = fields.Integer(default=10)

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'Ký hiệu mặt răng phải là duy nhất.'),
    ]

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for surface in self:
            surface.display_name = f'{surface.code} – {surface.name}'


class DmagDentalCondition(models.Model):
    _name = 'dmag.dental.condition'
    _description = 'Tình trạng / chỉ định trên răng'
    _order = 'sequence, name'

    name = fields.Char('Tên', required=True, translate=True)
    code = fields.Char('Mã', required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    category = fields.Selection([
        ('finding', 'Bệnh lý phát hiện'),
        ('existing', 'Phục hồi / điều trị đã có'),
        ('missing', 'Mất răng / chưa mọc'),
    ], string='Nhóm', required=True, default='finding')
    scope = fields.Selection([
        ('surface', 'Theo mặt răng'),
        ('tooth', 'Cả răng'),
    ], string='Phạm vi ghi nhận', required=True, default='tooth',
        help='Theo mặt răng: chọn mặt cụ thể (ví dụ sâu mặt nhai). Cả răng: áp cho toàn bộ răng.')
    color = fields.Char('Màu hiển thị', default='#E5484D',
                        help='Màu tô trên sơ đồ răng, dạng mã hex.')
    symbol = fields.Selection([
        ('fill', 'Tô màu'),
        ('cross', 'Dấu X (mất răng)'),
        ('ring', 'Viền (mão / chụp)'),
        ('implant', 'Trụ implant'),
        ('root', 'Ống tủy'),
        ('dash', 'Gạch (chưa mọc / ngầm)'),
    ], string='Ký hiệu trên sơ đồ', required=True, default='fill')
    diagnosis_id = fields.Many2one('dmag.dental.diagnosis', string='Chẩn đoán gợi ý (ICD-10)')
    suggested_service_ids = fields.Many2many(
        'product.product', string='Dịch vụ gợi ý',
        domain=[('is_dental_service', '=', True)],
        help='Dịch vụ được đề xuất khi bác sĩ ghi nhận tình trạng này, dùng để lập kế hoạch điều trị nhanh.')

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'Mã tình trạng phải là duy nhất.'),
    ]


class DmagDentalDiagnosis(models.Model):
    _name = 'dmag.dental.diagnosis'
    _description = 'Chẩn đoán (ICD-10)'
    _order = 'code'

    code = fields.Char('Mã ICD-10', required=True)
    name = fields.Char('Tên chẩn đoán', required=True, translate=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'Mã ICD-10 phải là duy nhất.'),
    ]

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for diagnosis in self:
            diagnosis.display_name = f'{diagnosis.code} – {diagnosis.name}'

    @api.model
    def _name_search(self, name, domain=None, operator='ilike', limit=None, order=None):
        domain = domain or []
        if name and operator in ('ilike', 'like', '=', '=like', '=ilike'):
            domain = ['&'] + domain + ['|', ('code', '=ilike', name + '%'), ('name', operator, name)]
            return self._search(domain, limit=limit, order=order)
        return super()._name_search(name, domain, operator, limit, order)


class DmagPatientAlert(models.Model):
    _name = 'dmag.patient.alert'
    _description = 'Cảnh báo y khoa'
    _order = 'sequence, name'

    name = fields.Char('Cảnh báo', required=True, translate=True)
    sequence = fields.Integer(default=10)
    color = fields.Integer('Màu', default=1)
    severity = fields.Selection([
        ('info', 'Lưu ý'),
        ('warning', 'Thận trọng'),
        ('danger', 'Nguy hiểm'),
    ], string='Mức độ', required=True, default='warning')
    active = fields.Boolean(default=True)


class DmagPracticeScope(models.Model):
    _name = 'dmag.practice.scope'
    _description = 'Phạm vi hành nghề / chuyên môn'
    _order = 'sequence, name'

    name = fields.Char('Phạm vi', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)


class DmagClinicalLevel(models.Model):
    _name = 'dmag.clinical.level'
    _description = 'Bậc lâm sàng'
    _order = 'level'

    name = fields.Char('Tên bậc', required=True, translate=True)
    level = fields.Integer('Bậc', required=True)
    description = fields.Text('Mô tả / loại ca được giao', translate=True)

    _sql_constraints = [
        ('level_uniq', 'unique(level)', 'Mỗi bậc lâm sàng chỉ khai báo một lần.'),
    ]


class DmagCustomerSource(models.Model):
    _name = 'dmag.customer.source'
    _description = 'Nguồn khách'
    _order = 'sequence, name'

    name = fields.Char('Nguồn khách', required=True, translate=True)
    code = fields.Char('Mã')
    sequence = fields.Integer(default=10)
    is_referral = fields.Boolean('Là giới thiệu',
                                 help='Bật để bắt buộc chọn người giới thiệu trên hồ sơ bệnh nhân.')
    active = fields.Boolean(default=True)


class DmagPatientFamily(models.Model):
    _name = 'dmag.patient.family'
    _description = 'Nhóm gia đình'

    name = fields.Char('Tên gia đình', required=True)
    head_id = fields.Many2one('res.partner', string='Chủ hộ / người liên hệ chính')
    member_ids = fields.One2many('res.partner', 'dental_family_id', string='Thành viên')
    member_count = fields.Integer(compute='_compute_member_count', string='Số thành viên')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    @api.depends('member_ids')
    def _compute_member_count(self):
        for family in self:
            family.member_count = len(family.member_ids)
