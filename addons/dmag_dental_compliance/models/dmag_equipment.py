from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

from odoo.addons.dmag_dental_base.models.dmag_access import check_director, is_director, is_workflow

EQUIPMENT_CATEGORIES = [
    ('chair', 'Ghế nha'),
    ('xray', 'X-quang trong miệng / cận chóp'),
    ('pano', 'X-quang toàn cảnh (Panorama / Cephalo)'),
    ('cbct', 'CT Cone Beam (CBCT)'),
    ('autoclave', 'Nồi hấp tiệt khuẩn (autoclave)'),
    ('compressor', 'Máy nén khí'),
    ('suction', 'Máy hút phẫu thuật'),
    ('scanner', 'Máy scan trong miệng'),
    ('sensor', 'Sensor / máy đọc phim'),
    ('light', 'Đèn quang trùng hợp'),
    ('other', 'Khác'),
]
RADIATION_CATEGORIES = ('xray', 'pano', 'cbct')


class DmagEquipment(models.Model):
    """Thiết bị phòng khám: lịch kiểm định (thiết bị bức xạ), hiệu chuẩn, bảo trì và nhật ký."""
    _name = 'dmag.equipment'
    _description = 'Thiết bị nha khoa'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'dmag.compliance.alert.mixin']
    _order = 'company_id, category, name'

    name = fields.Char('Tên thiết bị', required=True, tracking=True)
    code = fields.Char('Mã tài sản')
    category = fields.Selection(EQUIPMENT_CATEGORIES, string='Loại', required=True, default='other', tracking=True)
    company_id = fields.Many2one('res.company', string='Phòng khám', required=True, index=True,
                                 default=lambda self: self.env.company)
    brand = fields.Char('Hãng')
    model_name = fields.Char('Model')
    serial_no = fields.Char('Số serial', tracking=True)
    chair_id = fields.Many2one('dmag.dental.chair', string='Gắn với ghế')
    location = fields.Char('Vị trí / phòng')
    purchase_date = fields.Date('Ngày đưa vào sử dụng')
    warranty_end_date = fields.Date('Hết bảo hành hãng')
    responsible_id = fields.Many2one('res.users', string='Người phụ trách', default=lambda self: self.env.user)
    state = fields.Selection([
        ('in_use', 'Đang sử dụng'),
        ('repair', 'Đang sửa chữa'),
        ('retired', 'Ngừng sử dụng'),
    ], string='Tình trạng', default='in_use', required=True, tracking=True)
    is_radiation = fields.Boolean('Thiết bị bức xạ', compute='_compute_is_radiation', store=True, readonly=False,
                                  help='Thiết bị X-quang / CBCT phải kiểm định định kỳ và nằm trong giấy phép tiến hành '
                                       'công việc bức xạ (NĐ 142/2020/NĐ-CP; TT 59/2025/TT-BKHCN).')

    inspection_required = fields.Boolean('Phải kiểm định / hiệu chuẩn định kỳ',
                                         compute='_compute_is_radiation', store=True, readonly=False)
    inspection_interval_months = fields.Integer('Chu kỳ kiểm định (tháng)', default=12)
    last_inspection_date = fields.Date('Kiểm định gần nhất', tracking=True)
    next_inspection_date = fields.Date('Kiểm định kế tiếp', compute='_compute_next_dates', store=True,
                                       readonly=False, tracking=True)
    maintenance_interval_months = fields.Integer('Chu kỳ bảo trì (tháng)', default=6)
    last_maintenance_date = fields.Date('Bảo trì gần nhất', tracking=True)
    next_maintenance_date = fields.Date('Bảo trì kế tiếp', compute='_compute_next_dates', store=True,
                                        readonly=False)
    alert_days = fields.Integer('Cảnh báo trước (ngày)', default=30)
    next_due_date = fields.Date('Đến hạn gần nhất', compute='_compute_inspection_status')
    inspection_status = fields.Selection([
        ('na', 'Không áp dụng'),
        ('ok', 'Đạt'),
        ('due_soon', 'Sắp đến hạn'),
        ('overdue', 'Quá hạn'),
    ], string='Kiểm định / bảo trì', compute='_compute_inspection_status')
    log_ids = fields.One2many('dmag.equipment.log', 'equipment_id', string='Nhật ký')
    compliance_doc_ids = fields.One2many('dmag.compliance.doc', 'equipment_id', string='Hồ sơ pháp chế')
    note = fields.Text('Ghi chú')
    active = fields.Boolean(default=True)

    @api.depends('category')
    def _compute_is_radiation(self):
        for eq in self:
            eq.is_radiation = eq.category in RADIATION_CATEGORIES
            eq.inspection_required = eq.category in RADIATION_CATEGORIES + ('autoclave', 'compressor')

    @api.depends('last_inspection_date', 'inspection_interval_months',
                 'last_maintenance_date', 'maintenance_interval_months')
    def _compute_next_dates(self):
        for eq in self:
            if eq.last_inspection_date and eq.inspection_interval_months:
                eq.next_inspection_date = eq.last_inspection_date + relativedelta(months=eq.inspection_interval_months)
            if eq.last_maintenance_date and eq.maintenance_interval_months:
                eq.next_maintenance_date = eq.last_maintenance_date + relativedelta(
                    months=eq.maintenance_interval_months)

    @api.depends('next_inspection_date', 'next_maintenance_date', 'inspection_required', 'state', 'alert_days')
    def _compute_inspection_status(self):
        today = fields.Date.context_today(self)
        for eq in self:
            dates = [d for d in (eq.inspection_required and eq.next_inspection_date, eq.next_maintenance_date) if d]
            eq.next_due_date = min(dates) if dates else False
            if eq.state == 'retired':
                eq.inspection_status = 'na'
            elif eq.inspection_required and not eq.next_inspection_date:
                eq.inspection_status = 'overdue'  # chưa có kết quả kiểm định
            elif not dates:
                eq.inspection_status = 'na'
            elif eq.next_due_date < today:
                eq.inspection_status = 'overdue'
            elif eq.next_due_date <= today + timedelta(days=eq.alert_days or 0):
                eq.inspection_status = 'due_soon'
            else:
                eq.inspection_status = 'ok'

    def _due_label(self):
        self.ensure_one()
        if self.inspection_required and self.next_inspection_date and self.next_inspection_date == self.next_due_date:
            return _('kiểm định')
        if self.inspection_required and not self.next_inspection_date:
            return _('chưa có kết quả kiểm định')
        return _('bảo trì')

    def _item_dict(self):
        self.ensure_one()
        today = fields.Date.context_today(self)
        return {
            'kind': 'equipment',
            'model': self._name,
            'id': self.id,
            'name': self.name,
            'type': _('Kiểm định / bảo trì thiết bị: %s', self._due_label()),
            'category': 'equipment',
            'number': self.serial_no or '',
            'expiry_date': fields.Date.to_string(self.next_due_date) if self.next_due_date else False,
            'days_left': (self.next_due_date - today).days if self.next_due_date else None,
            'state': {'overdue': 'expired', 'due_soon': 'expiring'}.get(self.inspection_status, 'valid'),
            'responsible': self.responsible_id.name or '',
            'legal_basis': (_('NĐ 142/2020/NĐ-CP; TT 59/2025/TT-BKHCN – kiểm định thiết bị X-quang chẩn đoán y tế')
                            if self.is_radiation else ''),
        }


