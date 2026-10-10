{
    'name': 'DMAG – Thẻ bảo hành',
    'summary': 'Thẻ bảo hành điện tử tự sinh khi hoàn tất implant / răng sứ / chỉnh nha, '
               'yêu cầu bảo hành, nhắc trước khi hết hạn, in thẻ cỡ thẻ ngân hàng',
    'version': '17.0.1.0.0',
    'category': 'Healthcare/Dental',
    'author': 'DMAG – Dental Management & Analytics Group',
    'website': 'https://dmagroup.vn',
    'license': 'LGPL-3',
    'depends': ['dmag_dental_clinic'],
    'data': [
        'security/dmag_dental_warranty_security.xml',
        'security/ir.model.access.csv',
        'data/dmag_warranty_data.xml',
        'report/dmag_warranty_card_report.xml',
        'views/dmag_warranty_views.xml',
        'views/product_template_views.xml',
        'views/res_partner_views.xml',
        'views/dmag_warranty_menus.xml',
    ],
    'demo': [
        'data/dmag_warranty_demo.xml',
    ],
    'installable': True,
}
