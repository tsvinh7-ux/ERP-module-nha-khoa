from odoo import _, models


class DmagDentalVisit(models.Model):
    _name = 'dmag.dental.visit'
    _inherit = ['dmag.dental.visit', 'dmag.esign.mixin']

    def _dmag_esign_report_ref(self):
        """Ưu tiên mẫu bệnh án của module dmag_dental_emr (nếu cài), dự phòng mẫu SOAP của module này."""
        report = self.env.ref('dmag_dental_emr.action_report_dental_record', raise_if_not_found=False)
        if report and report._name == 'ir.actions.report' and report.model == self._name:
            return report
        return self.env.ref('dmag_esign_mysign.action_report_visit_record_esign')

    def _dmag_esign_signer(self):
        return self.signed_by_id or super()._dmag_esign_signer()

    def _dmag_esign_document_name(self):
        self.ensure_one()
        return _('Benh an %s', self.name).replace('/', '-')

    def _dmag_esign_request(self):
        res = super()._dmag_esign_request()
        Provider = self.env['dmag.esign.provider']
        for visit in self:
            if not Provider._dmag_get_provider(visit.company_id):
                visit.message_post(body=_('Bệnh án đã ký trong hệ thống. Phòng khám chưa cấu hình ký số MySign '
                                          'nên chưa có chữ ký số.'))
                continue
            visit.action_request_esign(signer=visit.signed_by_id)
        return res
