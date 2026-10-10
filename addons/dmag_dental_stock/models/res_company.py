from odoo import _, fields, models
from odoo.exceptions import UserError


class ResCompany(models.Model):
    _inherit = 'res.company'

    dmag_cogs_threshold = fields.Float(
        'Ngưỡng giá vốn vật tư & labo (% doanh thu)', default=22.0,
        help='KPI Q-Summit: giá vốn vật tư + labo ≤ 22% doanh thu. Vượt ngưỡng → cảnh báo đỏ trên Buồng lái.')
    dmag_consumption_location_id = fields.Many2one(
        'stock.location', string='Địa điểm "Tiêu hao lâm sàng"',
        help='Vật tư dùng cho thủ thuật được chuyển từ kho phòng khám tới địa điểm này. Để trống: tự tạo.')

    def _dmag_consumption_setup(self):
        """(loại hoạt động, kho nguồn, địa điểm tiêu hao) – tự tạo nếu chưa có. Chạy quyền hệ thống."""
        self.ensure_one()
        company = self.sudo()
        warehouse = self.env['stock.warehouse'].sudo().search([('company_id', '=', company.id)], limit=1)
        if not warehouse:
            raise UserError(_('Phòng khám %s chưa có kho vật tư.', company.name))
        location = company.dmag_consumption_location_id
        if not location:
            Location = self.env['stock.location'].sudo()
            location = Location.search([('dmag_is_clinical_consumption', '=', True),
                                        ('company_id', '=', company.id)], limit=1)
            if not location:
                location = Location.create({
                    'name': _('Tiêu hao lâm sàng'),
                    'usage': 'inventory',
                    'location_id': self.env.ref('stock.stock_location_locations_virtual').id,
                    'company_id': company.id,
                    'dmag_is_clinical_consumption': True,
                })
            company.dmag_consumption_location_id = location
        PickingType = self.env['stock.picking.type'].sudo()
        ptype = PickingType.search([('dmag_is_clinical_consumption', '=', True),
                                    ('warehouse_id', '=', warehouse.id)], limit=1)
        if not ptype:
            ptype = PickingType.create({
                'name': _('Tiêu hao lâm sàng'),
                'code': 'outgoing',
                'sequence_code': 'TH',
                'warehouse_id': warehouse.id,
                'company_id': company.id,
                'default_location_src_id': warehouse.lot_stock_id.id,
                'default_location_dest_id': location.id,
                'use_existing_lots': True,
                'use_create_lots': False,
                'create_backorder': 'never',
                'dmag_is_clinical_consumption': True,
            })
        return ptype, warehouse.lot_stock_id, location
