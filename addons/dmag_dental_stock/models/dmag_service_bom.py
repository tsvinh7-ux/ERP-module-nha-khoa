from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class DmagServiceBom(models.Model):
    """Định mức vật tư cho một dịch vụ nha khoa."""
    _name = 'dmag.service.bom'
    _description = 'Định mức vật tư dịch vụ'
    _inherit = ['mail.thread']
    _order = 'product_tmpl_id'

    product_tmpl_id = fields.Many2one('product.template', string='Dịch vụ', required=True, index=True,
                                      domain=[('is_dental_service', '=', True)], tracking=True)
    company_id = fields.Many2one('res.company', string='Phòng khám', index=True,
                                 default=lambda self: self.env.company,
                                 help='Để trống: dùng chung cho mọi phòng khám / chi nhánh.')
    line_ids = fields.One2many('dmag.service.bom.line', 'bom_id', string='Vật tư', copy=True)
    has_tracked = fields.Boolean('Có vật tư theo serial / lô', compute='_compute_has_tracked', store=True)
    active = fields.Boolean(default=True)
    note = fields.Text('Ghi chú')
    standard_cost = fields.Float('Giá vốn định mức / 1 răng', compute='_compute_standard_cost',
                                 digits='Product Price', help='Theo giá vốn hiện tại của vật tư.')

    @api.depends('line_ids.product_id.tracking')
    def _compute_has_tracked(self):
        for bom in self:
            bom.has_tracked = any(t != 'none' for t in bom.line_ids.mapped('product_id.tracking'))

    @api.depends('line_ids.quantity', 'line_ids.uom_id', 'line_ids.product_id')
    def _compute_standard_cost(self):
        for bom in self:
            company = bom.company_id or self.env.company
            bom.standard_cost = sum(
                line.uom_id._compute_quantity(line.quantity, line.product_id.uom_id)
                * line.product_id.with_company(company).standard_price
                for line in bom.line_ids if line.product_id and line.uom_id)

    @api.depends('product_tmpl_id')
    def _compute_display_name(self):
        for bom in self:
            bom.display_name = _('Định mức: %s', bom.product_tmpl_id.name or '')

    @api.constrains('product_tmpl_id', 'company_id', 'active')
    def _check_unique(self):
        for bom in self.filtered('active'):
            if self.search_count([('id', '!=', bom.id), ('product_tmpl_id', '=', bom.product_tmpl_id.id),
                                  ('company_id', '=', bom.company_id.id)]):
                raise ValidationError(_('Dịch vụ "%s" đã có định mức.', bom.product_tmpl_id.name))

    @api.model
    def _dmag_find(self, product, company):
        """Định mức áp dụng: ưu tiên của phòng khám, sau đó định mức dùng chung."""
        boms = self.sudo().search([('product_tmpl_id', '=', product.product_tmpl_id.id),
                                   ('company_id', 'in', [company.id, False])])
        return boms.filtered(lambda b: b.company_id == company)[:1] or boms[:1]


class DmagServiceBomLine(models.Model):
    _name = 'dmag.service.bom.line'
    _description = 'Dòng định mức vật tư'
    _order = 'sequence, id'

    bom_id = fields.Many2one('dmag.service.bom', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    product_id = fields.Many2one('product.product', string='Vật tư', required=True,
                                 domain=[('type', 'in', ('product', 'consu'))])
    tracking = fields.Selection(related='product_id.tracking', string='Theo dõi')
    quantity = fields.Float('Số lượng', required=True, default=1.0, digits='Product Unit of Measure')
    basis = fields.Selection([
        ('per_tooth', 'Mỗi răng'),
        ('per_procedure', 'Mỗi lần thủ thuật'),
    ], string='Tính theo', required=True, default='per_procedure')
    uom_id = fields.Many2one('uom.uom', string='Đơn vị', required=True,
                             compute='_compute_uom_id', store=True, readonly=False, precompute=True)
    uom_category_id = fields.Many2one(related='product_id.uom_id.category_id')

    @api.depends('product_id')
    def _compute_uom_id(self):
        for line in self:
            if line.product_id and (not line.uom_id or line.uom_id.category_id != line.product_id.uom_id.category_id):
                line.uom_id = line.product_id.uom_id

    @api.constrains('quantity', 'uom_id', 'product_id')
    def _check_line(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError(_('Số lượng định mức phải lớn hơn 0.'))
            if line.uom_id.category_id != line.product_id.uom_id.category_id:
                raise ValidationError(_('Đơn vị của "%s" không cùng nhóm với đơn vị tồn kho.', line.product_id.name))
            if line.product_id.tracking == 'serial' and line.quantity != int(line.quantity):
                raise ValidationError(_('Vật tư theo serial (%s) phải có số lượng nguyên.', line.product_id.name))
