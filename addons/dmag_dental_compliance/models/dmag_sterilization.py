from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.dmag_dental_base.models.dmag_access import check_director, is_director, is_workflow

RESULTS = [('pending', 'Chờ kết quả'), ('pass', 'Đạt'), ('fail', 'Không đạt')]
# Phụ tá được cập nhật khi mẻ còn nháp; sau khi phát hành chỉ cập nhật kết quả sinh học đang chờ
BIO_UPDATE_FIELDS = {'biological_result', 'biological_read_date', 'note'}


class DmagInstrumentSet(models.Model):
    _name = 'dmag.instrument.set'
    _description = 'Bộ dụng cụ'
    _order = 'name'

    name = fields.Char('Tên bộ dụng cụ', required=True)
    code = fields.Char('Mã / mã vạch')
    company_id = fields.Many2one('res.company', string='Phòng khám', required=True,
                                 default=lambda self: self.env.company)
    category = fields.Selection([
        ('exam', 'Khám'), ('restorative', 'Trám / nội nha'), ('surgery', 'Phẫu thuật / nhổ'),
        ('implant', 'Implant'), ('hygiene', 'Cạo vôi'), ('ortho', 'Chỉnh nha'), ('other', 'Khác'),
    ], string='Loại', default='exam')
    active = fields.Boolean(default=True)
    note = fields.Text('Thành phần')


