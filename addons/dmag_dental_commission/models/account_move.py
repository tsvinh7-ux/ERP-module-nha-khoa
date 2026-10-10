from odoo import models


def _dmag_recompute_for_moves(env, moves):
    moves = moves.filtered(lambda m: m.move_type in ('out_invoice', 'out_refund'))
    if not moves:
        return
    sale_lines = moves.sudo().line_ids.sale_line_ids
    if not sale_lines:
        return
    procedures = env['dmag.dental.procedure'].sudo().search([('sale_line_id', 'in', sale_lines.ids)])
    procedures.mapped('visit_id')._dmag_compute_commissions()


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        _dmag_recompute_for_moves(self.env, posted.filtered(lambda m: m.move_type == 'out_refund'))
        return posted

    def button_draft(self):
        moves = self.filtered(lambda m: m.move_type in ('out_invoice', 'out_refund'))
        res = super().button_draft()
        _dmag_recompute_for_moves(self.env, moves)
        return res


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    def reconcile(self):
        res = super().reconcile()
        _dmag_recompute_for_moves(self.env, self.move_id)
        return res

    def remove_move_reconcile(self):
        involved = (self | self.matched_debit_ids.debit_move_id | self.matched_credit_ids.credit_move_id).move_id
        res = super().remove_move_reconcile()
        _dmag_recompute_for_moves(self.env, involved)
        return res
