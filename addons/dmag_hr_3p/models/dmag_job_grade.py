from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

TRACKS = [('P', 'Ngạch chuyên môn (P)'), ('M', 'Ngạch quản lý (M)')]
MAX_LEVEL = {'P': 6, 'M': 4}


class DmagJobGrade(models.Model):
    """Bậc trong khung ngạch P/M – mỗi bậc có khung lương P1 (min / mid / max)."""
    _name = 'dmag.job.grade'
    _description = 'Ngạch bậc P/M'
    _order = 'track desc, level, id'

    name = fields.Char('Tên bậc', required=True, translate=True)
    code = fields.Char('Mã bậc', required=True, help='P1…P6, M1…M4 – dùng làm khóa khi nhập khung chuẩn.')
    track = fields.Selection(TRACKS, string='Ngạch', required=True, default='P')
    level = fields.Integer('Bậc', required=True, default=1)
    description = fields.Text('Mô tả / tiêu chuẩn bậc', translate=True)
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id, required=True)
    wage_min = fields.Monetary('P1 tối thiểu')
    wage_mid = fields.Monetary('P1 chuẩn (mid)')
    wage_max = fields.Monetary('P1 tối đa')
    company_id = fields.Many2one('res.company', string='Phòng khám',
                                 help='Để trống: dùng chung cho cả chuỗi.')
    active = fields.Boolean(default=True)
    is_sample = fields.Boolean('Dữ liệu mẫu', help='Dữ liệu mẫu – sẽ thay bằng khung P/M chuẩn của DMAG.')

    _sql_constraints = [
        ('code_company_uniq', 'unique(code, company_id)', 'Mã bậc phải là duy nhất trong một phòng khám.'),
    ]

    @api.constrains('track', 'level')
    def _check_level(self):
        for grade in self:
            if not 1 <= grade.level <= MAX_LEVEL[grade.track]:
                raise ValidationError(_('Ngạch %(track)s chỉ có bậc 1 đến %(max)s.',
                                        track=grade.track, max=MAX_LEVEL[grade.track]))

    @api.constrains('wage_min', 'wage_mid', 'wage_max')
    def _check_band(self):
        for grade in self:
            if grade.wage_max and not (grade.wage_min <= grade.wage_mid <= grade.wage_max):
                raise ValidationError(_('Khung P1 của %s phải thỏa: tối thiểu ≤ chuẩn ≤ tối đa.', grade.code))

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for grade in self:
            grade.display_name = f'{grade.code} – {grade.name}' if grade.code else grade.name
