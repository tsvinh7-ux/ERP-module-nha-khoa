from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from odoo.addons.dmag_dental_clinic.tests.common import DentalCommon


@tagged('post_install', '-at_install')
class TestMaterial(DentalCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        Product = env['product.product']
        cls.company = env.company
        cls.company.dmag_cogs_threshold = 22.0
        cls.glove = Product.create({'name': 'Găng T', 'detailed_type': 'consu', 'standard_price': 3000})
        cls.composite = Product.create({
            'name': 'Composite T', 'detailed_type': 'product', 'standard_price': 40000,
            'uom_id': env.ref('uom.product_uom_gram').id, 'uom_po_id': env.ref('uom.product_uom_gram').id})
        cls.fixture = Product.create({'name': 'Trụ T', 'detailed_type': 'product', 'tracking': 'serial',
                                      'standard_price': 3000000})
        cls.svc_implant = Product.create({
            'name': 'Implant T', 'is_dental_service': True, 'list_price': 15000000,
            'dental_result_condition_id': env.ref('dmag_dental_base.condition_implant').id,
        })
        Bom = env['dmag.service.bom']
        Bom.create({'product_tmpl_id': cls.svc_filling.product_tmpl_id.id, 'company_id': False, 'line_ids': [
            (0, 0, {'product_id': cls.composite.id, 'quantity': 0.5, 'basis': 'per_tooth'}),
            (0, 0, {'product_id': cls.glove.id, 'quantity': 2, 'basis': 'per_procedure'}),
        ]})
        Bom.create({'product_tmpl_id': cls.svc_implant.product_tmpl_id.id, 'line_ids': [
            (0, 0, {'product_id': cls.fixture.id, 'quantity': 1, 'basis': 'per_tooth'}),
            (0, 0, {'product_id': cls.glove.id, 'quantity': 3, 'basis': 'per_procedure'}),
        ]})
        cls.lot1 = env['stock.lot'].create({'name': 'SN-T-001', 'product_id': cls.fixture.id,
                                            'company_id': cls.company.id})
        cls.lot2 = env['stock.lot'].create({'name': 'SN-T-002', 'product_id': cls.fixture.id,
                                            'company_id': cls.company.id})
        warehouse = env['stock.warehouse'].search([('company_id', '=', cls.company.id)], limit=1)
        cls.stock_loc = warehouse.lot_stock_id
        Quant = env['stock.quant']
        Quant._update_available_quantity(cls.composite, cls.stock_loc, 100)
        Quant._update_available_quantity(cls.fixture, cls.stock_loc, 1, lot_id=cls.lot1)
        Quant._update_available_quantity(cls.fixture, cls.stock_loc, 1, lot_id=cls.lot2)
        cls.assistant_user = env['res.users'].create({
            'name': 'Phụ tá VT', 'login': 'pt_vt_test', 'email': 'ptvt@dmag.test',
            'groups_id': [(6, 0, [env.ref('dmag_dental_base.group_dmag_assistant').id])],
        })
        cls.today = fields.Date.context_today(env.user)

    def _visit_in_chair(self):
        visit = self._visit(scheduled_start=fields.Datetime.now())
        visit.action_check_in()
        visit.action_start()
        return visit

    def test_bom_consumption(self):
        # Số liệu có sẵn trong CSDL (vd. đã cài dmag_dental_demo) → so sánh phần chênh lệch
        base = self.env['dmag.material.usage'].get_material_kpis(self.today - timedelta(days=1), self.today)
        visit = self._visit_in_chair()
        Proc = self.env['dmag.dental.procedure']
        res = Proc.add_from_workspace(visit.id, self.svc_filling.id, teeth=['36', '37'])
        proc = Proc.browse(res['id'])
        self.assertEqual(proc.state, 'done')
        usages = proc.material_usage_ids
        self.assertEqual(len(usages), 2)
        comp = usages.filtered(lambda u: u.product_id == self.composite)
        self.assertEqual(comp.quantity, 1.0)  # 0.5 g × 2 răng
        self.assertEqual(usages.filtered(lambda u: u.product_id == self.glove).quantity, 2.0)
        self.assertEqual(comp.move_id.state, 'done')
        self.assertTrue(comp.move_id.location_dest_id.dmag_is_clinical_consumption)
        self.assertEqual(comp.picking_id.state, 'done')
        self.assertEqual(self.composite.with_context(location=self.stock_loc.id).qty_available, 99.0)
        self.assertEqual(proc.material_cost, 1.0 * 40000 + 2 * 3000)

        # Phụ tá ghi vật tư phát sinh (tạo được – không sửa)
        Usage = self.env['dmag.material.usage'].with_user(self.assistant_user)
        with self.assertRaises(UserError):
            Usage.create({'procedure_id': proc.id, 'product_id': self.composite.id, 'quantity': 0.5})
        extra = Usage.create({'procedure_id': proc.id, 'product_id': self.composite.id, 'quantity': 0.5,
                              'reason': 'Lỗ sâu rộng'})
        self.assertEqual(extra.kind, 'extra')
        self.assertEqual(extra.move_id.state, 'done')
        self.assertEqual(self.composite.with_context(location=self.stock_loc.id).qty_available, 98.5)
        with self.assertRaises(AccessError):
            extra.write({'quantity': 0.1})
        with self.assertRaises(AccessError):
            extra.unlink()

        # KPI giá vốn
        kpi = self.env['dmag.material.usage'].get_material_kpis(self.today - timedelta(days=1), self.today)
        self.assertEqual(kpi['revenue'] - base['revenue'], 800000)
        self.assertEqual(kpi['bom_cost'] - base['bom_cost'], 46000)
        self.assertEqual(kpi['extra_cost'] - base['extra_cost'], 20000)
        self.assertEqual(kpi['material_cost'] - base['material_cost'], 66000)
        self.assertAlmostEqual(kpi['material_ratio'], round(kpi['material_cost'] / kpi['revenue'] * 100, 2), places=1)
        self.assertEqual(kpi['threshold'], 22.0)
        if 'dmag.lab.order' not in self.env and not base['revenue']:
            self.assertFalse(kpi['alert'])
        self.company.dmag_cogs_threshold = 0.01
        kpi = self.env['dmag.material.usage'].get_material_kpis(self.today, self.today)
        self.assertTrue(kpi['alert'])
        self.assertTrue(kpi['message'])

    def test_serial_required_for_implant(self):
        visit = self._visit_in_chair()
        Proc = self.env['dmag.dental.procedure']
        proc = Proc.create({'visit_id': visit.id, 'product_id': self.svc_implant.id,
                            'tooth_ids': [(6, 0, self.tooth_36.ids)]})
        self.assertTrue(proc.dmag_lot_required)
        self.assertEqual(proc.dmag_lot_product_ids, self.fixture)
        with self.assertRaises(UserError):
            proc.action_done()
        self.assertEqual(proc.state, 'draft')
        proc.lot_ids = [(6, 0, (self.lot1 | self.lot2).ids)]
        with self.assertRaises(UserError):
            proc.action_done()  # 1 răng chỉ cần 1 serial
        proc.lot_ids = [(6, 0, self.lot1.ids)]
        proc.action_done()
        self.assertEqual(proc.state, 'done')
        fixture_usage = proc.material_usage_ids.filtered(lambda u: u.product_id == self.fixture)
        self.assertEqual(fixture_usage.lot_id, self.lot1)
        self.assertEqual(self.lot1.dmag_patient_id, self.patient)
        self.assertEqual(self.fixture.with_context(location=self.stock_loc.id).qty_available, 1.0)
        # Truy xuất: serial → bệnh nhân
        trace = self.env['dmag.material.usage'].search([('lot_id', '=', self.lot1.id)])
        self.assertEqual(trace.patient_id, self.patient)
        # Serial đã dùng không dùng lại được
        visit2 = self._visit(scheduled_start=fields.Datetime.now() + timedelta(hours=3))
        visit2.action_check_in()
        visit2.action_start()
        with self.assertRaises(ValidationError):
            Proc.add_from_workspace(visit2.id, self.svc_implant.id, teeth=['46'], lot_ids=self.lot1.ids)
        res = Proc.add_from_workspace(visit2.id, self.svc_implant.id, teeth=['46'], lot_ids=self.lot2.ids)
        self.assertEqual(res['state'], 'done')
        self.assertEqual(res['lots'][0]['name'], 'SN-T-002')

    def test_no_bom_no_move(self):
        visit = self._visit_in_chair()
        res = self.env['dmag.dental.procedure'].add_from_workspace(visit.id, self.svc_heavy.id)
        proc = self.env['dmag.dental.procedure'].browse(res['id'])
        self.assertFalse(proc.material_usage_ids)
        self.assertFalse(proc.dmag_lot_required)
