from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from odoo.addons.dmag_dental_base.models.dmag_access import check_director, check_discount, is_director, is_workflow

PRICE_FIELDS = {'price_unit', 'discount', 'quantity', 'product_id', 'plan_line_id'}


class DmagDentalProcedure(models.Model):
    """Thủ thuật đã thực hiện trong một lượt khám.

    Khi xác nhận hoàn tất:
    * cập nhật sơ đồ răng (bệnh lý được xử lý → lưu trữ; ghi tình trạng sau điều trị),
    * đánh dấu dòng kế hoạch điều trị đã làm,
    * ghi số lượng "đã thực hiện" lên đơn bán để thu tiền theo tiến độ.
    """
    _name = 'dmag.dental.procedure'
    _description = 'Thủ thuật nha khoa'
    _order = 'id desc'

    visit_id = fields.Many2one('dmag.dental.visit', string='Lượt khám', required=True,
                               ondelete='cascade', index=True)
    patient_id = fields.Many2one(related='visit_id.patient_id', store=True, index=True)
    company_id = fields.Many2one(related='visit_id.company_id', store=True)
    plan_line_id = fields.Many2one('dmag.treatment.plan.line', string='Dòng kế hoạch',
                                   domain="[('plan_id.patient_id', '=', patient_id), ('state', '=', 'todo'),"
                                          " ('option_id.is_accepted', '=', True)]")
    product_id = fields.Many2one('product.product', string='Dịch vụ', required=True,
                                 domain=[('is_dental_service', '=', True)])
    tooth_ids = fields.Many2many('dmag.dental.tooth', string='Răng')
    surface_ids = fields.Many2many('dmag.dental.surface', string='Mặt răng')
    quantity = fields.Float('Số lượng', default=1.0, required=True)
    price_unit = fields.Float('Đơn giá', digits='Product Price')
    discount = fields.Float('Giảm (%)', digits='Discount')
    amount = fields.Float('Thành tiền', compute='_compute_amount', store=True, digits='Product Price')
    doctor_id = fields.Many2one('dmag.dental.practitioner', string='Bác sĩ thực hiện',
                                domain=[('role', '=', 'doctor')])
    assistant_id = fields.Many2one('dmag.dental.practitioner', string='Phụ tá',
                                   domain=[('role', 'in', ('assistant', 'technician'))])
    note = fields.Char('Ghi chú')
    state = fields.Selection([('draft', 'Đang làm'), ('done', 'Hoàn tất')],
                             default='draft', required=True, string='Trạng thái')
    sale_line_id = fields.Many2one('sale.order.line', string='Dòng đơn bán', readonly=True, copy=False)

    @api.depends('quantity', 'price_unit', 'discount')
    def _compute_amount(self):
        for proc in self:
            proc.amount = proc.quantity * proc.price_unit * (1 - (proc.discount or 0.0) / 100.0)

    @api.onchange('plan_line_id')
    def _onchange_plan_line_id(self):
        line = self.plan_line_id
        if line:
            self.product_id = line.product_id
            self.tooth_ids = line.tooth_ids
            self.surface_ids = line.surface_ids
            self.quantity = line.quantity
            self.price_unit = line.price_unit
            self.discount = line.discount

    @api.onchange('product_id', 'tooth_ids')
    def _onchange_product_id(self):
        if self.product_id and not self.plan_line_id:
            self.price_unit = self.product_id.lst_price
            if self.product_id.dental_requires_tooth and self.tooth_ids:
                self.quantity = len(self.tooth_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            visit = self.env['dmag.dental.visit'].browse(vals.get('visit_id'))
            vals.setdefault('doctor_id', visit.doctor_id.id)
            vals.setdefault('assistant_id', visit.assistant_id.id)
            if vals.get('plan_line_id'):
                line = self.env['dmag.treatment.plan.line'].browse(vals['plan_line_id'])
                if not vals.get('product_id'):
                    vals['product_id'] = line.product_id.id
                vals.setdefault('tooth_ids', [(6, 0, line.tooth_ids.ids)])
                vals.setdefault('surface_ids', [(6, 0, line.surface_ids.ids)])
                vals.setdefault('quantity', line.quantity)
                vals.setdefault('price_unit', line.price_unit)
                vals.setdefault('discount', line.discount)
            elif vals.get('product_id'):
                list_price = self.env['product.product'].browse(vals['product_id']).lst_price
                if 'price_unit' not in vals:
                    vals['price_unit'] = list_price
                elif vals['price_unit'] != list_price and not is_director(self.env):
                    raise AccessError(_('Giá thủ thuật lấy theo bảng giá – chỉ Giám đốc / Quản lý cấp cao được đổi giá.'))
            check_discount(self.env, vals.get('discount'), visit.company_id)
        return super().create(vals_list)

    def write(self, vals):
        if not is_workflow(self.env) and not is_director(self.env):
            if any(p.state == 'done' for p in self):
                raise AccessError(_('Thủ thuật đã hoàn tất – chỉ Giám đốc / Quản lý cấp cao được sửa.'))
            if 'price_unit' in vals:
                raise AccessError(_('Giá thủ thuật lấy theo bảng giá – chỉ Giám đốc / Quản lý cấp cao được đổi giá.'))
            if 'discount' in vals:
                for proc in self:
                    check_discount(self.env, vals['discount'], proc.company_id)
        return super().write(vals)

    @api.constrains('product_id', 'tooth_ids')
    def _check_tooth(self):
        for proc in self:
            if proc.product_id.dental_requires_tooth and not proc.tooth_ids:
                raise ValidationError(_('Dịch vụ "%s" cần chọn răng.', proc.product_id.name))

    def unlink(self):
        if any(p.state == 'done' for p in self):
            raise UserError(_('Không xóa được thủ thuật đã hoàn tất (đã ghi sơ đồ răng và doanh thu).'))
        return super().unlink()

    @api.depends('product_id', 'tooth_ids')
    def _compute_display_name(self):
        for proc in self:
            teeth = ', '.join(proc.tooth_ids.mapped('code'))
            proc.display_name = f'{proc.product_id.name} – R{teeth}' if teeth else (proc.product_id.name or '')

    def action_done(self):
        for proc in self.filtered(lambda p: p.state == 'draft'):
            if proc.visit_id.state not in ('in_chair', 'done'):
                raise UserError(_('Bệnh nhân cần lên ghế trước khi ghi nhận thủ thuật.'))
            if proc.doctor_id:
                proc.doctor_id.check_can_perform(proc.product_id)
            proc = proc.with_context(dmag_workflow=True)
            proc._update_chart()
            proc._update_sale_line()
            proc.state = 'done'
            if proc.plan_line_id:
                proc.plan_line_id.write({'state': 'done', 'done_visit_id': proc.visit_id.id})
        return True

    def _update_chart(self):
        self.ensure_one()
        Entry = self.env['dmag.dental.chart.entry']
        if self.plan_line_id:
            self.plan_line_id.finding_ids.action_resolve()
            Entry.search([('plan_line_id', '=', self.plan_line_id.id), ('layer', '=', 'planned')]).action_resolve()
        result = self.product_id.dental_result_condition_id
        if result:
            if result.category == 'missing':
                # Nhổ răng: các ghi nhận cũ trên răng không còn ý nghĩa
                Entry.search([('patient_id', '=', self.patient_id.id),
                              ('tooth_id', 'in', self.tooth_ids.ids)]).action_resolve()
            for tooth in self.tooth_ids:
                Entry.create({
                    'patient_id': self.patient_id.id,
                    'visit_id': self.visit_id.id,
                    'tooth_id': tooth.id,
                    'surface_ids': [(6, 0, self.surface_ids.ids)] if result.scope == 'surface' else False,
                    'condition_id': result.id,
                    'layer': 'done' if result.category != 'missing' else 'existing',
                    'practitioner_id': self.doctor_id.id,
                    'procedure_id': self.id,
                    'plan_line_id': self.plan_line_id.id,
                })

    def _update_sale_line(self):
        self.ensure_one()
        plan_sale_line = self.plan_line_id.sale_line_id.sudo()
        if plan_sale_line:
            plan_sale_line.qty_delivered += self.quantity
            self.sale_line_id = plan_sale_line
            return
        order = self.visit_id._get_or_create_sale_order()
        line = self.env['sale.order.line'].sudo().create({
            'order_id': order.id,
            'product_id': self.product_id.id,
            'name': self._sale_line_description(),
            'product_uom_qty': self.quantity,
            'price_unit': self.price_unit,
            'discount': self.discount,
        })
        if order.state in ('draft', 'sent'):
            order.action_confirm()
        line.qty_delivered = self.quantity
        self.sale_line_id = line

    def _sale_line_description(self):
        self.ensure_one()
        desc = self.product_id.display_name
        if self.tooth_ids:
            desc += _(' – Răng %s', ', '.join(self.tooth_ids.mapped('code')))
            if self.surface_ids:
                desc += ' (%s)' % ''.join(self.surface_ids.mapped('code'))
        return desc

    def _workspace_dict(self):
        self.ensure_one()
        return {
            'id': self.id,
            'name': self.display_name,
            'product_id': self.product_id.id,
            'teeth': self.tooth_ids.mapped('code'),
            'quantity': self.quantity,
            'amount': self.amount,
            'state': self.state,
            'doctor': self.doctor_id.name or '',
            'plan_line_id': self.plan_line_id.id,
        }

    @api.model
    def add_from_workspace(self, visit_id, product_id, teeth=None, surfaces=None, plan_line_id=False,
                           done=True):
        Tooth = self.env['dmag.dental.tooth']
        Surface = self.env['dmag.dental.surface']
        vals = {'visit_id': visit_id}
        if product_id:
            vals['product_id'] = product_id
        if plan_line_id:
            vals['plan_line_id'] = plan_line_id
        else:
            tooth_ids = Tooth.search([('code', 'in', teeth or [])]).ids
            vals['tooth_ids'] = [(6, 0, tooth_ids)]
            vals['surface_ids'] = [(6, 0, Surface.search([('code', 'in', surfaces or [])]).ids)]
            product = self.env['product.product'].browse(product_id)
            if product.dental_requires_tooth and tooth_ids:
                vals['quantity'] = len(tooth_ids)
        proc = self.create(vals)
        if done:
            proc.action_done()
        return proc._workspace_dict()
