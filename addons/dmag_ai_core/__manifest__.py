{
    'name': 'DMAG – Trợ lý AI (nền tảng)',
    'summary': 'Cổng gọi AI dùng chung: Claude API / giả lập, ẩn danh dữ liệu bệnh nhân, nhật ký & chi phí, '
               'trần ngân sách, đồng ý của bệnh nhân, bật/tắt từng tính năng AI',
    'version': '17.0.1.0.0',
    'category': 'Healthcare/Dental',
    'author': 'DMAG – Dental Management & Analytics Group',
    'website': 'https://dmagroup.vn',
    'license': 'LGPL-3',
    'depends': ['dmag_dental_base', 'mail'],
    'data': [
        'security/dmag_ai_security.xml',
        'security/ir.model.access.csv',
        'data/dmag_ai_feature_data.xml',
        'views/dmag_ai_views.xml',
    ],
    'installable': True,
}
