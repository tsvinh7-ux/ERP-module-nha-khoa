import json

from odoo import _, api, models
from odoo.exceptions import AccessError

from odoo.addons.dmag_dental_base.models.dmag_access import is_director, is_manager

from ..generator.generator import MODULE, PARAM_INFO, PARAM_MODE, XMLID_PREFIX
from ..generator.purge import purge_demo, regenerate_demo


class DmagDemo(models.AbstractModel):
    """Dịch vụ quản lý dữ liệu demo (dùng cho biểu tượng "CHẾ ĐỘ DEMO" và màn hình cấu hình)."""
    _name = 'dmag.demo'
    _description = 'DMAG – Quản lý dữ liệu demo'

    @api.model
    def is_demo_mode(self):
        return self.env['ir.config_parameter'].sudo().get_param(PARAM_MODE) == '1'

    @api.model
    def get_demo_status(self):
        """Trạng thái demo cho mọi người dùng nội bộ (biểu tượng cảnh báo trên thanh trên cùng)."""
        info = {}
        if self.is_demo_mode():
            try:
                info = json.loads(self.env['ir.config_parameter'].sudo().get_param(PARAM_INFO) or '{}')
            except ValueError:
                info = {}
        return {
            'active': self.is_demo_mode(),
            'can_manage': is_manager(self.env),
            'generated_at': info.get('generated_at') or False,
            'title': _('CHẾ ĐỘ DEMO – dữ liệu mẫu, tích hợp giả lập (không gửi Zalo / đơn thuốc / ký số thật)'),
        }

    @api.model
    def get_demo_counts(self):
        Data = self.env['ir.model.data'].sudo()
        groups = Data._read_group([('module', '=', MODULE), ('name', '=like', XMLID_PREFIX + '%')],
                                  ['model'], ['__count'])
        return {model: count for model, count in groups}

    @api.model
    def action_regenerate(self):
        if not is_manager(self.env):
            raise AccessError(_('Chỉ Quản lý phòng khám / Giám đốc được tạo lại dữ liệu demo.'))
        regenerate_demo(self.env)
        return self._reload_action(_('Đã tạo lại dữ liệu demo.'))

    @api.model
    def action_purge(self):
        if not is_director(self.env):
            raise AccessError(_('Chỉ Giám đốc / Quản lý cấp cao được xóa dữ liệu demo.'))
        purge_demo(self.env)
        return self._reload_action(_('Đã xóa dữ liệu demo. Gỡ module "DMAG – Dữ liệu demo" để ẩn hẳn menu.'))

    @api.model
    def _reload_action(self, message):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Dữ liệu demo'),
                'message': message,
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            },
        }
