import re
from datetime import datetime, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

PHONE_RE = re.compile(r'^(?:\+?84|0)(?:3|5|7|8|9)\d{8}$')
MAX_PER_PHONE_DAY = 3
MAX_PER_IP_HOUR = 10
MAX_DAYS_AHEAD = 90


def normalize_phone(phone):
    digits = re.sub(r'[^\d+]', '', phone or '')
    if digits.startswith('+84'):
        digits = '0' + digits[3:]
    elif digits.startswith('84') and len(digits) == 11:
        digits = '0' + digits[2:]
    return digits


class DmagPortalBookingLog(models.Model):
    """Nhật ký đặt lịch trực tuyến – phục vụ chống spam (giới hạn theo IP / số điện thoại)."""
    _name = 'dmag.portal.booking.log'
    _description = 'Nhật ký đặt lịch trực tuyến'
    _order = 'id desc'

    ip = fields.Char('Địa chỉ IP', index=True)
    phone = fields.Char('Số điện thoại', index=True)
    company_id = fields.Many2one('res.company', string='Chi nhánh')
    visit_id = fields.Many2one('dmag.dental.visit', string='Lịch hẹn tạo ra', ondelete='set null')
    channel = fields.Selection([('web', 'Trang đặt lịch'), ('api', 'Ứng dụng / API')], default='web')

    @api.model
    def _check_rate_limit(self, ip, phone):
        now = fields.Datetime.now()
        Log = self.sudo()
        if phone and Log.search_count([('phone', '=', phone), ('create_date', '>=', now - timedelta(days=1))]) \
                >= MAX_PER_PHONE_DAY:
            raise UserError(_('Số điện thoại này đã gửi nhiều yêu cầu đặt lịch trong 24 giờ. '
                              'Phòng khám sẽ liên hệ lại, hoặc vui lòng gọi hotline.'))
        if ip and Log.search_count([('ip', '=', ip), ('create_date', '>=', now - timedelta(hours=1))]) \
                >= MAX_PER_IP_HOUR:
            raise UserError(_('Bạn đã gửi quá nhiều yêu cầu. Vui lòng thử lại sau ít phút.'))

    @api.model
    def _booking_services(self):
        return self.env['product.product'].sudo().search([
            ('is_dental_service', '=', True), ('sale_ok', '=', True)], order='name')

    @api.model
    def _booking_branches(self):
        return self.env['res.company'].sudo().search([])

    @api.model
    def _dmag_create_booking(self, values, ip=None, channel='web', partner=None):
        """Tạo lịch hẹn nháp từ yêu cầu đặt lịch trực tuyến.

        values: name, phone, date (YYYY-MM-DD), time (HH:MM), service_id, company_id, note, consent.
        Bắt buộc đồng ý xử lý dữ liệu cá nhân (Nghị định 13/2023/NĐ-CP).
        Trả về lượt khám (sudo).
        """
        name = (values.get('name') or '').strip()
        phone = normalize_phone(values.get('phone'))
        if not values.get('consent'):
            raise ValidationError(_('Vui lòng đồng ý với việc xử lý dữ liệu cá nhân (Nghị định 13/2023/NĐ-CP) '
                                    'để phòng khám liên hệ xác nhận lịch.'))
        if not name or len(name) > 120:
            raise ValidationError(_('Vui lòng nhập họ tên.'))
        if not PHONE_RE.match(phone):
            raise ValidationError(_('Số điện thoại không hợp lệ.'))
        Company = self.env['res.company'].sudo()
        company = Company.browse(int(values.get('company_id') or 0)).exists() if values.get('company_id') \
            else Company.search([], limit=1)
        if not company:
            raise ValidationError(_('Vui lòng chọn chi nhánh.'))
        try:
            local = datetime.strptime('%s %s' % (values.get('date'), values.get('time') or '09:00'), '%Y-%m-%d %H:%M')
        except (TypeError, ValueError):
            raise ValidationError(_('Ngày giờ mong muốn không hợp lệ.'))
        tz = pytz.timezone(company.partner_id.tz or 'Asia/Ho_Chi_Minh')
        start = tz.localize(local).astimezone(pytz.utc).replace(tzinfo=None)
        now = fields.Datetime.now()
        if start < now:
            raise ValidationError(_('Vui lòng chọn thời điểm trong tương lai.'))
        if start > now + timedelta(days=MAX_DAYS_AHEAD):
            raise ValidationError(_('Chỉ nhận đặt lịch trong vòng %s ngày tới.', MAX_DAYS_AHEAD))
        service = self.env['product.product'].sudo().browse(int(values.get('service_id') or 0)).exists()
        if service and not service.is_dental_service:
            service = service.browse()
        self._check_rate_limit(ip, phone)

        Partner = self.env['res.partner'].sudo()
        patient = partner.sudo() if partner else Partner.browse()
        if not patient:
            patient = Partner.search([
                ('is_patient', '=', True), ('company_id', 'in', (False, company.id)),
                '|', ('mobile', '=', phone), ('phone', '=', phone)], limit=1)
        note_parts = [_('Đặt lịch trực tuyến (%s).', dict(self._fields['channel'].selection)[channel])]
        if patient:
            if patient.name.strip().lower() != name.lower():
                note_parts.append(_('Tên khai báo: %s – lễ tân kiểm tra lại khi xác nhận.', name))
            if not patient.data_consent:
                patient.with_context(dmag_workflow=True).write({'data_consent': True})
        else:
            source = self.env['dmag.customer.source'].sudo().search(
                ['|', ('code', '=ilike', 'web'), ('name', 'ilike', 'web')], limit=1)
            patient = Partner.create({
                'name': name,
                'mobile': phone,
                'is_patient': True,
                'company_id': company.id,
                'data_consent': True,
                'customer_source_id': source.id,
            })
        if values.get('note'):
            note_parts.append(str(values['note'])[:500])
        source = self.env['dmag.customer.source'].sudo().search(
            ['|', ('code', '=ilike', 'web'), ('name', 'ilike', 'web')], limit=1)
        # create() của lượt khám bắn sự kiện hành trình 'booked'
        visit = self.env['dmag.dental.visit'].sudo().with_company(company).create({
            'patient_id': patient.id,
            'company_id': company.id,
            'scheduled_start': start,
            'service_ids': [(6, 0, service.ids)],
            'reason': ' '.join(note_parts)[:250],
            'source_id': source.id,
        })
        visit.message_post(body=' '.join(note_parts))
        self.sudo().create({'ip': ip, 'phone': phone, 'company_id': company.id,
                            'visit_id': visit.id, 'channel': channel})
        return visit
