from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError

from odoo.addons.dmag_dental_base.models.dmag_access import check_director, is_director, is_workflow

LAYERS = [
    ('existing', 'Hiện trạng'),
    ('planned', 'Kế hoạch'),
    ('done', 'Đã điều trị'),
]


class DmagDentalChartEntry(models.Model):
    """Một ghi nhận trên sơ đồ răng: răng + (mặt răng) + tình trạng + lớp.

    Sơ đồ răng của bệnh nhân = tập các ghi nhận còn hiệu lực (active). Khi một
    bệnh lý được điều trị xong, ghi nhận bệnh lý được lưu trữ (active=False) và
    sinh ghi nhận lớp "Đã điều trị", nên lịch sử luôn đầy đủ.
    """
    _name = 'dmag.dental.chart.entry'
    _description = 'Ghi nhận sơ đồ răng'
    _order = 'date desc, id desc'

    patient_id = fields.Many2one('res.partner', string='Bệnh nhân', required=True,
                                 index=True, ondelete='cascade')
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    visit_id = fields.Many2one('dmag.dental.visit', string='Lượt khám', index=True, ondelete='set null')
    tooth_id = fields.Many2one('dmag.dental.tooth', string='Răng', required=True)
    surface_ids = fields.Many2many('dmag.dental.surface', string='Mặt răng')
    condition_id = fields.Many2one('dmag.dental.condition', string='Tình trạng', required=True)
    condition_category = fields.Selection(related='condition_id.category')
    layer = fields.Selection(LAYERS, string='Lớp', required=True, default='existing')
    diagnosis_id = fields.Many2one('dmag.dental.diagnosis', string='Chẩn đoán',
                                   compute='_compute_diagnosis_id', store=True, readonly=False)
    note = fields.Char('Ghi chú')
    practitioner_id = fields.Many2one('dmag.dental.practitioner', string='Người ghi nhận')
    date = fields.Datetime('Thời điểm', required=True, default=fields.Datetime.now)
    plan_line_id = fields.Many2one('dmag.treatment.plan.line', string='Dòng kế hoạch', ondelete='set null')
    procedure_id = fields.Many2one('dmag.dental.procedure', string='Thủ thuật', ondelete='set null')
    active = fields.Boolean(default=True, help='Bỏ chọn khi bệnh lý đã được xử lý.')

    @api.depends('condition_id')
    def _compute_diagnosis_id(self):
        for entry in self:
            if not entry.diagnosis_id:
                entry.diagnosis_id = entry.condition_id.diagnosis_id

    @api.constrains('condition_id', 'surface_ids')
    def _check_surfaces(self):
        for entry in self:
            if (entry.condition_id.scope == 'surface' and entry.condition_id.category == 'finding'
                    and not entry.surface_ids):
                raise ValidationError(_('"%s" cần chọn ít nhất một mặt răng.', entry.condition_id.name))

    @api.model
    def get_patient_chart(self, patient_id):
        """Dữ liệu dựng sơ đồ răng (dùng cho giao diện OWL)."""
        entries = self.search([('patient_id', '=', patient_id)], order='date asc, id asc')
        return [{
            'id': e.id,
            'tooth': e.tooth_id.code,
            'surfaces': e.surface_ids.mapped('code'),
            'condition_id': e.condition_id.id,
            'condition': e.condition_id.name,
            'condition_code': e.condition_id.code,
            'scope': e.condition_id.scope,
            'category': e.condition_id.category,
            'symbol': e.condition_id.symbol,
            'color': e.condition_id.color,
            'layer': e.layer,
            'note': e.note or '',
            'date': fields.Datetime.to_string(e.date),
            'by': e.practitioner_id.name or '',
            'diagnosis': e.diagnosis_id.display_name or '',
        } for e in entries]

    @api.model
    def get_chart_catalog(self):
        teeth = self.env['dmag.dental.tooth'].search([])
        conditions = self.env['dmag.dental.condition'].search([])
        return {
            'teeth': [{'code': t.code, 'name': t.name, 'quadrant': t.quadrant, 'position': t.position,
                       'dentition': t.dentition, 'type': t.tooth_type} for t in teeth],
            'surfaces': [{'code': s.code, 'name': s.name, 'alias': s.alias_code or '',
                          'description': s.description or ''}
                         for s in self.env['dmag.dental.surface'].search([])],
            'conditions': [{
                'id': c.id, 'name': c.name, 'code': c.code, 'category': c.category, 'scope': c.scope,
                'color': c.color, 'symbol': c.symbol,
                'services': [{'id': p.id, 'name': p.display_name, 'price': p.lst_price}
                             for p in c.suggested_service_ids],
            } for c in conditions],
        }

    @api.model
    def add_from_chart(self, patient_id, teeth, condition_id, surfaces=None, layer='existing',
                       visit_id=False, note=False):
        """Ghi nhanh từ sơ đồ: một tình trạng cho nhiều răng trong một lần chạm."""
        Tooth = self.env['dmag.dental.tooth']
        Surface = self.env['dmag.dental.surface']
        practitioner = self.env['dmag.dental.visit']._current_practitioner()
        surface_ids = Surface.search([('code', 'in', surfaces or [])]).ids
        vals_list = []
        for code in teeth:
            tooth = Tooth.search([('code', '=', code)], limit=1)
            if not tooth:
                raise ValidationError(_('Không tìm thấy răng %s.', code))
            duplicates = self.search([
                ('patient_id', '=', patient_id), ('tooth_id', '=', tooth.id),
                ('condition_id', '=', condition_id), ('layer', '=', layer),
            ]).filtered(lambda e: set(e.surface_ids.ids) == set(surface_ids))
            if duplicates:
                continue
            vals_list.append({
                'patient_id': patient_id,
                'tooth_id': tooth.id,
                'surface_ids': [(6, 0, surface_ids)],
                'condition_id': condition_id,
                'layer': layer,
                'visit_id': visit_id or False,
                'note': note or False,
                'practitioner_id': practitioner.id,
            })
        return self.with_context(dmag_workflow=True).create(vals_list).ids

    def write(self, vals):
        if not is_workflow(self.env) and not is_director(self.env):
            raise AccessError(_('Ghi nhận sơ đồ răng không sửa được. Hãy tạo ghi nhận mới hoặc đánh dấu "Đã xử lý".'))
        return super().write(vals)

    def unlink(self):
        check_director(self.env, _('Chỉ Giám đốc / Quản lý cấp cao được xóa ghi nhận sơ đồ răng.'))
        return super().unlink()

    def action_resolve(self):
        self.with_context(dmag_workflow=True).write({'active': False})
        return True
