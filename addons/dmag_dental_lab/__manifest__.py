{
    'name': 'DMAG – Labo',
    'summary': 'Phiếu gửi labo (màu răng, vật liệu, lấy dấu/scan, hạn trả), thử sườn/thử sứ, '
               'trễ hạn, chi phí labo → đơn mua hàng, tỷ lệ labo / doanh thu',
    'version': '17.0.1.0.0',
    'category': 'Healthcare/Dental',
    'author': 'DMAG – Dental Management & Analytics Group',
    'website': 'https://dmagroup.vn',
    'license': 'LGPL-3',
    'depends': ['dmag_dental_clinic', 'purchase'],
    'data': [
        'security/dmag_dental_lab_security.xml',
        'security/ir.model.access.csv',
        'data/dmag_lab_data.xml',
        'views/dmag_lab_order_views.xml',
        'views/res_partner_views.xml',
        'views/dmag_dental_visit_views.xml',
        'views/dmag_lab_menus.xml',
    ],
    'demo': [
        'data/dmag_lab_demo.xml',
    ],
    'installable': True,
}
