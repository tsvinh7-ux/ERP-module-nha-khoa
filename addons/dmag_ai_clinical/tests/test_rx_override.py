from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestRxOverride(TransactionCase):
    """AI-03 – chặn đơn vi phạm an toàn trên MỌI đường phát hành; chỉ Giám đốc duyệt vượt (lý do + ký + ghi vết)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.company = env.company
        cls.company.write({'dmag_facility_code': '79001'})
        cls.doctor_user = env['res.users'].create({
            'name': 'BS Kê Đơn', 'login': 'bs_rx_override', 'email': 'bsrx@dmag.test',
            'groups_id': [(6, 0, [env.ref('dmag_dental_base.group_dmag_doctor').id])]})
        cls.director_user = env['res.users'].create({
            'name': 'GĐ Duyệt Vượt', 'login': 'gd_rx_override', 'email': 'gdrx@dmag.test',
            'groups_id': [(6, 0, [env.ref('dmag_dental_base.group_dmag_director').id])]})
        cls.manager_user = env['res.users'].create({
            'name': 'QL Không Duyệt', 'login': 'ql_rx_override', 'email': 'qlrx@dmag.test',
            'groups_id': [(6, 0, [env.ref('dmag_dental_base.group_dmag_manager').id])]})
        cls.doctor = env['dmag.dental.practitioner'].create({
            'name': 'BS Kê Đơn', 'role': 'doctor', 'user_id': cls.doctor_user.id, 'license_number': 'GPHN-RX-1'})
        cls.patient = env['res.partner'].create({
            'name': 'Phan Thị Dị Ứng', 'is_patient': True, 'gender': 'female', 'citizen_id': '079088009999',
            'birthdate': fields.Date.today() - relativedelta(years=40), 'allergy': 'Dị ứng Penicillin'})
        cls.visit = env['dmag.dental.visit'].create({'patient_id': cls.patient.id, 'doctor_id': cls.doctor.id})
        cls.visit._workflow_write({'state': 'in_chair', 'assessment': 'Viêm quanh chóp răng 36'})
        Drug = env['dmag.drug']
        cls.amox = Drug.create({'inn_name': 'Amoxicillin', 'strength': '500 mg', 'unit': 'Viên'})
        cls.para = Drug.create({'inn_name': 'Paracetamol', 'strength': '500 mg', 'unit': 'Viên'})
        cls.augmentin = Drug.create({'inn_name': 'Amoxicillin + Acid clavulanic', 'strength': '500 mg + 125 mg',
                                     'brand_name': 'Augmentin', 'multi_ingredient': True, 'unit': 'Viên'})

    def _rx(self, lines=None):
        lines = lines or [{'drug_id': self.amox.id, 'dose_per_time': 1, 'times_per_day': 2, 'days': 5}]
        res = self.visit.with_user(self.doctor_user).save_prescription_from_workspace({'lines': lines})
        return self.env['dmag.prescription'].browse(res['id'])

    def test_block_on_every_issue_path(self):
        rx = self._rx()
        self.assertEqual(rx.rx_safety_block_count, 1)
        # Đường máy chủ dmag.prescription.action_issue (form đơn thuốc) – không chỉ màn hình bác sĩ
        with self.assertRaisesRegex(UserError, 'vi phạm quy tắc an toàn'):
            rx.with_user(self.doctor_user).action_issue()
        with self.assertRaisesRegex(UserError, 'vi phạm quy tắc an toàn'):
            self.visit.with_user(self.doctor_user).issue_prescription(rx.id)
        # Giám đốc cũng không phát hành thẳng được khi chưa duyệt vượt
        with self.assertRaises(UserError):
            rx.with_user(self.director_user).action_issue()
        # Kể cả quyền hệ thống
        with self.assertRaises(UserError):
            rx.sudo().action_issue()
        self.assertEqual(rx.state, 'draft')
        self.assertFalse(rx.name)
        # Đơn an toàn vẫn phát hành bình thường
        safe = self._rx([{'drug_id': self.para.id, 'dose_per_time': 1, 'times_per_day': 3, 'days': 3}])
        self.visit.with_user(self.doctor_user).issue_prescription(safe.id)
        self.assertEqual(len(safe.name), 14)

    def test_only_director_can_override_with_reason(self):
        rx = self._rx()
        reason = 'Đã hỏi lại: phản ứng cũ chỉ là buồn nôn, không phải dị ứng; theo dõi 30 phút tại phòng khám.'
        for user in (self.doctor_user, self.manager_user):
            with self.assertRaises(AccessError):
                rx.with_user(user).action_director_override(reason)
        # Không ghi trực tiếp được cờ duyệt vượt (kể cả bác sĩ sở hữu đơn nháp)
        with self.assertRaises(AccessError):
            rx.with_user(self.doctor_user).write({'rx_safety_override': True})
        with self.assertRaisesRegex(UserError, 'lý do'):
            rx.with_user(self.director_user).action_director_override('ok')
        with self.assertRaisesRegex(UserError, 'chịu trách nhiệm'):
            rx.with_user(self.director_user).action_director_override(reason, confirm=False)
        res = rx.with_user(self.director_user).action_director_override(reason, confirm=True)
        self.assertTrue(res['overridden'])
        self.assertTrue(rx.rx_safety_override)
        self.assertEqual(rx.rx_override_uid, self.director_user)
        self.assertTrue(rx.rx_override_date)
        self.assertEqual(rx.rx_override_reason, reason)
        self.assertIn('Dị ứng thuốc', rx.rx_override_rules)
        self.assertIn('Amoxicillin', rx.rx_override_rules)
        self.assertTrue(rx.rx_override_esign, 'Ghi nhận trạng thái ký số bổ sung (hoặc lý do chưa ký)')
        bodies = ' '.join(rx.message_ids.mapped('body'))
        self.assertIn('DUYỆT VƯỢT', bodies)
        self.assertIn(reason, bodies)
        # Sau duyệt vượt: bác sĩ phát hành được qua mọi đường
        self.visit.with_user(self.doctor_user).issue_prescription(rx.id)
        self.assertNotEqual(rx.state, 'draft')
        self.assertIn('Phát hành theo duyệt vượt', ' '.join(rx.message_ids.mapped('body')))
        # Đơn đã phát hành: dữ liệu duyệt vượt không sửa được
        with self.assertRaises(AccessError):
            rx.with_user(self.director_user).write({'rx_override_reason': 'sửa lại'})

    def test_override_bound_to_reviewed_violations(self):
        rx = self._rx()
        rx.with_user(self.director_user).action_director_override(
            'Bệnh nhân đã test lại âm tính với Penicillin tại bệnh viện, có giấy xác nhận.', confirm=True)
        # Bác sĩ sửa đơn → phát sinh vi phạm khác (thêm Augmentin cũng thuộc nhóm Penicillin) → chặn lại, duyệt lần nữa
        self.visit.with_user(self.doctor_user).save_prescription_from_workspace({'id': rx.id, 'lines': [
            {'drug_id': self.amox.id, 'dose_per_time': 1, 'times_per_day': 2, 'days': 5},
            {'drug_id': self.augmentin.id, 'dose_per_time': 1, 'times_per_day': 2, 'days': 5}]})
        self.assertFalse(rx._rx_override_valid())
        with self.assertRaisesRegex(UserError, 'thay đổi sau khi Giám đốc duyệt vượt'):
            rx.with_user(self.doctor_user).action_issue()
        # Wizard trên form đơn thuốc (đường giao diện Odoo) – Giám đốc duyệt lại và phát hành ngay
        wizard = self.env['dmag.rx.override.wizard'].with_user(self.director_user).create({
            'prescription_id': rx.id, 'reason': 'Điều trị duy trì theo chỉ định bệnh viện, đã đối chiếu hồ sơ.',
            'confirm': True, 'issue_now': True})
        self.assertIn('Augmentin', wizard.rules)
        wizard.action_confirm()
        self.assertNotEqual(rx.state, 'draft')

    def test_doctor_requests_director_and_ui_api(self):
        rx = self._rx()
        Ai = self.env['dmag.ai.clinical']
        check = Ai.with_user(self.doctor_user).rx_check(self.visit.id, rx._rx_safety_lines(), 0, rx.id)
        self.assertEqual(check['blocks'], 1)
        self.assertFalse(check['is_director'])
        self.assertFalse(check['override_valid'])
        res = Ai.with_user(self.doctor_user).rx_request_override(self.visit.id, rx.id, 'Bệnh nhân cần gấp')
        self.assertGreaterEqual(res['requested'], 1)
        self.assertIn(self.director_user.name, res['directors'])
        activity = rx.activity_ids.filtered(lambda a: a.user_id == self.director_user)
        self.assertTrue(activity, 'Có việc cần làm cho Giám đốc')
        self.assertEqual(rx.rx_override_requested_uid, self.doctor_user)
        check = Ai.with_user(self.doctor_user).rx_check(self.visit.id, rx._rx_safety_lines(), 0, rx.id)
        self.assertTrue(check['override_requested'])
        # Bác sĩ không gọi được API duyệt vượt
        with self.assertRaises(AccessError):
            Ai.with_user(self.doctor_user).rx_override(self.visit.id, rx.id, 'Lý do đủ dài để duyệt vượt', True)
        res = Ai.with_user(self.director_user).rx_override(
            self.visit.id, rx.id, 'Giám đốc chuyên môn đã khám lại, đồng ý kê và theo dõi.', True, True)
        self.assertTrue(res['issued'])
        self.assertEqual(len(res['code']), 14)
        self.assertFalse(rx.activity_ids.filtered(lambda a: a.user_id == self.director_user),
                         'Việc đề nghị được đánh dấu xong khi Giám đốc duyệt')

    def test_override_esign_soft_dependency(self):
        if 'dmag.esign.provider' not in self.env:
            self.skipTest('dmag_esign_mysign chưa cài')
        self.env['dmag.esign.provider'].search([]).write({'active': False})
        self.env['dmag.esign.provider'].create({'name': 'Giả lập RX', 'provider_type': 'mock', 'sequence': 1,
                                                'client_id': 'cid', 'client_secret': 'secret'})
        rx = self._rx()
        # Giám đốc chưa có hồ sơ ký số → ghi rõ lý do chưa ký, vẫn duyệt vượt được
        rx.with_user(self.director_user).action_director_override(
            'Giám đốc đã khám lại, đồng ý kê kháng sinh này.', confirm=True)
        self.assertIn('Chưa ký số', rx.rx_override_esign)
        # Có hồ sơ ký số (lưu trữ, không hiện trong danh sách bác sĩ) → gửi ký văn bản chịu trách nhiệm
        self.env['dmag.dental.practitioner'].create({
            'name': 'GĐ Duyệt Vượt', 'role': 'doctor', 'user_id': self.director_user.id, 'active': False,
            'license_number': 'GPHN-GD-1'})
        rx2 = self._rx()
        res = rx2.with_user(self.director_user).action_director_override(
            'Đã đối chiếu xét nghiệm dị ứng âm tính tại bệnh viện.', confirm=True)
        request = self.env['dmag.esign.request'].search([('res_model', '=', 'dmag.prescription'),
                                                         ('res_id', '=', rx2.id)])
        self.assertEqual(len(request), 1)
        self.assertEqual(request.state, 'signed')
        self.assertEqual(res['esign']['state'], 'signed')
        self.assertIn(request.name, rx2.rx_override_esign)
        self.assertEqual(request.document_format, 'html')

    def test_override_kept_when_tt26_info_missing(self):
        rx = self._rx()
        rx.write({'diagnosis_text': False, 'diagnosis_ids': [(5, 0, 0)]})
        res = self.env['dmag.ai.clinical'].with_user(self.director_user).rx_override(
            self.visit.id, rx.id, 'Đã đối chiếu xét nghiệm dị ứng âm tính tại bệnh viện.', True, True)
        self.assertFalse(res['issued'])
        self.assertTrue(any('chẩn đoán' in e for e in res['issue_errors']))
        self.assertTrue(rx.rx_safety_override, 'Duyệt vượt vẫn được lưu')
        self.assertEqual(rx.state, 'draft')
        # Bác sĩ bổ sung chẩn đoán rồi phát hành theo duyệt vượt
        rx.write({'diagnosis_text': 'Viêm quanh chóp răng 36'})
        self.visit.with_user(self.doctor_user).issue_prescription(rx.id)
        self.assertNotEqual(rx.state, 'draft')
