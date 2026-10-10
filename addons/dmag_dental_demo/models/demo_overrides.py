from odoo import models


class DmagDentalVisit(models.Model):
    """Điểm móc chỉ có hiệu lực trong ngữ cảnh sinh / xóa dữ liệu demo – không đổi nghiệp vụ thật."""
    _inherit = 'dmag.dental.visit'

    def _compute_retention_until(self):
        super()._compute_retention_until()
        if self.env.context.get('dmag_demo_purge') and self.env.su:
            # Xóa dữ liệu DEMO (không phải hồ sơ bệnh án thật): bỏ qua thời hạn lưu trữ
            demo_ids = set(self.env['ir.model.data'].sudo().search([
                ('module', '=', 'dmag_dental_demo'), ('model', '=', self._name),
                ('res_id', 'in', self.ids), ('name', '=like', 'gen_%')]).mapped('res_id'))
            for visit in self:
                if visit.id in demo_ids:
                    visit.retention_until = False

    def _dmag_esign_request(self):
        """Bệnh án demo cũ: chỉ khóa (không dựng PDF + ký số) để cài đặt nhanh; lượt gần đây vẫn ký số giả lập."""
        if self.env.context.get('dmag_demo_skip_esign') and self.env.context.get('dmag_demo_generate'):
            return True
        return super()._dmag_esign_request()
