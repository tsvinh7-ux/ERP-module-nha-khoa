from datetime import datetime, time, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from odoo.addons.dmag_dental_base.models.dmag_access import check_director, is_director, is_workflow

OPEN_STATES = ('sent', 'in_progress', 'try_in')
# Sau khi gửi labo: chi phí / labo / sản phẩm tính phí chỉ Giám đốc được sửa
LOCKED_AFTER_SENT = {'cost', 'lab_partner_id', 'cost_product_id', 'patient_id', 'company_id', 'currency_id'}

WORK_TYPES = [
    ('crown_bridge', 'Mão / cầu sứ'),
    ('veneer', 'Mặt dán sứ (veneer)'),
    ('inlay_onlay', 'Inlay / Onlay'),
    ('implant_abutment', 'Abutment / sứ trên implant'),
    ('removable', 'Hàm tháo lắp'),
    ('aligner', 'Khay chỉnh nha trong suốt'),
    ('retainer', 'Hàm duy trì'),
    ('splint', 'Máng (nhai / tẩy trắng / chống nghiến)'),
    ('other', 'Khác'),
]
MATERIALS = [
    ('zirconia', 'Zirconia'),
    ('emax', 'Lithium disilicate (E.max)'),
    ('pfm', 'Sứ kim loại thường'),
    ('pfm_titan', 'Sứ Titan'),
    ('pfm_precious', 'Sứ kim loại quý'),
    ('pmma', 'PMMA / tạm'),
    ('acrylic', 'Nhựa acrylic'),
    ('flexible', 'Nhựa dẻo'),
    ('thermoform', 'Nhựa ép nhiệt'),
    ('other', 'Khác'),
]


def to_date_range(date_from, date_to):
    """Chuẩn hóa khoảng ngày → (datetime bắt đầu, datetime kết thúc loại trừ)."""
    d_from = fields.Date.to_date(date_from)
    d_to = fields.Date.to_date(date_to)
    return datetime.combine(d_from, time.min), datetime.combine(d_to + timedelta(days=1), time.min)


def procedure_revenue(env, date_from, date_to, company):
    """Doanh thu dịch vụ = giá trị thủ thuật đã hoàn tất, theo ngày lượt khám (chưa trừ thuế, chưa phải thực thu)."""
    dt_from, dt_to = to_date_range(date_from, date_to)
    procs = env['dmag.dental.procedure'].sudo().search([
        ('state', '=', 'done'), ('company_id', '=', company.id),
        ('visit_id.scheduled_start', '>=', dt_from), ('visit_id.scheduled_start', '<', dt_to),
    ])
    return sum(procs.mapped('amount'))


