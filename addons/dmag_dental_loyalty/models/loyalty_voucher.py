import secrets
import string
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from odoo.addons.dmag_dental_base.models.dmag_access import (
    check_director, check_discount, is_director, is_manager, is_workflow)

MIN_VALIDITY_DAYS = 7
CODE_ALPHABET = string.ascii_uppercase.replace('O', '').replace('I', '') + '23456789'


class DmagLoyaltyVoucher(models.Model):
    """Voucher ưu đãi – đổi từ điểm hoặc quà theo hạng.

    * Cầu chì y đức: hạn dùng tối thiểu 7 ngày (không có ưu đãi "chỉ hôm nay").
    * Dùng một lần; sau khi phát hành, nhân viên không sửa được (tạo được – không sửa).
    """
    _name = 'dmag.loyalty.voucher'
    _description = 'Voucher khách hàng thân thiết'
    _inherit = ['mail.thread']
    _order = 'id desc'

    name = fields.Char('Mã voucher', required=True, copy=False, readonly=True,
                       default=lambda self: self._generate_code(), index=True)
    partner_id = fields.Many2one('res.partner', string='Bệnh nhân', required=True, index=True,
                                 domain=[('is_patient', '=', True)], tracking=True)
    company_id = fields.Many2one('res.company', string='Phòng khám', required=True,
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    value_type = fields.Selection([('amount', 'Số tiền'), ('percent', 'Phần trăm')],
                                  string='Loại ưu đãi', default='amount', required=True)
    value = fields.Float('Giá trị', required=True, help='Số tiền (₫) hoặc % tùy loại ưu đãi.')
    max_amount = fields.Monetary('Giảm tối đa', help='Chỉ áp dụng cho voucher phần trăm. 0 = không giới hạn.')
    points_cost = fields.Integer('Điểm đã đổi', readonly=True)
    origin = fields.Selection([
        ('points', 'Đổi điểm'),
        ('gift', 'Quà theo hạng / sinh nhật'),
        ('manual', 'Khác'),
    ], string='Nguồn', default='gift', required=True)
    valid_from = fields.Date('Hiệu lực từ', required=True, default=fields.Date.context_today)
    valid_to = fields.Date('Hiệu lực đến', required=True,
                           default=lambda self: fields.Date.context_today(self) + timedelta(
                               days=max(self.env.company.dmag_loyalty_voucher_days, MIN_VALIDITY_DAYS)))
    state = fields.Selection([
        ('to_approve', 'Chờ duyệt'),
        ('active', 'Có hiệu lực'),
        ('used', 'Đã dùng'),
        ('expired', 'Hết hạn'),
        ('cancel', 'Đã hủy'),
    ], string='Trạng thái', default='to_approve', required=True, tracking=True, copy=False)
    approved_by_id = fields.Many2one('res.users', string='Người duyệt', readonly=True, copy=False)
    used_visit_id = fields.Many2one('dmag.dental.visit', string='Dùng tại lượt khám', readonly=True, copy=False)
    used_date = fields.Datetime('Thời điểm dùng', readonly=True, copy=False)
    used_amount = fields.Monetary('Số tiền đã giảm', readonly=True, copy=False)
    sale_line_id = fields.Many2one('sale.order.line', string='Dòng giảm giá', readonly=True, copy=False)
    note = fields.Char('Ghi chú')

    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'Mã voucher đã tồn tại.'),
    ]

    @api.model
    def _generate_code(self):
        return 'DM' + ''.join(secrets.choice(CODE_ALPHABET) for _i in range(8))

    # ------------------------------------------------------------------ constraints
    @api.constrains('valid_from', 'valid_to')
    def _check_min_validity(self):
        for voucher in self:
            if (voucher.valid_to - voucher.valid_from).days < MIN_VALIDITY_DAYS:
                raise ValidationError(_(
                    'Voucher phải có hiệu lực tối thiểu %s ngày – cầu chì y đức: không có ưu đãi kiểu '
                    '"chỉ hôm nay" ép khách quyết định.', MIN_VALIDITY_DAYS))

    @api.constrains('value', 'value_type')
    def _check_value(self):
        for voucher in self:
            if voucher.value <= 0:
                raise ValidationError(_('Giá trị voucher phải lớn hơn 0.'))
            if voucher.value_type == 'percent' and voucher.value > 100:
                raise ValidationError(_('Voucher phần trăm không vượt quá 100%.'))

    # ------------------------------------------------------------------ CRUD
    @api.model_create_multi
    def create(self, vals_list):
        if not is_workflow(self.env) and not is_manager(self.env):
            raise AccessError(_('Nhân viên đổi điểm qua nút "Đổi điểm lấy voucher"; '
                                'voucher quà tặng do Quản lý phòng khám phát hành.'))
        for vals in vals_list:
            if not is_workflow(self.env):
                # Tạo tay luôn qua bước duyệt
                vals['state'] = 'to_approve'
                vals.pop('points_cost', None)
        return super().create(vals_list)

    def write(self, vals):
        if not is_workflow(self.env) and not is_director(self.env):
            if set(vals) - {'note'}:
                raise AccessError(_('Voucher đã phát hành – chỉ Giám đốc / Quản lý cấp cao được sửa.'))
        return super().write(vals)

    def unlink(self):
        for voucher in self:
            if voucher.state != 'cancel' or voucher.points_cost:
                raise UserError(_('Không xóa voucher %s – hãy hủy để giữ vết.', voucher.name))
        check_director(self.env)
        return super().unlink()

    def _workflow_write(self, vals):
        return self.with_context(dmag_workflow=True).write(vals)

    # ------------------------------------------------------------------ redemption
    @api.model
    def create_from_points(self, partner_id, points, note=False):
        """Đổi điểm lấy voucher số tiền. Trên ngưỡng công ty → chờ Quản lý duyệt.

        Điểm bị trừ ngay khi đổi (giữ chỗ); bị từ chối / hủy thì hoàn điểm.
        """
        partner = self.env['res.partner'].browse(partner_id).exists()
        if not partner or not partner.is_patient:
            raise UserError(_('Chỉ bệnh nhân mới đổi được điểm.'))
        company = self.env.company
        points = int(points or 0)
        if points < max(company.dmag_loyalty_min_redeem, 1):
            raise UserError(_('Mỗi lần đổi tối thiểu %s điểm.', company.dmag_loyalty_min_redeem))
        balance = partner._dmag_points_balance()
        if points > balance:
            raise UserError(_('Không đủ điểm: hiện có %(bal)s điểm, cần %(need)s.', bal=balance, need=points))
        needs_approval = points > company.dmag_loyalty_approval_points and not is_manager(self.env)
        voucher = self.with_context(dmag_workflow=True).sudo().create({
            'partner_id': partner.id,
            'company_id': company.id,
            'value_type': 'amount',
            'value': points * company.dmag_loyalty_point_value,
            'points_cost': points,
            'origin': 'points',
            'state': 'to_approve' if needs_approval else 'active',
            'approved_by_id': False if needs_approval else self.env.user.id,
            'note': note or False,
        })
        self.env['dmag.loyalty.ledger']._dmag_earn(
            partner, 'redemption', -points, source=voucher, key='voucher:%s' % voucher.id,
            note=_('Đổi %(pts)s điểm lấy voucher %(code)s', pts=points, code=voucher.name), company=company)
        voucher.message_post(body=_('Đổi %(pts)s điểm – người thực hiện: %(user)s',
                                    pts=points, user=self.env.user.name))
        return voucher.with_env(self.env)

    def action_approve(self):
        if not is_manager(self.env):
            raise AccessError(_('Chỉ Quản lý phòng khám trở lên được duyệt voucher.'))
        for voucher in self.filtered(lambda v: v.state == 'to_approve'):
            if voucher.value_type == 'percent':
                check_discount(self.env, voucher.value, voucher.company_id)
            voucher._workflow_write({'state': 'active', 'approved_by_id': self.env.user.id})
        return True

    def _refund_points(self, label):
        for voucher in self.filtered('points_cost'):
            self.env['dmag.loyalty.ledger']._dmag_earn(
                voucher.partner_id, 'redemption', voucher.points_cost, source=voucher,
                key='voucher_refund:%s' % voucher.id, note=label % voucher.name, company=voucher.company_id)

    def action_reject(self):
        if not is_manager(self.env):
            raise AccessError(_('Chỉ Quản lý phòng khám trở lên được từ chối voucher.'))
        vouchers = self.filtered(lambda v: v.state == 'to_approve')
        vouchers._workflow_write({'state': 'cancel'})
        vouchers._refund_points(_('Hoàn điểm – voucher %s không được duyệt'))
        return True

    def action_cancel(self):
        check_director(self.env, _('Chỉ Giám đốc / Quản lý cấp cao được hủy voucher đã phát hành.'))
        vouchers = self.filtered(lambda v: v.state in ('to_approve', 'active'))
        vouchers._workflow_write({'state': 'cancel'})
        vouchers._refund_points(_('Hoàn điểm – hủy voucher %s'))
        return True

    @api.model
    def _cron_expire(self):
        today = fields.Date.context_today(self)
        self.search([('state', '=', 'active'), ('valid_to', '<', today)])._workflow_write({'state': 'expired'})

    # ------------------------------------------------------------------ usage
    def _check_usable_for(self, patient, company):
        self.ensure_one()
        today = fields.Date.context_today(self)
        if self.state != 'active':
            raise UserError(_('Voucher %(code)s không dùng được (trạng thái: %(state)s).', code=self.name,
                              state=dict(self._fields['state'].selection)[self.state]))
        if not self.valid_from <= today <= self.valid_to:
            raise UserError(_('Voucher %s không trong thời hạn hiệu lực.', self.name))
        if self.company_id != company:
            raise UserError(_('Voucher %s thuộc phòng khám khác.', self.name))
        owners = patient._dmag_pool_members()
        if self.partner_id not in owners:
            raise UserError(_('Voucher %s không thuộc bệnh nhân này / gia đình của bệnh nhân.', self.name))

    def _compute_discount_amount(self, base_amount):
        self.ensure_one()
        if self.value_type == 'amount':
            amount = self.value
        else:
            amount = base_amount * self.value / 100.0
            if self.max_amount:
                amount = min(amount, self.max_amount)
        return self.currency_id.round(min(amount, base_amount))

    def _voucher_dict(self):
        return [{
            'id': v.id, 'code': v.name, 'value_type': v.value_type, 'value': v.value,
            'max_amount': v.max_amount, 'valid_from': fields.Date.to_string(v.valid_from),
            'valid_to': fields.Date.to_string(v.valid_to), 'state': v.state,
            'state_label': dict(self._fields['state'].selection)[v.state],
            'partner': v.partner_id.name, 'note': v.note or '',
        } for v in self]
