from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from odoo.addons.dmag_dental_base.models.dmag_access import check_director, is_director, is_workflow


class DmagWarrantyCard(models.Model):
    """Thẻ bảo hành điện tử – sinh tự động khi thủ thuật có bảo hành hoàn tất.

    Thẻ khóa sau khi tạo: chỉ quy trình (hết hạn, yêu cầu bảo hành) đổi trạng thái;
    chỉ Giám đốc / Quản lý cấp cao được hủy (vô hiệu) hoặc sửa.
    """
    _name = 'dmag.warranty.card'
    _description = 'Thẻ bảo hành nha khoa'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'start_date desc, id desc'

    name = fields.Char('Mã thẻ', required=True, copy=False, readonly=True, default='/', index=True)
    company_id = fields.Many2one('res.company', string='Phòng khám', required=True, index=True,
                                 default=lambda self: self.env.company)
    patient_id = fields.Many2one('res.partner', string='Bệnh nhân', required=True, index=True,
                                 domain=[('is_patient', '=', True)])
    patient_code = fields.Char(related='patient_id.patient_code', string='Mã BN')
    procedure_id = fields.Many2one('dmag.dental.procedure', string='Thủ thuật', index=True, ondelete='restrict')
    visit_id = fields.Many2one('dmag.dental.visit', string='Lượt khám')
    doctor_id = fields.Many2one('dmag.dental.practitioner', string='Bác sĩ thực hiện')
    product_id = fields.Many2one('product.product', string='Dịch vụ', required=True)
    tooth_ids = fields.Many2many('dmag.dental.tooth', string='Răng')
    teeth_label = fields.Char('Vị trí răng', compute='_compute_teeth_label')
    lab_order_ref = fields.Char('Phiếu labo', help='Số phiếu labo của phục hình (nếu có).')
    serial_ref = fields.Char('Số serial / lô', help='Serial trụ implant, lô vật liệu (nếu có).')
    months = fields.Integer('Thời hạn (tháng)', required=True)
    start_date = fields.Date('Ngày bắt đầu', required=True, default=fields.Date.context_today)
    end_date = fields.Date('Ngày hết hạn', required=True)
    days_left = fields.Integer('Còn (ngày)', compute='_compute_days_left')
    conditions = fields.Text('Điều kiện bảo hành')
    state = fields.Selection([
        ('active', 'Còn hiệu lực'),
        ('claimed', 'Đã bảo hành'),
        ('expired', 'Hết hạn'),
        ('void', 'Vô hiệu'),
    ], string='Trạng thái', default='active', required=True, tracking=True, index=True)
    void_reason = fields.Char('Lý do vô hiệu', tracking=True)
    claim_ids = fields.One2many('dmag.warranty.claim', 'card_id', string='Yêu cầu bảo hành')
    claim_count = fields.Integer(compute='_compute_claim_count')

    _sql_constraints = [
        ('name_company_uniq', 'unique(name, company_id)', 'Mã thẻ bảo hành đã tồn tại.'),
    ]

    @api.depends('tooth_ids')
    def _compute_teeth_label(self):
        for card in self:
            card.teeth_label = ', '.join(card.tooth_ids.mapped('code'))

    @api.depends('end_date')
    def _compute_days_left(self):
        today = fields.Date.context_today(self)
        for card in self:
            card.days_left = (card.end_date - today).days if card.end_date else 0

    def _compute_claim_count(self):
        for card in self:
            card.claim_count = len(card.claim_ids)

    @api.depends('name', 'product_id')
    def _compute_display_name(self):
        for card in self:
            card.display_name = f'{card.name} – {card.product_id.name}' if card.product_id else card.name

    # ------------------------------------------------------------------ CRUD
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('dmag.warranty.card') or '/'
            if not vals.get('end_date') and vals.get('months'):
                start = fields.Date.to_date(vals.get('start_date')) or fields.Date.context_today(self)
                vals['end_date'] = start + relativedelta(months=vals['months'])
        return super().create(vals_list)

    def write(self, vals):
        if not is_workflow(self.env) and not is_director(self.env):
            raise AccessError(_('Thẻ bảo hành đã phát hành – chỉ Giám đốc / Quản lý cấp cao được sửa hoặc vô hiệu.'))
        return super().write(vals)

    def unlink(self):
        check_director(self.env, _('Không xóa thẻ bảo hành – dùng "Vô hiệu" (Giám đốc).'))
        if any(card.claim_ids for card in self):
            raise UserError(_('Thẻ đã có yêu cầu bảo hành – không xóa được, hãy vô hiệu.'))
        return super().unlink()

    @api.constrains('start_date', 'end_date')
    def _check_dates(self):
        for card in self:
            if card.end_date < card.start_date:
                raise ValidationError(_('Ngày hết hạn phải sau ngày bắt đầu.'))

    @api.model
    def _prepare_from_procedure(self, proc):
        """Giá trị thẻ từ thủ thuật. Liên kết mềm tới labo / serial nếu có module tương ứng."""
        product = proc.product_id
        visit = proc.visit_id
        # Bảo hành tính từ ngày hoàn tất thủ thuật
        start = fields.Date.context_today(self)
        vals = {
            'company_id': proc.company_id.id or self.env.company.id,
            'patient_id': proc.patient_id.id,
            'procedure_id': proc.id,
            'visit_id': visit.id,
            'doctor_id': proc.doctor_id.id,
            'product_id': product.id,
            'tooth_ids': [(6, 0, proc.tooth_ids.ids)],
            'months': product.warranty_months,
            'start_date': start,
            'end_date': start + relativedelta(months=product.warranty_months),
            'conditions': product.warranty_conditions or False,
        }
        # Serial implant / lô vật liệu (dmag_dental_stock)
        if 'lot_ids' in proc._fields and proc.lot_ids:
            vals['serial_ref'] = ', '.join(proc.sudo().lot_ids.mapped('display_name'))
        # Phiếu labo (dmag_dental_lab)
        if 'dmag.lab.order' in self.env:
            LabOrder = self.env['dmag.lab.order'].sudo()
            domain = [('patient_id', '=', proc.patient_id.id), ('state', 'not in', ('cancelled', 'remake', 'draft'))]
            if proc.plan_line_id:
                orders = LabOrder.search(domain + [('plan_line_id', '=', proc.plan_line_id.id)], limit=1)
            else:
                orders = LabOrder.browse()
            if not orders and proc.tooth_ids:
                orders = LabOrder.search(domain + [('tooth_ids', 'in', proc.tooth_ids.ids)], limit=1)
            if orders:
                vals['lab_order_ref'] = orders.name
        return vals

    # ------------------------------------------------------------------ actions
    def action_void(self):
        check_director(self.env, _('Chỉ Giám đốc / Quản lý cấp cao được vô hiệu thẻ bảo hành.'))
        for card in self:
            if not card.void_reason:
                raise UserError(_('Nhập lý do vô hiệu thẻ %s.', card.name))
            card.with_context(dmag_workflow=True).state = 'void'
        return True

    def action_open_claims(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Yêu cầu bảo hành'),
            'res_model': 'dmag.warranty.claim',
            'view_mode': 'tree,form',
            'domain': [('card_id', '=', self.id)],
            'context': {'default_card_id': self.id},
        }

    def action_print_card(self):
        return self.env.ref('dmag_dental_warranty.action_report_warranty_card').report_action(self)

    # ------------------------------------------------------------------ expiry
    @api.model
    def _dmag_warranty_expiring(self, days=30, company_id=False):
        """Thẻ còn hiệu lực sẽ hết hạn trong ``days`` ngày tới (dùng cho nhắc ZNS ở module hành trình)."""
        today = fields.Date.context_today(self)
        domain = [('state', '=', 'active'), ('end_date', '>=', today),
                  ('end_date', '<=', today + timedelta(days=days))]
        if company_id:
            domain.append(('company_id', '=', company_id))
        return self.sudo().search(domain, order='end_date')

    def _dmag_warranty_expiry_notify(self):
        """Điểm móc: module hành trình (ZNS) mở rộng bằng super() để gửi tin nhắc bệnh nhân."""
        return True

    @api.model
    def _cron_warranty_expiry(self, days=30):
        today = fields.Date.context_today(self)
        expired = self.sudo().search([('state', '=', 'active'), ('end_date', '<', today)])
        expired.with_context(dmag_workflow=True).write({'state': 'expired'})
        expiring = self._dmag_warranty_expiring(days)
        todo = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        manager_group = self.env.ref('dmag_dental_base.group_dmag_manager', raise_if_not_found=False)
        for card in expiring:
            if todo and card.activity_ids.filtered(lambda a: a.activity_type_id == todo):
                continue
            user = card.doctor_id.user_id
            if not user and manager_group:
                user = manager_group.users.filtered(lambda u: card.company_id in u.company_ids)[:1]
            card.activity_schedule(
                act_type_xmlid='mail.mail_activity_data_todo',
                date_deadline=card.end_date - timedelta(days=7) if card.days_left > 7 else today,
                summary=_('Thẻ bảo hành %s hết hạn ngày %s – mời bệnh nhân kiểm tra', card.name, card.end_date),
                user_id=(user or self.env.user).id,
            )
        expiring._dmag_warranty_expiry_notify()
        return expiring


