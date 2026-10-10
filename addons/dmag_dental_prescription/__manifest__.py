{
    'name': 'DMAG – Đơn thuốc điện tử & liên thông',
    'summary': 'Kê đơn thuốc điện tử theo TT 26/2025/TT-BYT, mã đơn 14 ký tự, đơn mẫu, '
               'liên thông Hệ thống đơn thuốc quốc gia (donthuocquocgia.vn)',
    'version': '17.0.1.0.0',
    'category': 'Healthcare/Dental',
    'author': 'DMAG – Dental Management & Analytics Group',
    'website': 'https://dmagroup.vn',
    'license': 'LGPL-3',
    'depends': ['dmag_dental_clinic'],
    'external_dependencies': {'python': ['requests']},
    'data': [
        'security/dmag_prescription_security.xml',
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'report/dmag_prescription_report.xml',
        'views/dmag_drug_views.xml',
        'views/dmag_prescription_template_views.xml',
        'views/dmag_prescription_views.xml',
        'views/dmag_rx_national_views.xml',
        'views/res_config_views.xml',
        'views/dmag_prescription_menus.xml',
    ],
    'demo': [
        'data/dmag_drug_demo.xml',
        'data/dmag_prescription_template_demo.xml',
    ],
    'installable': True,
}
