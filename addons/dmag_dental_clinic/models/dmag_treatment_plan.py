from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class DmagTreatmentPlan(models.Model):
    """Kế hoạch điều trị – tư vấn đồng thuận 2 bước.

    Bác sĩ lập ≥ 1 phương án (cơ bản / khuyến nghị / cao cấp), bệnh nhân tự chọn.
    Phương án được chọn sinh đơn bán (hợp đồng điều trị) với chính sách thu theo
    tiến độ: chỉ xuất hóa đơn phần đã làm.
    """
    _name = 'dmag.treatment.plan'
    _description = 'Kế hoạch điều trị'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char('Mã kế hoạch', required=True, readonly=True, copy=False, default='/')
    title = fields.Char('Tiêu đề', help='Ví dụ: Phục hình răng hàm dưới, Niềng răng 2 hàm')
    company_id = fields.Many2one('res.company', string='Phòng khám', required=True,
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    patient_id = fields.Many2one('res.partner', string='Bệnh nhân', required=True, index=True, tracking=True,
                                 domain=[('is_patient', '=', True)],
                                 context={'dmag_patient_search': True})
    doctor_id = fields.Many2one('dmag.dental.practitioner', string='Bác sĩ lập kế hoạch',
                                domain=[('role', '=', 'doctor')], tracking=True)
    visit_id = fields.Many2one('dmag.dental.visit', string='Lập tại lượt khám')
    date = fields.Date('Ngày lập', default=fields.Date.context_today, required=True)
    state = fields.Selection([
        ('draft', 'Đang soạn'),
        ('presented', 'Đã tư vấn'),
        ('accepted', 'Bệnh nhân đồng ý'),
        ('in_progress', 'Đang điều trị'),
        ('done', 'Hoàn thành'),
        ('cancel', 'Hủy / từ chối'),
    ], string='Trạng thái', default='draft', required=True, tracking=True, copy=False)
    option_ids = fields.One2many('dmag.treatment.option', 'plan_id', string='Phương án', copy=True)
    accepted_option_id = fields.Many2one('dmag.treatment.option', string='Phương án được chọn',
                                         readonly=True, copy=False, tracking=True)
    accepted_date = fields.Datetime('Thời điểm đồng ý', readonly=True, copy=False)
    sale_order_id = fields.Many2one('sale.order', string='Hợp đồng điều trị', readonly=True, copy=False)
    amount_accepted = fields.Monetary(related='accepted_option_id.amount_total', string='Giá trị đồng ý')
    progress = fields.Float('Tiến độ (%)', compute='_compute_progress', store=True)
    note = fields.Html('Ghi chú tư vấn')
    reject_reason = fields.Char('Lý do từ chối')

    second_opinion_required = fields.Boolean(compute='_compute_second_opinion_required',
                                             string='Cần bác sĩ thứ hai duyệt')
    second_opinion_by_id = fields.Many2one('dmag.dental.practitioner', string='Bác sĩ thứ hai duyệt',
                                           readonly=True, copy=False, tracking=True)
    second_opinion_date = fields.Datetime('Thời điểm duyệt', readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('dmag.treatment.plan') or '/'
        return super().create(vals_list)

    @api.depends('accepted_option_id.line_ids.state')
    def _compute_progress(self):
        for plan in self:
            lines = plan.accepted_option_id.line_ids
            plan.progress = 100.0 * len(lines.filtered(lambda l: l.state == 'done')) / len(lines) if lines else 0.0

    @api.depends('option_ids.line_ids.product_id.requires_second_opinion')
    def _compute_second_opinion_required(self):
        for plan in self:
            plan.second_opinion_required = any(
                plan.option_ids.mapped('line_ids.product_id.requires_second_opinion'))

    def action_present(self):
        for plan in self:
            if not plan.option_ids or not plan.option_ids.mapped('line_ids'):
                raise UserError(_('Kế hoạch %s chưa có phương án / dịch vụ.', plan.name))
        self.filtered(lambda p: p.state == 'draft').write({'state': 'presented'})
        return True

    def action_second_opinion(self):
        practitioner = self.env['dmag.dental.visit']._current_practitioner()
        for plan in self:
            if not practitioner or practitioner.role != 'doctor':
                raise UserError(_('Chỉ bác sĩ mới được duyệt chỉ định.'))
            if practitioner == plan.doctor_id:
                raise UserError(_('Bác sĩ thứ hai phải khác bác sĩ lập kế hoạch.'))
            plan.write({'second_opinion_by_id': practitioner.id,
                        'second_opinion_date': fields.Datetime.now()})
            plan.message_post(body=_('BS %s đã duyệt chỉ định (cầu chì y đức).', practitioner.name))
        return True

    def action_cancel(self):
        for plan in self:
            if plan.sale_order_id and plan.sale_order_id.state == 'sale' and plan.progress:
                raise UserError(_('Kế hoạch đã điều trị một phần, không hủy được. Hãy điều chỉnh phương án.'))
            if plan.sale_order_id and plan.sale_order_id.state != 'cancel':
                plan.sale_order_id._action_cancel()
        self.write({'state': 'cancel'})
        return True

    def action_reset_draft(self):
        self.filtered(lambda p: p.state in ('presented', 'cancel') and not p.sale_order_id).write(
            {'state': 'draft'})
        return True

    def _check_progress_state(self):
        for plan in self.filtered(lambda p: p.state in ('accepted', 'in_progress')):
            if plan.progress >= 100:
                plan.state = 'done'
            elif plan.progress > 0:
                plan.state = 'in_progress'

    def action_open_sale_order(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'form',
            'res_id': self.sale_order_id.id,
        }

    def _workspace_dict(self):
        self.ensure_one()
        return {
            'id': self.id,
            'name': self.name,
            'title': self.title or '',
            'state': self.state,
            'progress': self.progress,
            'doctor': self.doctor_id.name or '',
            'second_opinion_required': self.second_opinion_required,
            'second_opinion_by': self.second_opinion_by_id.name or '',
            'accepted_option_id': self.accepted_option_id.id,
            'options': [o._workspace_dict() for o in self.option_ids],
        }

    @api.model
    def create_from_workspace(self, patient_id, visit_id, options):
        """options: [{'name':..., 'summary':..., 'installment_months':..,
                      'lines': [{'product_id', 'teeth', 'surfaces', 'phase'}]}]"""
        Tooth = self.env['dmag.dental.tooth']
        Surface = self.env['dmag.dental.surface']
        practitioner = self.env['dmag.dental.visit']._current_practitioner()
        option_cmds = []
        for seq, opt in enumerate(options, start=1):
            line_cmds = []
            for line in opt.get('lines', []):
                product = self.env['product.product'].browse(line['product_id'])
                tooth_ids = Tooth.search([('code', 'in', line.get('teeth') or [])]).ids
                line_cmds.append((0, 0, {
                    'product_id': product.id,
                    'tooth_ids': [(6, 0, tooth_ids)],
                    'surface_ids': [(6, 0, Surface.search([('code', 'in', line.get('surfaces') or [])]).ids)],
                    'quantity': len(tooth_ids) if product.dental_requires_tooth and tooth_ids else 1,
                    'price_unit': product.lst_price,
                    'phase': line.get('phase') or 1,
                    'finding_ids': [(6, 0, line.get('finding_ids') or [])],
                }))
            option_cmds.append((0, 0, {
                'name': opt.get('name') or _('Phương án %s', seq),
                'sequence': seq,
                'summary': opt.get('summary') or False,
                'installment_months': opt.get('installment_months') or 0,
                'is_recommended': bool(opt.get('is_recommended')),
                'line_ids': line_cmds,
            }))
        plan = self.create({
            'patient_id': patient_id,
            'visit_id': visit_id or False,
            'doctor_id': practitioner.id if practitioner.role == 'doctor' else False,
            'title': options and options[0].get('title') or False,
            'option_ids': option_cmds,
        })
        return plan._workspace_dict()


class DmagTreatmentOption(models.Model):
    _name = 'dmag.treatment.option'
    _description = 'Phương án điều trị'
    _order = 'sequence, id'

    plan_id = fields.Many2one('dmag.treatment.plan', required=True, ondelete='cascade', index=True)
    currency_id = fields.Many2one(related='plan_id.currency_id')
    name = fields.Char('Tên phương án', required=True, default='Phương án')
    sequence = fields.Integer(default=10)
    is_recommended = fields.Boolean('Bác sĩ khuyến nghị')
    summary = fields.Text('Ưu / nhược điểm', help='Giải thích rõ theo y đức, hiển thị cho bệnh nhân.')
    line_ids = fields.One2many('dmag.treatment.plan.line', 'option_id', string='Dịch vụ', copy=True)
    amount_total = fields.Monetary('Tổng chi phí', compute='_compute_amounts', store=True)
    estimated_visits = fields.Integer('Số buổi dự kiến', compute='_compute_amounts', store=True)
    deposit_amount = fields.Monetary('Đặt cọc')
    installment_months = fields.Integer('Trả góp (tháng)')
    monthly_amount = fields.Monetary('Mỗi tháng', compute='_compute_amounts', store=True)
    is_accepted = fields.Boolean(compute='_compute_is_accepted', store=True)

    @api.depends('line_ids.price_subtotal', 'line_ids.phase', 'installment_months', 'deposit_amount')
    def _compute_amounts(self):
        for option in self:
            total = sum(option.line_ids.mapped('price_subtotal'))
            option.amount_total = total
            option.estimated_visits = len(set(option.line_ids.mapped('phase')))
            remaining = max(total - (option.deposit_amount or 0.0), 0.0)
            option.monthly_amount = remaining / option.installment_months if option.installment_months else 0.0

    @api.depends('plan_id.accepted_option_id')
    def _compute_is_accepted(self):
        for option in self:
            option.is_accepted = option.plan_id.accepted_option_id == option

    @api.constrains('installment_months', 'deposit_amount')
    def _check_installment(self):
        for option in self:
            if option.installment_months < 0 or option.deposit_amount < 0:
                raise ValidationError(_('Số tháng trả góp và tiền đặt cọc không được âm.'))

    def action_accept(self):
        """Bệnh nhân chọn phương án này → sinh hợp đồng điều trị (đơn bán)."""
        self.ensure_one()
        plan = self.plan_id
        if plan.state not in ('draft', 'presented'):
            raise UserError(_('Kế hoạch đã được chốt trước đó.'))
        if not self.line_ids:
            raise UserError(_('Phương án chưa có dịch vụ.'))
        if any(self.line_ids.mapped('product_id.requires_second_opinion')) and not plan.second_opinion_by_id:
            raise UserError(_('Phương án có dịch vụ cần bác sĩ thứ hai duyệt chỉ định trước khi '
                              'bệnh nhân ký (cầu chì y đức).'))
        if plan.doctor_id:
            plan.doctor_id.check_can_perform(self.line_ids.mapped('product_id'))
        order = self.env['sale.order'].sudo().create({
            'partner_id': plan.patient_id.id,
            'company_id': plan.company_id.id,
            'dental_plan_id': plan.id,
            'origin': plan.name,
            'order_line': [(0, 0, line._prepare_sale_line()) for line in self.line_ids],
        })
        order.action_confirm()
        for line, sale_line in zip(self.line_ids, order.order_line):
            line.sale_line_id = sale_line
        self.line_ids._create_planned_chart_entries()
        plan.write({
            'accepted_option_id': self.id,
            'accepted_date': fields.Datetime.now(),
            'sale_order_id': order.id,
            'state': 'accepted',
        })
        plan.message_post(body=_('Bệnh nhân chọn "%(opt)s" – tổng %(amount)s.',
                                 opt=self.name, amount=self.amount_total))
        return True

    def _workspace_dict(self):
        self.ensure_one()
        return {
            'id': self.id,
            'name': self.name,
            'summary': self.summary or '',
            'is_recommended': self.is_recommended,
            'is_accepted': self.is_accepted,
            'amount_total': self.amount_total,
            'deposit_amount': self.deposit_amount,
            'installment_months': self.installment_months,
            'monthly_amount': self.monthly_amount,
            'estimated_visits': self.estimated_visits,
            'lines': [{
                'id': l.id, 'product_id': l.product_id.id, 'product': l.product_id.name,
                'teeth': l.tooth_ids.mapped('code'), 'surfaces': l.surface_ids.mapped('code'),
                'quantity': l.quantity, 'price_unit': l.price_unit, 'discount': l.discount,
                'subtotal': l.price_subtotal, 'phase': l.phase, 'state': l.state,
                'warranty_months': l.product_id.warranty_months,
            } for l in self.line_ids],
        }


class DmagTreatmentPlanLine(models.Model):
    _name = 'dmag.treatment.plan.line'
    _description = 'Dòng kế hoạch điều trị'
    _order = 'phase, sequence, id'

    option_id = fields.Many2one('dmag.treatment.option', required=True, ondelete='cascade', index=True)
    plan_id = fields.Many2one(related='option_id.plan_id', store=True, index=True)
    currency_id = fields.Many2one(related='option_id.currency_id')
    sequence = fields.Integer(default=10)
    phase = fields.Integer('Giai đoạn / buổi', default=1)
    product_id = fields.Many2one('product.product', string='Dịch vụ', required=True,
                                 domain=[('is_dental_service', '=', True)])
    tooth_ids = fields.Many2many('dmag.dental.tooth', string='Răng')
    surface_ids = fields.Many2many('dmag.dental.surface', string='Mặt răng')
    quantity = fields.Float('Số lượng', default=1.0, required=True)
    price_unit = fields.Float('Đơn giá', digits='Product Price')
    discount = fields.Float('Giảm (%)', digits='Discount')
    price_subtotal = fields.Monetary('Thành tiền', compute='_compute_subtotal', store=True)
    state = fields.Selection([('todo', 'Chưa làm'), ('done', 'Đã làm')], default='todo', required=True,
                             string='Tình trạng')
    done_visit_id = fields.Many2one('dmag.dental.visit', string='Làm tại lượt khám', readonly=True)
    finding_ids = fields.Many2many('dmag.dental.chart.entry', 'dmag_plan_line_finding_rel',
                                   'line_id', 'entry_id', string='Bệnh lý được xử lý',
                                   context={'active_test': False})
    sale_line_id = fields.Many2one('sale.order.line', readonly=True, copy=False)

    @api.depends('quantity', 'price_unit', 'discount')
    def _compute_subtotal(self):
        for line in self:
            line.price_subtotal = line.quantity * line.price_unit * (1 - (line.discount or 0.0) / 100.0)

    @api.onchange('product_id', 'tooth_ids')
    def _onchange_product(self):
        if self.product_id:
            if not self.price_unit:
                self.price_unit = self.product_id.lst_price
            if self.product_id.dental_requires_tooth and self.tooth_ids:
                self.quantity = len(self.tooth_ids)

    @api.constrains('discount')
    def _check_discount(self):
        for line in self:
            if not 0 <= line.discount <= 100:
                raise ValidationError(_('Giảm giá phải trong khoảng 0–100%.'))

    def write(self, vals):
        res = super().write(vals)
        if 'state' in vals:
            self.mapped('plan_id')._check_progress_state()
        return res

    @api.depends('product_id', 'tooth_ids')
    def _compute_display_name(self):
        for line in self:
            teeth = ', '.join(line.tooth_ids.mapped('code'))
            line.display_name = f'{line.product_id.name} – R{teeth}' if teeth else (line.product_id.name or '')

    def _prepare_sale_line(self):
        self.ensure_one()
        name = self.product_id.display_name
        if self.tooth_ids:
            name += _(' – Răng %s', ', '.join(self.tooth_ids.mapped('code')))
        if self.phase:
            name += _(' (giai đoạn %s)', self.phase)
        return {
            'product_id': self.product_id.id,
            'name': name,
            'product_uom_qty': self.quantity,
            'price_unit': self.price_unit,
            'discount': self.discount,
        }

    def _create_planned_chart_entries(self):
        Entry = self.env['dmag.dental.chart.entry']
        for line in self:
            condition = line.product_id.dental_result_condition_id
            if not condition or not line.tooth_ids:
                continue
            for tooth in line.tooth_ids:
                Entry.create({
                    'patient_id': line.plan_id.patient_id.id,
                    'tooth_id': tooth.id,
                    'surface_ids': [(6, 0, line.surface_ids.ids)] if condition.scope == 'surface' else False,
                    'condition_id': condition.id,
                    'layer': 'planned',
                    'plan_line_id': line.id,
                    'practitioner_id': line.plan_id.doctor_id.id,
                })
