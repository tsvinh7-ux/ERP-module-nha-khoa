import secrets
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

TOKEN_VALID_DAYS = 30


class DmagNpsResponse(models.Model):
    """Khảo sát NPS 1 câu (0–10) sau lượt khám."""
    _name = 'dmag.nps.response'
    _description = 'Khảo sát NPS'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char('Mã phiếu', compute='_compute_name', store=True)
    token = fields.Char('Mã truy cập', required=True, copy=False, index=True, readonly=True,
                        default=lambda self: secrets.token_urlsafe(16), groups='dmag_dental_base.group_dmag_manager')
    company_id = fields.Many2one('res.company', string='Phòng khám', required=True, index=True,
                                 default=lambda self: self.env.company, readonly=True)
    partner_id = fields.Many2one('res.partner', string='Bệnh nhân', required=True, index=True, readonly=True)
    visit_id = fields.Many2one('dmag.dental.visit', string='Lượt khám', index=True, readonly=True)
    doctor_id = fields.Many2one(related='visit_id.doctor_id', store=True, string='Bác sĩ')
    channel = fields.Selection([
        ('zns', 'Zalo ZNS'),
        ('call', 'Gọi điện'),
        ('kiosk', 'Máy tính bảng tại quầy'),
        ('web', 'Web / tài khoản khách'),
    ], string='Kênh', default='zns', required=True, readonly=True)
    state = fields.Selection([
        ('pending', 'Chờ trả lời'),
        ('answered', 'Đã trả lời'),
    ], string='Trạng thái', default='pending', required=True, index=True, readonly=True, tracking=True)
    score = fields.Integer('Điểm NPS (0–10)', readonly=True, tracking=True)
    comment = fields.Text('Góp ý của khách', readonly=True)
    date = fields.Datetime('Trả lời lúc', readonly=True, index=True)
    category = fields.Selection([
        ('promoter', 'Ủng hộ (9–10)'),
        ('passive', 'Trung lập (7–8)'),
        ('detractor', 'Không hài lòng (0–6)'),
    ], string='Nhóm', compute='_compute_category', store=True)
    is_complaint = fields.Boolean('Phiếu phàn nàn', readonly=True, tracking=True)
    complaint_resolved = fields.Boolean('Đã xử lý phàn nàn', tracking=True)
    url = fields.Char('Link khảo sát', compute='_compute_url')
    expire_date = fields.Datetime('Hết hạn', readonly=True,
                                  default=lambda self: fields.Datetime.now() + timedelta(days=TOKEN_VALID_DAYS))

    _sql_constraints = [('token_uniq', 'unique(token)', 'Mã khảo sát bị trùng.')]

    @api.depends('partner_id', 'visit_id')
    def _compute_name(self):
        for resp in self:
            resp.name = 'NPS %s' % (resp.visit_id.name or resp.partner_id.display_name or '')

    @api.depends('score', 'state')
    def _compute_category(self):
        for resp in self:
            if resp.state != 'answered':
                resp.category = False
            elif resp.score >= 9:
                resp.category = 'promoter'
            elif resp.score >= 7:
                resp.category = 'passive'
            else:
                resp.category = 'detractor'

    def _compute_url(self):
        for resp in self:
            resp.url = '%s/dmag/nps/%s' % (resp.get_base_url(), resp.sudo().token)

    @api.model
    def _dmag_create_for_visit(self, visit, channel='zns'):
        existing = self.sudo().search([('visit_id', '=', visit.id), ('state', '=', 'pending')], limit=1)
        if existing:
            return existing
        return self.sudo().create({
            'company_id': visit.company_id.id,
            'partner_id': visit.patient_id.id,
            'visit_id': visit.id,
            'channel': channel,
        })

    @api.model
    def _dmag_from_token(self, token):
        if not token:
            return self.browse()
        return self.sudo().search([('token', '=', token)], limit=1)

    def submit(self, score, comment=False, channel=False):
        """Ghi nhận câu trả lời NPS (một lần – không sửa). Điểm ≤ 6 → phiếu phàn nàn cho Trưởng CSKH."""
        self.ensure_one()
        resp = self.sudo()
        try:
            score = int(score)
        except (TypeError, ValueError) as exc:
            raise ValidationError(_('Điểm NPS phải là số từ 0 đến 10.')) from exc
        if not 0 <= score <= 10:
            raise ValidationError(_('Điểm NPS phải từ 0 đến 10.'))
        if resp.state == 'answered':
            raise UserError(_('Phiếu khảo sát này đã được trả lời. Cảm ơn bạn!'))
        if resp.expire_date and resp.expire_date < fields.Datetime.now():
            raise UserError(_('Phiếu khảo sát đã hết hạn.'))
        vals = {'score': score, 'comment': comment or False, 'state': 'answered', 'date': fields.Datetime.now()}
        if channel:
            vals['channel'] = channel
        resp.write(vals)
        if score <= 6:
            resp._dmag_open_complaint()
        return True

    def _dmag_open_complaint(self):
        self.ensure_one()
        rule = self.env['dmag.journey.rule']
        lead = rule._dmag_responsible_user('cskh_lead', self.visit_id, self.company_id)
        self.write({'is_complaint': True})
        note = _('Khách %(name)s chấm NPS %(score)s/10.%(comment)s',
                 name=self.partner_id.name, score=self.score,
                 comment=(' Góp ý: %s' % self.comment) if self.comment else '')
        self.activity_schedule(
            'dmag_dental_journey.activity_type_complaint',
            date_deadline=fields.Date.context_today(self),
            summary=_('Phàn nàn NPS %s/10 – %s', self.score, self.partner_id.name),
            note=note, user_id=lead.id)
        if self.visit_id:
            self.visit_id.message_post(body=note)

    def action_mark_resolved(self):
        self.sudo().write({'complaint_resolved': True})
        self.activity_ids.action_done()
        return True

    def write(self, vals):
        protected = {'score', 'comment', 'state', 'partner_id', 'visit_id', 'token'}
        if protected & set(vals) and not self.env.su:
            from odoo.addons.dmag_dental_base.models.dmag_access import check_director
            check_director(self.env, _('Câu trả lời NPS do khách nhập – không sửa được.'))
        return super().write(vals)
