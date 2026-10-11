{
    'name': 'DMAG – Điều hành mục tiêu (Mục tiêu kinh doanh · OKR · KPI)',
    'summary': 'Bảng điều hành mục tiêu cho chủ phòng khám: Giám đốc đặt mục tiêu kinh doanh theo tháng / quý / năm, '
               'theo dõi thực tế – tiến độ – dự báo cuối kỳ, OKR, KPI hành trình khách hàng, KPI theo bác sĩ / vị trí, '
               'sức khỏe tài chính và cảnh báo có việc cần làm',
    'version': '17.0.1.0.0',
    'category': 'Healthcare/Dental',
    'author': 'DMAG – Dental Management & Analytics Group',
    'website': 'https://dmagroup.vn',
    'license': 'LGPL-3',
    'depends': ['dmag_clinic_workspace'],
    'data': [
        'security/dmag_dental_goals_security.xml',
        'security/ir.model.access.csv',
        'views/dmag_business_target_views.xml',
        'views/dmag_goal_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'dmag_dental_goals/static/src/goal_dashboard/**/*',
        ],
    },
    'installable': True,
    'application': False,
}
