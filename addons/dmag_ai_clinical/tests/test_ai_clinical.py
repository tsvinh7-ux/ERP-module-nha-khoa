import json
from types import SimpleNamespace
from unittest.mock import patch

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.dmag_ai_clinical.models import rx_safety
from odoo.addons.dmag_ai_clinical.models.dmag_ai_clinical import AI01_KEYS


def _block(**kw):
    return SimpleNamespace(**kw)


def _response(content, stop='end_turn', inp=1500, out=400):
    return SimpleNamespace(content=content, stop_reason=stop, model='claude-opus-5-5', _request_id='req_x',
                           usage=SimpleNamespace(input_tokens=inp, output_tokens=out,
                                                 cache_read_input_tokens=0, cache_creation_input_tokens=0))


def _fake_client(create):
    return SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)),
                           messages=SimpleNamespace(create=create))


def _assert_strict_schema(case, schema):
    """Mọi object trong schema: additionalProperties=False và required đủ khóa (structured outputs)."""
    if isinstance(schema, dict):
        if schema.get('type') == 'object':
            case.assertIs(schema.get('additionalProperties'), False)
            case.assertEqual(set(schema.get('required', [])), set(schema.get('properties', {})))
        for value in schema.values():
            _assert_strict_schema(case, value)
    elif isinstance(schema, list):
        for value in schema:
            _assert_strict_schema(case, value)


