from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.dmag_dental_base.models.dmag_access import is_director, is_workflow


class DmagCommissionStatement(models.Model):
    """Bảng kê thủ thuật phí / hoa hồng tháng của một người hưởng."""
    _name = 'dmag.commission.statement'
    _description = 'Bảng kê hoa hồng tháng'
    _inherit = ['mail.thread']
    _order = 'date_from desc, beneficiary'

    name = fields.Char('Bảng kê', compute='_compute_name', store=True)
    company_id = fields.Many2one('res.company', string='Phòng khám', required=True, index=True,
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    date_from = fields.Date('Tháng', required=True)
    date_to = fields.Date('Đến ngày', compute='_compute_date_to', store=True)
    user_id = fields.Many2one('res.users', string='Người hưởng (tài khoản)', index=True)
    partner_id = fields.Many2one('res.partner', string='Người hưởng (đối tác)', index=True)
    beneficiary = fields.Char('Người hưởng', compute='_compute_name', store=True)
    line_ids = fields.One2many('dmag.commission.line', 'statement_id', string='Chi tiết')
    total = fields.Monetary('Tổng hợp lệ', compute='_compute_totals', store=True)
    void_total = fields.Monetary('Đã hủy (cầu chì y đức)', compute='_compute_totals', store=True)
    state = fields.Selection([('draft', 'Nháp'), ('confirmed', 'Đã chốt')], default='draft',
                             required=True, tracking=True, string='Trạng thái')

    @api.depends('date_from')
    def _compute_date_to(self):
        for st in self:
            st.date_to = st.date_from and st.date_from + relativedelta(day=31)

    @api.depends('user_id', 'partner_id', 'date_from')
    def _compute_name(self):
        for st in self:
            st.beneficiary = st.user_id.name or st.partner_id.name or ''
            st.name = _('Hoa hồng %(month)s – %(who)s',
                        month=st.date_from.strftime('%m/%Y') if st.date_from else '', who=st.beneficiary)

    @api.depends('line_ids.amount', 'line_ids.state')
    def _compute_totals(self):
        for st in self:
            st.total = sum(st.line_ids.filtered(lambda l: l.state == 'valid').mapped('amount'))
            st.void_total = sum(st.line_ids.filtered(lambda l: l.state == 'void').mapped('amount'))

    def write(self, vals):
        if not is_workflow(self.env) and not is_director(self.env) and any(s.state == 'confirmed' for s in self):
            raise AccessError(_('Bảng kê đã chốt – chỉ Giám đốc / Quản lý cấp cao được sửa.'))
        return super().write(vals)

    def unlink(self):
        if any(s.state == 'confirmed' for s in self) and not is_director(self.env):
            raise AccessError(_('Bảng kê đã chốt – chỉ Giám đốc / Quản lý cấp cao được xóa.'))
        return super().unlink()

    def action_confirm(self):
        self.with_context(dmag_workflow=True).write({'state': 'confirmed'})
        return True

    def action_reset_draft(self):
        if not is_director(self.env):
            raise AccessError(_('Chỉ Giám đốc / Quản lý cấp cao được mở lại bảng kê.'))
        self.with_context(dmag_workflow=True).write({'state': 'draft'})
        return True

    @api.model
    def _generate(self, company, month):
        """Gom các dòng chưa vào bảng kê trong tháng theo người hưởng."""
        month = fields.Date.to_date(month).replace(day=1)
        end = month + relativedelta(day=31)
        Line = self.env['dmag.commission.line'].sudo()
        lines = Line.search([('company_id', '=', company.id), ('date', '>=', month), ('date', '<=', end),
                             ('statement_id', '=', False)])
        if not lines:
            raise UserError(_('Không có dòng hoa hồng mới trong tháng %s.', month.strftime('%m/%Y')))
        groups = {}
        for line in lines:
            groups.setdefault((line.user_id.id, line.partner_id.id if not line.user_id else False), Line)
            groups[(line.user_id.id, line.partner_id.id if not line.user_id else False)] |= line
        statements = self.browse()
        for (user_id, partner_id), group_lines in groups.items():
            statement = self.search([('company_id', '=', company.id), ('date_from', '=', month),
                                     ('user_id', '=', user_id), ('partner_id', '=', partner_id),
                                     ('state', '=', 'draft')], limit=1)
            if not statement:
                statement = self.create({'company_id': company.id, 'date_from': month,
                                         'user_id': user_id, 'partner_id': partner_id})
            group_lines.with_context(dmag_workflow=True).write({'statement_id': statement.id})
            statements |= statement
        return statements
