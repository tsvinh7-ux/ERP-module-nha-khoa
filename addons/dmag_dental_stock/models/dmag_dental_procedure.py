from collections import OrderedDict

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class DmagDentalProcedure(models.Model):
    _inherit = 'dmag.dental.procedure'

    lot_ids = fields.Many2many('stock.lot', 'dmag_procedure_stock_lot_rel', 'procedure_id', 'lot_id',
                               string='Serial / lô vật tư',
                               help='Bắt buộc khi định mức có vật tư theo serial (trụ implant…) hoặc theo lô.')
    dmag_lot_product_ids = fields.Many2many('product.product', compute='_compute_dmag_lot_info',
                                            string='Vật tư cần serial / lô')
    dmag_lot_required = fields.Boolean('Cần serial / lô', compute='_compute_dmag_lot_info')
    material_usage_ids = fields.One2many('dmag.material.usage', 'procedure_id', string='Vật tư đã dùng')
    material_cost = fields.Float('Giá vốn vật tư', compute='_compute_material_cost', store=True,
                                 digits='Product Price')

    @api.depends('product_id', 'company_id')
    def _compute_dmag_lot_info(self):
        Bom = self.env['dmag.service.bom']
        for proc in self:
            products = self.env['product.product']
            if proc.product_id:
                bom = Bom._dmag_find(proc.product_id, proc.company_id or self.env.company)
                products = bom.line_ids.mapped('product_id').filtered(lambda p: p.tracking != 'none')
            proc.dmag_lot_product_ids = products
            proc.dmag_lot_required = bool(products)

    @api.depends('material_usage_ids.cost')
    def _compute_material_cost(self):
        for proc in self:
            proc.material_cost = sum(proc.material_usage_ids.mapped('cost'))

    # ------------------------------------------------------------------ định mức
    def _dmag_material_requirements(self):
        """{product: số lượng theo đơn vị tồn kho} theo định mức của dịch vụ."""
        self.ensure_one()
        reqs = OrderedDict()
        bom = self.env['dmag.service.bom']._dmag_find(self.product_id, self.company_id or self.env.company)
        for line in bom.line_ids:
            factor = 1.0
            if line.basis == 'per_tooth':
                factor = len(self.tooth_ids) or self.quantity or 1.0
            qty = line.uom_id._compute_quantity(line.quantity * factor, line.product_id.uom_id)
            reqs[line.product_id] = reqs.get(line.product_id, 0.0) + qty
        return reqs

    def _dmag_check_lots(self):
        Usage = self.env['dmag.material.usage'].sudo()
        for proc in self:
            reqs = proc._dmag_material_requirements()
            for product, qty in reqs.items():
                if product.tracking == 'none':
                    continue
                lots = proc.lot_ids.filtered(lambda l, p=product: l.product_id == p)
                if product.tracking == 'serial':
                    need = int(round(qty))
                    if len(lots) != need:
                        raise UserError(_('Thủ thuật "%(proc)s" cần %(need)s serial cho "%(product)s" '
                                          '(đã chọn %(got)s). Quét / chọn serial trụ implant trước khi hoàn tất.',
                                          proc=proc.display_name, need=need, product=product.display_name,
                                          got=len(lots)))
                    used = Usage.search([('lot_id', 'in', lots.ids)], limit=1)
                    if used:
                        raise ValidationError(_('Serial %(lot)s đã dùng cho bệnh nhân %(patient)s.',
                                                lot=used.lot_id.name, patient=used.patient_id.name))
                elif not lots:
                    raise UserError(_('Chọn số lô cho "%(product)s" của thủ thuật "%(proc)s".',
                                      product=product.display_name, proc=proc.display_name))
            stray = proc.lot_ids.filtered(lambda l: l.product_id not in reqs)
            if stray:
                raise ValidationError(_('Serial / lô %s không thuộc định mức của dịch vụ.',
                                        ', '.join(stray.mapped('name'))))

    def _dmag_consume_materials(self):
        """Ghi nhận vật tư theo định mức và xuất kho tiêu hao (quyền hệ thống)."""
        Usage = self.env['dmag.material.usage'].sudo().with_context(dmag_workflow=True)
        vals_list = []
        for proc in self:
            if proc.material_usage_ids.filtered(lambda u: u.kind == 'bom'):
                continue
            for product, qty in proc._dmag_material_requirements().items():
                base = {'procedure_id': proc.id, 'product_id': product.id, 'kind': 'bom',
                        'user_id': self.env.user.id}
                lots = proc.lot_ids.filtered(lambda l, p=product: l.product_id == p)
                if product.tracking == 'serial':
                    vals_list += [dict(base, quantity=1.0, lot_id=lot.id) for lot in lots]
                elif product.tracking == 'lot':
                    vals_list.append(dict(base, quantity=qty, lot_id=lots[:1].id))
                elif qty > 0:
                    vals_list.append(dict(base, quantity=qty))
        return Usage.create(vals_list) if vals_list else Usage

    def action_done(self):
        todo = self.filtered(lambda p: p.state == 'draft')
        todo._dmag_check_lots()
        res = super().action_done()
        todo.filtered(lambda p: p.state == 'done')._dmag_consume_materials()
        return res

    # ------------------------------------------------------------------ workspace
    def _workspace_dict(self):
        res = super()._workspace_dict()
        res.update({
            'lot_required': self.dmag_lot_required,
            'lots': [{'id': lot.id, 'name': lot.name, 'product': lot.product_id.display_name}
                     for lot in self.sudo().lot_ids],
            'material_cost': self.material_cost,
        })
        return res

    @api.model
    def add_from_workspace(self, visit_id, product_id, teeth=None, surfaces=None, plan_line_id=False,
                           done=True, lot_ids=None):
        if not lot_ids:
            return super().add_from_workspace(visit_id, product_id, teeth=teeth, surfaces=surfaces,
                                              plan_line_id=plan_line_id, done=done)
        res = super().add_from_workspace(visit_id, product_id, teeth=teeth, surfaces=surfaces,
                                         plan_line_id=plan_line_id, done=False)
        proc = self.browse(res['id'])
        proc.lot_ids = [(6, 0, lot_ids)]
        if done:
            proc.action_done()
        return proc._workspace_dict()

    def action_open_material_usage(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Vật tư đã dùng'),
            'res_model': 'dmag.material.usage',
            'view_mode': 'tree,form',
            'domain': [('procedure_id', '=', self.id)],
            'context': {'default_procedure_id': self.id},
        }
