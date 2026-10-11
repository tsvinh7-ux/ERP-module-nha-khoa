from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class DmagDentalPractitioner(models.Model):
    """Nhân sự lâm sàng (bác sĩ, phụ tá, KTV).

    Tách khỏi hr.employee để lễ tân/phụ tá đọc được thông tin chuyên môn mà
    không cần quyền Nhân sự; liên kết hr.employee (tùy chọn) để ráp lương 3P sau.
    """
    _name = 'dmag.dental.practitioner'
    _description = 'Nhân sự lâm sàng'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'role, sequence, name'

    name = fields.Char('Họ tên', required=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    role = fields.Selection([
        ('doctor', 'Bác sĩ'),
        ('assistant', 'Phụ tá / Điều dưỡng'),
        ('technician', 'Kỹ thuật viên'),
    ], string='Vai trò', required=True, default='doctor', tracking=True)
    title = fields.Char('Học hàm / chức danh', help='Ví dụ: ThS.BS, BSCKI…')
    user_id = fields.Many2one('res.users', string='Tài khoản đăng nhập', tracking=True)
    employee_id = fields.Many2one('hr.employee', string='Hồ sơ nhân viên',
                                  groups='hr.group_hr_user')
    company_id = fields.Many2one('res.company', string='Phòng khám', required=True,
                                 default=lambda self: self.env.company)
    image_128 = fields.Image('Ảnh', max_width=128, max_height=128)
    color = fields.Integer('Màu lịch')
    phone = fields.Char('Điện thoại')
    work_weekday_ids = fields.Many2many(
        'dmag.weekday', string='Ngày làm việc',
        help='Để trống = làm việc mọi ngày phòng khám mở cửa (theo Lịch làm việc phòng khám). '
             'Chọn các thứ nếu bác sĩ chỉ làm một số ngày – đặt lịch / gợi ý giờ trống sẽ theo đó.')

    clinical_level_id = fields.Many2one('dmag.clinical.level', string='Bậc lâm sàng', tracking=True)
    scope_ids = fields.Many2many('dmag.practice.scope', string='Phạm vi hành nghề', tracking=True)
    license_number = fields.Char('Số giấy phép hành nghề', tracking=True)
    license_issue_date = fields.Date('Ngày cấp')
    license_expiry_date = fields.Date('Ngày hết hạn', tracking=True,
                                      help='Giấy phép hành nghề có thời hạn 5 năm theo Luật KCB 2023.')
    license_state = fields.Selection([
        ('missing', 'Chưa khai báo'),
        ('valid', 'Còn hiệu lực'),
        ('expiring', 'Sắp hết hạn'),
        ('expired', 'Hết hạn'),
    ], string='Tình trạng giấy phép', compute='_compute_license_state')

    _sql_constraints = [
        ('user_company_uniq', 'unique(user_id, company_id)',
         'Mỗi tài khoản chỉ gắn với một hồ sơ lâm sàng trong một phòng khám.'),
    ]

    @api.depends('license_number', 'license_expiry_date')
    def _compute_license_state(self):
        today = fields.Date.context_today(self)
        for practitioner in self:
            if not practitioner.license_number:
                practitioner.license_state = 'missing'
            elif not practitioner.license_expiry_date:
                practitioner.license_state = 'valid'
            elif practitioner.license_expiry_date < today:
                practitioner.license_state = 'expired'
            elif practitioner.license_expiry_date <= today + timedelta(days=60):
                practitioner.license_state = 'expiring'
            else:
                practitioner.license_state = 'valid'

    @api.constrains('license_issue_date', 'license_expiry_date')
    def _check_license_dates(self):
        for practitioner in self:
            if (practitioner.license_issue_date and practitioner.license_expiry_date
                    and practitioner.license_expiry_date < practitioner.license_issue_date):
                raise ValidationError(_('Ngày hết hạn giấy phép phải sau ngày cấp.'))

    def _get_service_blockers(self, products):
        """Trả về danh sách lý do bác sĩ này KHÔNG được thực hiện các dịch vụ.

        Dùng chung cho xếp lịch, lập kế hoạch và ghi nhận thủ thuật: chặn chỉ định
        ngoài phạm vi hành nghề, dưới bậc lâm sàng, hoặc khi giấy phép hết hạn.
        """
        self.ensure_one()
        reasons = []
        if self.role == 'doctor' and self.license_state == 'expired':
            reasons.append(_('Giấy phép hành nghề của %s đã hết hạn.', self.name))
        my_level = self.clinical_level_id.level or 0
        for product in products.mapped('product_tmpl_id'):
            if not product.is_dental_service:
                continue
            if product.practice_scope_id and product.practice_scope_id not in self.scope_ids:
                reasons.append(_('%(svc)s yêu cầu phạm vi "%(scope)s" – %(doc)s chưa có.',
                                 svc=product.name, scope=product.practice_scope_id.name, doc=self.name))
            if product.min_clinical_level_id and my_level < product.min_clinical_level_id.level:
                reasons.append(_('%(svc)s yêu cầu %(lvl)s trở lên – %(doc)s chưa đạt.',
                                 svc=product.name, lvl=product.min_clinical_level_id.name, doc=self.name))
        return reasons

    def works_on(self, day, info=None):
        """Bác sĩ làm việc ngày ``day``: phòng khám mở cửa và (nếu có khai) đúng thứ làm việc của bác sĩ."""
        self.ensure_one()
        info = info or self.env['dmag.clinic.schedule'].get_info(self.company_id)
        if not info.is_open_day(day):
            return False
        codes = self.work_weekday_ids.mapped('code')
        return not codes or day.weekday() in codes

    def check_can_perform(self, products):
        for practitioner in self:
            reasons = practitioner._get_service_blockers(products)
            if reasons:
                raise ValidationError('\n'.join(reasons))
        return True

    @api.model
    def _cron_notify_license_expiry(self):
        """Tạo việc nhắc cho quản lý khi giấy phép sắp hết hạn."""
        manager_group = self.env.ref('dmag_dental_base.group_dmag_manager', raise_if_not_found=False)
        todo_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        if not manager_group or not todo_type:
            return
        limit_date = fields.Date.context_today(self) + timedelta(days=60)
        practitioners = self.search([
            ('license_expiry_date', '!=', False),
            ('license_expiry_date', '<=', limit_date),
        ])
        for practitioner in practitioners:
            managers = manager_group.users.filtered(lambda u: practitioner.company_id in u.company_ids)
            for manager in managers[:1]:
                if practitioner.activity_ids.filtered(lambda a: a.user_id == manager):
                    continue
                practitioner.activity_schedule(
                    act_type_xmlid='mail.mail_activity_data_todo',
                    date_deadline=practitioner.license_expiry_date,
                    summary=_('Gia hạn giấy phép hành nghề'),
                    user_id=manager.id,
                )
