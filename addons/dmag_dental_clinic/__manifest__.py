{
    'name': 'DMAG Dental – Vận hành phòng khám',
    'summary': 'Lượt khám theo hành trình khách hàng, sơ đồ răng, bệnh án có khóa ký, '
               'kế hoạch điều trị nhiều phương án, thủ thuật và thu tiền theo tiến độ',
    'version': '17.0.1.0.0',
    'category': 'Healthcare/Dental',
    'author': 'DMAG – Dental Management & Analytics Group',
    'website': 'https://dmagroup.vn',
    'license': 'LGPL-3',
    'depends': ['dmag_dental_base', 'sale_management'],
    'data': [
        'security/dmag_dental_clinic_security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'report/dmag_treatment_plan_report.xml',
        'views/dmag_dental_visit_views.xml',
        'views/dmag_dental_chart_views.xml',
        'views/dmag_treatment_plan_views.xml',
        'views/res_partner_views.xml',
        'views/product_template_views.xml',
        'views/dmag_dental_clinic_menus.xml',
    ],
    'demo': [
        'data/dmag_dental_clinic_demo.xml',
    ],
    'installable': True,
}
