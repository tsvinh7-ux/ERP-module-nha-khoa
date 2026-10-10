{
    'name': 'DMAG Clinic Workspace',
    'summary': 'Giao diện vận hành cho lễ tân và bác sĩ: bảng điều phối theo hành trình khách hàng, '
               'bàn làm việc bác sĩ, sơ đồ răng chạm, chế độ tư vấn 2 phương án',
    'version': '17.0.1.0.0',
    'category': 'Healthcare/Dental',
    'author': 'DMAG – Dental Management & Analytics Group',
    'website': 'https://dmagroup.vn',
    'license': 'LGPL-3',
    'depends': ['dmag_dental_clinic', 'web'],
    'data': [
        'report/payment_receipt.xml',
        'views/dmag_workspace_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'dmag_clinic_workspace/static/src/scss/workspace.scss',
            'dmag_clinic_workspace/static/src/js/**/*',
            'dmag_clinic_workspace/static/src/odontogram/**/*',
            'dmag_clinic_workspace/static/src/consult/**/*',
            'dmag_clinic_workspace/static/src/dialogs/**/*',
            'dmag_clinic_workspace/static/src/cockpit/**/*',
            'dmag_clinic_workspace/static/src/frontdesk/**/*',
            'dmag_clinic_workspace/static/src/doctor_desk/**/*',
        ],
    },
    'installable': True,
}
