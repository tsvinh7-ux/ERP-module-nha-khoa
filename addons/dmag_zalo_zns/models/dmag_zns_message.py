import json
import logging
import uuid
from datetime import timedelta

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.modules import module as odoo_module

from odoo.addons.dmag_dental_base.models.dmag_access import check_director, is_director

from .res_company import ZNS_SEND_URL
from .zns_utils import quiet_until

_logger = logging.getLogger(__name__)

# Mã lỗi Zalo không nên thử lại (số không hợp lệ, không có Zalo, mẫu sai…) – cần xác nhận bảng mã lỗi chính thức.
NON_RETRYABLE_ERRORS = {-108, -109, -112, -118, -119, -131, -133, -139}
TOKEN_ERRORS = {-124, -216}

STATES = [
    ('queued', 'Chờ gửi'),
    ('sent', 'Đã gửi'),
    ('delivered', 'Đã nhận'),
    ('failed', 'Lỗi'),
    ('skipped', 'Bỏ qua'),
    ('cancel', 'Đã hủy'),
]


class DmagZnsMessage(models.Model):
    """Nhật ký tin ZNS (hàng đợi + kết quả). Chỉ đọc với nhân viên."""
    _name = 'dmag.zns.message'
    _description = 'Tin Zalo ZNS'
    _order = 'id desc'
    _rec_name = 'tracking_id'

    company_id = fields.Many2one('res.company', string='Phòng khám', required=True, index=True,
                                 default=lambda self: self.env.company, readonly=True)
    partner_id = fields.Many2one('res.partner', string='Khách hàng', index=True, readonly=True)
    phone = fields.Char('Số nhận (84…)', readonly=True)
    template_id = fields.Many2one('dmag.zns.template', string='Mẫu ZNS', readonly=True, index=True,
                                  ondelete='restrict')
    template_code = fields.Char(related='template_id.code', string='Mã mẫu')
    zalo_template_id = fields.Char('Template ID Zalo', readonly=True)
    params_json = fields.Text('Tham số (JSON)', readonly=True)
    preview = fields.Text('Nội dung', readonly=True)
    state = fields.Selection(STATES, string='Trạng thái', default='queued', required=True, index=True,
                             readonly=True)
    transactional = fields.Boolean('Tin giao dịch', readonly=True)
    mode = fields.Char('Chế độ gửi', readonly=True)
    tracking_id = fields.Char('Tracking ID', readonly=True, copy=False, index=True,
                              default=lambda self: uuid.uuid4().hex)
    msg_id = fields.Char('Zalo msg_id', readonly=True, copy=False, index=True)
    error = fields.Text('Lỗi', readonly=True)
    error_code = fields.Integer('Mã lỗi Zalo', readonly=True)
    response_raw = fields.Text('Phản hồi Zalo', readonly=True)
    attempt_count = fields.Integer('Số lần gửi', readonly=True)
    next_try = fields.Datetime('Gửi lúc', readonly=True, index=True, default=fields.Datetime.now)
    expire_at = fields.Datetime('Hết hạn lúc', readonly=True,
                                help='Quá thời điểm này mà chưa gửi được thì hủy (ví dụ nhắc lịch sau giờ hẹn).')
    sent_date = fields.Datetime('Gửi thành công lúc', readonly=True)
    delivered_date = fields.Datetime('Khách nhận lúc', readonly=True)
    feedback = fields.Text('Phản hồi của khách', readonly=True)
    res_model = fields.Char('Đối tượng', readonly=True, index=True)
    res_id = fields.Many2oneReference('ID đối tượng', model_field='res_model', readonly=True, index=True)
    origin = fields.Char('Nguồn', readonly=True)

    _sql_constraints = [('tracking_uniq', 'unique(tracking_id)', 'Tracking ID ZNS bị trùng.')]

    # ------------------------------------------------------------------ public API
    @api.model
    def send(self, template, partner, record=None, params_override=None, send_now=False,
             variables=None, expire_at=False, origin=False, company=None):
        """Xếp hàng một tin ZNS.

        :param template: mã nội bộ (``'booking_confirm'``), id hoặc bản ghi ``dmag.zns.template``
        :param partner: ``res.partner`` người nhận
        :param record: bản ghi nguồn (lượt khám…) – biến ``record`` và ``visit`` (nếu là lượt khám)
        :param params_override: dict tham số ghi đè
        :param variables: dict biến bổ sung cho biểu thức tham số (ví dụ ``{'nps': response}``)
        :param send_now: gửi ngay (nếu không trong giờ yên lặng) thay vì chờ cron
        :return: bản ghi ``dmag.zns.message`` (trạng thái queued / skipped / sent / failed)
        """
        partner = partner[:1]
        company = company or (record and 'company_id' in record._fields and record.company_id) or self.env.company
        tmpl = self.env['dmag.zns.template']._dmag_get(template, company)
        if not tmpl:
            raise UserError(_('Không tìm thấy mẫu ZNS "%s".', template))
        vals = {
            'company_id': company.id,
            'partner_id': partner.id,
            'template_id': tmpl.id,
            'zalo_template_id': tmpl.template_id,
            'transactional': tmpl.transactional,
            'mode': company.dmag_zns_mode,
            'expire_at': expire_at,
            'origin': origin or (record and record.display_name) or False,
        }
        if record:
            vals.update(res_model=record._name, res_id=record.id)
        skip_reason = False
        if not partner:
            skip_reason = _('Không có người nhận.')
        elif partner.zns_opt_out:
            skip_reason = _('Khách đã từ chối nhận tin Zalo ZNS.')
        else:
            vals['phone'] = partner._dmag_zns_phone()
            if not vals['phone']:
                skip_reason = _('Khách chưa có số điện thoại di động / Zalo hợp lệ.')
        if not skip_reason:
            env_vars = self._dmag_variables(partner, record, company)
            env_vars.update(variables or {})
            data = tmpl._build_params(env_vars, partner, params_override)
            vals['params_json'] = json.dumps(data, ensure_ascii=False)
            vals['preview'] = tmpl._render_preview(data)
            postpone = False if tmpl.transactional else quiet_until(self.env, company)
            vals['next_try'] = postpone or fields.Datetime.now()
        else:
            vals.update(state='skipped', error=skip_reason)
        message = self.sudo().create(vals)
        if message.state == 'queued':
            if send_now and message.next_try <= fields.Datetime.now():
                message._dmag_process()
            else:
                self._dmag_trigger_cron(message.next_try)
        return message.with_env(self.env)

    @api.model
    def _dmag_variables(self, partner, record, company):
        variables = {
            'partner': partner,
            'patient': partner,
            'company': company,
            'record': record or self.env['res.partner'],
            'today': fields.Date.context_today(self),
            'now': fields.Datetime.now(),
        }
        if record and record._name == 'dmag.dental.visit':
            variables['visit'] = record
        elif record and 'visit_id' in record._fields:
            variables['visit'] = record.visit_id
        return variables

    @api.model
    def _dmag_trigger_cron(self, at=None):
        cron = self.env.ref('dmag_zalo_zns.ir_cron_dmag_zns_send', raise_if_not_found=False)
        if cron and not getattr(odoo_module, 'current_test', False):
            cron.sudo()._trigger(at)

    # ------------------------------------------------------------------ queue
    @api.model
    def _cron_send_queue(self, limit=200):
        now = fields.Datetime.now()
        messages = self.sudo().search([('state', '=', 'queued'), ('next_try', '<=', now)],
                                      order='next_try, id', limit=limit)
        for message in messages:
            message._dmag_process()
            if not getattr(odoo_module, 'current_test', False):
                self.env.cr.commit()  # pylint: disable=invalid-commit
        return len(messages)

    def _dmag_process(self):
        """Gửi các tin đang chờ (tôn trọng giờ yên lặng, hạn gửi, từ chối nhận tin)."""
        now = fields.Datetime.now()
        for message in self.sudo().filtered(lambda m: m.state == 'queued'):
            if message.expire_at and message.expire_at < now:
                message.write({'state': 'cancel', 'error': _('Quá hạn gửi (%s).', message.expire_at)})
                continue
            if message.partner_id.zns_opt_out:
                message.write({'state': 'skipped', 'error': _('Khách đã từ chối nhận tin Zalo ZNS.')})
                continue
            if not message.transactional:
                postpone = quiet_until(self.env, message.company_id, now)
                if postpone:
                    message.write({'next_try': postpone})
                    continue
            message._dmag_send_one()
        return True

    def _dmag_payload(self):
        self.ensure_one()
        payload = {
            'phone': self.phone,
            'template_id': self.zalo_template_id or self.template_id.template_id,
            'template_data': json.loads(self.params_json or '{}'),
            'tracking_id': self.tracking_id,
        }
        if self.company_id.dmag_zns_dev_mode:
            payload['mode'] = 'development'
        return payload

    def _dmag_send_one(self):
        self.ensure_one()
        payload = self._dmag_payload()
        mode = self.company_id.dmag_zns_mode
        try:
            result = getattr(self, '_dmag_transport_%s' % mode)(payload)
        except UserError as exc:
            result = {'error': -1, 'message': str(exc), 'retry': False}
        except Exception as exc:  # lỗi mạng / bên thứ ba: thử lại
            _logger.warning('ZNS send error (%s): %s', self.tracking_id, exc)
            result = {'error': -2, 'message': str(exc), 'retry': True}
        self._dmag_apply_result(result, mode)

    def _dmag_apply_result(self, result, mode):
        attempts = self.attempt_count + 1
        vals = {'attempt_count': attempts, 'mode': mode,
                'response_raw': json.dumps(result, ensure_ascii=False, default=str)[:4000]}
        code = result.get('error', -1)
        try:
            code = int(code)
        except (TypeError, ValueError):
            code = -1
        if code == 0:
            data = result.get('data') or {}
            vals.update(state='sent', sent_date=fields.Datetime.now(), error=False, error_code=0,
                        msg_id=str(data.get('msg_id') or result.get('msg_id') or ''))
        else:
            retry = result.get('retry', code not in NON_RETRYABLE_ERRORS)
            vals.update(error=result.get('message') or _('Lỗi không xác định'), error_code=code)
            if retry and attempts < max(self.company_id.dmag_zns_max_retry, 1):
                vals['next_try'] = fields.Datetime.now() + timedelta(minutes=5 * 2 ** (attempts - 1))
            else:
                vals['state'] = 'failed'
        self.write(vals)

    # ------------------------------------------------------------------ transports
    def _dmag_transport_mock(self, payload):
        """Giả lập: thành công, trừ khi context ``dmag_zns_mock_error`` = mã lỗi."""
        error = self.env.context.get('dmag_zns_mock_error')
        if error:
            return {'error': int(error), 'message': 'Mock error %s' % error}
        _logger.info('ZNS mock send %s → %s', payload['template_id'], payload['phone'])
        return {'error': 0, 'message': 'Success',
                'data': {'msg_id': 'mock-%s' % payload['tracking_id'], 'sent_time': fields.Datetime.now()}}

    def _dmag_transport_live(self, payload):
        if not payload.get('template_id'):
            raise UserError(_('Mẫu "%s" chưa có Template ID do Zalo cấp.', self.template_id.name))
        company = self.company_id
        token = company._dmag_zalo_get_access_token()
        result = self._dmag_http_post(token, payload)
        if result.get('error') in TOKEN_ERRORS and company.sudo().dmag_zalo_refresh_token:
            company._dmag_zalo_refresh_token()
            result = self._dmag_http_post(company.sudo().dmag_zalo_access_token, payload)
        return result

    def _dmag_http_post(self, token, payload):
        response = requests.post(ZNS_SEND_URL, json=payload, timeout=20, headers={
            'access_token': token,
            'Content-Type': 'application/json',
        })
        try:
            return response.json()
        except ValueError:
            return {'error': -2, 'message': 'HTTP %s: %s' % (response.status_code, response.text[:500]),
                    'retry': response.status_code >= 500}

    def _dmag_transport_bizapps(self, payload):
        """Ủy quyền cho module biz_zalo_zns của Bizapps (tên hàm cấu hình theo công ty)."""
        model = self.env.get('biz.zalo.zns')
        if model is None:
            raise UserError(_('Chế độ Bizapps: không tìm thấy model biz.zalo.zns (module biz_zalo_zns chưa cài).'))
        method_name = self.company_id.dmag_zns_bizapps_method or 'send_zns_template'
        method = getattr(model.sudo(), method_name, None)
        if not method:
            raise UserError(_('Chế độ Bizapps: model biz.zalo.zns không có hàm %s.', method_name))
        res = method(phone=payload['phone'], template_id=payload['template_id'],
                     template_data=payload['template_data'], tracking_id=payload['tracking_id'])
        if isinstance(res, dict):
            if 'error' in res:
                return res
            return {'error': 0, 'data': {'msg_id': res.get('msg_id') or (res.get('data') or {}).get('msg_id')}}
        if isinstance(res, models.BaseModel):
            return {'error': 0, 'data': {'msg_id': 'bizapps-%s' % res[:1].id}}
        return {'error': 0 if res else -1, 'data': {'msg_id': str(res) if res else ''},
                'message': '' if res else 'Bizapps trả về rỗng'}

    # ------------------------------------------------------------------ actions
    def action_retry(self):
        if not (is_director(self.env) or self.env.user.has_group('dmag_dental_base.group_dmag_manager')):
            check_director(self.env)
        for message in self.sudo().filtered(lambda m: m.state in ('failed', 'queued')):
            message.write({'state': 'queued', 'next_try': fields.Datetime.now(), 'error': False})
            message._dmag_process()
        return True

    def action_cancel(self):
        if not self.env.user.has_group('dmag_dental_base.group_dmag_manager'):
            check_director(self.env)
        self.sudo().filtered(lambda m: m.state == 'queued').write({'state': 'cancel'})
        return True

    def action_open_record(self):
        self.ensure_one()
        if not self.res_model or not self.res_id:
            return False
        return {'type': 'ir.actions.act_window', 'res_model': self.res_model, 'res_id': self.res_id,
                'view_mode': 'form'}

    def write(self, vals):
        if not self.env.su and not is_director(self.env):
            check_director(self.env, _('Nhật ký tin ZNS chỉ đọc.'))
        return super().write(vals)

    def unlink(self):
        check_director(self.env, _('Chỉ Giám đốc / Quản lý cấp cao được xóa nhật ký tin ZNS.'))
        return super().unlink()

    # ------------------------------------------------------------------ webhook
    @api.model
    def _dmag_find_from_webhook(self, msg_id=None, tracking_id=None):
        domain = []
        if msg_id and tracking_id:
            domain = ['|', ('msg_id', '=', str(msg_id)), ('tracking_id', '=', str(tracking_id))]
        elif msg_id:
            domain = [('msg_id', '=', str(msg_id))]
        elif tracking_id:
            domain = [('tracking_id', '=', str(tracking_id))]
        else:
            return self.browse()
        return self.sudo().search(domain, limit=1)
