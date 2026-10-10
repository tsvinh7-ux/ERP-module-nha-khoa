{
    'name': 'DMAG – Vật tư theo định mức',
    'summary': 'Định mức vật tư theo dịch vụ, tự trừ kho khi hoàn tất thủ thuật, serial implant ↔ bệnh nhân, '
               'ghi nhận tiêu hao thực tế, giá vốn vật tư / doanh thu (≤ 22%)',
    'version': '17.0.1.0.0',
    'category': 'Healthcare/Dental',
    'author': 'DMAG – Dental Management & Analytics Group',
    'website': 'https://dmagroup.vn',
    'license': 'LGPL-3',
    'depends': ['dmag_dental_clinic', 'stock'],
    'data': [
        'security/dmag_dental_stock_security.xml',
        'security/ir.model.access.csv',
        'views/dmag_service_bom_views.xml',
        'views/dmag_material_usage_views.xml',
        'views/dmag_dental_procedure_views.xml',
        'views/res_company_views.xml',
        'views/stock_lot_views.xml',
        'views/dmag_stock_menus.xml',
    ],
    'demo': [
        'data/dmag_stock_demo.xml',
    ],
    'installable': True,
}
