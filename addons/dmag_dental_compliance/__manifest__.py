{
    'name': 'DMAG – Hồ sơ pháp chế',
    'summary': 'Giấy phép, hành nghề, bức xạ, kiểm định X-quang/CBCT, chất thải y tế, PCCC; thiết bị & bảo trì; '
               'mẻ tiệt khuẩn; cảnh báo trước hạn và "Sẵn sàng thanh tra" 1 click',
    'version': '17.0.1.0.0',
    'category': 'Healthcare/Dental',
    'author': 'DMAG – Dental Management & Analytics Group',
    'website': 'https://dmagroup.vn',
    'license': 'LGPL-3',
    'depends': ['dmag_dental_base', 'dmag_dental_clinic'],
    'data': [
        'security/dmag_dental_compliance_security.xml',
        'security/ir.model.access.csv',
        'data/dmag_compliance_data.xml',
        'views/dmag_compliance_doc_views.xml',
        'views/dmag_equipment_views.xml',
        'views/dmag_sterilization_views.xml',
        'views/dmag_dental_visit_views.xml',
        'views/dmag_compliance_menus.xml',
    ],
    'demo': [
        'data/dmag_compliance_demo.xml',
    ],
    'installable': True,
}
