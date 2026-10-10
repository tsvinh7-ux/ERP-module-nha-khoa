from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from odoo.addons.dmag_dental_base.models.dmag_access import is_director, is_workflow


class DmagCompetencyAssessment(models.Model):
    """Đánh giá năng lực theo kỳ → hệ số P2."""
    _name = 'dmag.competency.assessment'
    _description = 'Đánh giá năng lực (P2)'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'

    name = fields.Char('Kỳ đánh giá', required=True, default=lambda self: _('Đánh giá năng lực'))
    employee_id = fields.Many2one('hr.employee', string='Nhân viên', required=True, index=True, tracking=True)
    company_id = fields.Many2one(related='employee_id.company_id', store=True, string='Phòng khám')
    profile_id = fields.Many2one(related='employee_id.dmag_profile_id', string='Vị trí')
    date = fields.Date('Ngày hiệu lực', required=True, default=fields.Date.context_today, tracking=True)
    assessor_id = fields.Many2one('res.users', string='Người đánh giá', default=lambda self: self.env.user)
    line_ids = fields.One2many('dmag.competency.assessment.line', 'assessment_id', string='Tiêu chí')
    score = fields.Float('Điểm bình quân (1–5)', compute='_compute_score', store=True, digits=(16, 2))
    p2_coefficient = fields.Float('Hệ số P2', compute='_compute_score', store=True, digits=(16, 2))
    state = fields.Selection([('draft', 'Nháp'), ('confirmed', 'Đã chốt')], default='draft',
                             required=True, tracking=True, string='Trạng thái')
    note = fields.Text('Nhận xét')

    @api.depends('line_ids.score', 'line_ids.weight', 'company_id.dmag_p2_standard_score')
    def _compute_score(self):
        for assessment in self:
            lines = assessment.line_ids
            total_weight = sum(lines.mapped('weight'))
            if total_weight:
                score = sum(l.score * l.weight for l in lines) / total_weight
            elif lines:
                score = sum(lines.mapped('score')) / len(lines)
            else:
                score = 0.0
            standard = assessment.company_id.dmag_p2_standard_score or 3.0
            assessment.score = score
            assessment.p2_coefficient = round(score / standard, 2) if score else 0.0

    def action_prefill(self):
        """Nạp tiêu chí theo hồ sơ vị trí; tiêu chí lâm sàng gợi ý điểm từ hồ sơ bác sĩ / phụ tá."""
        for assessment in self:
            profile = assessment.employee_id.sudo().dmag_profile_id
            if not profile:
                raise UserError(_('Nhân viên %s chưa có hồ sơ vị trí 3P.', assessment.employee_id.name))
            existing = assessment.line_ids.mapped('competency_id')
            vals = []
            for pos_line in profile.competency_line_ids.filtered(lambda l: l.competency_id not in existing):
                vals.append((0, 0, {
                    'competency_id': pos_line.competency_id.id,
                    'weight': pos_line.weight,
                    'score': assessment._suggest_score(pos_line.competency_id) or pos_line.required_level,
                }))
            assessment.line_ids = vals
        return True

    def _suggest_score(self, competency):
        self.ensure_one()
        if competency.basis == 'manual':
            return 0
        practitioner = self.env['dmag.dental.practitioner'].sudo().search(
            [('employee_id', '=', self.employee_id.id)], limit=1)
        if not practitioner and self.employee_id.user_id:
            practitioner = self.env['dmag.dental.practitioner'].sudo().search(
                [('user_id', '=', self.employee_id.user_id.id)], limit=1)
        if not practitioner:
            return 1
        if competency.basis == 'clinical_level':
            return min(5, (practitioner.clinical_level_id.level or 0) + 2) if practitioner.clinical_level_id else 1
        ok = practitioner.license_state in ('valid', 'expiring') and \
            not (competency.practice_scope_ids - practitioner.scope_ids)
        return 5 if ok else 1

    def action_confirm(self):
        for assessment in self:
            if not assessment.line_ids:
                raise UserError(_('Chưa có tiêu chí nào được chấm.'))
        self.with_context(dmag_workflow=True).write({'state': 'confirmed'})
        return True

    def action_reset_draft(self):
        if not is_director(self.env):
            raise AccessError(_('Chỉ Giám đốc / Quản lý cấp cao được mở lại đánh giá đã chốt.'))
        self.with_context(dmag_workflow=True).write({'state': 'draft'})
        return True

    def write(self, vals):
        if not is_workflow(self.env) and not is_director(self.env) and any(a.state == 'confirmed' for a in self):
            raise AccessError(_('Đánh giá năng lực đã chốt – chỉ Giám đốc / Quản lý cấp cao được sửa.'))
        return super().write(vals)


class DmagCompetencyAssessmentLine(models.Model):
    _name = 'dmag.competency.assessment.line'
    _description = 'Điểm tiêu chí năng lực'

    assessment_id = fields.Many2one('dmag.competency.assessment', required=True, ondelete='cascade', index=True)
    competency_id = fields.Many2one('dmag.competency', string='Tiêu chí', required=True)
    weight = fields.Float('Trọng số (%)')
    score = fields.Integer('Điểm (1–5)', default=3)
    note = fields.Char('Minh chứng / nhận xét')

    @api.constrains('score')
    def _check_score(self):
        for line in self:
            if not 1 <= line.score <= 5:
                raise ValidationError(_('Điểm năng lực phải từ 1 đến 5.'))

    def write(self, vals):
        if not is_workflow(self.env) and not is_director(self.env) and \
                any(l.assessment_id.state == 'confirmed' for l in self):
            raise AccessError(_('Đánh giá năng lực đã chốt – chỉ Giám đốc / Quản lý cấp cao được sửa.'))
        return super().write(vals)
