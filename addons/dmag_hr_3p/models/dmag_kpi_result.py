from odoo import _, api, fields, models
from odoo.exceptions import AccessError

from odoo.addons.dmag_dental_base.models.dmag_access import is_director, is_workflow


class DmagKpiResult(models.Model):
    """Kết quả một chỉ tiêu KPI của nhân viên trong kỳ (tháng)."""
    _name = 'dmag.kpi.result'
    _description = 'Kết quả KPI (P3)'
    _order = 'date_from desc, employee_id, sequence, id'

    employee_id = fields.Many2one('hr.employee', string='Nhân viên', required=True, index=True)
    company_id = fields.Many2one(related='employee_id.company_id', store=True, string='Phòng khám')
    kpi_id = fields.Many2one('dmag.kpi.definition', string='Chỉ tiêu', required=True, ondelete='restrict')
    sequence = fields.Integer(related='kpi_id.sequence', store=True)
    date_from = fields.Date('Từ ngày', required=True)
    date_to = fields.Date('Đến ngày', required=True)
    weight = fields.Float('Trọng số (%)')
    target = fields.Float('Mục tiêu')
    unit = fields.Char(related='kpi_id.unit')
    data_source = fields.Selection(related='kpi_id.data_source')
    actual = fields.Float('Thực tế', digits=(16, 2))
    is_auto = fields.Boolean('Tự tính', readonly=True,
                             help='Giá trị lấy tự động từ dữ liệu – không ai phải nhập tay.')
    achievement = fields.Float('% hoàn thành', compute='_compute_achievement', store=True, digits=(16, 1))
    sheet_id = fields.Many2one('dmag.pay3p.sheet', string='Bảng 3P', ondelete='set null', index=True)

    _sql_constraints = [('kpi_period_uniq', 'unique(employee_id, kpi_id, date_from)',
                         'Mỗi chỉ tiêu chỉ có một kết quả cho một nhân viên trong một kỳ.')]

    @api.depends('actual', 'target', 'kpi_id.direction', 'company_id.dmag_kpi_cap')
    def _compute_achievement(self):
        for result in self:
            kpi = result.kpi_id
            if not kpi:
                result.achievement = 0.0
                continue
            target = result.target or kpi.target
            if kpi.direction == 'lower':
                pct = (target * 100.0 / result.actual) if result.actual > 0 else 100.0
            else:
                pct = result.actual * 100.0 / target if target else 0.0
            cap = result.company_id.dmag_kpi_cap or 120.0
            result.achievement = max(0.0, min(cap, pct))

    def action_refresh(self):
        for result in self:
            value = result.kpi_id._compute_actual(result.employee_id, result.date_from, result.date_to)
            if value is not None:
                result.with_context(dmag_workflow=True).write({'actual': value, 'is_auto': True})
        return True

    def write(self, vals):
        if not is_workflow(self.env) and not is_director(self.env):
            if any(r.sheet_id.state in ('approved', 'exported') for r in self):
                raise AccessError(_('Bảng lương 3P đã duyệt – chỉ Giám đốc / Quản lý cấp cao được sửa KPI.'))
            if 'actual' in vals and any(r.is_auto for r in self):
                raise AccessError(_('KPI tự tính từ dữ liệu – không sửa tay (chỉ Giám đốc).'))
        return super().write(vals)