class DmagLabOrder(models.Model):
    """Phiếu gửi labo: theo dõi phục hình gia công ngoài từ lúc lấy dấu đến khi gắn cho bệnh nhân."""
    _name = 'dmag.lab.order'
    _description = 'Phiếu labo'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char('Số phiếu', required=True, copy=False, readonly=True, default='/')
    company_id = fields.Many2one('res.company', string='Phòng khám', required=True, index=True,
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    patient_id = fields.Many2one('res.partner', string='Bệnh nhân', required=True, index=True, tracking=True,
                                 domain=[('is_patient', '=', True)])
    visit_id = fields.Many2one('dmag.dental.visit', string='Lượt khám lấy dấu',
                               domain="[('patient_id', '=', patient_id)]")
    plan_line_id = fields.Many2one('dmag.treatment.plan.line', string='Dòng kế hoạch',
                                   domain="[('plan_id.patient_id', '=', patient_id)]")
    doctor_id = fields.Many2one('dmag.dental.practitioner', string='Bác sĩ chỉ định',
                                domain=[('role', '=', 'doctor')])
    lab_partner_id = fields.Many2one('res.partner', string='Labo', tracking=True,
                                     domain=[('is_dental_lab', '=', True)])
    work_type = fields.Selection(WORK_TYPES, string='Loại phục hình', required=True, default='crown_bridge',
                                 tracking=True)
    tooth_ids = fields.Many2many('dmag.dental.tooth', string='Răng')
    unit_count = fields.Integer('Số đơn vị', compute='_compute_unit_count', store=True, readonly=False)
    shade = fields.Char('Màu răng', help='Theo bảng màu Vita Classical (A1–D4) hoặc Vita 3D-Master; '
                                         'ghi cả màu cổ/thân/rìa cắn nếu khác nhau.')
    material = fields.Selection(MATERIALS, string='Vật liệu')
    material_note = fields.Char('Ghi chú vật liệu / hãng')
    impression_type = fields.Selection([
        ('conventional', 'Lấy dấu thường (silicone / alginate)'),
        ('scan', 'Scan kỹ thuật số'),
    ], string='Lấy dấu', default='conventional', required=True)
    scan_reference = fields.Char('Mã file scan / link', help='Mã ca trên phần mềm scan hoặc link chia sẻ file STL.')
    instructions = fields.Text('Chỉ định cho labo')

    sent_date = fields.Date('Ngày gửi', copy=False, tracking=True)
    due_date = fields.Date('Hẹn trả', tracking=True)
    received_date = fields.Date('Ngày nhận', copy=False, readonly=True)
    fitted_date = fields.Date('Ngày gắn', copy=False, readonly=True)
    fit_visit_id = fields.Many2one('dmag.dental.visit', string='Lượt gắn', copy=False,
                                   domain="[('patient_id', '=', patient_id)]")
    tryin_ids = fields.One2many('dmag.lab.tryin', 'order_id', string='Các bước thử')

    state = fields.Selection([
        ('draft', 'Nháp'),
        ('sent', 'Đã gửi labo'),
        ('in_progress', 'Labo đang làm'),
        ('try_in', 'Đang thử'),
        ('received', 'Đã nhận'),
        ('fitted', 'Đã gắn'),
        ('remake', 'Làm lại'),
        ('cancelled', 'Đã hủy'),
    ], string='Trạng thái', default='draft', required=True, tracking=True, copy=False, index=True)
    is_late = fields.Boolean('Trễ hạn', compute='_compute_is_late', search='_search_is_late')
    late_days = fields.Integer('Số ngày trễ', compute='_compute_is_late')

    cost = fields.Monetary('Chi phí labo', tracking=True, help='Giá gia công thỏa thuận với labo – '
                                                               'sinh đơn mua hàng khi gửi phiếu.')
    cost_product_id = fields.Many2one('product.product', string='Khoản phí',
                                      default=lambda self: self.env.ref('dmag_dental_lab.product_lab_fee',
                                                                        raise_if_not_found=False),
                                      domain=[('purchase_ok', '=', True)])
    purchase_order_id = fields.Many2one('purchase.order', string='Đơn mua labo', readonly=True, copy=False)
    purchase_order_name = fields.Char('Số đơn mua', compute='_compute_purchase_order_name')
    remake_of_id = fields.Many2one('dmag.lab.order', string='Làm lại từ phiếu', readonly=True, copy=False)
    remake_ids = fields.One2many('dmag.lab.order', 'remake_of_id', string='Phiếu làm lại')
    remake_reason = fields.Char('Lý do làm lại', copy=False)
    remake_responsibility = fields.Selection([
        ('lab', 'Lỗi labo'), ('clinic', 'Lỗi phòng khám (dấu/màu/chỉ định)'), ('patient', 'Do bệnh nhân'),
    ], string='Trách nhiệm làm lại', copy=False)
    attachment_ids = fields.Many2many('ir.attachment', string='Ảnh / file đính kèm')
    note = fields.Text('Ghi chú')

    # ------------------------------------------------------------------ compute
    @api.depends('tooth_ids')
    def _compute_unit_count(self):
        for order in self:
            order.unit_count = len(order.tooth_ids) or order.unit_count or 1

    @api.depends('state', 'due_date')
    def _compute_is_late(self):
        today = fields.Date.context_today(self)
        for order in self:
            late = order.state in OPEN_STATES and order.due_date and order.due_date < today
            order.is_late = bool(late)
            order.late_days = (today - order.due_date).days if late else 0

    def _search_is_late(self, operator, value):
        today = fields.Date.context_today(self)
        domain = [('state', 'in', OPEN_STATES), ('due_date', '<', today)]
        positive = (operator == '=' and value) or (operator == '!=' and not value)
        return domain if positive else ['!', '&'] + domain[:1] + domain[1:]

    def _compute_purchase_order_name(self):
        for order in self:
            order.purchase_order_name = order.purchase_order_id.sudo().name or False

    @api.onchange('lab_partner_id')
    def _onchange_lab_partner_id(self):
        if self.lab_partner_id and not self.due_date:
            self.due_date = fields.Date.context_today(self) + timedelta(days=self.lab_partner_id.dmag_lab_lead_days or 7)

    @api.onchange('visit_id')
    def _onchange_visit_id(self):
        if self.visit_id:
            self.patient_id = self.visit_id.patient_id
            self.doctor_id = self.visit_id.doctor_id

    @api.onchange('plan_line_id')
    def _onchange_plan_line_id(self):
        if self.plan_line_id:
            self.tooth_ids = self.plan_line_id.tooth_ids

    @api.constrains('due_date', 'sent_date')
    def _check_dates(self):
        for order in self:
            if order.due_date and order.sent_date and order.due_date < order.sent_date:
                raise ValidationError(_('Ngày hẹn trả không được trước ngày gửi labo.'))

    @api.constrains('lab_partner_id')
    def _check_lab_partner(self):
        for order in self:
            if order.lab_partner_id and not order.lab_partner_id.is_dental_lab:
                raise ValidationError(_('"%s" chưa được đánh dấu là labo nha khoa.', order.lab_partner_id.name))

    # ------------------------------------------------------------------ CRUD
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('dmag.lab.order') or '/'
            if vals.get('visit_id') and not vals.get('patient_id'):
                vals['patient_id'] = self.env['dmag.dental.visit'].browse(vals['visit_id']).patient_id.id
        return super().create(vals_list)

    def write(self, vals):
        if not is_workflow(self.env) and not is_director(self.env):
            if 'state' in vals or 'purchase_order_id' in vals:
                raise AccessError(_('Trạng thái phiếu labo đổi bằng các nút theo quy trình.'))
            if LOCKED_AFTER_SENT & set(vals) and any(o.state != 'draft' for o in self):
                raise AccessError(_('Phiếu labo đã gửi – chỉ Giám đốc / Quản lý cấp cao được sửa chi phí, labo.'))
            if any(o.state in ('fitted', 'cancelled', 'remake') for o in self):
                raise AccessError(_('Phiếu labo đã đóng – chỉ Giám đốc / Quản lý cấp cao được sửa.'))
        res = super().write(vals)
        if 'cost' in vals:
            self.filtered('purchase_order_id')._sync_purchase_cost()
        return res

    def unlink(self):
        if any(o.state != 'draft' for o in self):
            check_director(self.env, _('Chỉ xóa được phiếu labo nháp. Phiếu đã gửi hãy dùng "Hủy".'))
        return super().unlink()

    def _workflow_write(self, vals):
        return self.with_context(dmag_workflow=True).write(vals)

    # ------------------------------------------------------------------ workflow
    def action_send(self):
        for order in self:
            if order.state != 'draft':
                raise UserError(_('Phiếu %s không ở trạng thái nháp.', order.name))
            if not order.lab_partner_id:
                raise UserError(_('Chọn labo trước khi gửi phiếu %s.', order.name))
            if not order.due_date:
                raise UserError(_('Nhập ngày hẹn trả cho phiếu %s.', order.name))
            vals = {'state': 'sent'}
            if not order.sent_date:
                vals['sent_date'] = fields.Date.context_today(order)
            order._workflow_write(vals)
            order._create_purchase_order()
            order.message_post(body=_('Đã gửi labo %(lab)s, hẹn trả %(due)s.',
                                      lab=order.lab_partner_id.name, due=order.due_date))
        return True

    def action_start(self):
        self._check_state(('sent',))
        self._workflow_write({'state': 'in_progress'})
        return True

    def action_try_in(self):
        self._check_state(('sent', 'in_progress', 'try_in'))
        self._workflow_write({'state': 'try_in'})
        return True

    def action_receive(self):
        self._check_state(OPEN_STATES)
        self._workflow_write({'state': 'received', 'received_date': fields.Date.context_today(self)})
        self.activity_unlink(['mail.mail_activity_data_todo'])
        return True

    def action_fit(self):
        self._check_state(('received',))
        self._workflow_write({'state': 'fitted', 'fitted_date': fields.Date.context_today(self)})
        return True

    def action_remake(self):
        """Đóng phiếu hiện tại ở trạng thái "Làm lại" và mở phiếu mới (nháp) cùng chỉ định."""
        new_orders = self.browse()
        for order in self:
            if order.state not in OPEN_STATES + ('received', 'fitted'):
                raise UserError(_('Chỉ làm lại được phiếu đã gửi labo.'))
            if not order.remake_reason:
                raise UserError(_('Nhập lý do làm lại cho phiếu %s.', order.name))
            new = order.copy({'remake_of_id': order.id, 'due_date': False,
                              'tryin_ids': False, 'attachment_ids': [(6, 0, order.attachment_ids.ids)]})
            order._workflow_write({'state': 'remake'})
            order.message_post(body=_('Làm lại: %(reason)s → phiếu mới %(new)s.',
                                      reason=order.remake_reason, new=new.name))
            new_orders |= new
        if len(new_orders) == 1:
            return {'type': 'ir.actions.act_window', 'res_model': 'dmag.lab.order',
                    'res_id': new_orders.id, 'view_mode': 'form'}
        return True

    def action_cancel(self):
        for order in self:
            if order.state in ('fitted', 'cancelled', 'remake'):
                raise UserError(_('Phiếu %s đã đóng.', order.name))
            if order.state != 'draft':
                check_director(self.env, _('Phiếu labo đã gửi – chỉ Giám đốc / Quản lý cấp cao được hủy.'))
            po = order.purchase_order_id.sudo()
            if po and po.state not in ('cancel', 'done') and not po.invoice_ids.filtered(lambda m: m.state == 'posted'):
                po.button_cancel()
            order._workflow_write({'state': 'cancelled'})
        return True

    def _check_state(self, states):
        for order in self:
            if order.state not in states:
                raise UserError(_('Phiếu %(name)s đang ở trạng thái "%(state)s" – không thực hiện được thao tác này.',
                                  name=order.name,
                                  state=dict(self._fields['state'].selection).get(order.state)))

    # ------------------------------------------------------------------ purchase
    def _purchase_line_name(self):
        self.ensure_one()
        work = dict(self._fields['work_type'].selection).get(self.work_type)
        parts = [f'{self.name} – {work}']
        if self.tooth_ids:
            parts.append(_('Răng %s', ', '.join(self.tooth_ids.mapped('code'))))
        if self.shade:
            parts.append(_('Màu %s', self.shade))
        if self.material:
            parts.append(dict(self._fields['material'].selection).get(self.material))
        parts.append(_('BN %s', self.patient_id.patient_code or self.patient_id.name))
        return ' · '.join(parts)

    def _create_purchase_order(self):
        """Sinh đơn mua (quyền hệ thống) ghi nhận chi phí labo → công nợ labo khi có hóa đơn."""
        self.ensure_one()
        if self.purchase_order_id or not self.cost:
            return False
        product = self.cost_product_id or self.env.ref('dmag_dental_lab.product_lab_fee')
        PO = self.env['purchase.order'].sudo().with_company(self.company_id)
        po = PO.create({
            'partner_id': self.lab_partner_id.id,
            'company_id': self.company_id.id,
            'origin': self.name,
            'partner_ref': self.name,
            'date_planned': fields.Datetime.to_datetime(self.due_date),
            'order_line': [(0, 0, {
                'product_id': product.id,
                'name': self._purchase_line_name(),
                'product_qty': 1.0,
                'product_uom': product.uom_po_id.id or product.uom_id.id,
                'price_unit': self.cost,
                'taxes_id': [(6, 0, [])],
                'date_planned': fields.Datetime.to_datetime(self.due_date),
            })],
        })
        po.button_confirm()
        self._workflow_write({'purchase_order_id': po.id})
        self.message_post(body=_('Đã tạo đơn mua labo %s.', po.name))
        return po

    def _sync_purchase_cost(self):
        for order in self:
            po = order.purchase_order_id.sudo()
            line = po.order_line[:1]
            if line and not line.qty_invoiced:
                line.price_unit = order.cost
                po.message_post(body=_('Cập nhật chi phí labo theo phiếu %s.', order.name))

    def action_open_purchase_order(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'purchase.order',
                'res_id': self.purchase_order_id.id, 'view_mode': 'form'}

    # ------------------------------------------------------------------ cron
    @api.model
    def _cron_check_overdue(self):
        """Tạo việc nhắc cho bác sĩ / người tạo phiếu khi labo trễ hạn."""
        todo = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        if not todo:
            return
        for order in self.search([('is_late', '=', True)]):
            user = order.doctor_id.user_id or order.create_uid
            if order.activity_ids.filtered(lambda a: a.activity_type_id == todo):
                continue
            order.activity_schedule(
                act_type_xmlid='mail.mail_activity_data_todo',
                date_deadline=fields.Date.context_today(order),
                summary=_('Labo trễ hạn %s ngày – liên hệ %s', order.late_days, order.lab_partner_id.name),
                user_id=user.id,
            )

    # ------------------------------------------------------------------ KPI
    @api.model
    def get_lab_kpis(self, date_from, date_to, company_id=False):
        """Chỉ số labo cho Bảng điều hành mục tiêu.

        Chi phí labo ghi nhận theo ngày gửi; doanh thu = thủ thuật hoàn tất theo ngày lượt khám.
        """
        company = self.env['res.company'].browse(company_id) if company_id else self.env.company
        d_from, d_to = fields.Date.to_date(date_from), fields.Date.to_date(date_to)
        orders = self.sudo().search([
            ('company_id', '=', company.id), ('state', 'not in', ('draft', 'cancelled')),
            ('sent_date', '>=', d_from), ('sent_date', '<=', d_to),
        ])
        lab_cost = sum(orders.mapped('cost'))
        revenue = procedure_revenue(self.env, d_from, d_to, company)
        ratio = round(lab_cost / revenue * 100.0, 2) if revenue else 0.0
        threshold = getattr(company, 'dmag_cogs_threshold', 0.0) or 22.0
        closed = orders.filtered(lambda o: o.state in ('received', 'fitted', 'remake'))
        on_time = closed.filtered(lambda o: o.received_date and o.due_date and o.received_date <= o.due_date)
        return {
            'company_id': company.id,
            'date_from': fields.Date.to_string(d_from),
            'date_to': fields.Date.to_string(d_to),
            'currency': company.currency_id.name,
            'lab_cost': lab_cost,
            'revenue': revenue,
            'lab_cost_ratio': ratio,
            'threshold': threshold,
            'alert': bool(revenue) and ratio > threshold,
            'order_count': len(orders),
            'open_count': self.sudo().search_count([('company_id', '=', company.id), ('state', 'in', OPEN_STATES)]),
            'late_count': self.sudo().search_count([('company_id', '=', company.id), ('is_late', '=', True)]),
            'remake_count': len(orders.filtered(lambda o: o.state == 'remake')),
            'on_time_rate': round(len(on_time) / len(closed) * 100.0, 1) if closed else 0.0,
        }


class DmagLabTryin(models.Model):
    _name = 'dmag.lab.tryin'
    _description = 'Bước thử phục hình labo'
    _order = 'date, id'

    order_id = fields.Many2one('dmag.lab.order', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='order_id.company_id', store=True)
    step = fields.Selection([
        ('framework', 'Thử sườn'),
        ('bisque', 'Thử sứ (biscuit)'),
        ('wax', 'Thử sáp / thử răng'),
        ('bite', 'Ghi khớp cắn'),
        ('other', 'Khác'),
    ], string='Bước', required=True, default='framework')
    date = fields.Date('Ngày thử', default=fields.Date.context_today, required=True)
    visit_id = fields.Many2one('dmag.dental.visit', string='Lượt khám')
    result = fields.Selection([('ok', 'Đạt'), ('adjust', 'Cần chỉnh – gửi lại labo')],
                              string='Kết quả', default='ok', required=True)
    note = fields.Char('Ghi chú')

    @api.model_create_multi
    def create(self, vals_list):
        steps = super().create(vals_list)
        for order in steps.mapped('order_id'):
            if order.state in ('sent', 'in_progress'):
                order.action_try_in()
        return steps
