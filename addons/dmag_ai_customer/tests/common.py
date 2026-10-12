from datetime import timedelta
from types import SimpleNamespace

from odoo import fields
from odoo.tests import TransactionCase


def block(**kw):
    return SimpleNamespace(**kw)


def response(content, stop='end_turn', inp=900, out=150):
    return SimpleNamespace(content=content, stop_reason=stop, model='claude-opus-5-5', _request_id='req_test',
                           usage=SimpleNamespace(input_tokens=inp, output_tokens=out,
                                                 cache_read_input_tokens=0, cache_creation_input_tokens=0))


def fake_client(create):
    """Client giả: ``create(**kwargs)`` trả về phản hồi kiểu Messages API (beta.messages vì có fallbacks)."""
    messages = SimpleNamespace(create=create)
    return SimpleNamespace(beta=SimpleNamespace(messages=messages), messages=messages)


class AiCustomerCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True, mail_notrack=True,
                                       dmag_journey_disable=True, tz='Asia/Ho_Chi_Minh'))
        cls.env.user.tz = 'Asia/Ho_Chi_Minh'
        cls.company = cls.env.company
        cls.company.sudo().write({'dmag_ai_mode': 'simulate', 'dmag_ai_monthly_budget': 5000000,
                                  'dmag_ai_zalo_reply_mode': 'auto', 'phone': '028 3999 9999',
                                  'dmag_zns_mode': 'mock'})
        Chair = cls.env['dmag.dental.chair']
        # ghế riêng cho bài test – không trùng lịch demo (bảng điều phối hôm nay sinh theo giờ mở máy)
        cls.chairs = Chair.create([{'name': 'Ghế AI 1'}, {'name': 'Ghế AI 2'}])
        Practitioner = cls.env['dmag.dental.practitioner']
        cls.doctor = Practitioner.create({'name': 'BS Trợ Lý Test', 'role': 'doctor', 'user_id': cls.env.user.id
                                          if not Practitioner.search([('user_id', '=', cls.env.user.id)]) else False})
        cls.doctor2 = Practitioner.create({'name': 'BS Cân Tải', 'role': 'doctor'})
        Product = cls.env['product.product']
        cls.scaling = Product.create({
            'name': 'Cạo vôi răng AI test', 'is_dental_service': True, 'dental_category': 'hygiene',
            'dental_duration': 30, 'lst_price': 345000, 'dental_requires_tooth': False, 'type': 'service',
            'dental_complexity': 'light'})
        cls.extraction = Product.create({
            'name': 'Nhổ răng khôn AI test', 'is_dental_service': True, 'dental_category': 'surgery',
            'dental_duration': 60, 'lst_price': 2500000, 'dental_requires_tooth': False, 'type': 'service',
            'dental_complexity': 'heavy',
            'aftercare_note': '<p>Cắn gạc 30 phút; chườm lạnh 24 giờ đầu; ăn đồ mềm, nguội; không súc miệng mạnh trong 24 giờ.</p>'})
        cls.patient = cls.env['res.partner'].create({
            'name': 'Lê Thị Hoa', 'is_patient': True, 'mobile': '0911222333', 'gender': 'female',
            'data_consent': True, 'dmag_ai_consent': True})
        cls.tomorrow = fields.Date.context_today(cls.env['res.partner']) + timedelta(days=1)

    @classmethod
    def _done_visit(cls, patient=None, product=None):
        Visit = cls.env['dmag.dental.visit']
        visit = Visit.create({
            'patient_id': (patient or cls.patient).id, 'doctor_id': cls.doctor.id, 'chair_id': cls.chairs[0].id,
            'scheduled_start': fields.Datetime.now() - timedelta(hours=3),
            'service_ids': [(6, 0, (product or cls.extraction).ids)],
        })
        visit.action_check_in()
        visit.action_start(chair_id=cls.chairs[0].id)
        proc = cls.env['dmag.dental.procedure'].create({'visit_id': visit.id, 'product_id': (product or cls.extraction).id})
        proc.action_done()
        visit.write({'advice': 'Uống thuốc theo đơn, tái khám cắt chỉ sau 7 ngày.'})
        visit.action_done()
        return visit
