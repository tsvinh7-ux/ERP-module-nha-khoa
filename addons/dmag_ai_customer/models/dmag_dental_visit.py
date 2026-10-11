import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

NOSHOW_SUGGESTION = {
    'high': 'Gọi xác nhận ngay hôm nay; nếu không liên lạc được, xếp khách dự phòng cho khung giờ này.',
    'medium': 'Gọi hoặc nhắn Zalo xác nhận trước 1 ngày.',
    'low': 'Nhắc lịch tự động là đủ.',
}


class DmagDentalVisit(models.Model):
    _inherit = 'dmag.dental.visit'

    dmag_ai_conversation_id = fields.Many2one('dmag.ai.conversation', string='Đặt qua hội thoại AI', readonly=True,
                                              copy=False, index=True)
    dmag_noshow_risk = fields.Float('Nguy cơ không đến', readonly=True, copy=False, digits=(4, 3),
                                    help='AI-08: xác suất không đến (0–1) – mô hình thống kê tại chỗ.')
    dmag_noshow_level = fields.Selection([('low', 'Thấp'), ('medium', 'Trung bình'), ('high', 'Cao')],
                                         string='Mức nguy cơ', compute='_compute_dmag_noshow_level')
    dmag_noshow_factors = fields.Char('Yếu tố nguy cơ', readonly=True, copy=False)
    dmag_noshow_scored_at = fields.Datetime('Chấm điểm lúc', readonly=True, copy=False)
    dmag_noshow_model_id = fields.Many2one('dmag.ai.noshow.model', string='Mô hình', readonly=True, copy=False)
    dmag_was_confirmed = fields.Boolean('Đã từng xác nhận', readonly=True, copy=False,
                                        help='AI-08: lịch đã được xác nhận (gọi / Zalo) trước giờ hẹn.')
    dmag_ai_followup_ids = fields.One2many('dmag.ai.followup', 'visit_id', string='Theo dõi sau điều trị')
    dmag_ai_care_ids = fields.One2many('dmag.ai.care.draft', 'visit_id', string='Nội dung chăm sóc')

    @api.depends('dmag_noshow_risk', 'company_id.dmag_ai_noshow_threshold')
    def _compute_dmag_noshow_level(self):
        for visit in self:
            threshold = visit.company_id.dmag_ai_noshow_threshold or 0.35
            risk = visit.dmag_noshow_risk
            visit.dmag_noshow_level = 'high' if risk >= max(threshold + 0.2, 0.55) else 'medium' if risk >= threshold else 'low'

    # ------------------------------------------------------------------ AI-08 hooks
    def _dmag_ai_rescore(self):
        if self.env.context.get('dmag_noshow_scoring') or self.env.context.get('dmag_ai_no_score'):
            return
        try:
            with self.env.cr.savepoint():
                self.env['dmag.ai.noshow.model'].sudo().score_visits(self)
        except Exception:  # chấm điểm không được chặn đặt lịch
            _logger.exception('AI-08 scoring failed for %s', self.ids)

    @api.model_create_multi
    def create(self, vals_list):
        visits = super().create(vals_list)
        visits._dmag_ai_rescore()
        return visits

    def write(self, vals):
        if vals.get('state') == 'confirmed':
            vals = dict(vals, dmag_was_confirmed=True)
        res = super().write(vals)
        if {'state', 'scheduled_start', 'service_ids', 'source_id'} & set(vals):
            self.filtered(lambda v: v.state in ('draft', 'confirmed'))._dmag_ai_rescore()
        return res

    def _dmag_journey_event(self, event):
        res = super()._dmag_journey_event(event)
        if event == 'done' and not self.env.context.get('dmag_ai_no_followup'):
            try:
                with self.env.cr.savepoint():
                    self.env['dmag.ai.followup'].sudo()._create_for_visits(self)
            except Exception:
                _logger.exception('AI-18 follow-up creation failed for %s', self.ids)
        return res

    def _workspace_card(self):
        card = super()._workspace_card()
        card['ai_booked'] = bool(self.dmag_ai_conversation_id)
        card['noshow'] = False
        if self.state in ('draft', 'confirmed') and self.dmag_noshow_scored_at \
                and self.env['dmag.ai'].is_feature_active('AI-08'):
            threshold = self.company_id.dmag_ai_noshow_threshold or 0.35
            model = self.dmag_noshow_model_id
            card['noshow'] = {
                'risk': round(self.dmag_noshow_risk * 100),
                'level': self.dmag_noshow_level,
                'show': self.dmag_noshow_risk >= threshold,
                'factors': self.dmag_noshow_factors or '',
                'suggestion': NOSHOW_SUGGESTION[self.dmag_noshow_level],
                'method': model.method_text if model else '',
            }
        return card

    # ------------------------------------------------------------------ AI-12
    def action_dmag_ai_care_draft(self):
        self.ensure_one()
        draft = self.env['dmag.ai.care.draft'].generate_for_visit(self)
        return {
            'type': 'ir.actions.act_window', 'name': _('Nội dung chăm sóc – %s', self.patient_id.name),
            'res_model': 'dmag.ai.care.draft', 'res_id': draft.id, 'views': [[False, 'form']], 'target': 'new',
        }

    def action_dmag_open_noshow_model(self):
        model = self.env['dmag.ai.noshow.model']._current()
        return {'type': 'ir.actions.act_window', 'res_model': 'dmag.ai.noshow.model', 'res_id': model.id,
                'views': [[False, 'form']], 'target': 'new'}
