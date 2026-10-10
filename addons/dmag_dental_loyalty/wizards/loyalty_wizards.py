from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.dmag_dental_base.models.dmag_access import check_director


class DmagLoyaltyRedeemWizard(models.TransientModel):
    _name = 'dmag.loyalty.redeem.wizard'
    _description = 'Đổi điểm lấy voucher'

    partner_id = fields.Many2one('res.partner', string='Bệnh nhân', required=True)
    points_balance = fields.Integer('Điểm khả dụng', compute='_compute_info')
    points = fields.Integer('Số điểm đổi', required=True)
    point_value = fields.Float('Giá trị 1 điểm', compute='_compute_info')
    voucher_value = fields.Float('Giá trị voucher', compute='_compute_info')
    approval_needed = fields.Boolean('Cần Quản lý duyệt', compute='_compute_info')
    note = fields.Char('Ghi chú')

    @api.depends('partner_id', 'points')
    def _compute_info(self):
        company = self.env.company
        for wiz in self:
            wiz.points_balance = wiz.partner_id._dmag_points_balance() if wiz.partner_id else 0
            wiz.point_value = company.dmag_loyalty_point_value
            wiz.voucher_value = wiz.points * company.dmag_loyalty_point_value
            wiz.approval_needed = wiz.points > company.dmag_loyalty_approval_points

    def action_redeem(self):
        self.ensure_one()
        voucher = self.env['dmag.loyalty.voucher'].create_from_points(self.partner_id.id, self.points, self.note)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'dmag.loyalty.voucher',
            'res_id': voucher.id,
            'view_mode': 'form',
            'target': 'current',
        }


class DmagLoyaltyAdjustWizard(models.TransientModel):
    _name = 'dmag.loyalty.adjust.wizard'
    _description = 'Điều chỉnh điểm (Giám đốc)'

    partner_id = fields.Many2one('res.partner', string='Bệnh nhân', required=True)
    points = fields.Integer('Số điểm (+/-)', required=True)
    note = fields.Char('Lý do điều chỉnh', required=True)

    def action_adjust(self):
        self.ensure_one()
        check_director(self.env, _('Chỉ Giám đốc / Quản lý cấp cao được điều chỉnh điểm.'))
        if not self.points:
            raise UserError(_('Nhập số điểm điều chỉnh.'))
        self.env['dmag.loyalty.ledger'].create({
            'partner_id': self.partner_id.id,
            'points': self.points,
            'reason': 'adjustment',
            'note': self.note,
            'company_id': (self.partner_id.company_id or self.env.company).id,
        })
        self.partner_id.message_post(body=_('Điều chỉnh %(pts)s điểm – %(note)s – bởi %(user)s',
                                            pts=self.points, note=self.note, user=self.env.user.name))
        return {'type': 'ir.actions.act_window_close'}


class DmagLoyaltyVisitWizard(models.TransientModel):
    _name = 'dmag.loyalty.visit.wizard'
    _description = 'Ưu đãi thành viên tại lượt khám'

    visit_id = fields.Many2one('dmag.dental.visit', string='Lượt khám', required=True)
    patient_id = fields.Many2one(related='visit_id.patient_id')
    tier_id = fields.Many2one(related='visit_id.patient_id.dmag_tier_id', string='Hạng')
    mode = fields.Selection([('voucher', 'Áp voucher'), ('care', 'Dùng quyền lợi gói chăm sóc')],
                            string='Ưu đãi', default='voucher', required=True)
    voucher_code = fields.Char('Mã voucher')
    available_voucher_ids = fields.Many2many('dmag.loyalty.voucher', compute='_compute_available',
                                             string='Voucher đang có')
    procedure_id = fields.Many2one('dmag.dental.procedure', string='Thủ thuật',
                                   domain="[('visit_id', '=', visit_id), ('plan_line_id', '=', False)]")

    @api.depends('visit_id')
    def _compute_available(self):
        Voucher = self.env['dmag.loyalty.voucher'].sudo()
        for wiz in self:
            members = wiz.visit_id.patient_id._dmag_pool_members() if wiz.visit_id else self.env['res.partner']
            wiz.available_voucher_ids = Voucher.search([('partner_id', 'in', members.ids), ('state', '=', 'active')])

    def action_apply(self):
        self.ensure_one()
        if self.mode == 'voucher':
            if not self.voucher_code:
                raise UserError(_('Nhập mã voucher.'))
            self.visit_id.dmag_apply_voucher(self.voucher_code)
        else:
            if not self.procedure_id:
                raise UserError(_('Chọn thủ thuật dùng quyền lợi gói.'))
            self.visit_id.dmag_use_care_entitlement(self.procedure_id.id)
        return {'type': 'ir.actions.act_window_close'}
