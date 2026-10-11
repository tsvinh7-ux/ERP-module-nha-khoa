{
    'name': 'DMAG – AI chăm sóc khách hàng',
    'summary': 'Trợ lý Zalo OA 24/7 đặt lịch thật vào Odoo, dự báo khách không đến, phân loại phản hồi, '
               'quét CCCD, gợi ý xếp lịch, nội dung chăm sóc, trợ lý cổng bệnh nhân, theo dõi sau điều trị, '
               'mô phỏng nụ cười (AI-07 … AI-12, AI-17 … AI-19)',
    'version': '17.0.1.0.0',
    'category': 'Healthcare/Dental',
    'author': 'DMAG – Dental Management & Analytics Group',
    'website': 'https://dmagroup.vn',
    'license': 'LGPL-3',
    'depends': [
        'dmag_ai_core',
        'dmag_clinic_workspace',
        'dmag_zalo_zns',
        'dmag_dental_journey',
        'dmag_patient_portal',
        'dmag_dental_loyalty',
    ],
    'data': [
        'security/dmag_ai_customer_security.xml',
        'security/ir.model.access.csv',
        'data/dmag_ai_customer_data.xml',
        'data/ir_cron_data.xml',
        'views/dmag_ai_conversation_views.xml',
        'views/dmag_ai_feedback_views.xml',
        'views/dmag_ai_care_views.xml',
        'views/dmag_ai_followup_views.xml',
        'views/dmag_ai_smile_views.xml',
        'views/dmag_ai_noshow_views.xml',
        'views/dmag_dental_visit_views.xml',
        'views/res_company_views.xml',
        'views/portal_templates.xml',
        'views/dmag_ai_customer_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'dmag_ai_customer/static/src/scss/ai_customer.scss',
            'dmag_ai_customer/static/src/components/**/*',
            'dmag_ai_customer/static/src/zalo/**/*',
            'dmag_ai_customer/static/src/inbox/**/*',
            'dmag_ai_customer/static/src/patches/**/*',
        ],
        'web.assets_frontend': [
            'dmag_ai_customer/static/src/portal/portal_ai.css',
            'dmag_ai_customer/static/src/portal/portal_ai.js',
        ],
    },
    'installable': True,
}
