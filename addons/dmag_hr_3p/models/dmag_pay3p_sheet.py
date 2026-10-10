import base64
import csv
import io

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.dmag_dental_base.models.dmag_access import is_director, is_manager, is_workflow

# Cột xuất cho Payroll Bizapps. Các mã DMAG_* đồng thời là mã "Loại đầu vào" (hr.payslip.input.type.code)
# để quy tắc lương đọc: inputs.DMAG_P1.amount, inputs.DMAG_P2.amount, inputs.DMAG_P3.amount …
EXPORT_COLUMNS = [
    ('PERIOD', 'Kỳ lương (YYYY-MM)', lambda l: l.sheet_id.date_from.strftime('%Y-%m')),
    ('COMPANY', 'Phòng khám', lambda l: l.sheet_id.company_id.name),
    ('EMP_CODE', 'Mã nhân viên', lambda l: l.employee_code),
    ('EMP_NAME', 'Họ tên', lambda l: l.employee_id.name),
    ('JOB', 'Chức danh', lambda l: l.job_id.name or ''),
    ('TRACK', 'Ngạch (P/M)', lambda l: l.track or ''),
    ('GRADE', 'Bậc', lambda l: l.grade_id.code or ''),
    ('DMAG_P1', 'P1 – Lương vị trí', lambda l: l.p1_amount),
    ('DMAG_P2_COEF', 'Hệ số năng lực P2', lambda l: l.p2_coefficient),
    ('DMAG_P2', 'P2 – Lương năng lực', lambda l: l.p2_amount),
    ('DMAG_P3_KPI_SCORE', 'Điểm KPI (%)', lambda l: l.kpi_score),
    ('DMAG_P3_KPI', 'P3 – Thưởng KPI', lambda l: l.p3_kpi_amount),
    ('DMAG_P3_COMM', 'P3 – Hoa hồng / thủ thuật phí', lambda l: l.commission_amount),
    ('DMAG_P3_OKR', 'P3 – Thưởng OKR', lambda l: l.okr_bonus),
    ('DMAG_P3_ADJ', 'P3 – Điều chỉnh', lambda l: l.adjustment),
    ('DMAG_P3', 'P3 – Lương kết quả', lambda l: l.p3_amount),
    ('DMAG_3P_TOTAL', 'Tổng thu nhập 3P', lambda l: l.total),
]
LOCKED_STATES = ('approved', 'exported')


def _check_unlocked(env, sheets):
    if is_workflow(env) or is_director(env):
        return
    if any(s.state in LOCKED_STATES for s in sheets):
        raise AccessError(_('Bảng lương 3P đã được Giám đốc duyệt – chỉ Giám đốc / Quản lý cấp cao được sửa.'))


