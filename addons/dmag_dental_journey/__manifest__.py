{
    'name': 'DMAG – Hành trình khách hàng Trước–Trong–Sau',
    'summary': 'Tự động hóa điểm chạm hành trình khách hàng: xác nhận & nhắc lịch ZNS, chào mừng check-in, '
               'cảm ơn sau khám, gọi hỏi thăm +24h, NPS +48h, nhắc tái khám, sinh nhật, bảo hành; '
               'bảng việc CSKH và bảng điều khiển hành trình',
    'version': '17.0.1.0.0',
    'category': 'Healthcare/Dental',
    'author': 'DMAG – Dental Management & Analytics Group',
    'website': 'https://dmagroup.vn',
    'license': 'LGPL-3',
    'depends': ['dmag_dental_clinic', 'dmag_zalo_zns'],
    'data': [
        'security/dmag_dental_journey_security.xml',
        'security/ir.model.access.csv',
        'data/mail_activity_type_data.xml',
        'data/dmag_zns_template_data.xml',
        'data/dmag_journey_rule_data.xml',
        'data/ir_cron_data.xml',
        'views/dmag_journey_rule_views.xml',
        'views/dmag_journey_execution_views.xml',
        'views/dmag_nps_response_views.xml',
        'views/mail_activity_views.xml',
        'views/dmag_dental_visit_views.xml',
        'views/res_company_views.xml',
        'views/dmag_nps_templates.xml',
        'wizard/dmag_journey_pain_wizard_views.xml',
        'views/dmag_dental_journey_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'dmag_dental_journey/static/src/dashboard/*',
        ],
    },
    'installable': True,
}
