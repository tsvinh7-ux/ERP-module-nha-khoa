{
    'name': 'DMAG – OKR nha khoa tự đo',
    'summary': 'Cầu nối OKR Scale: KR tự cập nhật từ dữ liệu nha khoa (NPS, thời gian chờ, điểm đau, '
               'ca niềng mới, tỷ lệ chốt, doanh thu giới thiệu, công suất ghế chiều…) và chỉ số cầu chì',
    'version': '17.0.1.0.0',
    'category': 'Healthcare/Dental',
    'author': 'DMAG – Dental Management & Analytics Group',
    'website': 'https://dmagroup.vn',
    'license': 'LGPL-3',
    'depends': ['dmag_dental_clinic', 'okr_scale'],
    'data': [
        'security/dmag_okr_dental_security.xml',
        'security/ir.model.access.csv',
        'data/dmag_okr_dental_data.xml',
        'views/okr_key_result_views.xml',
        'views/dmag_okr_guardrail_views.xml',
    ],
    'installable': True,
}
