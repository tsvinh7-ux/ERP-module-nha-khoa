"""Báo cáo bệnh án: mọi lần in / xuất đều ghi nhật ký truy cập hồ sơ."""
from odoo import api, models


class _EmrReportMixin(models.AbstractModel):
    _name = 'dmag.emr.report.mixin'
    _description = 'Báo cáo bệnh án – ghi nhật ký truy cập'
    _emr_model = 'dmag.dental.visit'
    _emr_document = ''

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env[self._emr_model].browse(docids)
        if docs:
            self.env['dmag.record.access.log']._log(docs, 'print', document=self._emr_document)
        return {
            'doc_ids': docids,
            'doc_model': self._emr_model,
            'docs': docs,
            'data': data,
            'company': docs[:1].company_id or self.env.company,
        }


class ReportDentalRecord(models.AbstractModel):
    _name = 'report.dmag_dental_emr.report_dental_record'
    _inherit = 'dmag.emr.report.mixin'
    _description = 'Bệnh án ngoại trú Răng Hàm Mặt'
    _emr_document = 'Bệnh án ngoại trú Răng Hàm Mặt (16/BV1)'


class ReportTreatmentSheet(models.AbstractModel):
    _name = 'report.dmag_dental_emr.report_treatment_sheet'
    _inherit = 'dmag.emr.report.mixin'
    _description = 'Phiếu điều trị'
    _emr_document = 'Phiếu điều trị'


class ReportRecordSummary(models.AbstractModel):
    _name = 'report.dmag_dental_emr.report_record_summary'
    _inherit = 'dmag.emr.report.mixin'
    _description = 'Tóm tắt hồ sơ bệnh án'
    _emr_document = 'Tóm tắt hồ sơ bệnh án'


class ReportConsent(models.AbstractModel):
    _name = 'report.dmag_dental_emr.report_consent'
    _inherit = 'dmag.emr.report.mixin'
    _description = 'Giấy cam kết đồng ý thực hiện thủ thuật'
    _emr_model = 'dmag.consent'
    _emr_document = 'Giấy cam kết / đồng ý thực hiện thủ thuật'
