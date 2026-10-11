import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class DmagNpsResponse(models.Model):
    _inherit = 'dmag.nps.response'

    dmag_ai_feedback_ids = fields.One2many('dmag.ai.feedback', 'nps_response_id', string='Phân loại AI')

    def submit(self, score, comment=False, channel=False):
        res = super().submit(score, comment=comment, channel=channel)
        resp = self.sudo()
        # AI-09: góp ý có chữ hoặc điểm chưa cao → phân loại (không bao giờ chặn khách gửi khảo sát)
        if (comment or resp.score <= 8) and self.env['dmag.ai'].is_feature_active('AI-09'):
            try:
                with self.env.cr.savepoint():
                    self.env['dmag.ai.feedback'].sudo()._create_from_text(
                        comment or ('Chấm %s/10, không ghi góp ý.' % resp.score), 'nps', partner=resp.partner_id,
                        visit=resp.visit_id or None, nps=resp, score=resp.score)
            except Exception:
                _logger.exception('AI-09 classify NPS %s failed', resp.id)
        return res