@tagged('post_install', '-at_install')
class TestAiClinical(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.company = env.company
        cls.company.write({'dmag_ai_mode': 'simulate', 'dmag_ai_require_consent': True, 'dmag_ai_monthly_budget': 0,
                           'dmag_facility_code': '79001'})
        for code in ('AI-01', 'AI-02', 'AI-03', 'AI-04', 'AI-05', 'AI-06'):
            env['dmag.ai.feature'].with_context(active_test=False).search([('code', '=', code)]).active = True
        cls.doctor_user = env['res.users'].create({
            'name': 'BS AI Test', 'login': 'bs_ai_clinical', 'email': 'bsai@dmag.test',
            'groups_id': [(6, 0, [env.ref('dmag_dental_base.group_dmag_doctor').id])],
        })
        cls.reception_user = env['res.users'].create({
            'name': 'Lễ tân AI', 'login': 'lt_ai_clinical', 'email': 'ltai@dmag.test',
            'groups_id': [(6, 0, [env.ref('dmag_dental_base.group_dmag_receptionist').id])],
        })
        cls.doctor = env['dmag.dental.practitioner'].create({
            'name': 'BS AI Test', 'role': 'doctor', 'user_id': cls.doctor_user.id, 'license_number': 'GPHN-AI-1',
        })
        cls.patient = env['res.partner'].create({
            'name': 'Trần Thị Lan', 'is_patient': True, 'mobile': '0901234567', 'gender': 'female',
            'birthdate': fields.Date.today() - relativedelta(years=34), 'citizen_id': '079088001234',
            'allergy': 'Dị ứng Penicillin (nổi mề đay)', 'dmag_ai_consent': True,
        })
        cls.visit = env['dmag.dental.visit'].create({
            'patient_id': cls.patient.id, 'doctor_id': cls.doctor.id, 'reason': 'Ê buốt răng hàm dưới',
        })
        cls.visit._workflow_write({'state': 'in_chair'})
        Entry = env['dmag.dental.chart.entry']
        cls.e_caries = Entry.create({'patient_id': cls.patient.id, 'tooth_id': env.ref('dmag_dental_base.tooth_36').id,
                                     'surface_ids': [(6, 0, [env.ref('dmag_dental_base.surface_o').id])],
                                     'condition_id': env.ref('dmag_dental_base.condition_caries').id,
                                     'visit_id': cls.visit.id})
        cls.e_missing = Entry.create({'patient_id': cls.patient.id, 'tooth_id': env.ref('dmag_dental_base.tooth_16').id,
                                      'condition_id': env.ref('dmag_dental_base.condition_missing').id})
        Product = env['product.product']
        cls.svc_filling = Product.create({'name': 'Trám răng Composite (test)', 'is_dental_service': True,
                                          'dental_category': 'restorative', 'dental_requires_tooth': True,
                                          'list_price': 400000, 'type': 'service'})
        cls.svc_implant = Product.create({'name': 'Cấy ghép Implant (test)', 'is_dental_service': True,
                                          'dental_category': 'implant', 'dental_requires_tooth': True,
                                          'list_price': 15000000, 'type': 'service'})
        Drug = env['dmag.drug']
        cls.amox = Drug.create({'inn_name': 'Amoxicillin', 'strength': '500 mg', 'unit': 'Viên'})
        cls.augmentin = Drug.create({'inn_name': 'Amoxicillin + Acid clavulanic', 'strength': '500 mg + 125 mg',
                                     'brand_name': 'Augmentin', 'multi_ingredient': True, 'unit': 'Viên'})
        cls.para = Drug.create({'inn_name': 'Paracetamol', 'strength': '500 mg', 'unit': 'Viên'})
        cls.ibu = Drug.create({'inn_name': 'Ibuprofen', 'strength': '400 mg', 'unit': 'Viên'})
        cls.doxy = Drug.create({'inn_name': 'Doxycyclin', 'strength': '100 mg', 'unit': 'Viên'})
        cls.diag_k021 = env.ref('dmag_dental_base.diag_k02_1')

    def _ai(self, user=None):
        return self.env['dmag.ai.clinical'].with_user(user or self.doctor_user)

    def _live(self, create):
        self.company.sudo().write({'dmag_ai_mode': 'live', 'dmag_ai_api_key': 'sk-test'})
        return patch.object(type(self.env['dmag.ai']), '_client', lambda self: _fake_client(create))

    # ------------------------------------------------------------------ chung
    def test_status_consent_and_access(self):
        status = self._ai().get_status(self.visit.id)
        self.assertTrue(status['is_doctor'])
        self.assertTrue(all(status['features'].values()))
        self.patient.dmag_ai_consent = False
        res = self._ai().ai04_summary(self.visit.id)
        self.assertTrue(res['consent_required'])
        self.assertTrue(res['can_consent'])
        self._ai().record_consent(self.patient.id)
        self.assertTrue(self.patient.dmag_ai_consent)
        self.assertTrue(self.patient.dmag_ai_consent_date)
        self.assertIn('headline', self._ai().ai04_summary(self.visit.id))
        # Lễ tân không gọi được tính năng lâm sàng
        self.assertFalse(self._ai(self.reception_user).get_status()['is_doctor'])
        for method, args in (('ai04_summary', [self.visit.id]), ('ai01_structure', [self.visit.id, 'x' * 20]),
                             ('ai02_check', [self.visit.id]), ('rx_check', [self.visit.id, []]),
                             ('ai05_suggest', [self.visit.id]), ('record_consent', [self.patient.id]),
                             ('ai01_apply', [self.visit.id, {'advice': 'x'}])):
            with self.assertRaises(AccessError, msg=method):
                getattr(self._ai(self.reception_user), method)(*args)

    def test_feature_off(self):
        self.env.ref('dmag_ai_core.feature_ai_04').active = False
        self.assertFalse(self._ai().get_status()['features']['AI-04'])
        with self.assertRaises(UserError):
            self._ai().ai04_summary(self.visit.id)

    # ------------------------------------------------------------------ AI-01
    def test_ai01_simulate_maps_real_fields_and_applies_only_on_accept(self):
        transcript = self._ai().ai01_sample_transcript(self.visit.id)['text']
        self.assertIn('36', transcript)
        self.assertIn('penicillin', transcript.lower())
        res = self._ai().ai01_structure(self.visit.id, transcript)
        self.assertTrue(res['simulated'])
        rows = {r['key']: r for r in res['rows']}
        self.assertTrue(set(rows) <= set(AI01_KEYS))
        for key in ('chief_complaint', 'exam_intraoral', 'assessment', 'advice', 'pulse', 'bp_systolic'):
            self.assertIn(key, rows)
        self.assertEqual(rows['bp_systolic']['suggested'], 120)
        self.assertIn('K02.1', [d['code'] for d in res['icd']])
        # Chưa ghi gì khi chưa chấp nhận
        self.assertFalse(self.visit.exam_intraoral)
        self.assertFalse(self.visit.diagnosis_ids)
        values = {k: rows[k]['suggested'] for k in ('exam_intraoral', 'pulse', 'advice')}
        k021 = next(d['id'] for d in res['icd'] if d['code'] == 'K02.1')
        self._ai().ai01_apply(self.visit.id, dict(values, bogus_field='x'), [k021])
        self.assertEqual(self.visit.exam_intraoral, rows['exam_intraoral']['suggested'])
        self.assertEqual(self.visit.pulse, 80)
        self.assertFalse(self.visit.assessment, 'Mục không chấp nhận không được ghi')
        self.assertIn(self.diag_k021, self.visit.diagnosis_ids)
        self.assertIn('AI-01', self.visit.message_ids[:1].body)

    def test_ai01_live_schema_and_catalog_only(self):
        calls = []
        payload = {'fields': {k: ('' if k not in ('pulse', 'assessment') else (88 if k == 'pulse' else 'Sâu ngà R36'))
                              for k in AI01_KEYS},
                   'icd10': [{'code': 'K02.1', 'reason': 'sâu ngà'}, {'code': 'Z99.9', 'reason': 'bịa'}],
                   'notes': ''}

        def create(**kw):
            calls.append(kw)
            return _response([_block(type='text', text=json.dumps(payload, ensure_ascii=False))])

        with self._live(create):
            res = self._ai().ai01_structure(self.visit.id, 'Bệnh nhân Trần Thị Lan mạch 88, sâu ngà răng 36.')
        kw = calls[0]
        self.assertNotIn('tool_choice', kw)
        schema = kw['output_config']['format']['schema']
        _assert_strict_schema(self, schema)
        self.assertNotIn('Trần Thị Lan', json.dumps(kw['messages'], ensure_ascii=False), 'Ẩn danh trước khi gửi')
        self.assertFalse(res['simulated'])
        self.assertGreater(res['cost_vnd'], 0)
        self.assertEqual([d['code'] for d in res['icd']], ['K02.1'], 'Chỉ mã có trong danh mục')
        self.assertEqual({r['key'] for r in res['rows']}, {'pulse', 'assessment'})
        self.assertFalse(self.visit.pulse, 'Kết quả AI chỉ ghi khi bác sĩ chấp nhận')

    # ------------------------------------------------------------------ AI-02
    def test_ai02_local_rules_and_icd_from_catalog(self):
        res = self._ai().ai02_check(self.visit.id)
        messages = ' '.join(i['message'] for i in res['local'])
        self.assertIn('ICD-10', messages)  # thiếu chẩn đoán bắt buộc
        self.assertIn('R36', messages)  # sơ đồ có sâu răng, bệnh án chưa có mã
        catalog = set(self.env['dmag.dental.diagnosis'].search([]).mapped('code'))
        self.assertTrue(res['icd'])
        self.assertTrue({d['code'] for d in res['icd']} <= catalog)
        self._ai().ai02_add_diagnosis(self.visit.id, res['icd'][0]['id'])
        self.assertTrue(self.visit.diagnosis_ids)

    def test_ai02_live_tool_strict_and_unknown_codes_dropped(self):
        calls = []

        def create(**kw):
            calls.append(kw)
            if len(calls) == 1:
                return _response([_block(type='tool_use', id='t1', name='lookup_icd10', input={'query': 'sâu ngà'})],
                                 stop='tool_use')
            tool_result = kw['messages'][-1]['content'][0]
            self.assertEqual(tool_result['type'], 'tool_result')
            self.assertIn('K02.1', tool_result['content'])
            data = {'summary': 'Cần bổ sung mã.', 'issues': [{'severity': 'medium', 'field': 'diagnosis_ids',
                                                               'message': 'Thiếu mã sâu ngà'}],
                    'icd10': [{'code': 'K02.1', 'reason': 'R36'}, {'code': 'X00.0', 'reason': 'bịa'}]}
            return _response([_block(type='text', text=json.dumps(data, ensure_ascii=False))])

        with self._live(create):
            res = self._ai().ai02_check(self.visit.id)
        tool = calls[0]['tools'][0]
        self.assertTrue(tool['strict'])
        self.assertIs(tool['input_schema']['additionalProperties'], False)
        self.assertNotIn('tool_choice', calls[0])
        self.assertEqual([d['code'] for d in res['icd']], ['K02.1'])
        self.assertEqual(res['ai']['issues'][0]['source'], 'ai')

    # ------------------------------------------------------------------ AI-03
    def test_rx_rules_block_allergy_and_warnings(self):
        res = self._ai().rx_check(self.visit.id, [{'drug_id': self.amox.id, 'days': 5},
                                                  {'drug_id': self.para.id, 'days': 3}])
        self.assertFalse(res['ok'])
        block = [f for f in res['findings'] if f['level'] == 'block']
        self.assertEqual(block[0]['code'], 'allergy')
        self.assertIn('Amoxicillin', block[0]['drug'])
        self.assertFalse([f for f in res['findings'] if 'Paracetamol' in f['drug']])
        # Phát hành từ màn hình bác sĩ bị chặn bởi quy tắc (không phụ thuộc AI)
        self.env.ref('dmag_ai_core.feature_ai_03').active = False
        rx = self.visit.with_user(self.doctor_user).save_prescription_from_workspace({
            'lines': [{'drug_id': self.amox.id, 'dose_per_time': 1, 'times_per_day': 2, 'days': 5}]})
        with self.assertRaises(UserError):
            self.visit.with_user(self.doctor_user).issue_prescription(rx['id'])

    def test_rx_rules_other_patients(self):
        other = self.env['res.partner'].create({
            'name': 'Lê Văn Hùng', 'is_patient': True, 'birthdate': fields.Date.today() - relativedelta(years=65),
            'current_medication': 'Warfarin 5 mg/ngày'})
        f = rx_safety.check_lines(self.env, other, [{'drug_id': self.ibu.id, 'days': 3},
                                                    {'drug_id': self.amox.id, 'days': 40},
                                                    {'drug_id': self.augmentin.id, 'days': 5}])
        codes = {x['code']: x['level'] for x in f}
        self.assertEqual(codes['nsaid_anticoagulant'], 'warn')
        self.assertEqual(codes['max_days'], 'block')
        self.assertEqual(codes['duplicate'], 'warn')
        pregnant = self.env['res.partner'].create({'name': 'Phạm Thu', 'is_patient': True, 'is_pregnant': True})
        f = rx_safety.check_lines(self.env, pregnant, [{'drug_id': self.ibu.id, 'days': 3},
                                                       {'drug_id': self.doxy.id, 'days': 5}])
        codes = {x['code']: x['level'] for x in f}
        self.assertEqual(codes['pregnancy_nsaid'], 'warn')
        self.assertEqual(codes['pregnancy_contra'], 'block')
        child = self.env['res.partner'].create({'name': 'Bé Na', 'is_patient': True,
                                                'birthdate': fields.Date.today() - relativedelta(years=7)})
        f = rx_safety.check_lines(self.env, child, [{'drug_id': self.para.id, 'days': 3},
                                                    {'drug_id': self.doxy.id, 'days': 3}])
        codes = {x['code']: x['level'] for x in f}
        self.assertEqual(codes['child_dose'], 'warn')
        self.assertEqual(codes['child_tetracycline'], 'block')
        lidocaine = self.env['dmag.drug'].create({'inn_name': 'Lidocain hydroclorid', 'strength': '2%', 'unit': 'Tuýp',
                                                  'brand_name': 'Xylocaine', 'route': 'topical'})
        allergic = self.env['res.partner'].create({'name': 'Ngô An', 'is_patient': True, 'allergy': 'Lidocaine'})
        self.assertEqual(rx_safety.check_lines(self.env, allergic, [{'drug_id': lidocaine.id}])[0]['level'], 'block')

    def test_ai03_explain_simulate(self):
        res = self._ai().ai03_explain(self.visit.id, [{'drug_id': self.amox.id, 'days': 5}])
        self.assertIn('Amoxicillin', res['explanation'])
        self.assertTrue(res['meta']['simulated'])

    # ------------------------------------------------------------------ AI-04
    def test_ai04_summary_from_real_data(self):
        res = self._ai().ai04_summary(self.visit.id)
        keys = [s['key'] for s in res['sections']]
        self.assertEqual(keys[0], 'safety')
        safety = ' '.join(res['sections'][0]['items'])
        self.assertIn('Penicillin', safety)
        self.assertGreater(res['estimated_cost_vnd'], 0)

    # ------------------------------------------------------------------ AI-05
    def test_ai05_simulate_catalog_only_and_no_plan_created(self):
        plans_before = self.env['dmag.treatment.plan'].search_count([('patient_id', '=', self.patient.id)])
        res = self._ai().ai05_suggest(self.visit.id)
        self.assertEqual({o['tier'] for o in res['options']}, {'basic', 'optimal'})
        catalog = set(self.env['product.product'].search([('is_dental_service', '=', True)]).ids)
        for option in res['options']:
            for line in option['lines']:
                self.assertIn(line['product_id'], catalog)
        optimal = next(o for o in res['options'] if o['tier'] == 'optimal')
        # Răng 16 mất → phương án tối ưu có một dịch vụ nhóm implant trong bảng giá (CSDL có thể có nhiều loại trụ)
        Product = self.env['product.product']
        self.assertTrue(any(Product.browse(l['product_id']).dental_category == 'implant' and l['teeth'] == ['16']
                            for l in optimal['lines']))
        self.assertTrue(res['patient_explanation'])
        self.assertEqual(self.env['dmag.treatment.plan'].search_count([('patient_id', '=', self.patient.id)]),
                         plans_before, 'Gợi ý không tự tạo kế hoạch')

    def test_ai05_live_unknown_product_dropped(self):
        data = {'options': [{'tier': 'optimal', 'name': 'Tối ưu', 'summary': '', 'visits': 3, 'lines': [
            {'product_id': self.svc_implant.id, 'teeth': ['16'], 'phase': 3, 'reason': 'Implant'},
            {'product_id': 999999, 'teeth': ['36'], 'phase': 1, 'reason': 'bịa'}]}],
            'sequence_note': '', 'patient_explanation': 'Giải thích'}

        def create(**kw):
            schema = kw['output_config']['format']['schema']
            _assert_strict_schema(self, schema)
            ids = schema['properties']['options']['items']['properties']['lines']['items']['properties']['product_id']['enum']
            self.assertIn(self.svc_implant.id, ids)
            return _response([_block(type='text', text=json.dumps(data))])

        with self._live(create):
            res = self._ai().ai05_suggest(self.visit.id)
        self.assertEqual([l['product_id'] for l in res['options'][0]['lines']], [self.svc_implant.id])

    # ------------------------------------------------------------------ AI-06
    def test_ai06_sample_simulate_and_live_image_block(self):
        img = self._ai().ai06_add_sample(self.visit.id, 'xray_sample_1')
        self.assertIn(img['id'], [i['id'] for i in self._ai().ai06_images(self.visit.id)['images']])
        res = self._ai().ai06_analyze(self.visit.id, img['id'])
        teeth = {f['tooth'] for f in res['findings']}
        self.assertTrue({'36', '46', '16'} <= teeth)
        self.assertTrue(all(f['box'] for f in res['findings']))
        missing = next(f for f in res['findings'] if f['tooth'] == '16')
        self.assertTrue(missing['on_chart'])
        seen = {}

        def create(**kw):
            content = kw['messages'][0]['content']
            seen['types'] = [b['type'] for b in content]
            data = {'image_quality': 'tốt', 'summary': 'Nghi sâu R36', 'findings': [
                {'tooth': '36', 'finding': 'thấu quang', 'condition_code': 'caries', 'confidence': 1.7,
                 'box': {'x': 0.7, 'y': 0.4, 'w': 0.05, 'h': 0.06}}]}
            return _response([_block(type='text', text=json.dumps(data, ensure_ascii=False))])

        with self._live(create):
            res = self._ai().ai06_analyze(self.visit.id, img['id'])
        self.assertEqual(seen['types'][0], 'image')
        self.assertEqual(res['findings'][0]['confidence'], 1.0)
        # Chấp nhận phát hiện tooth-scope → ghi lên sơ đồ qua đường sẵn có
        fracture = self.env.ref('dmag_dental_base.condition_fracture')
        self._ai().ai06_add_to_chart(self.visit.id, '46', fracture.id)
        self.assertTrue(self.env['dmag.dental.chart.entry'].search_count([
            ('patient_id', '=', self.patient.id), ('condition_id', '=', fracture.id)]))