class DmagPay3pSheet(models.Model):
    """Bảng đầu vào lương 3P theo tháng – nguồn cho Payroll Bizapps (không tính thuế / bảo hiểm ở đây)."""
    _name = 'dmag.pay3p.sheet'
    _description = 'Bảng lương 3P (đầu vào Payroll)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_from desc, id desc'

    name = fields.Char('Tên bảng', compute='_compute_name', store=True)
    date_from = fields.Date('Tháng', required=True, tracking=True,
                            default=lambda self: fields.Date.context_today(self).replace(day=1))
    date_to = fields.Date('Đến ngày', compute='_compute_date_to', store=True)
    company_id = fields.Many2one('res.company', string='Phòng khám', required=True, index=True,
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    state = fields.Selection([
        ('draft', 'Nháp'),
        ('reviewed', 'Quản lý đã soát'),
        ('approved', 'Giám đốc đã duyệt'),
        ('exported', 'Đã xuất cho Payroll'),
    ], string='Trạng thái', default='draft', required=True, tracking=True, copy=False)
    line_ids = fields.One2many('dmag.pay3p.line', 'sheet_id', string='Nhân viên', copy=False)
    kpi_result_ids = fields.One2many('dmag.kpi.result', 'sheet_id', string='Kết quả KPI')
    total_p1 = fields.Monetary('Tổng P1', compute='_compute_totals', store=True)
    total_p2 = fields.Monetary('Tổng P2', compute='_compute_totals', store=True)
    total_p3 = fields.Monetary('Tổng P3', compute='_compute_totals', store=True)
    total = fields.Monetary('Tổng 3P', compute='_compute_totals', store=True)
    reviewed_by_id = fields.Many2one('res.users', string='Quản lý soát', readonly=True, copy=False)
    approved_by_id = fields.Many2one('res.users', string='Giám đốc duyệt', readonly=True, copy=False)
    approved_date = fields.Datetime('Thời điểm duyệt', readonly=True, copy=False)
    exported_date = fields.Datetime('Thời điểm xuất', readonly=True, copy=False)
    note = fields.Text('Ghi chú')

    _sql_constraints = [('period_company_uniq', 'unique(date_from, company_id)',
                         'Mỗi phòng khám chỉ có một bảng lương 3P cho mỗi tháng.')]

    @api.depends('date_from')
    def _compute_date_to(self):
        for sheet in self:
            sheet.date_to = sheet.date_from and sheet.date_from + relativedelta(day=31)

    @api.depends('date_from', 'company_id')
    def _compute_name(self):
        for sheet in self:
            sheet.name = _('Lương 3P %(month)s – %(company)s',
                           month=sheet.date_from.strftime('%m/%Y') if sheet.date_from else '',
                           company=sheet.company_id.name or '')

    @api.depends('line_ids.p1_amount', 'line_ids.p2_amount', 'line_ids.p3_amount', 'line_ids.total')
    def _compute_totals(self):
        for sheet in self:
            sheet.total_p1 = sum(sheet.line_ids.mapped('p1_amount'))
            sheet.total_p2 = sum(sheet.line_ids.mapped('p2_amount'))
            sheet.total_p3 = sum(sheet.line_ids.mapped('p3_amount'))
            sheet.total = sum(sheet.line_ids.mapped('total'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('date_from'):
                vals['date_from'] = fields.Date.to_date(vals['date_from']).replace(day=1)
        return super().create(vals_list)

    def write(self, vals):
        _check_unlocked(self.env, self)
        if 'date_from' in vals and vals['date_from']:
            vals['date_from'] = fields.Date.to_date(vals['date_from']).replace(day=1)
        return super().write(vals)

    def unlink(self):
        if any(s.state != 'draft' for s in self) and not is_director(self.env):
            raise AccessError(_('Chỉ xóa được bảng lương 3P ở trạng thái nháp.'))
        return super().unlink()

    def _workflow_write(self, vals):
        return self.with_context(dmag_workflow=True).write(vals)

    # ------------------------------------------------------------------ computation
    def action_generate_lines(self):
        """Thêm mọi nhân viên đã gán ngạch/bậc của phòng khám vào bảng, rồi tính số liệu."""
        for sheet in self:
            if sheet.state != 'draft':
                raise UserError(_('Chỉ tạo dòng khi bảng đang ở trạng thái nháp.'))
            employees = self.env['hr.employee'].sudo().search([
                ('company_id', '=', sheet.company_id.id), ('dmag_grade_id', '!=', False)])
            missing = employees - sheet.line_ids.mapped('employee_id')
            self.env['dmag.pay3p.line'].with_context(dmag_workflow=True).create(
                [{'sheet_id': sheet.id, 'employee_id': emp.id} for emp in missing])
        return self.action_compute()

    def action_compute(self):
        for sheet in self:
            if sheet.state not in ('draft', 'reviewed'):
                raise UserError(_('Bảng đã duyệt – không tính lại được.'))
            sheet.line_ids._dmag_recompute()
        return True

    # ------------------------------------------------------------------ approval flow
    def action_review(self):
        if not is_manager(self.env):
            raise AccessError(_('Chỉ Quản lý phòng khám được soát bảng lương 3P.'))
        for sheet in self:
            if sheet.state != 'draft':
                raise UserError(_('Bảng %s không ở trạng thái nháp.', sheet.name))
            if not sheet.line_ids:
                raise UserError(_('Bảng %s chưa có nhân viên.', sheet.name))
        self._workflow_write({'state': 'reviewed', 'reviewed_by_id': self.env.uid})
        return True

    def action_approve(self):
        if not is_director(self.env):
            raise AccessError(_('Chỉ Giám đốc / Quản lý cấp cao được duyệt bảng lương 3P.'))
        for sheet in self:
            if sheet.state != 'reviewed':
                raise UserError(_('Bảng %s cần Quản lý soát trước khi Giám đốc duyệt.', sheet.name))
        self._workflow_write({'state': 'approved', 'approved_by_id': self.env.uid,
                              'approved_date': fields.Datetime.now()})
        return True

    def action_reset_draft(self):
        if not is_director(self.env):
            raise AccessError(_('Chỉ Giám đốc / Quản lý cấp cao được mở lại bảng lương 3P.'))
        self._workflow_write({'state': 'draft', 'approved_by_id': False, 'approved_date': False,
                              'reviewed_by_id': False})
        for sheet in self:
            sheet.message_post(body=_('Mở lại bảng lương 3P bởi %s.', self.env.user.name))
        return True

    # ------------------------------------------------------------------ export
    def _get_export_rows(self):
        self.ensure_one()
        header = [code for code, _label, _getter in EXPORT_COLUMNS]
        rows = []
        for line in self.line_ids.sorted(lambda l: (l.employee_code or '', l.id)):
            rows.append([getter(line) for _code, _label, getter in EXPORT_COLUMNS])
        return header, rows

    def _check_exportable(self):
        for sheet in self:
            if sheet.state not in LOCKED_STATES:
                raise UserError(_('Chỉ xuất được bảng lương 3P đã được Giám đốc duyệt.'))

    def _export_file(self, fmt):
        self.ensure_one()
        self._check_exportable()
        header, rows = self._get_export_rows()
        period = self.date_from.strftime('%Y_%m')
        if fmt == 'csv':
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(header)
            writer.writerows(rows)
            content = ('﻿' + buffer.getvalue()).encode('utf-8')
            mimetype, ext = 'text/csv', 'csv'
        else:
            import xlsxwriter
            output = io.BytesIO()
            workbook = xlsxwriter.Workbook(output, {'in_memory': True})
            sheet = workbook.add_worksheet('3P')
            bold = workbook.add_format({'bold': True})
            money = workbook.add_format({'num_format': '#,##0'})
            for col, code in enumerate(header):
                sheet.write(0, col, code, bold)
                sheet.write(1, col, EXPORT_COLUMNS[col][1])
            for row_idx, row in enumerate(rows, start=2):
                for col, value in enumerate(row):
                    sheet.write(row_idx, col, value, money if isinstance(value, float) else None)
            workbook.close()
            content = output.getvalue()
            mimetype, ext = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'xlsx'
        attachment = self.env['ir.attachment'].create({
            'name': f'luong_3p_{self.company_id.id}_{period}.{ext}',
            'datas': base64.b64encode(content),
            'mimetype': mimetype,
            'res_model': self._name,
            'res_id': self.id,
        })
        self._workflow_write({'state': 'exported', 'exported_date': fields.Datetime.now()})
        self.message_post(body=_('Xuất bảng lương 3P (%s) cho Payroll Bizapps.', ext.upper()),
                          attachment_ids=attachment.ids)
        return attachment

    def action_export_csv(self):
        attachment = self._export_file('csv')
        return {'type': 'ir.actions.act_url', 'url': f'/web/content/{attachment.id}?download=true',
                'target': 'self'}

    def action_export_xlsx(self):
        attachment = self._export_file('xlsx')
        return {'type': 'ir.actions.act_url', 'url': f'/web/content/{attachment.id}?download=true',
                'target': 'self'}


class DmagPay3pLine(models.Model):
    _name = 'dmag.pay3p.line'
    _description = 'Dòng lương 3P'
    _order = 'sheet_id, employee_id'

    sheet_id = fields.Many2one('dmag.pay3p.sheet', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='sheet_id.company_id', store=True)
    currency_id = fields.Many2one(related='sheet_id.currency_id')
    state = fields.Selection(related='sheet_id.state')
    employee_id = fields.Many2one('hr.employee', string='Nhân viên', required=True, index=True)
    employee_code = fields.Char('Mã NV', compute='_compute_employee_info', store=True)
    job_id = fields.Many2one('hr.job', string='Chức danh', compute='_compute_employee_info', store=True)
    profile_id = fields.Many2one('dmag.job.position.profile', string='Vị trí', readonly=True)
    track = fields.Selection([('P', 'P'), ('M', 'M')], string='Ngạch', readonly=True)
    grade_id = fields.Many2one('dmag.job.grade', string='Bậc', readonly=True)

    p1_amount = fields.Monetary('P1')
    p2_base = fields.Monetary('Mức P2 chuẩn')
    p2_coefficient = fields.Float('Hệ số P2', digits=(16, 2), default=1.0)
    p2_amount = fields.Monetary('P2', compute='_compute_amounts', store=True)
    kpi_score = fields.Float('Điểm KPI (%)', digits=(16, 1))
    p3_base = fields.Monetary('Mức P3 chuẩn')
    p3_kpi_amount = fields.Monetary('P3 KPI', compute='_compute_amounts', store=True)
    commission_amount = fields.Monetary('Hoa hồng / thủ thuật phí')
    okr_score = fields.Float('Điểm OKR (%)', digits=(16, 1))
    okr_bonus_base = fields.Monetary('Thưởng OKR tối đa')
    okr_bonus = fields.Monetary('Thưởng OKR', compute='_compute_amounts', store=True)
    adjustment = fields.Monetary('Điều chỉnh P3', help='Âm khi khấu trừ do vi phạm cầu chì y đức.')
    adjustment_note = fields.Char('Lý do điều chỉnh')
    p3_amount = fields.Monetary('P3', compute='_compute_amounts', store=True)
    total = fields.Monetary('Tổng 3P', compute='_compute_amounts', store=True)

    _sql_constraints = [('sheet_employee_uniq', 'unique(sheet_id, employee_id)',
                         'Mỗi nhân viên chỉ có một dòng trong bảng lương 3P.')]

    @api.depends('employee_id')
    def _compute_employee_info(self):
        for line in self:
            emp = line.employee_id.sudo()
            reg = emp['registration_number'] if 'registration_number' in emp._fields else False
            line.employee_code = reg or emp.barcode or ('NV%05d' % emp.id if emp.id else '')
            line.job_id = emp.job_id

    @api.depends('p2_base', 'p2_coefficient', 'kpi_score', 'p3_base', 'commission_amount', 'okr_score',
                 'okr_bonus_base', 'adjustment', 'p1_amount', 'sheet_id.company_id.dmag_okr_success')
    def _compute_amounts(self):
        for line in self:
            currency = line.currency_id or self.env.company.currency_id
            success = line.sheet_id.company_id.dmag_okr_success or 70.0
            line.p2_amount = currency.round(line.p2_base * line.p2_coefficient)
            line.p3_kpi_amount = currency.round(line.p3_base * line.kpi_score / 100.0)
            line.okr_bonus = currency.round(line.okr_bonus_base * min(line.okr_score / success, 1.0)) \
                if line.okr_score > 0 else 0.0
            line.p3_amount = line.p3_kpi_amount + line.commission_amount + line.okr_bonus + line.adjustment
            line.total = line.p1_amount + line.p2_amount + line.p3_amount

    @api.model_create_multi
    def create(self, vals_list):
        sheets = self.env['dmag.pay3p.sheet'].browse([v.get('sheet_id') for v in vals_list])
        _check_unlocked(self.env, sheets)
        return super().create(vals_list)

    def write(self, vals):
        _check_unlocked(self.env, self.mapped('sheet_id'))
        return super().write(vals)

    def unlink(self):
        _check_unlocked(self.env, self.mapped('sheet_id'))
        return super().unlink()

    def _dmag_recompute(self):
        KpiResult = self.env['dmag.kpi.result'].sudo()
        KpiDef = self.env['dmag.kpi.definition']
        for line in self:
            sheet = line.sheet_id
            emp = line.employee_id.sudo()
            profile = emp.dmag_profile_id
            date_from, date_to = sheet.date_from, sheet.date_to
            # KPI: tạo kết quả kỳ cho từng chỉ tiêu, tự tính phần có nguồn dữ liệu
            results = KpiResult.search([('employee_id', '=', emp.id), ('date_from', '=', date_from)])
            for kpi in profile.kpi_ids:
                if kpi not in results.mapped('kpi_id'):
                    results |= KpiResult.create({
                        'employee_id': emp.id, 'kpi_id': kpi.id, 'date_from': date_from, 'date_to': date_to,
                        'weight': kpi.weight, 'target': kpi.target, 'sheet_id': sheet.id})
            results.filtered(lambda r: not r.sheet_id).with_context(dmag_workflow=True).write({'sheet_id': sheet.id})
            results.action_refresh()
            total_weight = sum(results.mapped('weight'))
            kpi_score = sum(r.achievement * r.weight for r in results) / total_weight if total_weight else 0.0
            commission = KpiDef._dmag_kpi_value_commission(emp, date_from, date_to) or 0.0
            okr = KpiDef._dmag_kpi_value_okr_score(emp, date_from, date_to) or 0.0
            line.with_context(dmag_workflow=True).write({
                'profile_id': profile.id,
                'track': emp.dmag_track,
                'grade_id': emp.dmag_grade_id.id,
                'p1_amount': emp.dmag_p1_amount,
                'p2_base': profile.p2_base,
                'p2_coefficient': emp._dmag_get_p2_coefficient(date_to),
                'kpi_score': kpi_score,
                'p3_base': profile.p3_base,
                'commission_amount': commission,
                'okr_score': okr,
                'okr_bonus_base': profile.okr_bonus_base,
            })
        return True

    def action_open_kpi(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('KPI – %s', self.employee_id.name),
            'res_model': 'dmag.kpi.result',
            'view_mode': 'tree,form',
            'domain': [('employee_id', '=', self.employee_id.id), ('date_from', '=', self.sheet_id.date_from)],
            'context': {'default_employee_id': self.employee_id.id,
                        'default_date_from': self.sheet_id.date_from,
                        'default_date_to': self.sheet_id.date_to,
                        'default_sheet_id': self.sheet_id.id},
        }