class DmagEquipmentLog(models.Model):
    """Nhật ký thiết bị: bảo trì, sửa chữa, kiểm định, hiệu chuẩn, sự cố. Tạo được – không sửa."""
    _name = 'dmag.equipment.log'
    _description = 'Nhật ký thiết bị'
    _order = 'date desc, id desc'

    equipment_id = fields.Many2one('dmag.equipment', string='Thiết bị', required=True, ondelete='cascade',
                                   index=True)
    company_id = fields.Many2one(related='equipment_id.company_id', store=True)
    date = fields.Date('Ngày', required=True, default=fields.Date.context_today)
    log_type = fields.Selection([
        ('maintenance', 'Bảo trì định kỳ'),
        ('repair', 'Sửa chữa'),
        ('inspection', 'Kiểm định'),
        ('calibration', 'Hiệu chuẩn'),
        ('incident', 'Sự cố'),
    ], string='Loại', required=True, default='maintenance')
    result = fields.Selection([('pass', 'Đạt'), ('fail', 'Không đạt'), ('na', 'Không áp dụng')],
                              string='Kết quả', default='pass', required=True)
    vendor_id = fields.Many2one('res.partner', string='Đơn vị thực hiện')
    certificate_number = fields.Char('Số biên bản / chứng thư')
    user_id = fields.Many2one('res.users', string='Người ghi', default=lambda self: self.env.user, readonly=True)
    cost = fields.Monetary('Chi phí', currency_field='currency_id')
    currency_id = fields.Many2one(related='company_id.currency_id')
    note = fields.Text('Nội dung')
    attachment_ids = fields.Many2many('ir.attachment', string='Biên bản / ảnh')

    @api.model_create_multi
    def create(self, vals_list):
        logs = super().create(vals_list)
        for log in logs.sorted('date'):
            eq = log.equipment_id.sudo().with_context(dmag_workflow=True)
            vals = {}
            if log.log_type in ('inspection', 'calibration') and log.result == 'pass':
                if not eq.last_inspection_date or log.date >= eq.last_inspection_date:
                    vals['last_inspection_date'] = log.date
            if log.log_type == 'maintenance' and log.result != 'fail':
                if not eq.last_maintenance_date or log.date >= eq.last_maintenance_date:
                    vals['last_maintenance_date'] = log.date
            if log.result == 'fail' and log.log_type in ('inspection', 'calibration', 'incident'):
                vals['state'] = 'repair'
            if vals:
                eq.write(vals)
            eq.message_post(body=_('Nhật ký: %(type)s ngày %(date)s – %(result)s',
                                   type=dict(log._fields['log_type'].selection)[log.log_type], date=log.date,
                                   result=dict(log._fields['result'].selection)[log.result]))
        return logs

    def write(self, vals):
        if not is_workflow(self.env) and not is_director(self.env):
            raise AccessError(_('Nhật ký thiết bị đã ghi – chỉ Giám đốc / Quản lý cấp cao được sửa.'))
        return super().write(vals)

    def unlink(self):
        check_director(self.env)
        return super().unlink()
