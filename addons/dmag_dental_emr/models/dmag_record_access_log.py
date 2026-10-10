from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

ACCESS_ACTIONS = [
    ('workspace', 'Mở bệnh án trên màn hình bác sĩ'),
    ('view', 'Xem bệnh án'),
    ('print', 'In / xuất bệnh án'),
    ('provide', 'Cung cấp bản sao / tóm tắt cho người yêu cầu'),
]


def _client_ip():
    try:
        from odoo.http import request
        return request.httprequest.remote_addr if request else False
    except (ImportError, RuntimeError, AttributeError):
        return False


class DmagRecordAccessLog(models.Model):
    """Nhật ký truy cập hồ sơ bệnh án (Luật KCB 2023 Điều 10 khoản 2, Điều 69 khoản 2, 5: giữ bí mật).

    Chỉ hệ thống ghi (sudo). Không ai sửa / xóa được; Giám đốc được xem.
    """
    _name = 'dmag.record.access.log'
    _description = 'Nhật ký truy cập hồ sơ bệnh án'
    _order = 'access_time desc, id desc'
    _rec_name = 'access_time'

    access_time = fields.Datetime('Thời điểm', required=True, default=fields.Datetime.now, readonly=True, index=True)
    user_id = fields.Many2one('res.users', string='Người truy cập', required=True, readonly=True, index=True,
                              ondelete='restrict')
    action = fields.Selection(ACCESS_ACTIONS, string='Hành động', required=True, readonly=True)
    patient_id = fields.Many2one('res.partner', string='Người bệnh', readonly=True, index=True, ondelete='restrict')
    visit_id = fields.Many2one('dmag.dental.visit', string='Lượt khám', readonly=True, index=True,
                               ondelete='set null')
    res_model = fields.Char('Đối tượng', readonly=True)
    res_id = fields.Integer('Mã bản ghi', readonly=True)
    document = fields.Char('Tài liệu', readonly=True)
    ip_address = fields.Char('Địa chỉ IP', readonly=True)
    company_id = fields.Many2one('res.company', string='Phòng khám', readonly=True, index=True,
                                 default=lambda self: self.env.company)

    @api.model
    def _log(self, records, action, document=False, dedupe_minutes=0):
        """Ghi nhật ký cho các bản ghi bệnh án (lượt khám, phiếu đồng ý, yêu cầu…)."""
        Log = self.sudo()
        user = self.env.user
        vals_list = []
        for rec in records:
            visit = rec if rec._name == 'dmag.dental.visit' else rec['visit_id'] if 'visit_id' in rec._fields else False
            patient = rec['patient_id'] if 'patient_id' in rec._fields else False
            if dedupe_minutes and Log.search_count([
                    ('user_id', '=', user.id), ('action', '=', action),
                    ('res_model', '=', rec._name), ('res_id', '=', rec.id),
                    ('access_time', '>=', fields.Datetime.now() - timedelta(minutes=dedupe_minutes))], limit=1):
                continue
            vals_list.append({
                'user_id': user.id,
                'action': action,
                'patient_id': patient.id if patient else False,
                'visit_id': visit.id if visit else False,
                'res_model': rec._name,
                'res_id': rec.id,
                'document': document or False,
                'ip_address': _client_ip(),
                'company_id': rec['company_id'].id if 'company_id' in rec._fields and rec['company_id'] else self.env.company.id,
            })
        return Log.create(vals_list) if vals_list else Log

    def write(self, vals):
        raise UserError(_('Nhật ký truy cập hồ sơ bệnh án không được sửa.'))

    def unlink(self):
        raise UserError(_('Nhật ký truy cập hồ sơ bệnh án không được xóa.'))
