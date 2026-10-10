from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    dmag_bhyt_number = fields.Char('Số thẻ BHYT', copy=False,
                                   help='Ghi trên đơn thuốc và gửi liên thông nếu người bệnh có thẻ BHYT.')
    dmag_prescription_ids = fields.One2many('dmag.prescription', 'patient_id', string='Đơn thuốc')
