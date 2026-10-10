from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .dmag_job_grade import TRACKS


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    dmag_profile_id = fields.Many2one(
        'dmag.job.position.profile', string='Hồ sơ vị trí 3P', compute='_compute_dmag_profile_id',
        store=True, readonly=False, groups='hr.group_hr_user')
    dmag_track = fields.Selection(TRACKS, string='Ngạch', compute='_compute_dmag_track', store=True,
                                  readonly=False, groups='hr.group_hr_user')
    dmag_grade_id = fields.Many2one('dmag.job.grade', string='Bậc', tracking=True, groups='hr.group_hr_user',
                                    compute='_compute_dmag_grade_id', store=True, readonly=False,
                                    domain="[('track', '=', dmag_track)]")
    dmag_p1_amount = fields.Monetary('P1 – Lương vị trí', compute='_compute_dmag_p1_amount', store=True,
                                     readonly=False, tracking=True, groups='hr.group_hr_user',
                                     currency_field='currency_id',
                                     help='Mặc định = mức chuẩn (mid) của bậc; điều chỉnh trong khung min–max.')
    dmag_assessment_ids = fields.One2many('dmag.competency.assessment', 'employee_id',
                                          string='Đánh giá năng lực', groups='hr.group_hr_user')
    dmag_kpi_result_ids = fields.One2many('dmag.kpi.result', 'employee_id', string='Kết quả KPI',
                                          groups='hr.group_hr_user')
    dmag_p2_coefficient = fields.Float('Hệ số P2 hiện tại', compute='_compute_dmag_p2_coefficient',
                                       groups='hr.group_hr_user')

    @api.depends('job_id')
    def _compute_dmag_profile_id(self):
        Profile = self.env['dmag.job.position.profile'].sudo()
        for employee in self:
            if employee.job_id:
                employee.dmag_profile_id = Profile.search([
                    ('job_id', '=', employee.job_id.id),
                    ('company_id', 'in', (employee.company_id.id, False))], limit=1)
            elif not employee.dmag_profile_id:
                employee.dmag_profile_id = False

    @api.depends('dmag_profile_id')
    def _compute_dmag_track(self):
        for employee in self:
            employee.dmag_track = employee.dmag_profile_id.track or employee.dmag_track or 'P'

    @api.depends('dmag_profile_id')
    def _compute_dmag_grade_id(self):
        for employee in self:
            grade = employee.dmag_grade_id
            allowed = employee.dmag_profile_id.grade_ids
            if not grade or (allowed and grade not in allowed):
                employee.dmag_grade_id = employee.dmag_profile_id.default_grade_id

    @api.depends('dmag_grade_id')
    def _compute_dmag_p1_amount(self):
        for employee in self:
            employee.dmag_p1_amount = employee.dmag_grade_id.wage_mid

    def _compute_dmag_p2_coefficient(self):
        today = fields.Date.context_today(self)
        for employee in self:
            employee.dmag_p2_coefficient = employee._dmag_get_p2_coefficient(today)

    def _dmag_get_assessment(self, date):
        self.ensure_one()
        return self.env['dmag.competency.assessment'].sudo().search([
            ('employee_id', '=', self.id), ('state', '=', 'confirmed'), ('date', '<=', date),
        ], order='date desc, id desc', limit=1)

    def _dmag_get_p2_coefficient(self, date):
        self.ensure_one()
        assessment = self._dmag_get_assessment(date)
        return assessment.p2_coefficient if assessment else 1.0

    @api.constrains('dmag_grade_id', 'dmag_p1_amount', 'dmag_profile_id')
    def _check_dmag_grade(self):
        for employee in self.sudo():
            grade = employee.dmag_grade_id
            if not grade:
                continue
            profile = employee.dmag_profile_id
            if profile.grade_ids and grade not in profile.grade_ids:
                raise ValidationError(_('Bậc %(grade)s không thuộc các bậc được phép của vị trí %(job)s.',
                                        grade=grade.code, job=profile.name))
            if grade.wage_max and not grade.wage_min <= employee.dmag_p1_amount <= grade.wage_max:
                raise ValidationError(_('P1 của %(emp)s phải nằm trong khung %(min)s – %(max)s của bậc %(grade)s.',
                                        emp=employee.name, min=grade.wage_min, max=grade.wage_max,
                                        grade=grade.code))
