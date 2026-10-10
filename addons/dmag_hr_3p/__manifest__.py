{
    'name': 'DMAG – Ngạch bậc P/M & Lương 3P (bản demo)',
    'summary': 'Khung ngạch P (chuyên môn) / M (quản lý), hồ sơ vị trí, năng lực P2, KPI P3, '
               'bảng đầu vào lương 3P có duyệt và xuất cho Payroll Bizapps',
    'version': '17.0.1.0.0',
    'category': 'Healthcare/Dental',
    'author': 'DMAG – Dental Management & Analytics Group',
    'website': 'https://dmagroup.vn',
    'license': 'LGPL-3',
    'depends': ['hr', 'dmag_dental_base'],
    'data': [
        'security/dmag_hr_3p_security.xml',
        'security/ir.model.access.csv',
        'data/dmag_hr_3p_sample_data.xml',
        'views/dmag_job_grade_views.xml',
        'views/dmag_position_profile_views.xml',
        'views/hr_employee_views.xml',
        'views/dmag_assessment_views.xml',
        'views/dmag_pay3p_sheet_views.xml',
        'views/dmag_hr_3p_menus.xml',
    ],
    'installable': True,
}
