{
    'name': 'DMAG – Ký số Viettel MySign',
    'summary': 'Ký số từ xa bệnh án / chứng từ y tế bằng Viettel MySign (ký trên điện thoại bác sĩ), '
               'khung ký số dùng chung cho mọi module DMAG',
    'version': '17.0.1.0.0',
    'category': 'Healthcare/Dental',
    'author': 'DMAG – Dental Management & Analytics Group',
    'website': 'https://dmagroup.vn',
    'license': 'LGPL-3',
    'depends': ['dmag_dental_clinic'],
    # Phụ thuộc python MỀM: `cryptography` (ký giả lập / đọc chứng thư), `requests` (gọi API MySign),
    # `pyhanko` hoặc `endesive` (nhúng chữ ký PAdES vào PDF) – không khai báo cứng.
    'data': [
        'security/dmag_esign_security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/ir_cron_data.xml',
        'report/dmag_visit_record_report.xml',
        'views/dmag_esign_provider_views.xml',
        'views/dmag_esign_request_views.xml',
        'views/dmag_dental_practitioner_views.xml',
        'views/dmag_dental_visit_views.xml',
        'views/dmag_esign_menus.xml',
    ],
    'installable': True,
}
