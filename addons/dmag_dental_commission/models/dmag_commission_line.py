from odoo import _, api, fields, models
from odoo.exceptions import AccessError

from odoo.addons.dmag_dental_base.models.dmag_access import is_director, is_workflow

from .dmag_commission_rule import ROLES


class DmagCommissionLine(models.Model):
    """Một khoản thủ thuật phí / hoa hồng phát sinh trên tiền thực thu.

    Dòng chỉ được sinh bởi hệ thống (khi thu tiền / đảo hóa đơn), không ai nhập tay.
    Dòng dương = phát sinh, dòng âm = đảo khi hóa đơn bị đảo / hủy đối trừ.
    """
    _name = 'dmag.commission.line'
    _description = 'Thủ thuật phí / hoa hồng'
    _order = 'date desc, id desc'

    name = fields.Char('Diễn giải', required=True)
    company_id = fields.Many2one('res.company', string='Phòng khám', required=True, index=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    date = fields.Date('Ngày ghi nhận', required=True, index=True, default=fields.Date.context_today)
    visit_id = fields.Many2one('dmag.dental.visit', string='Lượt khám', index=True, ondelete='restrict')
    procedure_id = fields.Many2one('dmag.dental.procedure', string='Thủ thuật', index=True, ondelete='restrict')
    patient_id = fields.Many2one('res.partner', string='Bệnh nhân')
    product_id = fields.Many2one('product.product', string='Dịch vụ')
    role = fields.Selection(ROLES, string='Vai trò', required=True, index=True)
    rule_id = fields.Many2one('dmag.commission.rule', string='Quy tắc', ondelete='restrict')
    user_id = fields.Many2one('res.users', string='Người hưởng (tài khoản)', index=True)
    practitioner_id = fields.Many2one('dmag.dental.practitioner', string='Nhân sự lâm sàng')
    partner_id = fields.Many2one('res.partner', string='Người hưởng (đối tác)', index=True)
    employee_id = fields.Many2one('hr.employee', string='Nhân viên', index=True)
    beneficiary = fields.Char('Người hưởng', compute='_compute_beneficiary', store=True)
    base_amount = fields.Monetary('Cơ sở tính')
    rate = fields.Float('Tỷ lệ (%)', digits=(16, 2))
    amount = fields.Monetary('Số tiền')
    kind = fields.Selection([('accrual', 'Phát sinh'), ('reversal', 'Đảo / giảm trừ')],
                            string='Loại', default='accrual', required=True)
    state = fields.Selection([('valid', 'Hợp lệ'), ('void', 'Hủy – cầu chì y đức')],
                             string='Trạng thái', default='valid', required=True, index=True)
    void_reason = fields.Char('Lý do hủy')
    statement_id = fields.Many2one('dmag.commission.statement', string='Bảng kê', index=True,
                                   ondelete='set null')

    @api.depends('user_id', 'partner_id', 'practitioner_id')
    def _compute_beneficiary(self):
        for line in self:
            line.beneficiary = line.practitioner_id.name or line.user_id.name or line.partner_id.name or ''

    def write(self, vals):
        if not is_workflow(self.env) and not is_director(self.env):
            raise AccessError(_('Thủ thuật phí / hoa hồng do hệ thống tính – chỉ Giám đốc / Quản lý cấp cao được sửa.'))
        return super().write(vals)

    def unlink(self):
        if not is_director(self.env):
            raise AccessError(_('Chỉ Giám đốc / Quản lý cấp cao được xóa dòng hoa hồng.'))
        return super().unlink()

    @api.model
    def _dmag_amount_for_employee(self, employee, date_from, date_to):
        """Tổng hoa hồng hợp lệ của nhân viên trong kỳ – nguồn P3 cho dmag_hr_3p (gọi mềm)."""
        domain = [('state', '=', 'valid'), ('date', '>=', date_from), ('date', '<=', date_to)]
        if employee.user_id:
            domain += ['|', ('employee_id', '=', employee.id), ('user_id', '=', employee.user_id.id)]
        else:
            domain.append(('employee_id', '=', employee.id))
        return sum(self.sudo().search(domain).mapped('amount'))
