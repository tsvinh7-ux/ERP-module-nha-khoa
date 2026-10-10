from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from odoo.addons.dmag_dental_base.models.dmag_access import check_director, is_director, is_workflow

PAYMENT_METHODS = [('cash', 'Tiền mặt'), ('transfer', 'Chuyển khoản'), ('card', 'Quẹt thẻ')]


class DmagCarePlan(models.Model):
    """Gói chăm sóc định kỳ (thuê bao năm trả trước)."""
    _name = 'dmag.care.plan'
    _description = 'Gói chăm sóc định kỳ'
    _order = 'sequence, id'

    name = fields.Char('Tên gói', required=True, translate=True)
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one('res.company', string='Phòng khám', default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    price = fields.Monetary('Giá gói', required=True)
    duration_months = fields.Integer('Thời hạn (tháng)', default=12, required=True)
    product_id = fields.Many2one('product.product', string='Sản phẩm bán gói',
                                 help='Dùng để lập đơn bán / hóa đơn. Để trống: dùng sản phẩm chung "Gói chăm sóc định kỳ".')
    line_ids = fields.One2many('dmag.care.plan.line', 'plan_id', string='Quyền lợi trong gói', copy=True)
    description = fields.Text('Mô tả cho bệnh nhân', translate=True)
    active = fields.Boolean(default=True)

    @api.constrains('duration_months', 'price')
    def _check_values(self):
        for plan in self:
            if plan.duration_months <= 0:
                raise ValidationError(_('Thời hạn gói phải lớn hơn 0 tháng.'))
            if plan.price < 0:
                raise ValidationError(_('Giá gói không âm.'))


class DmagCarePlanLine(models.Model):
    _name = 'dmag.care.plan.line'
    _description = 'Quyền lợi gói chăm sóc'

    plan_id = fields.Many2one('dmag.care.plan', required=True, ondelete='cascade', index=True)
    product_id = fields.Many2one('product.product', string='Dịch vụ', required=True,
                                 domain=[('is_dental_service', '=', True)])
    quantity = fields.Float('Số lần', default=1.0, required=True)

    @api.constrains('quantity')
    def _check_quantity(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError(_('Số lần quyền lợi phải lớn hơn 0.'))


class DmagCareSubscription(models.Model):
    """Thuê bao gói chăm sóc của một bệnh nhân."""
    _name = 'dmag.care.subscription'
    _description = 'Thuê bao gói chăm sóc'
    _inherit = ['mail.thread']
    _order = 'start_date desc, id desc'

    name = fields.Char('Mã thuê bao', required=True, readonly=True, copy=False, default='/')
    partner_id = fields.Many2one('res.partner', string='Bệnh nhân', required=True, index=True,
                                 domain=[('is_patient', '=', True)], tracking=True)
    plan_id = fields.Many2one('dmag.care.plan', string='Gói', required=True, tracking=True)
    company_id = fields.Many2one('res.company', string='Phòng khám', required=True,
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    price = fields.Monetary('Giá', readonly=True)
    start_date = fields.Date('Bắt đầu', required=True, default=fields.Date.context_today)
    end_date = fields.Date('Kết thúc', compute='_compute_end_date', store=True)
    state = fields.Selection([
        ('draft', 'Nháp'),
        ('active', 'Đang hiệu lực'),
        ('expired', 'Hết hạn'),
        ('cancel', 'Đã hủy'),
    ], string='Trạng thái', default='draft', required=True, tracking=True, copy=False)
    entitlement_ids = fields.One2many('dmag.care.entitlement', 'subscription_id', string='Quyền lợi còn lại')
    usage_ids = fields.One2many('dmag.care.usage', 'subscription_id', string='Lịch sử sử dụng')
    sale_order_id = fields.Many2one('sale.order', string='Đơn bán', readonly=True, copy=False)
    invoice_ids = fields.Many2many('account.move', string='Hóa đơn', readonly=True, copy=False)
    amount_due = fields.Monetary('Còn phải thu', compute='_compute_amount_due')

    @api.depends('start_date', 'plan_id.duration_months')
    def _compute_end_date(self):
        for sub in self:
            if sub.start_date and sub.plan_id:
                sub.end_date = sub.start_date + relativedelta(months=sub.plan_id.duration_months, days=-1)
            else:
                sub.end_date = False

    def _compute_amount_due(self):
        for sub in self:
            sub.amount_due = sum(sub.sudo().invoice_ids.filtered(
                lambda m: m.state == 'posted').mapped('amount_residual'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('dmag.care.subscription') or '/'
            if vals.get('plan_id') and 'price' not in vals:
                vals['price'] = self.env['dmag.care.plan'].browse(vals['plan_id']).price
        return super().create(vals_list)

    def write(self, vals):
        if not is_workflow(self.env) and not is_director(self.env):
            if any(sub.state != 'draft' for sub in self):
                raise AccessError(_('Thuê bao đã kích hoạt – chỉ Giám đốc / Quản lý cấp cao được sửa.'))
            if 'price' in vals:
                raise AccessError(_('Giá gói lấy theo cấu hình gói – chỉ Giám đốc được đổi.'))
        return super().write(vals)

    def unlink(self):
        if any(sub.state != 'draft' for sub in self):
            raise UserError(_('Chỉ xóa được thuê bao nháp – thuê bao đã kích hoạt hãy hủy.'))
        return super().unlink()

    def _workflow_write(self, vals):
        return self.with_context(dmag_workflow=True).write(vals)

    def action_activate(self):
        """Kích hoạt: sinh quyền lợi, lập đơn bán + hóa đơn (quyền hệ thống)."""
        for sub in self.filtered(lambda s: s.state == 'draft'):
            if not sub.plan_id.line_ids:
                raise UserError(_('Gói %s chưa có quyền lợi.', sub.plan_id.name))
            self.env['dmag.care.entitlement'].sudo().create([{
                'subscription_id': sub.id,
                'product_id': line.product_id.id,
                'qty_total': line.quantity,
            } for line in sub.plan_id.line_ids])
            vals = {'state': 'active'}
            if sub.price:
                product = sub.plan_id.product_id or self.env.ref('dmag_dental_loyalty.product_care_plan')
                order = self.env['sale.order'].sudo().create({
                    'partner_id': sub.partner_id.id,
                    'company_id': sub.company_id.id,
                    'origin': sub.name,
                    'order_line': [(0, 0, {
                        'product_id': product.id,
                        'name': _('%(plan)s (%(start)s – %(end)s)', plan=sub.plan_id.name,
                                  start=sub.start_date.strftime('%d/%m/%Y'),
                                  end=sub.end_date.strftime('%d/%m/%Y')),
                        'product_uom_qty': 1,
                        'price_unit': sub.price,
                    })],
                })
                order.action_confirm()
                moves = order._create_invoices()
                moves.action_post()
                vals.update({'sale_order_id': order.id, 'invoice_ids': [(6, 0, moves.ids)]})
            sub._workflow_write(vals)
            sub.message_post(body=_('Kích hoạt gói %(plan)s – người thực hiện: %(user)s',
                                    plan=sub.plan_id.name, user=self.env.user.name))
        return True

    def register_payment(self, method, amount=False, reference=False):
        """Thu tiền gói chăm sóc tại quầy – tích điểm theo thực thu."""
        self.ensure_one()
        invoices = self.sudo().invoice_ids.filtered(
            lambda m: m.state == 'posted' and m.payment_state not in ('paid', 'in_payment', 'reversed'))
        if not invoices:
            raise UserError(_('Thuê bao %s không còn khoản phải thu.', self.name))
        jtype = 'cash' if method == 'cash' else 'bank'
        journal = self.env['account.journal'].sudo().search(
            [('company_id', '=', self.company_id.id), ('type', '=', jtype)], limit=1)
        if not journal:
            raise UserError(_('Chưa cấu hình sổ nhật ký %s cho phòng khám.', jtype))
        residual = sum(invoices.mapped('amount_residual'))
        amount = amount or residual
        if amount <= 0 or amount > residual + 0.5:
            raise UserError(_('Số tiền thu không hợp lệ (còn phải thu %s).', residual))
        wizard = self.env['account.payment.register'].sudo().with_context(
            active_model='account.move', active_ids=invoices.ids).create({
                'journal_id': journal.id,
                'amount': amount,
                'payment_date': fields.Date.context_today(self),
                'communication': reference or self.name,
                'group_payment': True,
            })
        payments = wizard._create_payments()
        self.message_post(body=_('Thu %(amount)s – %(method)s – người thu: %(user)s',
                                 amount=amount, method=dict(PAYMENT_METHODS)[method], user=self.env.user.name))
        self.partner_id._dmag_loyalty_earn_from_invoices(self.sudo().invoice_ids, source=self)
        self.partner_id._dmag_loyalty_recompute()
        return payments.ids

    def action_cancel(self):
        check_director(self.env, _('Chỉ Giám đốc / Quản lý cấp cao được hủy thuê bao gói chăm sóc.'))
        self.filtered(lambda s: s.state in ('draft', 'active'))._workflow_write({'state': 'cancel'})
        return True

    @api.model
    def _cron_expire(self):
        today = fields.Date.context_today(self)
        self.search([('state', '=', 'active'), ('end_date', '<', today)])._workflow_write({'state': 'expired'})

    def _find_entitlement(self, product, quantity=1.0):
        """Quyền lợi còn đủ cho dịch vụ ``product`` trong các thuê bao đang hiệu lực."""
        today = fields.Date.context_today(self)
        for sub in self.filtered(lambda s: s.state == 'active' and s.start_date <= today <= s.end_date):
            ent = sub.entitlement_ids.filtered(
                lambda e: e.product_id == product and e.qty_remaining >= quantity - 1e-6)
            if ent:
                return ent[0]
        return self.env['dmag.care.entitlement']

    def _subscription_dict(self):
        return [{
            'id': sub.id, 'name': sub.name, 'plan': sub.plan_id.name,
            'start_date': fields.Date.to_string(sub.start_date),
            'end_date': fields.Date.to_string(sub.end_date),
            'state': sub.state,
            'state_label': dict(self._fields['state'].selection)[sub.state],
            'entitlements': [{
                'service': ent.product_id.name, 'total': ent.qty_total,
                'used': ent.qty_used, 'remaining': ent.qty_remaining,
            } for ent in sub.entitlement_ids],
        } for sub in self]


class DmagCareEntitlement(models.Model):
    _name = 'dmag.care.entitlement'
    _description = 'Quyền lợi thuê bao gói chăm sóc'

    subscription_id = fields.Many2one('dmag.care.subscription', required=True, ondelete='cascade', index=True)
    partner_id = fields.Many2one(related='subscription_id.partner_id', store=True)
    product_id = fields.Many2one('product.product', string='Dịch vụ', required=True, readonly=True)
    qty_total = fields.Float('Tổng số lần', readonly=True)
    usage_ids = fields.One2many('dmag.care.usage', 'entitlement_id', string='Đã dùng')
    qty_used = fields.Float('Đã dùng', compute='_compute_qty', store=True)
    qty_remaining = fields.Float('Còn lại', compute='_compute_qty', store=True)

    @api.depends('qty_total', 'usage_ids.quantity')
    def _compute_qty(self):
        for ent in self:
            ent.qty_used = sum(ent.usage_ids.mapped('quantity'))
            ent.qty_remaining = ent.qty_total - ent.qty_used

    @api.constrains('qty_remaining')
    def _check_remaining(self):
        for ent in self:
            if ent.qty_remaining < -1e-6:
                raise ValidationError(_('Quyền lợi "%s" đã dùng hết.', ent.product_id.name))


class DmagCareUsage(models.Model):
    """Một lần dùng quyền lợi gói tại lượt khám (thủ thuật được 0 đồng)."""
    _name = 'dmag.care.usage'
    _description = 'Sử dụng quyền lợi gói chăm sóc'
    _order = 'date desc, id desc'

    subscription_id = fields.Many2one(related='entitlement_id.subscription_id', store=True, index=True)
    entitlement_id = fields.Many2one('dmag.care.entitlement', required=True, ondelete='restrict', readonly=True)
    visit_id = fields.Many2one('dmag.dental.visit', string='Lượt khám', readonly=True, ondelete='restrict')
    procedure_id = fields.Many2one('dmag.dental.procedure', string='Thủ thuật', readonly=True, ondelete='restrict')
    product_id = fields.Many2one(related='entitlement_id.product_id', store=True)
    quantity = fields.Float('Số lần', readonly=True, default=1.0)
    original_price = fields.Float('Giá gốc', readonly=True, digits='Product Price')
    date = fields.Datetime('Thời điểm', readonly=True, default=fields.Datetime.now)
    user_id = fields.Many2one('res.users', string='Người ghi', readonly=True, default=lambda self: self.env.user)

    _sql_constraints = [
        ('procedure_uniq', 'unique(procedure_id)', 'Thủ thuật này đã dùng quyền lợi gói.'),
    ]
