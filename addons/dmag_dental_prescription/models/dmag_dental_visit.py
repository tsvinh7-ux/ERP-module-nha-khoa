from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .dmag_drug import ROUTES, TIMINGS
from .dmag_prescription import MAX_DAYS, MAX_DAYS_CHRONIC, RX_TYPES

RX_HEADER_FIELDS = ('rx_type', 'diagnosis_text', 'advice', 're_exam_date', 'weight', 'companion_name',
                    'identity_exemption_reason')
RX_LINE_FIELDS = ('drug_id', 'quantity', 'dose_per_time', 'times_per_day', 'days', 'route', 'timing',
                  'usage_note', 'usage', 'is_chronic', 'sequence', 'unit')


class DmagDentalVisit(models.Model):
    _inherit = 'dmag.dental.visit'

    prescription_ids = fields.One2many('dmag.prescription', 'visit_id', string='Đơn thuốc')
    prescription_count = fields.Integer('Số đơn thuốc', compute='_compute_prescription_count')

    @api.depends('prescription_ids')
    def _compute_prescription_count(self):
        for visit in self:
            visit.prescription_count = len(visit.prescription_ids)

    def action_open_prescriptions(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('dmag_dental_prescription.action_dmag_prescription')
        action['domain'] = [('visit_id', '=', self.id)]
        action['context'] = {'default_visit_id': self.id, 'default_patient_id': self.patient_id.id,
                             'default_company_id': self.company_id.id}
        return action

    # ------------------------------------------------------------------ workspace API
    def get_visit_workspace(self):
        res = super().get_visit_workspace()
        res['prescriptions'] = [rx._workspace_dict() for rx in self.prescription_ids.sorted('id')]
        return res

    @api.model
    def get_rx_catalog(self):
        """Danh mục cho màn hình kê đơn: thuốc (trừ thực phẩm chức năng), đơn mẫu, lựa chọn."""
        company = self.env.company
        company_domain = ['|', ('company_id', '=', False), ('company_id', 'in', self.env.companies.ids)]
        drugs = self.env['dmag.drug'].search(company_domain + [('is_supplement', '=', False)])
        templates = self.env['dmag.prescription.template'].search(company_domain)
        return {
            'drugs': [d._catalog_dict() for d in drugs],
            'templates': [t._catalog_dict() for t in templates],
            'routes': [list(r) for r in ROUTES],
            'timings': [list(t) for t in TIMINGS],
            'rx_types': [list(t) for t in RX_TYPES],
            'max_days': MAX_DAYS,
            'max_days_chronic': MAX_DAYS_CHRONIC if company.dmag_rx_allow_90_days else MAX_DAYS,
            'allow_controlled': company.dmag_rx_allow_controlled,
        }

    def save_prescription_from_workspace(self, vals):
        """Tạo / cập nhật đơn NHÁP của lượt khám. ``lines`` (nếu có) thay toàn bộ dòng thuốc."""
        self.ensure_one()
        vals = dict(vals or {})
        Prescription = self.env['dmag.prescription']
        rx = Prescription.browse(vals.get('id')) if vals.get('id') else Prescription
        if rx and (rx.visit_id != self or not rx.exists()):
            raise UserError(_('Đơn thuốc không thuộc lượt khám này.'))
        if rx and rx.state != 'draft':
            raise UserError(_('Đơn thuốc đã phát hành – không sửa được. Dùng "Kê đơn thay thế".'))
        header = {k: vals[k] for k in RX_HEADER_FIELDS if k in vals}
        if 're_exam_date' in header:
            header['re_exam_date'] = header['re_exam_date'] or False
        if 'diagnosis_ids' in vals:
            header['diagnosis_ids'] = [(6, 0, vals['diagnosis_ids'] or [])]
        if not rx:
            create_vals = {'visit_id': self.id}
            if 'diagnosis_ids' in header:
                create_vals['diagnosis_ids'] = header.pop('diagnosis_ids')
            rx = Prescription.create(create_vals)
        if vals.get('template_id'):
            rx._apply_template(self.env['dmag.prescription.template'].browse(vals['template_id']))
        if 're_exam_days' in vals and vals['re_exam_days'] and 're_exam_date' not in vals:
            header['re_exam_date'] = fields.Date.context_today(self) + relativedelta(days=int(vals['re_exam_days']))
        if 'lines' in vals:
            commands = [(5, 0, 0)]
            for seq, line in enumerate(vals['lines'] or [], start=1):
                line_vals = {k: line[k] for k in RX_LINE_FIELDS if k in line and line[k] not in (None, '')}
                line_vals.setdefault('sequence', seq * 10)
                commands.append((0, 0, line_vals))
            header['line_ids'] = commands
        if header:
            rx.write(header)
        return rx._workspace_dict()

    def issue_prescription(self, prescription_id):
        """Phát hành đơn (kiểm tra TT 26, cấp mã, gửi liên thông).

        Trả về {'id', 'code', 'state', 'state_label', 'send_status', 'send_error', 'patient_message'}
        với send_status ∈ 'sent' | 'error' | 'queued'.
        """
        self.ensure_one()
        rx = self.env['dmag.prescription'].browse(prescription_id).exists()
        if not rx or rx.visit_id != self:
            raise UserError(_('Đơn thuốc không thuộc lượt khám này.'))
        rx.action_issue()
        status = {'sent': 'sent', 'send_error': 'error'}.get(rx.state, 'queued')
        return {
            'id': rx.id, 'code': rx.name, 'state': rx.state,
            'state_label': dict(rx._fields['state'].selection).get(rx.state),
            'send_status': status, 'send_error': rx.send_error or '',
            'patient_message': rx.get_patient_message(),
        }
