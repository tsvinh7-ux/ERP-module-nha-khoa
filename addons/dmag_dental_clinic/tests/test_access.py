from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import DentalCommon


@tagged('post_install', '-at_install')
class TestCreateNotEdit(DentalCommon):
    """Nguyên tắc DMAG: nhân viên tạo được – không sửa; chỉ Giám đốc sửa chứng từ."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ref = cls.env.ref
        Users = cls.env['res.users'].with_context(no_reset_password=True)
        cls.recep = Users.create({
            'name': 'Lễ tân T', 'login': 'recep_t', 'email': 'recep@dmag.test',
            'groups_id': [(6, 0, [ref('dmag_dental_base.group_dmag_receptionist').id])],
        })
        cls.director = Users.create({
            'name': 'Giám đốc T', 'login': 'director_t', 'email': 'gd@dmag.test',
            'groups_id': [(6, 0, [ref('dmag_dental_base.group_dmag_director').id])],
        })
        cls.doctor2.user_id.groups_id = [(4, ref('dmag_dental_base.group_dmag_doctor').id)]

    def _visit_in_chair(self):
        visit = self._visit()
        visit.with_user(self.recep).action_check_in()
        visit.with_user(self.recep).action_start()
        return visit

    def test_receptionist_flow_and_payment(self):
        visit = self._visit_in_chair()
        self.env['dmag.dental.procedure'].add_from_workspace(visit.id, self.svc_filling.id, teeth=['36'], surfaces=['O'])
        visit.with_user(self.recep).action_done()
        as_recep = visit.with_user(self.recep)
        self.assertEqual(as_recep.payment_status, 'to_invoice')
        as_recep.register_payment('cash')
        visit.invalidate_recordset()
        self.assertEqual(as_recep.payment_status, 'paid')
        invoice = visit.sudo().invoice_ids
        self.assertEqual(invoice.state, 'posted')
        self.assertEqual(invoice.amount_tax, 0.0, 'Dịch vụ khám chữa bệnh không chịu thuế GTGT')
        with self.assertRaises(AccessError):
            invoice.with_user(self.recep).write({'ref': 'sửa'})

    def test_visit_locked_after_done(self):
        visit = self._visit_in_chair()
        with self.assertRaises(AccessError):
            visit.with_user(self.recep).write({'patient_id': self.env['res.partner'].create(
                {'name': 'Khác', 'is_patient': True}).id})
        visit.with_user(self.recep).action_done()
        with self.assertRaises(AccessError):
            visit.with_user(self.recep).write({'reason': 'sửa sau'})
        # Bác sĩ vẫn ghi tiếp bệnh án chưa ký
        visit.with_user(self.doctor_user2).write({'assessment': 'Bổ sung chẩn đoán'})
        visit.with_user(self.director).write({'reason': 'Giám đốc sửa'})
        self.assertEqual(visit.reason, 'Giám đốc sửa')

    def test_procedure_price_and_discount(self):
        visit = self._visit_in_chair()
        Proc = self.env['dmag.dental.procedure'].with_user(self.doctor_user2)
        with self.assertRaises(AccessError):
            Proc.create({'visit_id': visit.id, 'product_id': self.svc_filling.id,
                         'tooth_ids': [(6, 0, self.tooth_36.ids)], 'price_unit': 1})
        with self.assertRaises(AccessError):
            Proc.create({'visit_id': visit.id, 'product_id': self.svc_filling.id,
                         'tooth_ids': [(6, 0, self.tooth_36.ids)], 'discount': 50})
        proc = Proc.create({'visit_id': visit.id, 'product_id': self.svc_filling.id,
                            'tooth_ids': [(6, 0, self.tooth_36.ids)], 'discount': 5})
        proc.action_done()
        with self.assertRaises(AccessError):
            proc.write({'discount': 0})

    def test_plan_locked_after_presented(self):
        data = self.env['dmag.treatment.plan'].with_user(self.doctor_user2).create_from_workspace(
            self.patient.id, False, [{'name': 'A', 'lines': [{'product_id': self.svc_filling.id, 'teeth': ['36'],
                                                              'surfaces': ['O']}]}])
        plan = self.env['dmag.treatment.plan'].browse(data['id'])
        line = plan.option_ids.line_ids
        line.with_user(self.doctor_user2).write({'discount': 5})
        plan.with_user(self.doctor_user2).action_present()
        with self.assertRaises(AccessError):
            line.with_user(self.doctor_user2).write({'discount': 8})
        line.with_user(self.director).write({'discount': 20})
        self.assertEqual(line.discount, 20)

    def test_chart_entry_not_editable(self):
        ids = self.env['dmag.dental.chart.entry'].with_user(self.doctor_user2).add_from_chart(
            self.patient.id, ['36'], self.env.ref('dmag_dental_base.condition_caries').id, surfaces=['O'])
        entry = self.env['dmag.dental.chart.entry'].browse(ids)
        with self.assertRaises(AccessError):
            entry.with_user(self.doctor_user2).write({'note': 'sửa'})
        entry.with_user(self.doctor_user2).action_resolve()
        self.assertFalse(entry.active)

    def test_patient_identity_locked(self):
        self._visit_in_chair()
        with self.assertRaises(AccessError):
            self.patient.with_user(self.recep).write({'name': 'Đổi tên'})
        self.patient.with_user(self.recep).write({'mobile': '0900000099'})

    def test_vat_regime(self):
        self.assertEqual(self.svc_filling.dental_vat_regime, 'exempt')
        # Sản phẩm dùng chung nhiều công ty: mỗi công ty một thuế, tất cả đều KCT (không lọt thuế 10% của hệ thống tài khoản)
        self.assertEqual(set(self.svc_filling.taxes_id.mapped('description')), {'KCT'})
        self.assertEqual(self.svc_filling.taxes_id.filtered(lambda t: t.company_id == self.env.company).description, 'KCT')
        cosmetic = self.env['product.product'].create({
            'name': 'Tẩy trắng thẩm mỹ', 'is_dental_service': True, 'dental_category': 'cosmetic',
            'dental_requires_tooth': False})
        self.assertEqual(cosmetic.dental_vat_regime, 'taxable')
        self.assertNotIn('KCT', cosmetic.taxes_id.mapped('description'))
