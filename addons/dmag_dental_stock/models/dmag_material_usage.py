from collections import defaultdict
from datetime import datetime, time, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from odoo.addons.dmag_dental_base.models.dmag_access import check_director, is_director, is_workflow


def to_date_range(date_from, date_to):
    d_from = fields.Date.to_date(date_from)
    d_to = fields.Date.to_date(date_to)
    return d_from, d_to, datetime.combine(d_from, time.min), datetime.combine(d_to + timedelta(days=1), time.min)


class DmagMaterialUsage(models.Model):
    """Vật tư đã dùng cho thủ thuật – theo định mức (tự động) hoặc phát sinh thực tế (phụ tá ghi).

    Mỗi dòng gắn với một dịch chuyển kho từ kho phòng khám tới "Tiêu hao lâm sàng".
    Tạo được – không sửa: chỉ Giám đốc / Quản lý cấp cao sửa hoặc xóa (và tự điều chỉnh kho).
    """
    _name = 'dmag.material.usage'
    _description = 'Vật tư tiêu hao lâm sàng'
    _order = 'date desc, id desc'

    procedure_id = fields.Many2one('dmag.dental.procedure', string='Thủ thuật', required=True, index=True,
                                   ondelete='restrict')
    visit_id = fields.Many2one(related='procedure_id.visit_id', store=True, string='Lượt khám')
    patient_id = fields.Many2one(related='procedure_id.patient_id', store=True, string='Bệnh nhân', index=True)
    doctor_id = fields.Many2one(related='procedure_id.doctor_id', store=True, string='Bác sĩ')
    company_id = fields.Many2one(related='procedure_id.company_id', store=True, string='Phòng khám', index=True)
    service_id = fields.Many2one(related='procedure_id.product_id', store=True, string='Dịch vụ')
    date = fields.Datetime('Thời điểm', required=True, default=fields.Datetime.now, index=True)
    kind = fields.Selection([
        ('bom', 'Theo định mức'),
        ('extra', 'Phát sinh ngoài định mức'),
    ], string='Loại', required=True, default='extra', index=True)
    product_id = fields.Many2one('product.product', string='Vật tư', required=True, index=True,
                                 domain=[('type', 'in', ('product', 'consu'))])
    tracking = fields.Selection(related='product_id.tracking')
    quantity = fields.Float('Số lượng', required=True, default=1.0, digits='Product Unit of Measure')
    uom_id = fields.Many2one(related='product_id.uom_id', string='Đơn vị')
    lot_id = fields.Many2one('stock.lot', string='Serial / lô', index=True,
                             domain="[('product_id', '=', product_id)]")
    unit_cost = fields.Float('Giá vốn đơn vị', digits='Product Price', readonly=True)
    cost = fields.Float('Giá vốn', compute='_compute_cost', store=True, digits='Product Price')
    reason = fields.Char('Lý do phát sinh')
    user_id = fields.Many2one('res.users', string='Người ghi', default=lambda self: self.env.user, readonly=True)
    move_id = fields.Many2one('stock.move', string='Dịch chuyển kho', readonly=True, copy=False)
    picking_id = fields.Many2one('stock.picking', string='Phiếu xuất tiêu hao', readonly=True, copy=False)

    @api.depends('quantity', 'unit_cost')
    def _compute_cost(self):
        for usage in self:
            usage.cost = usage.quantity * usage.unit_cost

    @api.constrains('quantity', 'lot_id', 'product_id')
    def _check_usage(self):
        for usage in self:
            if usage.quantity <= 0:
                raise ValidationError(_('Số lượng vật tư phải lớn hơn 0.'))
            if usage.lot_id and usage.lot_id.product_id != usage.product_id:
                raise ValidationError(_('Serial / lô không thuộc vật tư "%s".', usage.product_id.name))
            if usage.product_id.tracking == 'serial' and usage.quantity != 1:
                raise ValidationError(_('Vật tư theo serial ghi mỗi dòng 1 đơn vị.'))

    # ------------------------------------------------------------------ CRUD
    @api.model_create_multi
    def create(self, vals_list):
        Procedure = self.env['dmag.dental.procedure']
        for vals in vals_list:
            proc = Procedure.browse(vals.get('procedure_id'))
            product = self.env['product.product'].browse(vals.get('product_id'))
            company = proc.company_id or self.env.company
            vals['unit_cost'] = product.sudo().with_company(company).standard_price
            if not is_workflow(self.env):
                # Nhân viên chỉ ghi phát sinh, không tự đặt người ghi / chứng từ kho
                vals['kind'] = 'extra'
                vals.pop('move_id', None)
                vals.pop('picking_id', None)
                vals.pop('user_id', None)
                if not vals.get('reason'):
                    raise UserError(_('Ghi rõ lý do dùng thêm vật tư ngoài định mức.'))
            if product.tracking != 'none' and not vals.get('lot_id'):
                raise UserError(_('Vật tư "%s" theo dõi serial / lô – chọn serial / lô đã dùng.', product.name))
        usages = super().create(vals_list)
        if not self.env.context.get('dmag_skip_stock'):
            usages._dmag_post_stock()
        usages._dmag_trace_lots()
        return usages

    def write(self, vals):
        if not is_workflow(self.env) and not is_director(self.env):
            raise AccessError(_('Ghi nhận vật tư đã lưu – chỉ Giám đốc / Quản lý cấp cao được sửa.'))
        return super().write(vals)

    def unlink(self):
        check_director(self.env, _('Không xóa ghi nhận vật tư – chỉ Giám đốc / Quản lý cấp cao '
                                   '(nhớ điều chỉnh tồn kho tương ứng).'))
        return super().unlink()

    # ------------------------------------------------------------------ stock
    def _dmag_post_stock(self):
        """Xuất kho tiêu hao (quyền hệ thống): một phiếu cho mỗi thủ thuật, một dịch chuyển cho mỗi dòng."""
        groups = defaultdict(lambda: self.browse())
        for usage in self:
            groups[usage.procedure_id] |= usage
        Picking = self.env['stock.picking'].sudo()
        MoveLine = self.env['stock.move.line'].sudo()
        for proc, usages in groups.items():
            company = proc.company_id
            ptype, src, dest = company._dmag_consumption_setup()
            origin = f'{proc.visit_id.name} – {proc.display_name}'
            picking = Picking.with_company(company).create({
                'picking_type_id': ptype.id,
                'location_id': src.id,
                'location_dest_id': dest.id,
                'company_id': company.id,
                'origin': origin,
                'move_ids': [(0, 0, {
                    'name': usage.product_id.display_name,
                    'product_id': usage.product_id.id,
                    'product_uom': usage.product_id.uom_id.id,
                    'product_uom_qty': usage.quantity,
                    'location_id': src.id,
                    'location_dest_id': dest.id,
                    'company_id': company.id,
                }) for usage in usages],
            })
            picking.action_confirm()
            # action_confirm có thể gộp các dịch chuyển cùng vật tư → phân bổ lại theo vật tư
            picking.move_ids.move_line_ids.unlink()
            moves_by_product = defaultdict(list)
            for move in picking.move_ids:
                moves_by_product[move.product_id].append(move)
            for usage in usages:
                candidates = moves_by_product[usage.product_id]
                move = candidates.pop(0) if len(candidates) > 1 else candidates[0]
                MoveLine.create({
                    'move_id': move.id,
                    'picking_id': picking.id,
                    'product_id': move.product_id.id,
                    'product_uom_id': move.product_uom.id,
                    'quantity': usage.quantity,
                    'lot_id': usage.lot_id.id,
                    'location_id': src.id,
                    'location_dest_id': dest.id,
                    'company_id': company.id,
                })
                move.picked = True
                usage.with_context(dmag_workflow=True).sudo().write({'move_id': move.id, 'picking_id': picking.id})
            picking.with_context(skip_backorder=True, skip_sms=True, skip_expired=True,
                                 cancel_backorder=True).button_validate()
            if picking.state != 'done':
                raise UserError(_('Không xuất được vật tư tiêu hao cho %s.', origin))
        return True

    def _dmag_trace_lots(self):
        for usage in self.filtered('lot_id'):
            usage.lot_id.sudo().write({
                'dmag_patient_id': usage.patient_id.id,
                'dmag_procedure_id': usage.procedure_id.id,
                'dmag_used_date': usage.date,
            })

    # ------------------------------------------------------------------ KPI
    @api.model
    def _dmag_revenue(self, date_from, date_to, company):
        """Doanh thu dịch vụ = giá trị thủ thuật hoàn tất theo ngày lượt khám (chưa phải thực thu)."""
        _d_from, _d_to, dt_from, dt_to = to_date_range(date_from, date_to)
        procs = self.env['dmag.dental.procedure'].sudo().search([
            ('state', '=', 'done'), ('company_id', '=', company.id),
            ('visit_id.scheduled_start', '>=', dt_from), ('visit_id.scheduled_start', '<', dt_to),
        ])
        return sum(procs.mapped('amount'))

    @api.model
    def get_material_kpis(self, date_from, date_to, company_id=False):
        """KPI giá vốn vật tư cho Bảng điều hành mục tiêu (≤ ngưỡng ``company.dmag_cogs_threshold``)."""
        company = self.env['res.company'].browse(company_id) if company_id else self.env.company
        d_from, d_to, dt_from, dt_to = to_date_range(date_from, date_to)
        usages = self.sudo().search([('company_id', '=', company.id),
                                     ('date', '>=', dt_from), ('date', '<', dt_to)])
        revenue = self._dmag_revenue(d_from, d_to, company)
        bom_cost = sum(usages.filtered(lambda u: u.kind == 'bom').mapped('cost'))
        extra_cost = sum(usages.filtered(lambda u: u.kind == 'extra').mapped('cost'))
        material_cost = bom_cost + extra_cost
        lab_cost = 0.0
        if 'dmag.lab.order' in self.env:
            lab_cost = self.env['dmag.lab.order'].get_lab_kpis(d_from, d_to, company.id)['lab_cost']
        threshold = company.dmag_cogs_threshold or 22.0
        material_ratio = round(material_cost / revenue * 100.0, 2) if revenue else 0.0
        cogs_ratio = round((material_cost + lab_cost) / revenue * 100.0, 2) if revenue else 0.0
        by_product = defaultdict(lambda: {'qty': 0.0, 'cost': 0.0})
        for usage in usages:
            by_product[usage.product_id]['qty'] += usage.quantity
            by_product[usage.product_id]['cost'] += usage.cost
        top = sorted(by_product.items(), key=lambda kv: kv[1]['cost'], reverse=True)[:5]
        return {
            'company_id': company.id,
            'date_from': fields.Date.to_string(d_from),
            'date_to': fields.Date.to_string(d_to),
            'currency': company.currency_id.name,
            'revenue': revenue,
            'material_cost': material_cost,
            'bom_cost': bom_cost,
            'extra_cost': extra_cost,
            'variance_ratio': round(extra_cost / bom_cost * 100.0, 2) if bom_cost else 0.0,
            'material_ratio': material_ratio,
            'lab_cost': lab_cost,
            'cogs_ratio': cogs_ratio,
            'threshold': threshold,
            'alert': bool(revenue) and cogs_ratio > threshold,
            'message': (_('Giá vốn vật tư & labo %(ratio)s%% vượt ngưỡng %(limit)s%% doanh thu.',
                          ratio=cogs_ratio, limit=threshold)
                        if revenue and cogs_ratio > threshold else ''),
            'implant_count': len(usages.filtered(lambda u: u.tracking == 'serial')),
            'top_products': [{'product_id': p.id, 'name': p.display_name, 'qty': v['qty'], 'cost': v['cost']}
                             for p, v in top],
        }
