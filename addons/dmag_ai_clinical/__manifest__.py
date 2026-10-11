{
    'name': 'DMAG – Trợ lý AI cho bác sĩ',
    'summary': 'AI trong bàn làm việc bác sĩ: ghi bệnh án bằng giọng nói (AI-01), kiểm tra bệnh án trước khi ký '
               '(AI-02), an toàn đơn thuốc (AI-03), tóm tắt hồ sơ 30 giây (AI-04), gợi ý kế hoạch điều trị (AI-05), '
               'hỗ trợ đọc phim minh họa (AI-06) – chạy được ở chế độ giả lập và Claude API',
    'version': '17.0.1.0.0',
    'category': 'Healthcare/Dental',
    'author': 'DMAG – Dental Management & Analytics Group',
    'website': 'https://dmagroup.vn',
    'license': 'LGPL-3',
    'depends': ['dmag_ai_core', 'dmag_clinic_workspace', 'dmag_dental_emr', 'dmag_dental_prescription'],
    'external_dependencies': {'python': ['requests']},
    'data': [
        'security/ir.model.access.csv',
        'views/res_company_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'dmag_ai_clinical/static/src/scss/ai_clinical.scss',
            'dmag_ai_clinical/static/src/js/**/*',
            'dmag_ai_clinical/static/src/xml/**/*',
        ],
    },
    'installable': True,
}
