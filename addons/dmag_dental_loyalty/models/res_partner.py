import math

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

from .loyalty_ledger import ENGAGEMENT_REASONS


class ResPartner(models.Model):
    _inherit = 'res.partner'

    dmag_tier_id = fields.Many2one('dmag.loyalty.tier', string='Hạng thành viên', readonly=True, index=True,
                                   help='Tính lại hằng đêm và mỗi khi thanh toán.')
    dmag_tier_color = fields.Char(related='dmag_tier_id.color')
    dmag_paid_12m = fields.Monetary('Thực thu 12 tháng', readonly=True, currency_field='dmag_currency_id')
    dmag_lifetime_paid = fields.Monetary('Thực thu tích lũy', readonly=True, currency_field='dmag_currency_id')
    dmag_engagement_12m = fields.Integer('Điểm gắn bó 12 tháng', readonly=True)
    dmag_loyalty_date = fields.Datetime('Xét hạng lúc', readonly=True)
    dmag_currency_id = fields.Many2one('res.currency', compute='_compute_dmag_currency')
    dmag_points_balance = fields.Integer('Điểm khả dụng', compute='_compute_dmag_points',
                                         help='Gồm điểm của cả gia đình khi bật "Ví gia đình".')
    dmag_own_points = fields.Integer('Điểm cá nhân', compute='_compute_dmag_points')
    dmag_ledger_ids = fields.One2many('dmag.loyalty.ledger', 'partner_id', string='Sổ điểm')
    dmag_voucher_ids = fields.One2many('dmag.loyalty.voucher', 'partner_id', string='Voucher')
    dmag_care_subscription_ids = fields.One2many('dmag.care.subscription', 'partner_id', string='Gói chăm sóc')

    def _compute_dmag_currency(self):
        for partner in self:
            partner.dmag_currency_id = (partner.company_id or self.env.company).currency_id

    def _compute_dmag_points(self):
        for partner in self:
            if not partner.id:
                partner.dmag_points_balance = partner.dmag_own_points = 0
                continue
            partner.dmag_own_points = partner._dmag_sum_points(partner)
            partner.dmag_points_balance = partner._dmag_points_balance()

    # ------------------------------------------------------------------ pool helpers
    def _dmag_loyalty_company(self):
        self.ensure_one()
        return self.company_id or self.env.company

    def _dmag_pool_members(self):
        """Bệnh nhân dùng chung hạng & điểm (gia đình khi bật ví gia đình)."""
        self.ensure_one()
        partner = self.sudo()
        if partner.dental_family_id and partner._dmag_loyalty_company().dmag_loyalty_family_pool:
            return (partner.dental_family_id.member_ids | partner).with_env(self.env)
        return self

    @api.model
    def _dmag_sum_points(self, partners, domain=None):
        data = self.env['dmag.loyalty.ledger'].sudo()._read_group(
            [('partner_id', 'in', partners.ids)] + (domain or []), [], ['points:sum'])
        return int(data[0][0] or 0) if data else 0

    def _dmag_points_balance(self):
        self.ensure_one()
        return self._dmag_sum_points(self._dmag_pool_members())

    def _dmag_paid_amounts(self):
        """(thực thu 12 tháng, thực thu tích lũy) từ các khoản thu khách hàng đã ghi sổ."""
        self.ensure_one()
        date_from = fields.Date.context_today(self) - relativedelta(months=12)
        payments = self.env['account.payment'].sudo().search([
            ('partner_id', '=', self.id), ('partner_type', '=', 'customer'),
            ('state', '=', 'posted'), ('is_internal_transfer', '=', False),
        ])
        paid_12m = lifetime = 0.0
        for pay in payments:
            amount = pay.amount_signed
            lifetime += amount
            if pay.date >= date_from:
                paid_12m += amount
        return paid_12m, lifetime

    def _dmag_engagement_points(self):
        self.ensure_one()
        date_from = fields.Datetime.now() - relativedelta(months=12)
        return self._dmag_sum_points(self, [('reason', 'in', ENGAGEMENT_REASONS), ('points', '>', 0),
                                            ('date', '>=', date_from)])

    # ------------------------------------------------------------------ tier
    def _dmag_loyalty_recompute(self):
        """Tính lại thực thu, điểm gắn bó và hạng (cả gia đình khi dùng chung)."""
        Tier = self.env['dmag.loyalty.tier'].sudo()
        todo = self.browse()
        for partner in self.sudo().filtered('is_patient'):
            todo |= partner._dmag_pool_members().sudo()
        todo = todo.filtered('is_patient')
        own = {}
        for partner in todo:
            paid_12m, lifetime = partner._dmag_paid_amounts()
            own[partner.id] = (paid_12m, lifetime, partner._dmag_engagement_points())
        done = set()
        now = fields.Datetime.now()
        for partner in todo:
            if partner.id in done:
                continue
            pool = partner._dmag_pool_members().sudo().filtered('is_patient') | partner
            for member in pool - todo:
                paid_12m, lifetime = member._dmag_paid_amounts()
                own[member.id] = (paid_12m, lifetime, member._dmag_engagement_points())
            pool_paid = sum(own[m.id][0] for m in pool)
            pool_eng = sum(own[m.id][2] for m in pool)
            tier = Tier._find_tier(partner._dmag_loyalty_company(), pool_paid, pool_eng)
            for member in pool:
                paid_12m, lifetime, eng = own[member.id]
                vals = {'dmag_paid_12m': paid_12m, 'dmag_lifetime_paid': lifetime,
                        'dmag_engagement_12m': eng, 'dmag_loyalty_date': now}
                if member.dmag_tier_id != tier:
                    vals['dmag_tier_id'] = tier.id
                    if member.dmag_tier_id and tier and tier.level > member.dmag_tier_id.level:
                        member.message_post(body=_('Chúc mừng! Thăng hạng thành viên %s.', tier.name))
                member.with_context(dmag_workflow=True).write(vals)
                done.add(member.id)
        return True

    @api.model
    def _cron_dmag_loyalty_recompute(self, batch=500):
        partners = self.sudo().search([('is_patient', '=', True)])
        for start in range(0, len(partners), batch):
            partners[start:start + batch]._dmag_loyalty_recompute()
        return True

    def action_dmag_loyalty_recompute(self):
        self._dmag_loyalty_recompute()
        return True

    # ------------------------------------------------------------------ earning
    def _dmag_loyalty_earn_from_invoices(self, invoices, source=None):
        """Tích điểm theo từng khoản thanh toán đã đối trừ vào ``invoices`` (lũy đẳng / khoản thu)."""
        self.ensure_one()
        company = self._dmag_loyalty_company()
        per_point = company.dmag_loyalty_amount_per_point
        if per_point <= 0:
            return self.env['dmag.loyalty.ledger']
        Ledger = self.env['dmag.loyalty.ledger']
        entries = Ledger
        payments = invoices.sudo().filtered(lambda m: m.state == 'posted')._get_reconciled_payments()
        for payment in payments.filtered(lambda p: p.payment_type == 'inbound'):
            amount = payment.amount_signed
            points = math.floor(amount / per_point)
            entries |= Ledger._dmag_earn(
                self, 'payment', points, source=payment, key='payment:%s' % payment.id, amount=amount,
                note=_('Thanh toán %(ref)s', ref=(source.display_name if source else payment.name)),
                company=company)
        return entries

    def dmag_loyalty_award_survey(self, source=None, key=None):
        """Cộng điểm hoàn thành khảo sát / NPS (gọi từ module hành trình). Lũy đẳng theo ``key``."""
        self.ensure_one()
        company = self._dmag_loyalty_company()
        if not key and source:
            key = 'survey:%s,%s' % (source._name, source.id)
        return self.env['dmag.loyalty.ledger']._dmag_earn(
            self, 'survey', company.dmag_loyalty_survey_points, source=source, key=key,
            note=_('Hoàn thành khảo sát'), company=company)

    # ------------------------------------------------------------------ summary
    @api.model
    def get_loyalty_summary(self, partner_id):
        """Dữ liệu tổng hợp cho giao diện nội bộ và cổng bệnh nhân."""
        partner = self.browse(partner_id).exists()
        if not partner:
            raise AccessError(_('Không tìm thấy bệnh nhân.'))
        partner.check_access_rights('read')
        partner.check_access_rule('read')
        partner = partner.sudo()
        company = partner._dmag_loyalty_company()
        pool = partner._dmag_pool_members().sudo()
        pooled = len(pool) > 1 or bool(partner.dental_family_id and company.dmag_loyalty_family_pool)
        pool_paid = sum(pool.mapped('dmag_paid_12m'))
        pool_eng = sum(pool.mapped('dmag_engagement_12m'))
        tier = partner.dmag_tier_id
        next_tier = False
        tiers = self.env['dmag.loyalty.tier'].sudo()._get_tiers(company)
        higher = tiers.filtered(lambda t: t.level > (tier.level if tier else -1))
        if higher:
            nt = higher[0]
            ratios = []
            if nt.min_paid_12m:
                ratios.append(min(pool_paid / nt.min_paid_12m, 1.0))
            if nt.min_engagement_points:
                ratios.append(min(pool_eng / nt.min_engagement_points, 1.0))
            if ratios:
                progress = (min(ratios) if nt.condition == 'and' else max(ratios)) * 100.0
            else:
                progress = 100.0
            next_tier = dict(nt._tier_dict(),
                             missing_paid=max(nt.min_paid_12m - pool_paid, 0.0),
                             missing_points=max(nt.min_engagement_points - pool_eng, 0),
                             progress=round(progress, 1))
        today = fields.Date.context_today(self)
        vouchers = self.env['dmag.loyalty.voucher'].sudo().search([
            ('partner_id', 'in', pool.ids), ('state', 'in', ('active', 'to_approve')),
            ('valid_to', '>=', today)], order='valid_to asc')
        subs = self.env['dmag.care.subscription'].sudo().search([
            ('partner_id', '=', partner.id), ('state', '=', 'active')])
        ledger = self.env['dmag.loyalty.ledger'].sudo().search([('partner_id', 'in', pool.ids)], limit=20)
        family = partner.dental_family_id
        return {
            'partner': {'id': partner.id, 'name': partner.name, 'patient_code': partner.patient_code or ''},
            'currency': company.currency_id.symbol,
            'pooled': pooled,
            'family': {'id': family.id, 'name': family.name,
                       'head': family.head_id.name or ''} if family else False,
            'members': [{'id': m.id, 'name': m.name, 'patient_code': m.patient_code or '',
                         'points': self._dmag_sum_points(m)} for m in pool],
            'tier': tier._tier_dict() if tier else False,
            'points': partner._dmag_points_balance(),
            'own_points': self._dmag_sum_points(partner),
            'point_value': company.dmag_loyalty_point_value,
            'min_redeem': company.dmag_loyalty_min_redeem,
            'paid_12m': pool_paid,
            'engagement_12m': pool_eng,
            'lifetime_paid': partner.dmag_lifetime_paid,
            'next_tier': next_tier,
            'tiers': [t._tier_dict() for t in tiers],
            'vouchers': vouchers._voucher_dict(),
            'subscriptions': subs._subscription_dict(),
            'ledger': ledger._ledger_dict(),
            'updated_at': fields.Datetime.to_string(partner.dmag_loyalty_date) if partner.dmag_loyalty_date else False,
        }

    # ------------------------------------------------------------------ UI actions
    def action_open_dmag_ledger(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sổ điểm – %s', self.name),
            'res_model': 'dmag.loyalty.ledger',
            'view_mode': 'tree,form',
            'domain': [('partner_id', 'in', self._dmag_pool_members().ids)],
        }

    def action_open_dmag_redeem(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Đổi điểm lấy voucher'),
            'res_model': 'dmag.loyalty.redeem.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_partner_id': self.id},
        }

    def action_open_dmag_adjust(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Điều chỉnh điểm'),
            'res_model': 'dmag.loyalty.adjust.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_partner_id': self.id},
        }
