from odoo import fields, models


class DmagCommissionStatementWizard(models.TransientModel):
    _name = 'dmag.commission.statement.wizard'
    _description = 'Lập bảng kê hoa hồng tháng'

    month = fields.Date('Tháng', required=True,
                        default=lambda self: fields.Date.context_today(self).replace(day=1))
    company_id = fields.Many2one('res.company', string='Phòng khám', required=True,
                                 default=lambda self: self.env.company)

    def action_generate(self):
        self.ensure_one()
        statements = self.env['dmag.commission.statement']._generate(self.company_id, self.month)
        return {
            'type': 'ir.actions.act_window',
            'name': 'Bảng kê hoa hồng',
            'res_model': 'dmag.commission.statement',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', statements.ids)],
        }