class DmagWarrantyClaim(models.Model):
    _name = 'dmag.warranty.claim'
    _description = 'Yêu cầu bảo hành'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'

    name = fields.Char('Số yêu cầu', required=True, copy=False, readonly=True, default='/')
    card_id = fields.Many2one('dmag.warranty.card', string='Thẻ bảo hành', required=True, index=True,
                              domain=[('state', 'in', ('active', 'claimed'))])
    company_id = fields.Many2one(related='card_id.company_id', store=True)
    patient_id = fields.Many2one(related='card_id.patient_id', store=True, string='Bệnh nhân')
    product_id = fields.Many2one(related='card_id.product_id', string='Dịch vụ')
    date = fields.Date('Ngày yêu cầu', required=True, default=fields.Date.context_today)
    issue = fields.Text('Tình trạng / vấn đề', required=True)
    decision = fields.Selection([
        ('pending', 'Chờ đánh giá'),
        ('covered', 'Được bảo hành'),
        ('not_covered', 'Không thuộc bảo hành'),
    ], string='Kết luận', default='pending', required=True, tracking=True)
    decision_note = fields.Text('Giải thích kết luận')
    decided_by_id = fields.Many2one('res.users', string='Người kết luận', readonly=True)
    decided_date = fields.Date('Ngày kết luận', readonly=True)
    visit_id = fields.Many2one('dmag.dental.visit', string='Lượt khám bảo hành',
                               domain="[('patient_id', '=', patient_id)]")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('dmag.warranty.claim') or '/'
            card = self.env['dmag.warranty.card'].browse(vals.get('card_id'))
            if card.state == 'void':
                raise ValidationError(_('Thẻ %s đã vô hiệu.', card.name))
            if not is_director(self.env):
                vals.pop('decision', None)
        return super().create(vals_list)

    def write(self, vals):
        if not is_workflow(self.env) and not is_director(self.env):
            if 'decision' in vals or 'decided_by_id' in vals:
                raise AccessError(_('Kết luận bảo hành dùng nút "Được bảo hành" / "Không thuộc bảo hành".'))
            if any(c.decision != 'pending' for c in self) and set(vals) - {'visit_id'}:
                raise AccessError(_('Yêu cầu bảo hành đã kết luận – chỉ Giám đốc / Quản lý cấp cao được sửa.'))
        return super().write(vals)

    def unlink(self):
        if any(c.decision != 'pending' for c in self):
            check_director(self.env)
        return super().unlink()

    def _decide(self, decision):
        if not self.env.user.has_group('dmag_dental_base.group_dmag_doctor') and not self.env.su:
            raise AccessError(_('Chỉ bác sĩ / quản lý được kết luận bảo hành.'))
        for claim in self:
            if claim.decision != 'pending':
                raise UserError(_('Yêu cầu %s đã kết luận.', claim.name))
            if decision == 'covered':
                if claim.card_id.state == 'void':
                    raise UserError(_('Thẻ đã vô hiệu.'))
                if claim.date > claim.card_id.end_date:
                    raise UserError(_('Ngày yêu cầu sau ngày hết hạn bảo hành (%s).', claim.card_id.end_date))
            elif not claim.decision_note:
                raise UserError(_('Ghi rõ lý do không thuộc bảo hành để giải thích với bệnh nhân.'))
            claim.with_context(dmag_workflow=True).write({
                'decision': decision,
                'decided_by_id': self.env.user.id,
                'decided_date': fields.Date.context_today(claim),
            })
            if decision == 'covered':
                claim.card_id.with_context(dmag_workflow=True).write({'state': 'claimed'})
            claim.card_id.message_post(body=_('Yêu cầu bảo hành %(claim)s: %(decision)s.', claim=claim.name,
                                              decision=dict(self._fields['decision'].selection)[decision]))
        return True

    def action_cover(self):
        return self._decide('covered')

    def action_reject(self):
        return self._decide('not_covered')

    def action_create_visit(self):
        """Tạo lượt khám bảo hành (lễ tân xếp giờ, ghế sau)."""
        self.ensure_one()
        if not self.visit_id:
            card = self.card_id
            visit = self.env['dmag.dental.visit'].create({
                'patient_id': card.patient_id.id,
                'company_id': card.company_id.id,
                'doctor_id': card.doctor_id.id,
                'reason': _('Bảo hành %(card)s – %(service)s', card=card.name, service=card.product_id.name),
            })
            self.with_context(dmag_workflow=True).visit_id = visit
        return {'type': 'ir.actions.act_window', 'res_model': 'dmag.dental.visit',
                'res_id': self.visit_id.id, 'view_mode': 'form'}
