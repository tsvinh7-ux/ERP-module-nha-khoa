import math

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .dmag_drug import ROUTE_VERBS, ROUTES, TIMINGS


def format_dose(value):
    """1.0 → '1'; 0.5 → '1/2'; 1.5 → '1,5' (không viết tắt, dấu phẩy thập phân)."""
    value = value or 0.0
    if abs(value - round(value)) < 1e-6:
        return str(int(round(value)))
    if abs(value - 0.5) < 1e-6:
        return '1/2'
    if abs(value - 0.25) < 1e-6:
        return '1/4'
    return ('%g' % value).replace('.', ',')


def format_quantity(value):
    """Số lượng < 10 ghi thêm số 0 phía trước (TT 26/2025): 8 → '08'."""
    value = value or 0.0
    if abs(value - round(value)) < 1e-6:
        number = int(round(value))
        return f'{number:02d}' if 0 <= number < 10 else str(number)
    text = ('%g' % value).replace('.', ',')
    return f'0{text}' if value < 10 else text


class DmagRxLineMixin(models.AbstractModel):
    """Trường chung của dòng thuốc (đơn mẫu và đơn thuốc)."""
    _name = 'dmag.rx.line.mixin'
    _description = 'Dòng thuốc (chung)'

    sequence = fields.Integer(default=10)
    drug_id = fields.Many2one('dmag.drug', string='Thuốc', required=True, ondelete='restrict')
    route = fields.Selection(ROUTES, string='Đường dùng', compute='_compute_route', store=True,
                             readonly=False)
    dose_per_time = fields.Float('Mỗi lần', default=1.0, digits=(6, 2))
    times_per_day = fields.Integer('Lần/ngày', default=2)
    days = fields.Integer('Số ngày', default=5)
    timing = fields.Selection(TIMINGS, string='Thời điểm', compute='_compute_timing', store=True,
                              readonly=False)
    usage_note = fields.Char('Ghi chú cách dùng', help='Bổ sung vào câu hướng dẫn, ví dụ: "uống với nhiều nước".')
    usage = fields.Char('Cách dùng', compute='_compute_usage', store=True, readonly=False,
                        help='Tự soạn từ đường dùng, liều, số lần, thời điểm; bác sĩ có thể sửa trước khi phát hành.')
    quantity = fields.Float('Số lượng', compute='_compute_quantity', store=True, readonly=False, digits=(10, 2))
    unit = fields.Char('Đơn vị tính', compute='_compute_unit', store=True, readonly=False)

    # Một phương thức cho mỗi trường: giá trị truyền vào khi tạo không bị ghi đè lẫn nhau
    @api.depends('drug_id')
    def _compute_route(self):
        for line in self:
            line.route = line.drug_id.route or line.route or 'oral'

    @api.depends('drug_id')
    def _compute_timing(self):
        for line in self:
            line.timing = line.drug_id.default_timing or line.timing or 'none'

    @api.depends('drug_id')
    def _compute_unit(self):
        for line in self:
            line.unit = line.drug_id.unit or line.unit

    @api.onchange('drug_id')
    def _onchange_drug_defaults(self):
        drug = self.drug_id
        if drug:
            self.dose_per_time = drug.default_dose_per_time or 1.0
            self.times_per_day = drug.default_times_per_day or 1
            self.days = drug.default_days or 1

    @api.depends('drug_id', 'route', 'dose_per_time', 'times_per_day', 'timing', 'usage_note')
    def _compute_usage(self):
        for line in self:
            line.usage = line._compose_usage() if line.drug_id else False

    @api.depends('drug_id', 'dose_per_time', 'times_per_day', 'days')
    def _compute_quantity(self):
        for line in self:
            line.quantity = line._suggest_quantity()

    def _compose_usage(self):
        """Câu hướng dẫn tiếng Việt đầy đủ, ví dụ "Uống ngày 2 lần, mỗi lần 1 viên, sau ăn"."""
        self.ensure_one()
        verb = ROUTE_VERBS.get(self.route or 'oral', 'Dùng')
        dose = f'{format_dose(self.dose_per_time)} {self.drug_id._get_dose_unit()}'.strip()
        timing_label = dict(TIMINGS).get(self.timing) if self.timing and self.timing != 'none' else ''
        if self.timing == 'when_pain':
            text = f'{verb} khi đau, mỗi lần {dose}, tối đa {self.times_per_day or 1} lần mỗi ngày'
        else:
            text = f'{verb} ngày {self.times_per_day or 1} lần, mỗi lần {dose}'
            if timing_label:
                text += f', {timing_label}'
        if self.usage_note:
            text += f', {self.usage_note.strip()}'
        return text

    def _suggest_quantity(self):
        self.ensure_one()
        drug = self.drug_id
        if not drug:
            return 0.0
        if drug.dose_unit and drug.dose_unit.strip().lower() != (drug.unit or '').strip().lower():
            return 1.0  # chai / tuýp: 1 đơn vị đóng gói
        if self.timing == 'when_pain':
            return float(math.ceil((self.dose_per_time or 1) * (self.times_per_day or 1) * (self.days or 1)))
        return float(math.ceil((self.dose_per_time or 0) * (self.times_per_day or 0) * (self.days or 0)))

    def _line_values(self):
        """Giá trị để chép sang dòng đơn thuốc."""
        self.ensure_one()
        return {
            'sequence': self.sequence, 'drug_id': self.drug_id.id, 'route': self.route,
            'dose_per_time': self.dose_per_time, 'times_per_day': self.times_per_day,
            'days': self.days, 'timing': self.timing, 'usage_note': self.usage_note,
            'usage': self.usage, 'quantity': self.quantity, 'unit': self.unit,
        }


class DmagPrescriptionTemplate(models.Model):
    _name = 'dmag.prescription.template'
    _description = 'Đơn thuốc mẫu'
    _order = 'sequence, name'

    name = fields.Char('Tên đơn mẫu', required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Phòng khám',
                                 help='Để trống = dùng chung cho mọi phòng khám.')
    diagnosis_ids = fields.Many2many('dmag.dental.diagnosis', string='Chẩn đoán gợi ý (ICD-10)')
    advice = fields.Text('Lời dặn')
    re_exam_days = fields.Integer('Tái khám sau (ngày)')
    line_ids = fields.One2many('dmag.prescription.template.line', 'template_id', string='Thuốc', copy=True)

    def _catalog_dict(self):
        self.ensure_one()
        return {
            'id': self.id, 'name': self.name, 'advice': self.advice or '',
            're_exam_days': self.re_exam_days,
            'diagnoses': [{'id': d.id, 'name': d.display_name} for d in self.diagnosis_ids],
            'lines': [dict(line._line_values(), drug_name=line.drug_id.name) for line in self.line_ids],
        }


class DmagPrescriptionTemplateLine(models.Model):
    _name = 'dmag.prescription.template.line'
    _inherit = 'dmag.rx.line.mixin'
    _description = 'Dòng đơn thuốc mẫu'
    _order = 'sequence, id'

    template_id = fields.Many2one('dmag.prescription.template', required=True, ondelete='cascade')

    @api.constrains('drug_id')
    def _check_supplement(self):
        for line in self:
            if line.drug_id.is_supplement:
                raise ValidationError(_('Không được đưa thực phẩm chức năng (%s) vào đơn thuốc mẫu.',
                                        line.drug_id.name))
