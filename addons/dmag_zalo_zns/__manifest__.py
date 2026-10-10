{
    'name': 'DMAG – Zalo ZNS',
    'summary': 'Gửi tin Zalo Notification Service (ZNS): cấu hình OA, làm mới token OAuth v4, '
               'danh mục mẫu ZNS, hàng đợi gửi có thử lại, giờ yên lặng, từ chối nhận tin, webhook trạng thái',
    'version': '17.0.1.0.0',
    'category': 'Healthcare/Dental',
    'author': 'DMAG – Dental Management & Analytics Group',
    'website': 'https://dmagroup.vn',
    'license': 'LGPL-3',
    'depends': ['dmag_dental_base', 'mail'],
    'data': [
        'security/dmag_zalo_zns_security.xml',
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'views/dmag_zns_template_views.xml',
        'views/dmag_zns_message_views.xml',
        'views/dmag_zns_webhook_event_views.xml',
        'views/res_company_views.xml',
        'views/res_partner_views.xml',
        'views/dmag_zalo_zns_menus.xml',
    ],
    'external_dependencies': {'python': ['requests']},
    'installable': True,
}
