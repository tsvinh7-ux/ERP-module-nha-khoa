from odoo import fields, models


class DmagJourneyPainWizard(models.TransientModel):
    _name = 'dmag.journey.pain.wizard'
    _description = 'Ghi điểm đau sau 24h'

    visit_id = fields.Many2one('dmag.dental.visit', string='Lượt khám', required=True)
    patient_id = fields.Many2one(related='visit_id.patient_id')
    score = fields.Integer('Điểm đau (0–10)', required=True)
    note = fields.Char('Ghi chú (bất thường, thuốc, sưng…)')

    def action_confirm(self):
        self.ensure_one()
        self.visit_id.record_pain_score_24h(self.score, self.note)
        return {'type': 'ir.actions.act_window_close'}
