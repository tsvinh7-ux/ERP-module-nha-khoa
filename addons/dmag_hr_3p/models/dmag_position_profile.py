from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .dmag_job_grade import TRACKS


class DmagCompetency(models.Model):
    """Tiêu chí năng lực (P2). Với vị trí lâm sàng có thể gắn bậc lâm sàng / phạm vi hành nghề
    để gợi ý điểm tự động từ hồ sơ nhân sự lâm sàng."""
    _name = 'dmag.competency'
    _description = 'Tiêu chí năng lực (P2)'
    _order = 'sequence, id'

    name = fields.Char('Tiêu chí', required=True, translate=True)
    code = fields.Char('Mã', required=True)
    sequence = fields.Integer(default=10)
    description = fields.Text('Mô tả')
    level_1 = fields.Char('Mức 1 – Chưa đạt')
    level_2 = fields.Char('Mức 2 – Cần cải thiện')
    level_3 = fields.Char('Mức 3 – Đạt chuẩn')
    level_4 = fields.Char('Mức 4 – Tốt')
    level_5 = fields.Char('Mức 5 – Xuất sắc / kèm cặp được')
    basis = fields.Selection([
        ('manual', 'Đánh giá của quản lý'),
        ('clinical_level', 'Theo bậc lâm sàng'),
        ('license', 'Theo giấy phép & phạm vi hành nghề'),
    ], string='Cơ sở chấm', default='manual', required=True,
        help='Bậc lâm sàng: bậc 1 → 3 điểm, bậc 2 → 4 điểm, bậc 3 → 5 điểm. '
             'Giấy phép: còn hiệu lực và có đủ phạm vi yêu cầu → 5 điểm, ngược lại 1 điểm.')
    clinical_level_id = fields.Many2one('dmag.clinical.level', string='Bậc lâm sàng tham chiếu')
    practice_scope_ids = fields.Many2many('dmag.practice.scope', string='Phạm vi hành nghề yêu cầu')
    active = fields.Boolean(default=True)
    is_sample = fields.Boolean('Dữ liệu mẫu')

    _sql_constraints = [('code_uniq', 'unique(code)', 'Mã tiêu chí năng lực phải là duy nhất.')]


class DmagPositionCompetency(models.Model):
    _name = 'dmag.position.competency'
    _description = 'Tiêu chí năng lực của vị trí'
    _order = 'sequence, id'

    profile_id = fields.Many2one('dmag.job.position.profile', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    competency_id = fields.Many2one('dmag.competency', string='Tiêu chí', required=True)
    weight = fields.Float('Trọng số (%)', default=0.0)
    required_level = fields.Integer('Mức yêu cầu (1–5)', default=3)

    @api.constrains('required_level', 'weight')
    def _check_values(self):
        for line in self:
            if not 1 <= line.required_level <= 5:
                raise ValidationError(_('Mức yêu cầu phải từ 1 đến 5.'))
            if line.weight < 0:
                raise ValidationError(_('Trọng số không được âm.'))


class DmagJobPositionProfile(models.Model):
    """Hồ sơ vị trí: ngạch/bậc cho phép, tiêu chí P2, bộ KPI P3 – gắn với chức danh (hr.job)."""
    _name = 'dmag.job.position.profile'
    _description = 'Hồ sơ vị trí 3P'
    _inherit = ['mail.thread']
    _order = 'sequence, id'

    name = fields.Char('Vị trí', compute='_compute_name', store=True)
    job_id = fields.Many2one('hr.job', string='Chức danh', required=True, ondelete='cascade', tracking=True)
    sequence = fields.Integer(default=10)
    code = fields.Char('Mã vị trí')
    track = fields.Selection(TRACKS, string='Ngạch chính', required=True, default='P', tracking=True)
    grade_ids = fields.Many2many('dmag.job.grade', string='Bậc được phép')
    default_grade_id = fields.Many2one('dmag.job.grade', string='Bậc khởi điểm',
                                       domain="[('id', 'in', grade_ids)]")
    is_clinical = fields.Boolean('Vị trí lâm sàng')
    clinical_role = fields.Selection([
        ('doctor', 'Bác sĩ'),
        ('assistant', 'Phụ tá / Điều dưỡng'),
        ('technician', 'Kỹ thuật viên'),
    ], string='Vai trò lâm sàng')
    competency_line_ids = fields.One2many('dmag.position.competency', 'profile_id', string='Tiêu chí năng lực (P2)')
    kpi_ids = fields.One2many('dmag.kpi.definition', 'profile_id', string='Bộ KPI (P3)')
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id, required=True)
    p2_base = fields.Monetary('Mức P2 chuẩn', tracking=True, help='P2 = mức chuẩn × hệ số năng lực.')
    p3_base = fields.Monetary('Mức P3 KPI chuẩn', tracking=True, help='P3 KPI = điểm KPI (%) × mức chuẩn.')
    okr_bonus_base = fields.Monetary('Thưởng OKR tối đa', tracking=True,
                                     help='Nhận đủ khi điểm OKR đạt ngưỡng thành công (mặc định 70%).')
    description = fields.Html('Mô tả công việc (JD)')
    company_id = fields.Many2one('res.company', string='Phòng khám', default=lambda self: self.env.company)
    active = fields.Boolean(default=True)
    is_sample = fields.Boolean('Dữ liệu mẫu', help='Dữ liệu mẫu – sẽ thay bằng khung P/M chuẩn của DMAG.')
    competency_weight_total = fields.Float('Tổng trọng số P2', compute='_compute_weight_totals')
    kpi_weight_total = fields.Float('Tổng trọng số P3', compute='_compute_weight_totals')

    _sql_constraints = [('job_company_uniq', 'unique(job_id, company_id)',
                         'Mỗi chức danh chỉ có một hồ sơ vị trí trong một phòng khám.')]

    @api.depends('job_id.name')
    def _compute_name(self):
        for profile in self:
            profile.name = profile.job_id.name

    @api.depends('competency_line_ids.weight', 'kpi_ids.weight')
    def _compute_weight_totals(self):
        for profile in self:
            profile.competency_weight_total = sum(profile.competency_line_ids.mapped('weight'))
            profile.kpi_weight_total = sum(profile.kpi_ids.mapped('weight'))

    @api.constrains('default_grade_id', 'grade_ids')
    def _check_default_grade(self):
        for profile in self:
            if profile.default_grade_id and profile.default_grade_id not in profile.grade_ids:
                raise ValidationError(_('Bậc khởi điểm phải nằm trong danh sách bậc được phép.'))
