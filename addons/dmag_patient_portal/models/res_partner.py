from odoo import _, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def _dmag_portal_patients(self):
        """Bệnh nhân mà người dùng cổng (partner ``self``) được xem:

        * chính mình,
        * thành viên gia đình khi mình là chủ hộ (``dmag.patient.family.head_id``),
        * người mình là giám hộ (``guardian_id``).
        """
        self.ensure_one()
        me = self.sudo()
        patients = me
        families = self.env['dmag.patient.family'].sudo().search([('head_id', '=', me.id)])
        patients |= families.member_ids
        patients |= me.search([('guardian_id', '=', me.id)])
        return patients.filtered(lambda p: p.is_patient or p == me)

    def _dmag_portal_relation(self, viewer):
        self.ensure_one()
        if self == viewer:
            return _('Bản thân')
        if self.sudo().guardian_id == viewer:
            return _('Người được giám hộ')
        return _('Thành viên gia đình')
