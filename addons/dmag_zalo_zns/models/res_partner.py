from odoo import fields, models

from .zns_utils import normalize_phone


class ResPartner(models.Model):
    _inherit = 'res.partner'

    zns_opt_out = fields.Boolean(
        'Từ chối nhận tin Zalo ZNS', tracking=True,
        help='Khách đã yêu cầu không nhận tin chăm sóc qua Zalo. Hệ thống sẽ không gửi ZNS cho khách này.')
    zns_opt_out_date = fields.Datetime('Ngày từ chối nhận tin', readonly=True)
    zns_message_count = fields.Integer('Tin ZNS', compute='_compute_zns_message_count')

    def _compute_zns_message_count(self):
        data = self.env['dmag.zns.message'].sudo()._read_group(
            [('partner_id', 'in', self.ids)], ['partner_id'], ['__count'])
        counts = {partner.id: count for partner, count in data}
        for partner in self:
            partner.zns_message_count = counts.get(partner.id, 0)

    def write(self, vals):
        if 'zns_opt_out' in vals:
            vals['zns_opt_out_date'] = fields.Datetime.now() if vals['zns_opt_out'] else False
        return super().write(vals)

    def _dmag_zns_phone(self):
        """Số nhận ZNS chuẩn 84xxxxxxxxx: ưu tiên SĐT Zalo, rồi di động, rồi điện thoại."""
        self.ensure_one()
        for number in (self.zalo_phone, self.mobile, self.phone):
            phone = normalize_phone(number)
            if phone:
                return phone
        return False

    def action_open_zns_messages(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Tin Zalo ZNS',
            'res_model': 'dmag.zns.message',
            'view_mode': 'tree,form',
            'domain': [('partner_id', '=', self.id)],
        }
