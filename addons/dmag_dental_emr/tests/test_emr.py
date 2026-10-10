import base64

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from odoo.addons.dmag_dental_clinic.tests.common import DentalCommon

PNG_1PX = base64.b64encode(base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='))


@tagged('post_install', '-at_install')
class TestDentalEmr(DentalCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.diag = cls.env.ref('dmag_dental_base.diag_k02_1')
        cls.diag2 = cls.env.ref('dmag_dental_base.diag_k05_1')
        cls.patient.write({'citizen_id': '079095001234', 'ethnicity': 'Kinh',
                           'family_history': 'Mẹ đái tháo đường'})
        cls.Log = cls.env['dmag.record.access.log'].sudo()

    def _in_chair_visit(self, **kw):
        visit = self._visit(**kw)
        visit.action_check_in()
        visit.action_start()
        return visit

    def _fill(self, visit):
        visit.write({
            'chief_complaint': 'Ê buốt răng 36 khi ăn lạnh',
            'present_illness': 'Hai tuần nay ê buốt',
            'pulse': 80, 'bp_systolic': 120, 'bp_diastolic': 80,
            'exam_intraoral': 'Sâu mặt nhai răng 36',
            'diagnosis_ids': [(6, 0, (self.diag | self.diag2).ids)],
        })
        self.env['dmag.dental.chart.entry'].add_from_chart(
            self.patient.id, ['36'], self.env.ref('dmag_dental_base.condition_caries').id,
            surfaces=['O'], visit_id=visit.id)

    # ------------------------------------------------------------------ lock
    def test_lock_covers_new_fields(self):
        visit = self._in_chair_visit()
        self.assertIn('đái tháo đường', visit.family_history)
        self._fill(visit)
        visit.action_sign_record()
        self.assertEqual(visit.record_state, 'signed')
        self.assertTrue(visit.outpatient_number)
        self.assertEqual(visit.primary_diagnosis_id, self.diag)
        self.assertEqual(visit.secondary_diagnosis_ids, self.diag2)
        for field, value in [('present_illness', 'sửa'), ('pulse', 90), ('exam_periodontal', 'x'),
                             ('treatment_direction', 'x'), ('primary_diagnosis_id', self.diag2.id),
                             ('summary_status_end', 'x'), ('bp_systolic', 150)]:
            with self.assertRaises(UserError, msg=field):
                visit.write({field: value})
        # Số lưu trữ là trường hành chính – vẫn ghi được sau ký
        visit.write({'archive_number': 'LT-0001'})
        # Mở bổ sung có ghi vết
        visit.with_context(dmag_record_amend=True).write({'summary_status_end': 'Ổn định'})
        self.assertEqual(visit.summary_status_end, 'Ổn định')

    def test_doctor_can_complete_emr_after_done_until_signed(self):
        visit = self._in_chair_visit(doctor_id=self.doctor2.id, service_ids=[(6, 0, [])])
        visit.action_done()
        visit.with_user(self.doctor_user2).write({'present_illness': 'Ghi bổ sung sau khám', 'pulse': 75})
        self.assertEqual(visit.pulse, 75)
        with self.assertRaises(AccessError):
            visit.with_user(self.doctor_user2).write({'chair_id': self.chair2.id})

    # ------------------------------------------------------------------ signing validation
    def test_signing_validation(self):
        patient = self.env['res.partner'].create({'name': 'BN Thiếu', 'is_patient': True})
        visit = self._in_chair_visit(patient_id=patient.id)
        with self.assertRaises(UserError) as err:
            visit.action_sign_record()
        msg = str(err.exception)
        for text in ('Số định danh', 'Lý do đến khám', 'ICD-10', 'Kết quả khám bệnh'):
            self.assertIn(text, msg)
        self.assertEqual(visit.record_state, 'draft')
        visit.write({'chief_complaint': 'Đau', 'exam_intraoral': 'Sâu răng',
                     'diagnosis_ids': [(6, 0, self.diag.ids)]})
        with self.assertRaises(UserError) as err:
            visit.action_sign_record()
        self.assertIn('Số định danh', str(err.exception))
        patient.identity_exemption_reason = 'Người nước ngoài, chưa xuất trình hộ chiếu'
        visit.action_sign_record()
        self.assertEqual(visit.record_state, 'signed')

    # ------------------------------------------------------------------ access log & workspace
    def test_access_log_and_workspace(self):
        visit = self._in_chair_visit()
        before = self.Log.search_count([('visit_id', '=', visit.id)])
        data = visit.get_visit_workspace()
        self.assertIn('emr', data)
        emr = data['emr']
        for key in ('present_illness', 'vitals', 'exam_intraoral', 'primary_diagnosis_id',
                    'missing_for_signature', 'patient_admin', 'summary_course'):
            self.assertIn(key, emr)
        log = self.Log.search([('visit_id', '=', visit.id), ('action', '=', 'workspace')])
        self.assertEqual(len(log), 1)
        self.assertEqual(log.user_id, self.env.user)
        visit.get_visit_workspace()  # trong 10 phút: không ghi trùng
        self.assertEqual(self.Log.search_count([('visit_id', '=', visit.id)]), before + 1)
        # Lưu từ giao diện bác sĩ: khóa phẳng và khóa lồng "emr"
        visit.save_record_from_workspace({
            'chief_complaint': 'Đau răng', 'exam_occlusion': 'Khớp cắn loại I',
            'emr': {'pulse': 72, 'primary_diagnosis_id': self.diag.id, 'not_allowed': 'x'},
            'diagnosis_ids': self.diag.ids,
        })
        self.assertEqual(visit.exam_occlusion, 'Khớp cắn loại I')
        self.assertEqual(visit.pulse, 72)
        self.assertEqual(visit.primary_diagnosis_id, self.diag)
        # In bệnh án → ghi nhật ký "print"
        self.env['ir.actions.report']._render_qweb_html('dmag_dental_emr.action_report_dental_record', visit.ids)
        self.assertTrue(self.Log.search_count([('visit_id', '=', visit.id), ('action', '=', 'print')]))
        # Nhật ký không sửa / xóa được, kể cả quyền hệ thống
        with self.assertRaises(UserError):
            log.write({'action': 'view'})
        with self.assertRaises(UserError):
            log.unlink()
        with self.assertRaises(AccessError):
            self.env['dmag.record.access.log'].with_user(self.doctor_user2).search([])

    # ------------------------------------------------------------------ retention
    def test_retention_blocks_unlink(self):
        visit = self._in_chair_visit()
        self._fill(visit)
        visit.action_done()
        self.assertTrue(visit.retention_until)
        with self.assertRaises(UserError) as err:
            visit.sudo().unlink()
        self.assertIn('lưu trữ', str(err.exception))
        # Lịch hẹn chưa phát sinh bệnh án vẫn xóa được (Giám đốc)
        empty = self._visit(scheduled_start=self.start.replace(hour=2), chair_id=self.chair2.id)
        empty.sudo().unlink()

    # ------------------------------------------------------------------ consent
    def test_consent_lock(self):
        visit = self._in_chair_visit()
        consent = self.env['dmag.consent'].create({
            'visit_id': visit.id, 'procedure_name': 'Trám răng 36', 'doctor_id': self.doctor.id,
            'tooth_ids': [(6, 0, self.tooth_36.ids)], 'expected_cost': 400000,
        })
        self.assertEqual(consent.patient_id, self.patient)
        self.assertTrue(consent.name.startswith('CK'))
        with self.assertRaises(UserError):
            consent.action_sign()  # thiếu người ký, nguy cơ, chữ ký
        consent.write({'signer_name': 'BN Test', 'risks': 'Ê buốt sau trám', 'signature': PNG_1PX})
        consent.action_sign()
        self.assertEqual(consent.state, 'signed')
        self.assertTrue(consent.signed_at)
        with self.assertRaises(UserError):
            consent.write({'risks': 'sửa'})
        with self.assertRaises(UserError):
            consent.sudo().unlink()
        other = self.env['dmag.consent'].create({'patient_id': self.patient.id, 'procedure_name': 'X',
                                                 'sign_method': 'paper'})
        with self.assertRaises(ValidationError):
            other.write({'state': 'signed'})

    # ------------------------------------------------------------------ record request
    def test_record_request_flow(self):
        visit = self._in_chair_visit()
        self._fill(visit)
        visit.action_sign_record()
        req = self.env['dmag.record.request'].create({
            'patient_id': self.patient.id, 'requester_type': 'insurer', 'scope': 'summary',
            'visit_ids': [(6, 0, visit.ids)],
        })
        with self.assertRaises(UserError) as err:
            req.sudo().action_approve()
        self.assertIn('văn bản', str(err.exception))
        with self.assertRaises(AccessError):
            req.with_user(self.doctor_user2).action_approve()
        attachment = self.env['ir.attachment'].create({'name': 'don-yeu-cau.pdf', 'datas': PNG_1PX})
        req.write({'requester_name': 'Bảo hiểm ABC', 'legal_basis': 'Giám định bồi thường theo hợp đồng',
                   'attachment_ids': [(6, 0, attachment.ids)]})
        req.sudo().action_approve()
        self.assertEqual(req.state, 'approved')
        with self.assertRaises(UserError):
            req.action_provide()  # chưa chọn hình thức
        req.provided_method = 'direct'
        req.action_provide()
        self.assertEqual(req.state, 'provided')
        self.assertTrue(req.provided_at)
        self.assertTrue(self.Log.search_count([('visit_id', '=', visit.id), ('action', '=', 'provide')]))
        action = req.action_print()
        self.assertEqual(action['report_name'], 'dmag_dental_emr.report_record_summary')

    # ------------------------------------------------------------------ reports
    def test_reports_render(self):
        visit = self._in_chair_visit()
        self._fill(visit)
        visit.write({'summary_status_end': 'Ổn định', 'treatment_direction': 'Tái khám 6 tháng'})
        visit.action_sign_record()
        consent = self.env['dmag.consent'].create({'visit_id': visit.id, 'procedure_name': 'Trám răng 36'})
        Report = self.env['ir.actions.report']
        checks = [
            ('dmag_dental_emr.action_report_dental_record', visit,
             ['BỆNH ÁN NGOẠI TRÚ RĂNG HÀM MẶT', '16/BV1', 'I. Hành chính', 'II. Lý do đến khám', 'III. Hỏi bệnh',
              'IV. Khám bệnh', 'V. Cận lâm sàng', 'VI. Chẩn đoán', 'VII. Đã xử lý',
              'VIII. Chẩn đoán khi kết thúc', 'IX. Hướng điều trị', 'Bác sĩ khám bệnh', 'Thủ trưởng cơ sở',
              'Tổng kết bệnh án', 'Sơ đồ răng', '48', '85', 'Đã ký xác nhận điện tử', self.diag.code]),
            ('dmag_dental_emr.action_report_treatment_sheet', visit,
             ['PHIẾU ĐIỀU TRỊ', 'Diễn biến bệnh', 'Y lệnh / xử trí']),
            ('dmag_dental_emr.action_report_record_summary', visit,
             ['TÓM TẮT HỒ SƠ BỆNH ÁN', 'Chẩn đoán', 'Bảng phân loại quốc tế bệnh tật']),
            ('dmag_dental_emr.action_report_consent', consent,
             ['GIẤY CAM KẾT / ĐỒNG Ý THỰC HIỆN THỦ THUẬT', 'Nguy cơ, tai biến', 'Phương pháp điều trị thay thế',
              'Người bệnh / người đại diện hợp pháp', 'Trám răng 36']),
        ]
        for xmlid, records, headings in checks:
            html, _fmt = Report._render_qweb_html(xmlid, records.ids)
            html = html.decode()
            for heading in headings:
                self.assertIn(heading, html, '%s: thiếu "%s"' % (xmlid, heading))
        demo = self.env.ref('dmag_dental_clinic.demo_visit_1', raise_if_not_found=False)
        if demo:
            html, _fmt = Report._render_qweb_html('dmag_dental_emr.action_report_dental_record', demo.ids)
            self.assertIn('BỆNH ÁN NGOẠI TRÚ RĂNG HÀM MẶT', html.decode())
