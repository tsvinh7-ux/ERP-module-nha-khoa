{
    'name': 'DMAG – AI điều hành & Trung tâm AI',
    'summary': 'Hỏi đáp số liệu bằng tiếng Việt (AI-13), bản tin điều hành hằng tuần (AI-14), phát hiện bất thường '
               'tại chỗ (AI-15), dự báo doanh thu & vật tư (AI-16) trên Bảng điều hành mục tiêu; Trung tâm AI giới '
               'thiệu và mở thử 20 tính năng AI-00 … AI-19 theo vai trò',
    'version': '17.0.1.0.0',
    'category': 'Healthcare/Dental',
    'author': 'DMAG – Dental Management & Analytics Group',
    'website': 'https://dmagroup.vn',
    'license': 'LGPL-3',
    'depends': ['dmag_ai_core', 'dmag_dental_goals'],
    'data': [
        'security/dmag_ai_insights_security.xml',
        'security/ir.model.access.csv',
        'data/dmag_ai_insights_cron.xml',
        'views/dmag_ai_brief_views.xml',
        'views/dmag_ai_anomaly_views.xml',
        'views/dmag_ai_insights_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'dmag_ai_insights/static/src/scss/ai_insights.scss',
            'dmag_ai_insights/static/src/common/**/*',
            'dmag_ai_insights/static/src/qa/**/*',
            'dmag_ai_insights/static/src/anomaly/**/*',
            'dmag_ai_insights/static/src/forecast/**/*',
            'dmag_ai_insights/static/src/brief/**/*',
            'dmag_ai_insights/static/src/hub/**/*',
            'dmag_ai_insights/static/src/goal_patch/**/*',
        ],
    },
    'installable': True,
    'application': False,
}
