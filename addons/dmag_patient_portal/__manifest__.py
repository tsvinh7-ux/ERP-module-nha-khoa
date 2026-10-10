{
    'name': 'DMAG – Tài khoản bệnh nhân',
    'summary': 'Cổng bệnh nhân (Nội dung khám hôm nay, kế hoạch điều trị, bảo hành, thành viên), '
               'đặt lịch trực tuyến có đồng ý xử lý dữ liệu, API JSON cho ứng dụng di động',
    'version': '17.0.1.0.0',
    'category': 'Healthcare/Dental',
    'author': 'DMAG – Dental Management & Analytics Group',
    'website': 'https://dmagroup.vn',
    'license': 'LGPL-3',
    'depends': ['dmag_dental_clinic', 'portal', 'dmag_dental_loyalty'],
    'data': [
        'security/ir.model.access.csv',
        'security/dmag_patient_portal_security.xml',
        'views/dmag_portal_templates.xml',
        'views/dmag_booking_templates.xml',
        'views/dmag_dental_visit_views.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'dmag_patient_portal/static/src/css/dmag_portal.css',
        ],
    },
    'installable': True,
}
