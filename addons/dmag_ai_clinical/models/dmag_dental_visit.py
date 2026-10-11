from odoo import _, models
from odoo.exceptions import UserError

from . import rx_safety


class DmagDentalVisit(models.Model):
    _inherit = 'dmag.dental.visit'

    def issue_prescription(self, prescription_id):
        """AI-03: quy tắc an toàn CỐ ĐỊNH chặn phát hành từ màn hình bác sĩ (dị ứng, chống chỉ định, vượt số ngày).

        Chỉ móc vào đường phát hành của Bàn làm việc bác sĩ; không phụ thuộc AI bật hay tắt.
        """
        self.ensure_one()
        rx = self.env['dmag.prescription'].browse(prescription_id).exists()
        if rx and rx.visit_id == self:
            max_days = self.get_rx_catalog().get('max_days') or 30
            lines = [{'drug_id': l.drug_id.id, 'days': l.days if not l.is_chronic else 0} for l in rx.line_ids]
            blocks = [f for f in rx_safety.check_lines(self.env, self.patient_id, lines, max_days=max_days,
                                                       weight=rx.weight)
                      if f['level'] == 'block']
            if blocks:
                raise UserError(_('Không phát hành được đơn thuốc – vi phạm quy tắc an toàn:\n%s',
                                  '\n'.join('• %s: %s' % (f['title'], f['message']) for f in blocks)))
        return super().issue_prescription(prescription_id)
