{
    'name': 'DMAG – Thủ thuật phí & hoa hồng',
    'summary': 'Thủ thuật phí bác sĩ / phụ tá, hoa hồng tư vấn, lễ tân, telesale, người giới thiệu – '
               'tính trên tiền thực thu, tự hủy khi vi phạm cầu chì y đức, bảng kê tháng',
    'version': '17.0.1.0.0',
    'category': 'Healthcare/Dental',
    'author': 'DMAG – Dental Management & Analytics Group',
    'website': 'https://dmagroup.vn',
    'license': 'LGPL-3',
    'depends': ['dmag_dental_clinic'],
    'data': [
        'security/dmag_commission_security.xml',
        'security/ir.model.access.csv',
        'data/dmag_commission_data.xml',
        'views/dmag_commission_rule_views.xml',
        'views/dmag_commission_line_views.xml',
        'views/dmag_commission_statement_views.xml',
        'views/dmag_dental_visit_views.xml',
        'wizard/dmag_commission_statement_wizard_views.xml',
        'views/dmag_commission_menus.xml',
    ],
    'installable': True,
}