class DmagSterilizationBatch(models.Model):
    """Mẻ tiệt khuẩn (autoclave) – truy vết dụng cụ ↔ lượt khám theo TT 16/2018/TT-BYT."""
    _name = 'dmag.sterilization.batch'
    _description = 'Mẻ tiệt khuẩn'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char('Số mẻ', required=True, copy=False, readonly=True, default='/')
    company_id = fields.Many2one('res.company', string='Phòng khám', required=True, index=True,
                                 default=lambda self: self.env.company)
    autoclave_id = fields.Many2one('dmag.equipment', string='Nồi hấp', required=True,
                                   domain="[('category', '=', 'autoclave'), ('company_id', '=', company_id)]")
    cycle_number = fields.Char('Số chu trình máy', help='Số đếm chu trình hiển thị trên máy / bản in của máy.')
    date = fields.Datetime('Thời điểm hấp', required=True, default=fields.Datetime.now, index=True)
    program = fields.Selection([
        ('134', '134°C – dụng cụ gói'),
        ('121', '121°C – vật liệu chịu nhiệt kém'),
        ('flash', 'Chu trình nhanh (không gói)'),
        ('other', 'Khác'),
    ], string='Chương trình', default='134', required=True)
    operator_id = fields.Many2one('res.users', string='Người vận hành', default=lambda self: self.env.user,
                                  required=True)
    instrument_set_ids = fields.Many2many('dmag.instrument.set', string='Bộ dụng cụ')
    pack_count = fields.Integer('Số gói')
    chemical_result = fields.Selection(RESULTS, string='Chỉ thị hóa học', default='pending', required=True,
                                       tracking=True)
    bowie_dick_result = fields.Selection(RESULTS + [('na', 'Không thực hiện')], string='Bowie-Dick',
                                         default='na', required=True)
    biological_result = fields.Selection(RESULTS + [('na', 'Không thực hiện')], string='Chỉ thị sinh học',
                                         default='na', required=True, tracking=True)
    biological_read_date = fields.Datetime('Thời điểm đọc chỉ thị sinh học')
    expiry_date = fields.Date('Hạn dùng gói', help='Theo quy trình KSNK của phòng khám.')
    state = fields.Selection([
        ('draft', 'Đang hấp / chờ kiểm tra'),
        ('released', 'Đạt – phát hành'),
        ('failed', 'Không đạt'),
        ('recalled', 'Thu hồi'),
    ], string='Trạng thái', default='draft', required=True, tracking=True, index=True, copy=False)
    visit_ids = fields.Many2many('dmag.dental.visit', 'dmag_visit_sterilization_rel', 'batch_id', 'visit_id',
                                 string='Lượt khám đã dùng', readonly=True)
    visit_count = fields.Integer(compute='_compute_visit_count')
    note = fields.Text('Ghi chú')

    def _compute_visit_count(self):
        for batch in self:
            batch.visit_count = len(batch.visit_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('dmag.sterilization.batch') or '/'
        return super().create(vals_list)

    def write(self, vals):
        if not is_workflow(self.env) and not is_director(self.env):
            if 'state' in vals:
                raise AccessError(_('Trạng thái mẻ tiệt khuẩn đổi bằng nút "Phát hành" / "Không đạt".'))
            for batch in self:
                if batch.state == 'draft':
                    continue
                allowed = BIO_UPDATE_FIELDS if batch.biological_result == 'pending' else set()
                if set(vals) - allowed:
                    raise AccessError(_('Mẻ %s đã phát hành – chỉ cập nhật kết quả chỉ thị sinh học đang chờ. '
                                        'Sửa khác cần Giám đốc / Quản lý cấp cao.', batch.name))
        res = super().write(vals)
        if vals.get('biological_result') == 'fail':
            self.filtered(lambda b: b.state == 'released')._dmag_recall()
        return res

    def unlink(self):
        if any(b.state != 'draft' for b in self):
            check_director(self.env)
        return super().unlink()

    def action_release(self):
        for batch in self:
            if batch.state != 'draft':
                raise UserError(_('Mẻ %s không ở trạng thái chờ kiểm tra.', batch.name))
            if batch.chemical_result != 'pass':
                raise UserError(_('Chỉ thị hóa học của mẻ %s chưa đạt – không phát hành dụng cụ.', batch.name))
            if batch.bowie_dick_result in ('fail', 'pending') or batch.biological_result == 'fail':
                raise UserError(_('Mẻ %s có kiểm tra không đạt / chưa có kết quả Bowie-Dick.', batch.name))
            vals = {'state': 'released'}
            if not batch.expiry_date:
                vals['expiry_date'] = fields.Date.context_today(batch) + timedelta(days=30)
            batch.with_context(dmag_workflow=True).write(vals)
        return True

    def action_fail(self):
        for batch in self:
            if batch.state not in ('draft', 'released'):
                raise UserError(_('Mẻ %s đã đóng.', batch.name))
            if batch.state == 'released':
                batch._dmag_recall()
            else:
                batch.with_context(dmag_workflow=True).write({'state': 'failed'})
        return True

    def _dmag_recall(self):
        """Mẻ đã phát hành nhưng chỉ thị sinh học không đạt → thu hồi, báo quản lý danh sách lượt khám đã dùng."""
        group = self.env.ref('dmag_dental_base.group_dmag_manager', raise_if_not_found=False)
        for batch in self:
            batch.sudo().with_context(dmag_workflow=True).write({'state': 'recalled'})
            visits = ', '.join(batch.visit_ids.mapped('name')) or _('chưa có')
            batch.sudo().message_post(body=_('THU HỒI mẻ %(name)s. Lượt khám đã dùng: %(visits)s.',
                                             name=batch.name, visits=visits))
            managers = group.users.filtered(lambda u: batch.company_id in u.company_ids) if group else False
            user = managers[:1] if managers else self.env.user
            batch.sudo().activity_schedule(
                act_type_xmlid='mail.mail_activity_data_todo',
                date_deadline=fields.Date.context_today(batch),
                summary=_('Mẻ tiệt khuẩn %s không đạt – rà soát %s lượt khám', batch.name, len(batch.visit_ids)),
                user_id=user.id)

    def action_open_visits(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'name': _('Lượt khám dùng mẻ %s', self.name),
                'res_model': 'dmag.dental.visit', 'view_mode': 'tree,form',
                'domain': [('id', 'in', self.visit_ids.ids)]}

    def _item_dict(self):
        self.ensure_one()
        return {
            'kind': 'sterilization',
            'model': self._name,
            'id': self.id,
            'name': _('Mẻ tiệt khuẩn %s', self.name),
            'type': dict(self._fields['state'].selection)[self.state],
            'category': 'infection',
            'number': self.cycle_number or '',
            'expiry_date': False,
            'days_left': None,
            'state': 'expired',
            'responsible': self.operator_id.name or '',
            'legal_basis': _('TT 16/2018/TT-BYT – kiểm soát nhiễm khuẩn'),
        }
