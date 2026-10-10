from odoo import _, fields, models

from odoo.addons.dmag_dental_base.models.dmag_access import check_director


class DmagJourneyExecution(models.Model):
    """Nhật ký thực thi luật hành trình – đảm bảo mỗi luật chỉ chạy 1 lần cho mỗi đối tượng / kỳ."""
    _name = 'dmag.journey.execution'
    _description = 'Nhật ký điểm chạm hành trình'
    _order = 'id desc'
    _rec_name = 'rule_id'

    rule_id = fields.Many2one('dmag.journey.rule', string='Luật', required=True, index=True,
                              ondelete='cascade', readonly=True)
    trigger = fields.Selection(related='rule_id.trigger', store=True)
    stage = fields.Selection(related='rule_id.stage', store=True)
    dedupe_key = fields.Char('Khóa chống trùng', required=True, readonly=True, index=True)
    company_id = fields.Many2one('res.company', string='Phòng khám', index=True, readonly=True)
    visit_id = fields.Many2one('dmag.dental.visit', string='Lượt khám', index=True, readonly=True,
                               ondelete='set null')
    partner_id = fields.Many2one('res.partner', string='Khách hàng', index=True, readonly=True)
    state = fields.Selection([
        ('done', 'Đã thực hiện'),
        ('skipped', 'Bỏ qua'),
        ('error', 'Lỗi'),
    ], string='Kết quả', readonly=True, default='done')
    message_id = fields.Many2one('dmag.zns.message', string='Tin ZNS', readonly=True)
    message_state = fields.Selection(related='message_id.state', string='Trạng thái tin')
    activity_id = fields.Many2one('mail.activity', string='Việc CSKH', readonly=True, ondelete='set null')
    nps_response_id = fields.Many2one('dmag.nps.response', string='Phiếu NPS', readonly=True, ondelete='set null')
    note = fields.Char('Ghi chú', readonly=True)

    _sql_constraints = [
        ('rule_key_uniq', 'unique(rule_id, dedupe_key)', 'Điểm chạm này đã được thực hiện.'),
    ]

    def write(self, vals):
        if not self.env.su:
            check_director(self.env, _('Nhật ký hành trình chỉ đọc.'))
        return super().write(vals)

    def unlink(self):
        check_director(self.env, _('Chỉ Giám đốc / Quản lý cấp cao được xóa nhật ký hành trình '
                                   '(xóa để cho phép chạy lại điểm chạm).'))
        return super().unlink()
