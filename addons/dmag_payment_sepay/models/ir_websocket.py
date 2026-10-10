from odoo import models

from .dmag_payment_request import BUS_CHANNEL


class IrWebsocket(models.AbstractModel):
    _inherit = 'ir.websocket'

    def _build_bus_channel_list(self, channels):
        """Lễ tân / thu ngân tự đăng ký kênh (res.company, 'dmag_payment') của các phòng khám được phép."""
        channels = super()._build_bus_channel_list(channels)
        user = self.env.user
        if user and not user._is_public() and user.has_group('dmag_dental_base.group_dmag_receptionist'):
            for company in user.company_ids:
                channels.append((company, BUS_CHANNEL))
        return channels
