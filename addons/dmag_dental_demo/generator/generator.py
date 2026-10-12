"""Bộ sinh dữ liệu demo DMAG – chạy qua nghiệp vụ thật của các module dmag_*.

Nguyên tắc:
* Mọi chứng từ được tạo đúng thứ tự thời gian bằng các hàm nghiệp vụ (đặt lịch → xác nhận → check-in →
  lên ghế → sơ đồ răng → thủ thuật → hoàn tất → ký bệnh án → hóa đơn → thu tiền …), đồng hồ hệ thống được
  "đóng băng" (freezegun) tại từng thời điểm nên giờ check-in, hóa đơn, thanh toán, chatter… đều khớp thực tế.
* Hạt giống ngẫu nhiên cố định → chạy lại cho cùng một bộ dữ liệu (tương đối theo ngày hôm nay).
* Mọi bản ghi phát sinh được gắn external id ``dmag_dental_demo.gen_*`` để gỡ module / tạo lại xóa sạch.
"""
import base64
import heapq
import itertools
import json
import logging
import math
import random
import secrets
import time
from collections import Counter, defaultdict
from contextlib import contextmanager, nullcontext
from datetime import datetime, timedelta

import pytz
from dateutil.relativedelta import relativedelta

from odoo import SUPERUSER_ID, fields
from odoo.exceptions import UserError, ValidationError

from . import data as D

_logger = logging.getLogger(__name__)

# Đồng hồ thật kể cả khi đang "đóng băng" thời gian: freezegun chỉ thay các hàm gán trực tiếp ở cấp module,
# không thay phần tử trong danh sách.
_REAL_CLOCK = [time.perf_counter]


def wall_time():
    return _REAL_CLOCK[0]()


MODULE = 'dmag_dental_demo'
XMLID_PREFIX = 'gen_'
PARAM_MODE = 'dmag.demo_mode'
PARAM_BACKUP = 'dmag.demo.backup'
PARAM_INFO = 'dmag.demo.info'
TZ_NAME = 'Asia/Ho_Chi_Minh'
TZ = pytz.timezone(TZ_NAME)
SEED = 20261010
HISTORY_DAYS = 60
ESIGN_RECENT_DAYS = 7
VISITS_PER_DAY = (4, 6)

# Model không gắn xmlid: tự xóa theo bản ghi cha, hoặc là dữ liệu kỹ thuật của hệ thống
SKIP_TAG_PREFIXES = ('ir.', 'bus.', 'base.', 'discuss.', 'web_', 'res.users.settings', 'res.users.log',
                     'res.users.apikeys', 'mail.message', 'mail.tracking.value', 'mail.notification',
                     'mail.followers', 'mail.link.preview', 'mail.guest', 'account.move.line',
                     'account.partial.reconcile', 'account.full.reconcile', 'auth_totp',
                     # cấu hình kế toán / hệ thống có thể được nạp trong lúc sinh (DB mới) – không xóa khi gỡ demo
                     'account.account', 'account.journal', 'account.tax', 'account.fiscal', 'account.group',
                     'account.root', 'account.reconcile.model', 'account.payment.method', 'mail.alias',
                     'account.report', 'account.cash.rounding',
                     'res.currency', 'res.country', 'res.lang', 'res.company', 'product.pricelist',
                     'uom.', 'stock.warehouse', 'stock.route', 'stock.rule', 'resource.calendar')
TAG_ALLOWED_IR = ('ir.attachment',)


def _skip_tag(model_name):
    if model_name in TAG_ALLOWED_IR:
        return False
    return model_name.startswith(SKIP_TAG_PREFIXES)


class PatientState:
    """Trạng thái điều trị của một bệnh nhân trong kịch bản sinh dữ liệu."""

    def __init__(self, key, partner, spec):
        self.key = key
        self.partner = partner
        self.spec = spec
        self.scenario = False
        self.teeth = []
        self.plan = False
        self.option = False
        self.decision = 'accept'
        self.next_due = False
        self.visits = 0
        self.last_visit = False
        self.lab_order = False
        self.ortho_visit = False
        self.findings = {}
        self.noshows = 0
        self.doctor_key = 'doctor'

    @property
    def is_child(self):
        return self.partner.age and self.partner.age < 13

    def todo_lines(self):
        if not self.plan or not self.plan.accepted_option_id:
            return self.plan.browse() if self.plan else False
        return self.plan.accepted_option_id.line_ids.filtered(lambda l: l.state == 'todo')


class DemoGenerator:

    def __init__(self, env):
        ctx = dict(env.context, tz=TZ_NAME, mail_create_nosubscribe=True, mail_notify_force_send=False,
                   no_reset_password=True, tracking_disable=True, mail_notrack=True, mail_create_nolog=True,
                   dmag_demo_generate=True)
        ctx.pop('dmag_demo_purge', None)
        self.env = env(user=SUPERUSER_ID, su=True, context=ctx)
        self.company = self.env['res.company'].browse(self.env.company.id)
        self.rng = random.Random(SEED)
        # Hạt giống riêng cho các tình huống phục vụ AI (giảm giá, vật tư phát sinh…) – không làm đổi chuỗi
        # ngẫu nhiên chính của lịch sử demo.
        self.rng_ai = random.Random(SEED + 15)
        self.frozen = None
        self.max_time = None
        self.stats = Counter()
        self.warnings = []
        self.backup = {}
        self.users = {}
        self.prac = {}
        self.svc = {}
        self.mat = {}
        self.lots = defaultdict(list)
        self.drugs = {}
        self.rx_templates = {}
        self.chairs = []
        self.labs = []
        self.patients = {}
        self.pstates = []
        self.batches = {}
        self.events = []
        self.booked_at = {}  # id lượt khám -> thời điểm đặt lịch (UTC) – để create_date phản ánh lúc khách đặt
        self._seq = itertools.count()
        self.today = fields.Date.context_today(self.env['res.partner'])
        self.now = fields.Datetime.now()

    # ======================================================================== helpers
    def ref(self, xmlid):
        return self.env.ref(xmlid, raise_if_not_found=False)

    def base_ref(self, name):
        return self.ref('dmag_dental_base.%s' % name)

    def M(self, model, user=None):
        """Model ``model`` dưới quyền người dùng demo ``user`` (khóa trong USERS) hoặc quyền hệ thống."""
        Model = self.env[model]
        if user:
            return Model.with_user(self.users[user]).with_company(self.company)
        return Model

    def as_user(self, records, user):
        return records.with_user(self.users[user]).with_company(self.company)

    def local_dt(self, day, hour, minute=0):
        local = TZ.localize(datetime(day.year, day.month, day.day, int(hour), int(minute)))
        return local.astimezone(pytz.utc).replace(tzinfo=None)

    def to_local(self, dt):
        return pytz.utc.localize(dt).astimezone(TZ)

    def at(self, dt):
        """Đặt đồng hồ hệ thống (UTC, naive) – chỉ khi đang sinh lịch sử."""
        if self.frozen is not None and dt:
            if self.max_time and dt > self.max_time:
                dt = self.max_time
            self.frozen.move_to(dt)

    @contextmanager
    def section(self, name, optional=True):
        """Một phần dữ liệu – phần tùy chọn lỗi thì ghi cảnh báo, không chặn cài đặt."""
        start = wall_time()
        if not optional:
            yield
            _logger.info('DMAG demo: %s (%.1fs)', name, wall_time() - start)
            return
        try:
            with self.env.cr.savepoint():
                yield
        except Exception as exc:  # noqa: BLE001 – dữ liệu demo không được làm hỏng cài đặt
            _logger.warning('DMAG demo: bỏ qua phần "%s": %s', name, exc, exc_info=True)
            self.warnings.append('%s: %s' % (name, exc))
        else:
            _logger.info('DMAG demo: %s (%.1fs)', name, wall_time() - start)

    def try_(self, label, func, *args, **kwargs):
        """Một thao tác nhỏ tùy chọn trong savepoint."""
        try:
            with self.env.cr.savepoint():
                return func(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            _logger.warning('DMAG demo: %s thất bại: %s', label, exc)
            self.warnings.append('%s: %s' % (label, exc))
            self.stats['warnings'] += 1
            return False

    def remember(self, record, values):
        """Ghi giá trị cũ của bản ghi KHÔNG do demo tạo, để khôi phục khi gỡ / tạo lại."""
        key = '%s,%s' % (record._name, record.id)
        old = self.backup.setdefault(key, {})
        for fname in values:
            if fname in old:
                continue
            field = record._fields[fname]
            value = record[fname]
            if field.type == 'many2one':
                value = value.id
            elif field.type in ('date', 'datetime'):
                value = fields.Datetime.to_string(value) if value else False
            old[fname] = value
        record.write(values)

    def schedule(self, when, func, *args):
        heapq.heappush(self.events, (when, next(self._seq), func, args))

    def run_events(self, until):
        while self.events and self.events[0][0] <= until:
            when, _seq, func, args = heapq.heappop(self.events)
            self.at(when)
            self.try_('Sự kiện %s' % getattr(func, '__name__', func), func, *args)

    @property
    def clinic_schedule(self):
        """Lịch làm việc phòng khám (dmag.clinic.schedule) – lịch sử chỉ sinh vào ngày / giờ mở cửa."""
        if getattr(self, '_schedule_info', None) is None:
            self._schedule_info = self.env['dmag.clinic.schedule'].get_info(self.company)
        return self._schedule_info

    def working_days(self, start, end):
        day = start
        while day <= end:
            if self.clinic_schedule.is_open_day(day):  # thứ nghỉ, ngày lễ theo Lịch làm việc phòng khám
                yield day
            day += timedelta(days=1)

    def open_starts(self, day, step=30, min_len=30):
        """Các giờ bắt đầu (phút trong ngày) nằm trong ca làm việc của ngày ``day``."""
        return [m for s, e in self.clinic_schedule.shifts(day) for m in range(s, e - min_len + 1, step)]

    def fit_schedule(self, start, duration):
        """Dời giờ hẹn (UTC naive) vào trọn một ca làm việc: cùng ca thì kéo sớm lại cho kịp giờ đóng ca, rơi vào giờ
        nghỉ trưa thì sang đầu ca sau."""
        local = self.to_local(start).replace(tzinfo=None)
        day, minute = local.date(), local.hour * 60 + local.minute
        shifts = self.clinic_schedule.shifts(day)
        if not shifts or self.clinic_schedule.contains(day, minute, minute + duration):
            return start
        for s, e in shifts:
            if s <= minute < e or minute < s:
                begin = max(s, min(minute, e - duration))
                if begin + duration <= e:
                    return self.local_dt(day, begin // 60, begin % 60)
        s, e = max(shifts, key=lambda se: se[1] - se[0])
        begin = max(s, e - duration)
        return self.local_dt(day, begin // 60, begin % 60)

    # ======================================================================== entry point
    def run(self):
        t0 = wall_time()
        # Hệ thống tài khoản (nếu DB chưa có) là cấu hình lâu dài – nạp TRƯỚC mốc id để không bị xóa khi gỡ demo
        self._ensure_accounting()
        self.watermarks = self._watermarks()
        with self.section('Thông tin pháp lý phòng khám', optional=False):
            self._setup_company()
        with self.section('Tích hợp ở chế độ giả lập', optional=False):
            self._setup_integrations()
        with self.section('Người dùng demo', optional=False):
            self._create_users()
        with self.section('Danh mục dịch vụ, ghế, vật tư, thuốc', optional=False):
            self._create_catalog()
        with self.section('Chính sách mẫu'):
            self._create_policies()
        with self.section('Hồ sơ pháp chế & thiết bị'):
            self._create_compliance()
        with self.section('Nhân sự 3P'):
            self._create_hr()
        with self.section('Lịch làm việc 7 ngày & lịch nghỉ luân phiên'):
            self._rotation()
        with self.section('Bệnh nhân', optional=False):
            self._create_patients()
        with self.section('Trợ lý AI: chế độ giả lập, đồng ý AI, thuốc đang dùng'):
            self._ai_setup()
        start = self.local_dt(self.today - timedelta(days=HISTORY_DAYS + 7), 8)
        try:
            from freezegun import freeze_time  # có trong requirements chuẩn của Odoo 17
            clock = freeze_time(start, tick=False)
        except ImportError:  # thiếu freezegun: vẫn sinh dữ liệu, chỉ là giờ hệ thống = hiện tại
            _logger.warning('DMAG demo: thiếu thư viện freezegun – thời điểm chứng từ sẽ là thời điểm cài đặt.')
            clock = nullcontext()
        with clock as frozen:
            self.frozen = frozen
            try:
                with self.section('Lịch sử 60 ngày', optional=False):
                    self._history()
                with self.section('Bảng điều phối hôm nay', optional=False):
                    self._today_board()
                with self.section('Lịch hẹn sắp tới', optional=False):
                    self._future_bookings()
            finally:
                self.frozen = None
        with self.section('Tin ZNS & điểm chạm hành trình'):
            self._journey_finalize()
        with self.section('Bảng kê hoa hồng tháng trước'):
            self._commission_statement()
        with self.section('Bảng lương 3P'):
            self._pay_sheets()
        with self.section('Hạng thành viên'):
            self._loyalty_finalize()
        with self.section('Tài khoản cổng bệnh nhân'):
            self._portal_user()
        with self.section('OKR (nếu đã cài OKR Scale)'):
            self._okr()
        with self.section('Mục tiêu kinh doanh (Bảng điều hành mục tiêu)'):
            self._business_targets()
        with self.section('Trợ lý AI: đồng ý AI, giả lập, nhật ký, bản tin, bất thường, dự báo'):
            self._ai_demo()
        self._drop_outgoing_mail()
        self.env.flush_all()
        tagged = self._tag(self.watermarks)
        self._save_params(tagged, wall_time() - t0)
        _logger.info('DMAG demo: đã sinh dữ liệu trong %.1fs – %s', wall_time() - t0, dict(self.stats))
        return self.stats

    # ======================================================================== watermarks / tags
    def _watermarks(self):
        self.env.flush_all()
        cr = self.env.cr
        marks = {}
        for name in sorted(self.env.registry.models):
            Model = self.env.registry[name]
            if Model._abstract or Model._transient or not Model._auto or Model._table_query or _skip_tag(name):
                continue
            cr.execute('SELECT COALESCE(MAX(id), 0) FROM "%s"' % Model._table)  # noqa: S608 – tên bảng của ORM
            marks[name] = cr.fetchone()[0]
        return marks

    def _demo_uids(self):
        return [SUPERUSER_ID] + [u.id for u in self.users.values()] + \
            ([self.portal_user.id] if getattr(self, 'portal_user', False) else [])

    def _tag(self, marks):
        """Gắn external id cho mọi bản ghi demo vừa tạo (theo id > mốc trước khi sinh + người tạo)."""
        self.env.flush_all()
        cr = self.env.cr
        uids = self._demo_uids()
        total = 0
        for name, mark in marks.items():
            Model = self.env.registry[name]
            table = Model._table
            where = 'id > %s'
            params = [mark]
            if Model._log_access:
                where += ' AND create_uid = ANY(%s)'
                params.append(uids)
            cr.execute(f"""
                INSERT INTO ir_model_data (module, name, model, res_id, noupdate,
                                           create_uid, write_uid, create_date, write_date)
                SELECT %s, %s || id, %s, id, TRUE, %s, %s, now() at time zone 'UTC', now() at time zone 'UTC'
                  FROM "{table}" WHERE {where}
                ON CONFLICT DO NOTHING
            """, [MODULE, '%s%s_' % (XMLID_PREFIX, name.replace('.', '_')), name, SUPERUSER_ID, SUPERUSER_ID]
                + params)  # noqa: S608
            total += cr.rowcount
        self.env.registry.clear_cache()
        return total

    def _save_params(self, tagged, seconds):
        ICP = self.env['ir.config_parameter']
        ICP.set_param(PARAM_MODE, '1')
        old = json.loads(ICP.get_param(PARAM_BACKUP) or '{}')
        # bản sao lưu cũ (nếu tạo lại) giữ ưu tiên: đó là giá trị TRƯỚC khi có demo
        for key, vals in self.backup.items():
            target = old.setdefault(key, {})
            for fname, value in vals.items():
                target.setdefault(fname, value)
        ICP.set_param(PARAM_BACKUP, json.dumps(old, ensure_ascii=False))
        info = {
            'generated_at': fields.Datetime.to_string(fields.Datetime.now()),
            'seconds': round(seconds, 1),
            'tagged': tagged,
            'stats': dict(self.stats),
            'warnings': self.warnings[:30],
            'logins': [u.login for u in self.users.values()],
        }
        ICP.set_param(PARAM_INFO, json.dumps(info, ensure_ascii=False))

    def _drop_outgoing_mail(self):
        """Không gửi email thật tới địa chỉ demo."""
        mails = self.env['mail.mail'].search([('id', '>', self.watermarks.get('mail.mail', 0))])
        if mails:
            mails.unlink()

    # ======================================================================== company & integrations
    def _setup_company(self):
        company = self.company
        vals = {}
        for fname in ('dmag_facility_code', 'dmag_license_number', 'dmag_professional_director', 'phone',
                      'street', 'city', 'email'):
            if fname in company._fields and not company[fname]:
                vals[fname] = D.COMPANY[fname]
        if company.name in ('My Company', 'YourCompany', 'Your Company'):
            vals['name'] = 'Nha khoa DMAG (Demo)'  # tên mặc định của Odoo → tên phòng khám demo (khôi phục khi gỡ)
        vn = self.ref('base.vn')
        if not company.country_id and vn:
            vals['country_id'] = vn.id
        if company.state_id and company.state_id.country_id != (company.country_id or vn):
            vals['state_id'] = False
        if not company.dmag_license_date:
            vals['dmag_license_date'] = self.today - relativedelta(years=3)
        if company.dmag_max_discount != 10.0:
            vals['dmag_max_discount'] = 10.0
        if 'dmag_cskh_user_id' in company._fields:
            pass  # gán sau khi có người dùng
        if vals:
            self.remember(company, vals)
        if company.partner_id.tz != TZ_NAME and not company.partner_id.tz:
            self.remember(company.partner_id, {'tz': TZ_NAME})

    def _ensure_accounting(self):
        """Cơ sở dữ liệu mới chưa có hệ thống tài khoản → nạp (l10n_vn nếu có, nếu không dùng bộ chung)."""
        Journal = self.env['account.journal']
        if Journal.search_count([('company_id', '=', self.company.id), ('type', '=', 'sale')]):
            return
        Template = self.env['account.chart.template']
        code = 'vn' if self.env['ir.module.module'].search_count(
            [('name', '=', 'l10n_vn'), ('state', '=', 'installed')]) else 'generic_coa'
        Template.try_loading(code, self.company, install_demo=False)
        self.stats['chart_loaded'] = 1

    def _setup_integrations(self):
        company = self.company
        # Zalo ZNS: giả lập
        zns_vals = {}
        if company.dmag_zns_mode != 'mock':
            zns_vals['dmag_zns_mode'] = 'mock'
        if not company.dmag_zalo_oa_id:
            zns_vals['dmag_zalo_oa_id'] = 'DEMO-OA-0001'
        if zns_vals:
            self.remember(company, zns_vals)
        # Đơn thuốc quốc gia: giả lập
        RxConfig = self.env['dmag.rx.national.config']
        rx_conf = RxConfig.search([('company_id', '=', company.id)], limit=1)
        rx_vals = {'enabled': True, 'mode': 'mock', 'mock_fail': False}
        if rx_conf:
            if not rx_conf.facility_link_code:
                rx_vals['facility_link_code'] = 'DEMO-CSKCB-79999'
            self.remember(rx_conf, rx_vals)
        else:
            RxConfig.create(dict(rx_vals, company_id=company.id, facility_link_code='DEMO-CSKCB-79999',
                                 facility_password='demo'))
        # Ký số: nhà cung cấp giả lập xếp đầu
        Provider = self.env['dmag.esign.provider']
        first = Provider.search([('company_id', '=', company.id)], order='sequence, id', limit=1)
        seq = min(first.sequence - 1, 0) if first else 0
        Provider.create({
            'name': 'Ký số giả lập (demo – không có giá trị pháp lý)',
            'company_id': company.id,
            'provider_type': 'mock',
            'sequence': seq,
            'mock_require_approval': False,
        })
        # SePay: chế độ demo
        Sepay = self.env['dmag.sepay.config']
        sepay_vals = {
            'enabled': True,
            'bank_code': 'MBBank',
            'account_number': '0000000000',
            'account_name': 'NHA KHOA DMAG DEMO',
            'api_key': secrets.token_urlsafe(24),
        }
        if 'demo_mode' in Sepay._fields:
            sepay_vals['demo_mode'] = True
        sepay = Sepay.with_context(active_test=False).search([('company_id', '=', company.id)], limit=1)
        if sepay:
            self.remember(sepay, sepay_vals)
        else:
            Sepay.create(dict(sepay_vals, company_id=company.id, code_prefix='DMAG'))
        self.env['ir.config_parameter'].set_param(PARAM_MODE, '1')

    # ======================================================================== users
    def _create_users(self):
        Users = self.env['res.users'].with_context(no_reset_password=True)
        lang = 'vi_VN' if self.env['res.lang']._lang_get('vi_VN') else False
        for key, login, name, group, _job, _grade in D.USERS:
            user = Users.with_context(active_test=False).search([('login', '=', login)], limit=1)
            if not user:
                vals = {
                    'name': name,
                    'login': login,
                    'password': D.PASSWORD,
                    'email': '%s@nhakhoa-dmag.demo' % login,
                    'tz': TZ_NAME,
                    'company_id': self.company.id,
                    'company_ids': [(6, 0, self.company.ids)],
                    'groups_id': [(6, 0, [self.env.ref(group).id])],
                    'notification_type': 'inbox',
                }
                if lang:
                    vals['lang'] = lang
                user = Users.create(vals)
                self.stats['users'] += 1
            self.users[key] = user
        Prac = self.env['dmag.dental.practitioner']
        today = self.today
        for key, (title, role, lic, level, scopes, color, rx_code) in D.PRACTITIONERS.items():
            user = self.users[key]
            prac = Prac.search([('user_id', '=', user.id), ('company_id', '=', self.company.id)], limit=1)
            if not prac:
                vals = {
                    'name': user.name, 'title': title, 'role': role, 'user_id': user.id,
                    'company_id': self.company.id, 'license_number': lic, 'color': color,
                    'phone': '09%08d' % self.rng.randint(10000000, 99999999),
                    'license_issue_date': today - relativedelta(years=3, months=key == 'doctor2' and 2 or 0),
                    'license_expiry_date': today + (relativedelta(days=45) if key == 'doctor2'
                                                    else relativedelta(years=2)),
                    'scope_ids': [(6, 0, [self.base_ref(s).id for s in scopes])],
                }
                if level:
                    vals['clinical_level_id'] = self.ref(level).id
                if rx_code and 'rx_link_code' in Prac._fields:
                    vals['rx_link_code'] = rx_code
                    vals['rx_link_password'] = 'demo'
                if role == 'doctor' and 'mysign_user_id' in Prac._fields:
                    vals['mysign_user_id'] = '0790%08d' % self.rng.randint(10000000, 99999999)
                prac = Prac.create(vals)
            self.prac[key] = prac
        # Hồ sơ ký số của Giám đốc (LƯU TRỮ – không hiện trong danh sách bác sĩ / xếp lịch) để "ký bổ sung chịu trách
        # nhiệm" khi duyệt vượt an toàn đơn thuốc (AI-03) bằng nhà cung cấp ký số giả lập
        director = self.users['director']
        if not Prac.with_context(active_test=False).search([('user_id', '=', director.id),
                                                            ('company_id', '=', self.company.id)], limit=1):
            vals = {'name': director.name, 'title': 'Giám đốc', 'role': 'doctor', 'user_id': director.id,
                    'company_id': self.company.id, 'license_number': '000999/HCM-CCHN', 'active': False}
            if 'mysign_user_id' in Prac._fields:
                vals['mysign_user_id'] = '079000000999'
            Prac.create(vals)
        for key in ('doctor', 'doctor2', 'doctor3'):
            if key in self.prac:
                self.try_('Lấy chứng thư ký số giả lập', self.prac[key].action_fetch_mysign_certificate)
        # Nhân viên CSKH mặc định cho hành trình khách hàng
        company_vals = {}
        if 'dmag_cskh_user_id' in self.company._fields:
            company_vals['dmag_cskh_user_id'] = self.users['receptionist'].id
            company_vals['dmag_cskh_lead_user_id'] = self.users['manager'].id
        if company_vals:
            self.remember(self.company, company_vals)

    # ======================================================================== catalog
    def _create_catalog(self):
        Chair = self.env['dmag.dental.chair']
        for seq, (name, code, room) in enumerate(D.CHAIRS, start=1):
            chair = Chair.with_context(active_test=False).search(
                [('name', '=', name), ('company_id', '=', self.company.id)], limit=1)
            self.chairs.append(chair or Chair.create({'name': name, 'code': code, 'room': room, 'sequence': seq,
                                                      'company_id': self.company.id}))
        Product = self.env['product.product']
        categ = self.env['product.category'].create({'name': 'Dịch vụ nha khoa (demo)'})
        for code, spec in D.SERVICES.items():
            (name, cat, price, duration, complexity, needs_tooth, scope, level, warranty, recall, result,
             second) = spec
            vals = {
                'name': name,
                'default_code': 'DM-%s' % code.upper(),
                'detailed_type': 'service',
                'categ_id': categ.id,
                'is_dental_service': True,
                'dental_category': cat,
                'list_price': price,
                'dental_duration': duration,
                'dental_complexity': complexity,
                'dental_requires_tooth': needs_tooth,
                'warranty_months': warranty,
                'recall_months': recall,
                'requires_second_opinion': second,
                'invoice_policy': 'delivery',
                'sale_ok': True,
                'purchase_ok': False,
            }
            if scope:
                vals['practice_scope_id'] = self.base_ref(scope).id
            if level:
                vals['min_clinical_level_id'] = self.base_ref('level_%s' % level).id
            if result:
                vals['dental_result_condition_id'] = self.base_ref(result).id
            if code in D.AFTERCARE:
                vals['aftercare_note'] = D.AFTERCARE[code]
            if warranty and 'warranty_conditions' in self.env['product.template']._fields:
                vals['warranty_conditions'] = ('Tái khám định kỳ đúng hẹn; không dùng răng cắn vật cứng; '
                                               'vệ sinh răng miệng theo hướng dẫn (mẫu).')
            self.svc[code] = Product.create(vals)
        for cond, codes in D.CONDITION_SUGGESTIONS.items():
            condition = self.base_ref(cond)
            if condition and not condition.suggested_service_ids:
                condition.suggested_service_ids = [(6, 0, [self.svc[c].id for c in codes])]
        self._create_materials()
        self._create_drugs()
        Partner = self.env['res.partner']
        for name, lead, phone, city in D.LAB_PARTNERS:
            self.labs.append(Partner.create({
                'name': name, 'is_company': True, 'is_dental_lab': True, 'dmag_lab_lead_days': lead,
                'phone': phone, 'city': city, 'country_id': self.ref('base.vn').id, 'supplier_rank': 1,
            }))

    def _create_materials(self):
        Product = self.env['product.product']
        categ = self.env['product.category'].create({'name': 'Vật tư nha khoa (demo)'})
        if 'property_valuation' in categ._fields:
            categ.with_company(self.company).write({'property_valuation': 'manual_periodic',
                                                    'property_cost_method': 'standard'})
        for code, (name, ptype, uom, cost, tracking, qty) in D.MATERIALS.items():
            vals = {
                'name': name, 'detailed_type': ptype, 'categ_id': categ.id, 'standard_price': cost,
                'sale_ok': False, 'purchase_ok': True, 'tracking': tracking, 'default_code': 'VT-%s' % code.upper(),
                'taxes_id': [(5, 0, 0)],
            }
            if uom:
                vals['uom_id'] = vals['uom_po_id'] = self.ref(uom).id
            self.mat[code] = Product.create(vals)
        warehouse = self.env['stock.warehouse'].search([('company_id', '=', self.company.id)], limit=1)
        if not warehouse:
            raise ValueError('Phòng khám chưa có kho – không tạo được vật tư demo.')
        location = warehouse.lot_stock_id
        Quant = self.env['stock.quant'].with_context(inventory_mode=True)
        quants = Quant.browse()
        Lot = self.env['stock.lot']
        for code, (_name, ptype, _uom, _cost, tracking, qty) in D.MATERIALS.items():
            product = self.mat[code]
            if tracking == 'serial':
                for serial in D.IMPLANT_SERIALS[code]:
                    lot = Lot.search([('name', '=', serial), ('product_id', '=', product.id)], limit=1) or \
                        Lot.create({'name': serial, 'product_id': product.id, 'company_id': self.company.id})
                    self.lots[code].append(lot)
                    quants |= Quant.create({'product_id': product.id, 'location_id': location.id,
                                            'lot_id': lot.id, 'inventory_quantity': 1})
            elif ptype == 'product' and qty:
                quants |= Quant.create({'product_id': product.id, 'location_id': location.id,
                                        'inventory_quantity': qty})
        if quants:
            quants.action_apply_inventory()
        Bom = self.env['dmag.service.bom']
        for svc_code, lines in D.BOMS.items():
            Bom.create({
                'product_tmpl_id': self.svc[svc_code].product_tmpl_id.id,
                'company_id': self.company.id,
                'note': 'Định mức mẫu – phòng khám điều chỉnh theo thực tế ' + D.SAMPLE,
                'line_ids': [(0, 0, {'product_id': self.mat[m].id, 'quantity': q, 'basis': basis})
                             for m, q, basis in lines],
            })

    def _create_drugs(self):
        Drug = self.env['dmag.drug']
        for code, spec in D.DRUGS.items():
            (inn, strength, form, unit, route, brand, multi, dose, times, days, timing, dose_unit) = spec
            self.drugs[code] = Drug.create({
                'inn_name': inn, 'strength': strength, 'dosage_form': form, 'unit': unit, 'route': route,
                'brand_name': brand or False, 'multi_ingredient': multi, 'default_dose_per_time': dose,
                'default_times_per_day': times, 'default_days': days, 'default_timing': timing,
                'dose_unit': dose_unit or False, 'company_id': self.company.id,
                'note': 'Danh mục mẫu – cập nhật số đăng ký / mã dược quốc gia theo sản phẩm thực tế.',
            })
        Template = self.env['dmag.prescription.template']
        for seq, (name, diag, days, advice, lines) in enumerate(D.RX_TEMPLATES, start=1):
            self.rx_templates[name] = Template.create({
                'name': name, 'sequence': 100 + seq, 'company_id': self.company.id,
                'diagnosis_ids': [(6, 0, self.base_ref(diag).ids)], 're_exam_days': days, 'advice': advice,
                'line_ids': [(0, 0, {'sequence': i * 10, 'drug_id': self.drugs[d].id, 'dose_per_time': dose,
                                     'times_per_day': times, 'days': nb})
                             for i, (d, dose, times, nb) in enumerate(lines, start=1)],
            })

    # ======================================================================== policies
    def _create_policies(self):
        Rule = self.env['dmag.commission.rule']
        for seq, (name, role, basis, rate, fixed, note) in enumerate(D.COMMISSION_RULES, start=1):
            Rule.create({'name': name, 'role': role, 'basis': basis, 'rate': rate, 'fixed_amount': fixed,
                         'scope': 'all', 'sequence': seq, 'company_id': self.company.id, 'note': note,
                         'active': True})
        Plan = self.env['dmag.care.plan']
        self.care_plans = []
        for seq, (name, price, months, lines) in enumerate(D.CARE_PLANS, start=1):
            self.care_plans.append(Plan.create({
                'name': name, 'sequence': seq, 'price': price, 'duration_months': months,
                'company_id': self.company.id,
                'line_ids': [(0, 0, {'product_id': self.svc[c].id, 'quantity': q}) for c, q in lines],
            }))
        self.stats['policies'] = len(D.COMMISSION_RULES) + len(D.CARE_PLANS)

    def _create_compliance(self):
        Equipment = self.env['dmag.equipment']
        self.equipment = {}
        manager = self.users['manager']
        for key, name, cat, brand, serial, location, insp, maint in D.COMPLIANCE_EQUIPMENT:
            vals = {'name': name, 'category': cat, 'brand': brand, 'serial_no': serial, 'location': location,
                    'company_id': self.company.id, 'responsible_id': manager.id,
                    'last_maintenance_date': self.today - relativedelta(months=maint)}
            if insp:
                vals['last_inspection_date'] = self.today - relativedelta(months=insp)
            self.equipment[key] = Equipment.create(vals)
        for chair in self.chairs[:2]:
            Equipment.create({'name': 'Thiết bị ghế – %s' % chair.name, 'category': 'chair', 'chair_id': chair.id,
                              'company_id': self.company.id, 'responsible_id': manager.id,
                              'last_maintenance_date': self.today - relativedelta(months=4)})
        Doc = self.env['dmag.compliance.doc']
        compliance_module = 'dmag_dental_compliance'
        for name, type_x, number, issuer, issued_ago, expires_in, eq in D.COMPLIANCE_DOCS:
            doc_type = self.ref('%s.%s' % (compliance_module, type_x))
            if not doc_type:
                continue
            vals = {'name': name, 'type_id': doc_type.id, 'number': number, 'issuer': issuer,
                    'company_id': self.company.id, 'responsible_id': manager.id,
                    'issue_date': self.today - timedelta(days=issued_ago)}
            if expires_in is None:
                vals['no_expiry'] = True
            else:
                vals['expiry_date'] = self.today + timedelta(days=expires_in)
            if eq:
                vals['equipment_id'] = self.equipment[eq].id
            Doc.create(vals)
        practice_type = self.ref('%s.doc_type_practice_license' % compliance_module)
        if practice_type:
            for key in ('doctor', 'doctor2', 'doctor3'):
                prac = self.prac.get(key)
                if not prac:
                    continue
                Doc.create({'name': 'Giấy phép hành nghề – %s %s' % (prac.name, D.SAMPLE),
                            'type_id': practice_type.id, 'number': prac.license_number, 'issuer': 'Sở Y tế TP.HCM',
                            'practitioner_id': prac.id, 'company_id': self.company.id,
                            'responsible_id': manager.id, 'issue_date': prac.license_issue_date,
                            'expiry_date': prac.license_expiry_date})
        Set = self.env['dmag.instrument.set']
        self.instrument_sets = Set.create([
            {'name': 'Bộ khám cơ bản – gương, kẹp, thám trâm (demo)', 'code': 'DM-KHAM', 'category': 'exam',
             'company_id': self.company.id},
            {'name': 'Bộ nhổ răng / tiểu phẫu (demo)', 'code': 'DM-NHO', 'category': 'surgery',
             'company_id': self.company.id},
        ])
        self.stats['compliance_docs'] = Doc.search_count([('id', '>', self.watermarks.get('dmag.compliance.doc', 0))])

    def _create_hr(self):
        Employee = self.env['hr.employee']
        Grade = self.env['dmag.job.grade']
        for key, _login, name, _group, job_x, grade_code in D.USERS:
            user = self.users[key]
            employee = user.employee_ids[:1]
            job = self.ref(job_x)
            vals = {'name': name, 'user_id': user.id, 'company_id': self.company.id,
                    'work_email': user.email, 'mobile_phone': '09%08d' % self.rng.randint(10000000, 99999999),
                    'barcode': 'DM%04d' % (len(self.users) * 10 + list(self.users).index(key))}
            if job:
                vals['job_id'] = job.id
                vals['job_title'] = job.name
            if not employee:
                employee = Employee.create(vals)
            grade = Grade.search([('code', '=', grade_code),
                                  ('company_id', 'in', (self.company.id, False))], limit=1)
            if grade and 'dmag_grade_id' in employee._fields:
                self.try_('Gán bậc 3P', employee.write, {'dmag_grade_id': grade.id})
            if key in self.prac:
                self.prac[key].employee_id = employee
        self.stats['employees'] = len(self.users)

    # ======================================================================== lịch nghỉ luân phiên
    def _rotation(self):
        """Phòng khám mở cửa cả tuần (Chủ nhật đông khách); nhân sự nghỉ luân phiên ngày thường: Quản lý demo bấm
        "Xếp lịch nghỉ luân phiên tự động" (nút thật), một nghỉ phép đã duyệt gây thiếu bác sĩ (ô đỏ trên lịch), một đổi
        ca, một yêu cầu nghỉ chờ duyệt, một nghỉ phép đã qua (lịch sử khám tôn trọng ngày nghỉ của từng bác sĩ)."""
        if 'dmag.staff.rotation' not in self.env:
            return
        company = self.company
        schedule = self.env['dmag.clinic.schedule']._get_for_company(company)
        if not schedule.line_ids.filtered(lambda l: l.weekday == '6'):
            schedule.write({'line_ids': [(0, 0, {'weekday': '6', 'hour_from': 8.0, 'hour_to': 12.0}),
                                         (0, 0, {'weekday': '6', 'hour_from': 13.5, 'hour_to': 20.0})]})
            schedule.message_post(body='Demo: mở cửa Chủ nhật (quyết định 11/10/2026 – Chủ nhật đông khách).')
            self.stats['schedule_sunday_added'] = 1
        Rot = self.env['dmag.staff.rotation']
        for seq, (key, role) in enumerate(D.ROTATION, start=1):
            user = self.users.get(key)
            if not user:
                continue
            prac = self.prac.get(key)
            domain = [('company_id', '=', company.id)] + ([('practitioner_id', '=', prac.id)] if prac
                                                          else [('user_id', '=', user.id)])
            if not Rot.search(domain, limit=1):
                Rot.create({'name': user.name, 'role': role, 'practitioner_id': prac.id if prac else False,
                            'user_id': user.id, 'company_id': company.id, 'sequence': seq * 10})
        res = Rot.with_user(self.users['manager']).with_company(company).action_generate_rotation()
        for warning in res['warnings']:
            self.warnings.append('Lịch luân phiên: %s' % warning)
        self._schedule_info = None
        info = self.clinic_schedule
        roster = info.roster
        members = {m.user_id.id: m for m in Rot.search([('company_id', '=', company.id)])}

        def member(key):
            return members.get(self.users[key].id)

        def next_off(key, start, skip=0):
            m = member(key)
            days = [start + timedelta(days=i) for i in range(1, 22)]
            offs = [d for d in days if info.is_open_day(d) and not roster.is_on_duty(m.id, d)]
            return offs[skip] if len(offs) > skip else None

        Leave = self.env['dmag.staff.leave']
        manager = self.users['manager']
        # (1) nghỉ phép đã duyệt trùng ngày bác sĩ khác nghỉ luân phiên → thiếu bác sĩ (cảnh báo đỏ trên lịch tháng)
        day = next_off('doctor3', self.today + timedelta(days=3))
        if day:
            leave = Leave.with_user(self.users['doctor2']).with_company(company).create({
                'member_id': member('doctor2').id, 'date_from': day, 'date_to': day,
                'reason': 'Hội thảo chỉnh nha ' + D.SAMPLE})
            leave.with_user(manager).action_approve()
        # (2) đổi ca đã duyệt: phụ tá nghỉ ngày khác, đi làm bù ngày nghỉ cố định
        regular = next_off('assistant2', self.today + timedelta(days=1))
        if regular:
            swap_day = regular + timedelta(days=1)
            while swap_day.weekday() == 6 or not info.is_open_day(swap_day):
                swap_day += timedelta(days=1)
            Leave.with_user(self.users['assistant2']).with_company(company).create({
                'member_id': member('assistant2').id, 'kind': 'swap', 'date_from': swap_day, 'swap_date': regular,
                'reason': 'Đổi ca với chị Trang ' + D.SAMPLE}).with_user(manager).action_approve()
        # (3) yêu cầu nghỉ chờ duyệt: tư vấn viên xin nghỉ đúng ngày lễ tân kia nghỉ luân phiên → cảnh báo nếu duyệt
        day = next_off('receptionist', self.today + timedelta(days=2))
        if day:
            Leave.with_user(self.users['consultant']).with_company(company).request_leave({
                'member_id': member('consultant').id, 'date_from': str(day), 'reason': 'Việc gia đình ' + D.SAMPLE})
        # (4) nghỉ phép đã qua của bác sĩ chính (lịch sử không có ca của bác sĩ hôm đó)
        past = self.today - timedelta(days=16)
        while past.weekday() == 6 or not roster.is_on_duty(member('doctor').id, past):
            past -= timedelta(days=1)
        Leave.with_user(self.users['doctor']).with_company(company).create({
            'member_id': member('doctor').id, 'date_from': past, 'date_to': past,
            'reason': 'Hội thảo implant ' + D.SAMPLE}).with_user(manager).action_approve()
        self._schedule_info = None
        self.stats['rotation_members'] = len(members)
        self.stats['rotation_leaves'] = Leave.search_count([('company_id', '=', company.id)])

    # ======================================================================== patients
    def _create_patients(self):
        Partner = self.env['res.partner']
        Family = self.env['dmag.patient.family']
        families = {k: Family.create({'name': v, 'company_id': self.company.id}) for k, v in D.FAMILIES.items()}
        vn = self.ref('base.vn')
        rng = self.rng
        phones = set()
        for idx, spec in enumerate(D.PATIENTS):
            (key, name, gender, birth, job, city, source, fam, head, guardian, alerts, allergy, history,
             referrer) = spec
            if isinstance(birth, str):
                years = int(birth.split(':')[1])
                birthdate = self.today - relativedelta(years=years, days=rng.randint(20, 300))
            else:
                birthdate = datetime(birth, rng.randint(1, 12), rng.randint(1, 28)).date()
            while True:
                phone = '09%d%d %03d %03d' % (rng.choice([0, 1, 3, 6, 7, 8]), rng.randint(0, 9),
                                              rng.randint(0, 999), rng.randint(0, 999))
                if phone not in phones:
                    phones.add(phone)
                    break
            province = '079' if city == 'hcm' else '001'
            century = 0 if birthdate.year < 2000 else 2
            gender_digit = century + (1 if gender == 'female' else 0)
            citizen = '%s%d%02d%06d' % (province, gender_digit, birthdate.year % 100, rng.randint(0, 999999))
            street = rng.choice(D.HCM_STREETS if city == 'hcm' else D.HN_STREETS)
            vals = {
                'name': name,
                'is_patient': True,
                'company_id': self.company.id,
                'mobile': phone,
                'birthdate': birthdate,
                'gender': gender,
                'citizen_id': citizen,
                'street': street,
                'city': 'TP. Hồ Chí Minh' if city == 'hcm' else 'Hà Nội',
                'country_id': vn.id if vn else False,
                'occupation': job or False,
                'customer_source_id': self.base_ref(source).id,
                'patient_alert_ids': [(6, 0, [self.base_ref(a).id for a in alerts])],
                'allergy': allergy or False,
                'medical_history': history or False,
                'data_consent': True,
                'tz': TZ_NAME,
                'lang': self.users['receptionist'].lang or False,
            }
            if 'identity_type' in Partner._fields and guardian and self.today.year - birthdate.year < 14:
                vals['identity_type'] = 'birth_cert'
            if 'ethnicity' in Partner._fields:
                vals['ethnicity'] = 'Kinh'
            if fam:
                vals['dental_family_id'] = families[fam].id
            if 'alert_pregnant' in alerts:
                vals['is_pregnant'] = True
            partner = Partner.create(vals)
            if fam and head:
                families[fam].head_id = partner
            self.patients[key] = partner
        # quan hệ cần bệnh nhân khác: giám hộ, người giới thiệu
        for spec in D.PATIENTS:
            key, guardian, referrer = spec[0], spec[9], spec[13]
            vals = {}
            if guardian:
                vals['guardian_id'] = self.patients[guardian].id
                vals['guardian_relation'] = 'Mẹ' if self.patients[guardian].gender == 'female' else 'Bố'
            if referrer:
                vals['referrer_id'] = self.patients[referrer].id
            if vals:
                self.patients[key].with_context(dmag_workflow=True).write(vals)
        self.stats['patients'] = len(self.patients)
        # kịch bản điều trị cho từng bệnh nhân
        adult_scenarios = ['caries', 'endo_crown', 'wisdom', 'implant', 'ortho', 'whitening', 'veneer', 'perio',
                           'caries', 'endo_crown', 'implant', 'hygiene', 'caries', 'perio', 'splint', 'checkup']
        idx = 0
        for spec in D.PATIENTS:
            key = spec[0]
            ps = PatientState(key, self.patients[key], spec)
            if ps.partner.age < 13:
                ps.scenario = 'kid' if ps.partner.age < 11 else 'ortho'
            elif ps.partner.age >= 60 and idx % 2:
                ps.scenario = 'implant'
                idx += 1
            else:
                ps.scenario = adult_scenarios[idx % len(adult_scenarios)]
                idx += 1
            if ps.scenario in ('ortho', 'kid'):
                ps.doctor_key = 'doctor2'
            elif ps.scenario in ('implant', 'wisdom'):
                ps.doctor_key = 'doctor'
            else:
                ps.doctor_key = self.rng.choice(['doctor', 'doctor2', 'doctor3'] if 'doctor3' in self.prac
                                                else ['doctor', 'doctor2'])
            ps.decision = 'pending' if self.rng.random() < 0.25 else 'accept'
            ps.first_day_offset = self.rng.randint(0, 3) if len(self.pstates) < 12 else \
                self.rng.randint(0, HISTORY_DAYS - 12)
            self.pstates.append(ps)

    # ======================================================================== visit primitives
    def _book(self, ps, start, codes, doctor_key, chair, reason, plan=False, booked_before=None, confirm=True):
        duration = sum(self.svc[c].dental_duration or 0 for c in codes) or 30
        start = self.fit_schedule(start, duration)
        booked_at = start - (booked_before if booked_before is not None
                             else timedelta(days=self.rng.randint(1, 6), hours=self.rng.randint(0, 6)))
        self.at(min(booked_at, start))
        vals = {
            'patient_id': ps.partner.id,
            'doctor_id': self.prac[doctor_key].id,
            'assistant_id': self.prac['assistant'].id,
            'chair_id': chair.id if chair else False,
            'service_ids': [(6, 0, [self.svc[c].id for c in codes])],
            'scheduled_start': start,
            'reason': reason,
            'source_id': ps.partner.customer_source_id.id,
            'treatment_plan_id': plan.id if plan else False,
            'company_id': self.company.id,
        }
        if 'dmag_consultant_id' in self.env['dmag.dental.visit']._fields and plan:
            vals['dmag_consultant_id'] = self.users['consultant'].id
        visit = self.M('dmag.dental.visit', 'receptionist').create(vals)
        self.booked_at[visit.id] = min(booked_at, start)
        self.stats['visits'] += 1
        if confirm:
            self.at(min(booked_at + timedelta(hours=2), start))
            visit.action_confirm()
        return visit

    def _check_in(self, visit, when):
        self.at(when)
        self.as_user(visit, 'receptionist').action_check_in()

    def _start(self, visit, when, chair):
        self.at(when)
        self.as_user(visit, 'assistant').action_start(chair_id=chair.id if chair else visit.chair_id.id)
        batch = self.batches.get(self.to_local(when).date())
        if batch:
            self.try_('Gắn mẻ tiệt khuẩn', self.as_user(visit, 'assistant').write,
                      {'sterilization_batch_ids': [(4, batch.id)]})

    def _chart(self, visit, ps, doctor_key, findings, teeth):
        Entry = self.M('dmag.dental.chart.entry', doctor_key)
        created = {}
        for cond, tooth_idx, surfaces in findings:
            if tooth_idx >= len(teeth):
                continue
            condition = self.base_ref(cond)
            ids = Entry.add_from_chart(ps.partner.id, [teeth[tooth_idx]], condition.id, surfaces=surfaces,
                                       layer='existing', visit_id=visit.id)
            created.setdefault(teeth[tooth_idx], []).extend(ids)
        return created

    def _procedure(self, visit, doctor_key, code=None, teeth=None, surfaces=None, plan_line=None, lots=None):
        Procedure = self.M('dmag.dental.procedure', doctor_key)
        product = plan_line.product_id if plan_line else self.svc[code]
        kwargs = {'teeth': teeth or [], 'surfaces': surfaces or [], 'plan_line_id': plan_line.id if plan_line else False,
                  'done': True}
        if lots:
            kwargs['lot_ids'] = [lot.id for lot in lots]
        res = Procedure.add_from_workspace(visit.id, product.id, **kwargs)
        self.stats['procedures'] += 1
        self._extra_material(res, doctor_key)
        return res

    # ------------------------------------------------------------------ tình huống cho AI-08 (không đến)
    @staticmethod
    def _is_online(partner):
        name = (partner.customer_source_id.name or '').lower()
        return any(w in name for w in ('online', 'zalo', 'web', 'facebook'))

    @staticmethod
    def _noshow_prob(ps, kind, online, lead, confirmed):
        """Khả năng không đến theo các yếu tố thật của phòng khám: đặt online, đặt trước lâu, chưa xác nhận,
        khách mới, từng bỏ hẹn – để mô hình AI-08 học được quy luật (tỷ lệ chung ~15–20 %)."""
        p = 0.01
        p += 0.10 if online else 0.0
        p += 0.08 if kind == 'first' else 0.0
        p += 0.08 if lead.days >= 7 else 0.0
        p += 0.22 if not confirmed else 0.0
        # từng bỏ hẹn: ảnh hưởng giảm dần khi khách đã đến đều đặn nhiều lần sau đó
        p += min(0.25, 0.5 * ps.noshows / (ps.noshows + ps.visits + 1))
        return min(p, 0.65)

    # ------------------------------------------------------------------ tình huống cho AI-15 (bất thường)
    def _plan_discounts(self, plan, doctor_key):
        """Giảm giá trên kế hoạch như thực tế: bác sĩ 2 hay "chiều khách" (10 % – sát hạn mức) ở phần lớn dịch vụ,
        bác sĩ chính thỉnh thoảng giảm 5 % – để AI-15 có số liệu thật để so sánh."""
        rng = self.rng_ai
        for line in plan.option_ids.line_ids:
            roll = rng.random()
            if doctor_key == 'doctor2' and roll < 0.7:
                self.try_('Giảm giá', self.as_user(line, doctor_key).write, {'discount': 10.0})
            elif doctor_key != 'doctor2' and roll < 0.1:
                self.try_('Giảm giá', self.as_user(line, doctor_key).write, {'discount': 5.0})

    def _extra_material(self, proc_res, doctor_key):
        """Vật tư dùng thêm ngoài định mức (hỏng vật liệu, ca khó) – bác sĩ 2 gặp nhiều hơn."""
        if 'dmag.material.usage' not in self.env or not isinstance(proc_res, dict) or not proc_res.get('id'):
            return
        if self.rng_ai.random() >= (0.3 if doctor_key == 'doctor2' else 0.05):
            return
        proc = self.env['dmag.dental.procedure'].browse(proc_res['id'])
        reqs = [(p, q) for p, q in proc._dmag_material_requirements().items() if p.tracking == 'none' and q > 0]
        if not reqs:
            return
        product, qty = reqs[self.rng_ai.randrange(len(reqs))]
        reason = self.rng_ai.choice(['Vật liệu bị nhiễm ẩm, làm lại', 'Ca khó, cần thêm', 'Rơi dụng cụ, thay mới',
                                     'Khách nhạy cảm, gây tê bổ sung'])
        self.try_('Vật tư phát sinh', self.M('dmag.material.usage', doctor_key).create, {
            'procedure_id': proc.id, 'product_id': product.id,
            'quantity': max(1.0, round(qty * self.rng_ai.choice([1.0, 1.5, 2.0]))) if product.uom_id.rounding >= 1
            else round(qty * self.rng_ai.choice([1.0, 1.5, 2.0]), 2),
            'reason': reason + ' ' + D.SAMPLE})

    def _record(self, visit, doctor_key, complaint, exam, assessment, diagnoses, note, advice):
        diag_ids = [self.base_ref(d).id for d in diagnoses]
        rng = self.rng
        values = {
            'chief_complaint': complaint,
            'examination': exam,
            'assessment': assessment,
            'treatment_note': note,
            'advice': advice,
            'pain_score': rng.choice([0, 0, 1, 1, 2, 3]),
            'diagnosis_ids': diag_ids,
            'present_illness': complaint,
            'pulse': rng.randint(68, 92),
            'temperature': rng.choice([36.5, 36.6, 36.8, 37.0]),
            'bp_systolic': rng.randint(110, 135),
            'bp_diastolic': rng.randint(70, 85),
            'respiratory_rate': rng.randint(16, 20),
            'general_exam': 'Tỉnh, tiếp xúc tốt, da niêm hồng.',
            'exam_extraoral': 'Mặt cân đối, không sưng, hạch dưới hàm không sờ thấy.',
            'exam_intraoral': exam,
            'exam_periodontal': 'Nướu hồng, cao răng ít.' if 'nướu' not in exam else exam,
            'primary_diagnosis_id': diag_ids[0] if diag_ids else False,
        }
        self.as_user(visit, doctor_key).save_record_from_workspace(values)

    def _finish(self, visit, doctor_key, when, sign=True):
        self.at(when)
        self.as_user(visit, doctor_key).action_done()
        if sign:
            self._sign(visit, doctor_key, when + timedelta(minutes=self.rng.randint(2, 15)))

    def _sign(self, visit, doctor_key, when):
        """Bác sĩ ký bệnh án (ký số MySign giả lập cho các lượt khám gần đây)."""
        self.at(when)
        recent = (self.today - self.to_local(when).date()).days <= ESIGN_RECENT_DAYS
        visit_doc = self.as_user(visit, doctor_key).with_context(dmag_demo_skip_esign=not recent)
        visit_doc.action_sign_record()
        self.stats['signed'] += 1
        if recent:
            self.stats['esigned'] += 1

    RX_BY_SERVICE = {
        'extract_wisdom': 'Sau nhổ răng khôn (mẫu)',
        'extract': 'Sau nhổ răng khôn (mẫu)',
        'implant_kr': 'Sau cấy ghép Implant (mẫu)',
        'implant_ch': 'Sau cấy ghép Implant (mẫu)',
        'endo_molar': 'Viêm tủy cấp (mẫu)',
        'endo_front': 'Viêm tủy cấp (mẫu)',
        'perio': 'Viêm nướu – nha chu (mẫu)',
    }

    def _rx_for(self, visit):
        """Đơn mẫu phù hợp với thủ thuật đã làm (một số ca cạo vôi kèm đơn viêm nướu)."""
        codes = [self._svc_code(p) for p in visit.procedure_ids.mapped('product_id')]
        for code in codes:
            if code in self.RX_BY_SERVICE:
                return self.RX_BY_SERVICE[code]
        if 'scaling' in codes and self.rng.random() < 0.35:
            return 'Viêm nướu – nha chu (mẫu)'
        if 'exam' in codes and self.rng.random() < 0.12:
            return 'Viêm tủy cấp (mẫu)' if visit.diagnosis_ids.filtered(lambda d: d.code.startswith('K04')) \
                else 'Viêm nướu – nha chu (mẫu)'
        return False

    def _prescribe(self, visit, doctor_key, template_name, when):
        template = self.rx_templates.get(template_name)
        if not template or visit.patient_id.age < 6:
            return False
        self.at(when)
        doc_visit = self.as_user(visit, doctor_key)
        rx = doc_visit.save_prescription_from_workspace({'template_id': template.id})
        res = doc_visit.issue_prescription(rx['id'])
        self.stats['prescriptions'] += 1
        return res

    def _pay(self, visit, when, amount=False, method=None):
        """Thu tiền tại quầy (tiền mặt / thẻ / chuyển khoản – chuyển khoản đi qua SePay giả lập)."""
        self.at(when)
        visit.invalidate_recordset(['amount_due', 'payment_status'])
        recep_visit = self.as_user(visit, 'receptionist')
        if visit.payment_status == 'to_invoice':
            recep_visit._create_and_post_invoices()
            visit.invalidate_recordset(['amount_due', 'payment_status'])
        due = visit.amount_due
        if due <= 0:
            return 0.0
        amount = min(amount or due, due)
        method = method or self.rng.choices(['cash', 'transfer', 'card'], weights=[45, 40, 15])[0]
        if method == 'transfer' and 'dmag.payment.request' in self.env:
            qr = recep_visit.get_payment_qr(amount)
            request = self.M('dmag.payment.request', 'receptionist').browse(qr['request_id'])
            request.action_simulate_transfer(amount)
            self.stats['sepay_transfers'] += 1
        else:
            recep_visit.register_payment(method, amount)
        self.stats['payments'] += 1
        return amount

    def _no_show(self, visit, when):
        self.at(when)
        self.as_user(visit, 'receptionist').write({'cancel_reason': 'Không liên lạc được, khách không đến'})
        self.as_user(visit, 'receptionist').action_no_show()
        self.stats['no_show'] += 1

    def _cancel(self, visit, when):
        self.at(when)
        recep = self.as_user(visit, 'receptionist')
        recep.write({'cancel_reason': self.rng.choice(D.CANCEL_REASONS)})
        recep.action_cancel()
        self.stats['cancelled'] += 1

    def _nps(self, visit):
        Nps = self.env['dmag.nps.response']
        resp = Nps._dmag_create_for_visit(visit, channel='zns')
        score = self.rng.choices([10, 9, 8, 7, 5, 3], weights=[38, 28, 14, 10, 6, 4])[0]
        resp.submit(score, self.rng.choice(D.NPS_COMMENTS[score]), channel='zns')
        self.stats['nps'] += 1
        if hasattr(visit.patient_id, 'dmag_loyalty_award_survey'):
            self.try_('Điểm khảo sát', visit.patient_id.dmag_loyalty_award_survey, key='nps:%s' % resp.id)

    # ======================================================================== history
    def _sterilization_batches(self, days):
        Batch = self.M('dmag.sterilization.batch', 'assistant')
        autoclave = self.equipment.get('autoclave') if hasattr(self, 'equipment') else False
        if not autoclave:
            return
        for n, day in enumerate(days[-14:]):
            self.at(self.local_dt(day, 7, 15))
            batch = Batch.create({
                'autoclave_id': autoclave.id, 'cycle_number': str(2400 + n), 'pack_count': self.rng.randint(8, 16),
                'chemical_result': 'pass', 'bowie_dick_result': 'pass',
                'biological_result': 'pass' if day < self.today - timedelta(days=2) else 'pending',
                'instrument_set_ids': [(6, 0, self.instrument_sets.ids)],
                'company_id': self.company.id,
            })
            batch.action_release()
            self.batches[day] = batch
        self.stats['sterilization_batches'] = len(self.batches)

    def _history(self):
        start_day = self.today - timedelta(days=HISTORY_DAYS)
        days = list(self.working_days(start_day, self.today - timedelta(days=1)))
        self.try_('Mẻ tiệt khuẩn', self._sterilization_batches, days)
        self._care_subscriptions(days)
        rng = self.rng
        for day_idx, day in enumerate(days):
            self.run_events(self.local_dt(day, 7, 0))
            n = rng.randint(*VISITS_PER_DAY)
            if day.weekday() == 6:  # Chủ nhật đông khách nhất (~1,5–2× ngày thường)
                n += rng.randint(*D.SUNDAY_EXTRA)
            todo = self._pick_patients(day, day_idx, n)
            # nửa giờ trong ca làm việc của ngày (Lịch làm việc phòng khám), không quá 18:30
            starts = [m for m in self.open_starts(day) if m <= 18 * 60 + 30] or self.open_starts(day)
            hour_slots = sorted(rng.sample(starts, min(len(todo), len(starts))))
            for (ps, kind), slot in zip(todo, hour_slots):
                start = self.local_dt(day, slot // 60, slot % 60 + rng.choice([0, 0, 5, 10]))
                self._simulate(ps, kind, start, final=True)
            if day_idx >= len(days) - 6 and 'dmag.cash.closing' in self.env:
                self.schedule(self.local_dt(day, 19, 40), self._cash_closing, day)
        self.run_events(self.local_dt(self.today, 7, 0))

    def doctor_on_duty(self, doctor_key, day):
        """Bác sĩ của khách trực ngày ``day`` (Lịch nghỉ luân phiên: nghỉ hằng tuần, nghỉ phép đã duyệt)."""
        prac = self.prac.get(doctor_key)
        return not prac or prac.works_on(day, self.clinic_schedule)

    def _pick_patients(self, day, day_idx, n):
        """Chọn bệnh nhân trong ngày: đến hẹn kế hoạch → khách mới → khách quay lại / tái khám – chỉ khách có bác sĩ
        phụ trách đang trực ngày đó (bác sĩ nghỉ luân phiên → khách hẹn ngày khác)."""
        rng = self.rng
        chosen = []
        off = {key for key in self.prac if not self.doctor_on_duty(key, day)}
        taken = {ps.key for ps in self.pstates if ps.doctor_key in off}

        def add(ps, kind):
            chosen.append((ps, kind))
            taken.add(ps.key)

        due = [ps for ps in self.pstates if ps.next_due and ps.next_due <= day and ps.last_visit != day
               and ps.key not in taken]
        rng.shuffle(due)
        for ps in due[:max(n - 2, 1)]:
            add(ps, 'treatment')
        new = [ps for ps in self.pstates if not ps.visits and ps.first_day_offset <= day_idx
               and ps.key not in taken]
        for ps in new[:max(n - len(chosen) - 1, 1)]:
            add(ps, 'first')
        for gap in ((14, 8, 4) if day.weekday() == 6 else (14, 8)):
            if len(chosen) >= n:
                break
            others = [ps for ps in self.pstates if ps.visits and ps.key not in taken
                      and (not ps.last_visit or (day - ps.last_visit).days > gap)
                      and (not ps.next_due or ps.next_due > day + timedelta(days=3))]
            rng.shuffle(others)
            for ps in others[:n - len(chosen)]:
                add(ps, 'return')
        return chosen[:n]

    def _chair_for(self, ps):
        if ps.scenario in ('ortho', 'kid'):
            return self.chairs[3]
        if ps.scenario in ('implant', 'wisdom'):
            return self.chairs[2]
        return self.chairs[self.rng.randint(0, 1)]

    def _simulate(self, ps, kind, start, final=True, stop_at=None):
        """Mô phỏng trọn một lượt khám. ``stop_at``: trạng thái dừng (cho bảng điều phối hôm nay)."""
        rng = self.rng
        outcome = 'done'
        # Đặc điểm lúc đặt lịch (dùng hạt giống AI riêng): kênh online, đặt trước bao lâu, đã xác nhận chưa
        online = self._is_online(ps.partner)
        far = online and kind == 'first' and self.rng_ai.random() < 0.6 or self.rng_ai.random() < 0.12
        lead = timedelta(days=self.rng_ai.randint(8, 15) if far else self.rng_ai.randint(1, 6),
                         hours=self.rng_ai.randint(0, 6))
        confirmed = self.rng_ai.random() < (0.55 if online else 0.92)
        if final and not stop_at:
            roll = rng.random()
            if 0.06 <= roll < 0.11:
                outcome = 'cancel'
            elif self.rng_ai.random() < self._noshow_prob(ps, kind, online, lead, confirmed):
                outcome = 'no_show'
        if kind == 'treatment' and not ps.todo_lines():
            if ps.scenario == 'ortho' and ps.ortho_visit:
                kind = 'ortho'
            else:
                ps.next_due = False
                kind = 'return'
        codes, reason, plan = self._visit_plan(ps, kind)
        chair = self._chair_for(ps)
        doctor_key = ps.doctor_key
        visit = self._book(ps, start, codes, doctor_key, chair, reason, plan=plan,
                           booked_before=lead if not stop_at else None,
                           confirm=stop_at != 'draft' and (confirmed or bool(stop_at)))
        if stop_at in ('draft', 'confirmed'):
            return visit
        day = self.to_local(start).date()
        if outcome == 'cancel':
            self._cancel(visit, start - timedelta(hours=rng.randint(2, 20)))
            if ps.next_due:
                ps.next_due = day + timedelta(days=rng.randint(3, 7))
            return visit
        if outcome == 'no_show':
            ps.noshows += 1
            self._no_show(visit, start + timedelta(minutes=45))
            if ps.next_due:
                ps.next_due = day + timedelta(days=rng.randint(3, 7))
            return visit
        checkin = start - timedelta(minutes=rng.randint(0, 15))
        self._check_in(visit, checkin)
        if stop_at == 'arrived':
            return visit
        chair_time = start + timedelta(minutes=rng.choice([2, 5, 8, 10, 15, 25]))
        self._start(visit, chair_time, chair)
        if stop_at == 'in_chair':
            # đang điều trị: đã khám, ghi sơ bộ, chưa hoàn tất
            self.at(chair_time + timedelta(minutes=5))
            if kind == 'first':
                self._first_visit_clinical(visit, ps, doctor_key, chair_time, partial=True)
            return visit
        if kind == 'first':
            self._first_visit_clinical(visit, ps, doctor_key, chair_time)
        elif kind in ('treatment', 'ortho'):
            self._treatment_clinical(visit, ps, doctor_key, chair_time)
        else:
            self._return_clinical(visit, ps, doctor_key, chair_time)
        done_time = chair_time + timedelta(minutes=max(visit.duration, 20) + rng.randint(-5, 15))
        self._finish(visit, doctor_key, done_time, sign=False)
        rx_name = self._rx_for(visit)
        if rx_name:
            self.try_('Kê đơn thuốc', self._prescribe, visit, doctor_key, rx_name,
                      done_time + timedelta(minutes=2))
        self._sign(visit, doctor_key, done_time + timedelta(minutes=rng.randint(4, 15)))
        ps.visits += 1
        ps.last_visit = day
        if stop_at == 'done_unpaid':
            return visit
        self._settle(visit, ps, done_time + timedelta(minutes=rng.randint(3, 12)))
        if stop_at is None and rng.random() < 0.55:
            self.schedule(done_time + timedelta(days=2, hours=rng.randint(0, 5)), self._nps, visit)
        return visit

    def _visit_plan(self, ps, kind):
        """(dịch vụ dự kiến, lý do, kế hoạch) của lượt khám."""
        if kind == 'treatment':
            lines = ps.todo_lines()
            phase = min(lines.mapped('phase'))
            phase_lines = lines.filtered(lambda l: l.phase == phase)
            codes = [code for code, prod in self.svc.items() if prod in phase_lines.mapped('product_id')]
            if ps.scenario == 'ortho' and ps.ortho_visit:
                codes = ['ortho_check']
            return codes, 'Điều trị theo kế hoạch %s' % ps.plan.name, ps.plan
        if kind == 'first':
            scenario = D.SCENARIOS.get(ps.scenario)
            if scenario:
                codes = ['exam', 'xray_pano'] + (['cbct'] if ps.scenario == 'implant' else [])
                return codes, scenario['complaint'], False
            simple = D.SIMPLE_VISITS[ps.scenario]
            return simple[5], simple[0], False
        if ps.is_child:
            return ['exam', 'filling_kid'], 'Khám định kỳ cho bé', False
        if ps.decision == 'later' and ps.plan and ps.plan.state == 'presented':
            return ['exam'], 'Tư vấn lại kế hoạch điều trị', ps.plan
        if self.rng.random() < 0.3:
            return ['exam', 'filling'], 'Ê buốt răng, kiểm tra sâu răng', False
        return ['exam', 'scaling'], 'Cạo vôi, kiểm tra định kỳ', False

    def _first_visit_clinical(self, visit, ps, doctor_key, when, partial=False):
        rng = self.rng
        scenario = D.SCENARIOS.get(ps.scenario)
        if not scenario:
            simple = D.SIMPLE_VISITS[ps.scenario]
            tooth = rng.choice(['54', '55', '64', '65', '74', '75', '84', '85'])
            fmt = {'t0': tooth}
            if ps.scenario == 'kid':
                self._chart(visit, ps, doctor_key, [('condition_caries', 0, ['O'])], [tooth])
            else:
                self._chart(visit, ps, doctor_key, [('condition_calculus', 0, [])], ['41'])
            self._record(visit, doctor_key, simple[1], simple[2].format(**fmt), simple[3].format(**fmt), simple[4],
                         'Khám, tư vấn, thực hiện %s.' % ', '.join(self.svc[c].name for c in simple[5][1:]),
                         'Chải răng 2 lần/ngày, tái khám sau 6 tháng.')
            if partial:
                return
            for code in simple[5]:
                if self.svc[code].dental_requires_tooth:
                    self._procedure(visit, doctor_key, code, teeth=[tooth], surfaces=['O'])
                else:
                    self._procedure(visit, doctor_key, code)
            return
        teeth = list(rng.choice(scenario['teeth']))
        ps.teeth = teeth
        fmt = {'t%d' % i: t for i, t in enumerate(teeth)}
        fmt.setdefault('t0', '')
        fmt.setdefault('t1', '')
        findings = self._chart(visit, ps, doctor_key, scenario['findings'], teeth)
        ps.findings = findings
        self._record(visit, doctor_key, scenario['complaint'], scenario['exam'].format(**fmt),
                     scenario['assessment'].format(**fmt), scenario['diagnoses'],
                     'Khám, chụp phim, tư vấn kế hoạch: %s.' % scenario['title'],
                     'Tái khám theo kế hoạch điều trị đã tư vấn.')
        for code in visit.service_ids.mapped('default_code'):
            svc_code = code.replace('DM-', '').lower()
            if svc_code in self.svc:
                self._procedure(visit, doctor_key, svc_code)
        self.at(when + timedelta(minutes=15))
        self._make_plan(visit, ps, doctor_key, scenario, teeth)
        if partial:
            return
        # Điều trị ngay giai đoạn 1 nếu đơn giản và khách đồng ý
        if ps.plan and ps.plan.accepted_option_id and ps.scenario in ('caries', 'perio', 'whitening') \
                and rng.random() < 0.6:
            self._do_phase(visit, ps, doctor_key, when + timedelta(minutes=25))

    def _make_plan(self, visit, ps, doctor_key, scenario, teeth):
        rng = self.rng
        options = []
        for name, recommended, summary, months, deposit, lines in scenario['options']:
            line_vals = []
            for code, tooth_idx, surfaces, phase in lines:
                line_teeth = [teeth[i] for i in tooth_idx if i < len(teeth)]
                finding_ids = []
                for tooth in line_teeth:
                    finding_ids += ps.findings.get(tooth, [])
                line_vals.append({'product_id': self.svc[code].id, 'teeth': line_teeth, 'surfaces': surfaces,
                                  'phase': phase, 'finding_ids': finding_ids})
            options.append({'name': name, 'summary': summary, 'installment_months': months,
                            'is_recommended': recommended, 'title': scenario['title'], 'lines': line_vals})
        Plan = self.M('dmag.treatment.plan', doctor_key)
        res = Plan.create_from_workspace(ps.partner.id, visit.id, options)
        plan = self.env['dmag.treatment.plan'].browse(res['id'])
        plan_doc = self.as_user(plan, doctor_key)
        self._plan_discounts(plan, doctor_key)
        vals = {}
        if 'dmag_consultant_id' in plan._fields:
            vals['dmag_consultant_id'] = self.users['consultant'].id
        for opt, (_n, _r, _s, _m, deposit, _l) in zip(plan.option_ids, scenario['options']):
            if deposit:
                self.as_user(opt, doctor_key).write({'deposit_amount': deposit})
        if vals:
            plan_doc.write(vals)
        plan_doc.action_present()
        self.stats['plans'] += 1
        ps.plan = plan
        if plan.second_opinion_required:
            other = 'doctor2' if doctor_key == 'doctor' else 'doctor'
            self.as_user(plan, other).action_second_opinion()
        if ps.decision == 'accept':
            self._accept(ps, visit)
        else:
            ps.next_due = False
            # khách hẹn suy nghĩ – một nửa quay lại đồng ý sau 1–3 tuần
            if rng.random() < 0.5:
                ps.decision = 'later'

    def _accept(self, ps, visit=False):
        plan = ps.plan
        option = plan.option_ids.filtered('is_recommended')[:1] or plan.option_ids[:1]
        if len(plan.option_ids) > 1 and self.rng.random() < 0.3:
            option = (plan.option_ids - option)[:1]
        # Bác sĩ chốt phương án cùng bệnh nhân (tư vấn viên ghi trên kế hoạch để tính hoa hồng tư vấn)
        self.as_user(option, ps.doctor_key).action_accept()
        self.stats['plans_accepted'] += 1
        ps.option = option
        day = self.to_local(fields.Datetime.now()).date()
        ps.next_due = day + timedelta(days=self.rng.randint(4, 12))
        if ps.scenario == 'ortho':
            ps.next_due = day + timedelta(days=self.rng.randint(5, 10))
        # Phục hình / khay chỉnh nha cần labo: gửi phiếu ngay sau khi chốt phương án
        lab = self._lab_spec(option)
        if lab and visit and not ps.lab_order:
            self._lab_order(visit, ps, ps.doctor_key, lab, fields.Datetime.now() + timedelta(minutes=10))

    LAB_BY_SERVICE = {
        'crown_zirconia': ('crown_bridge', 'zirconia', 1200000),
        'crown_metal': ('crown_bridge', 'pfm', 450000),
        'crown_implant': ('implant_abutment', 'zirconia', 1800000),
        'veneer': ('veneer', 'emax', 1500000),
        'ortho_clear': ('aligner', 'thermoform', 18000000),
    }

    def _lab_spec(self, option):
        for line in option.line_ids:
            spec = self.LAB_BY_SERVICE.get(self._svc_code(line.product_id))
            if spec:
                return spec
        return False

    def _do_phase(self, visit, ps, doctor_key, when):
        """Thực hiện các dòng kế hoạch của giai đoạn kế tiếp."""
        lines = ps.todo_lines()
        if not lines:
            return
        phase = min(lines.mapped('phase'))
        phase_lines = lines.filtered(lambda l: l.phase == phase)
        self.at(when)
        for line in phase_lines:
            lots = None
            product = line.product_id
            bom = D.BOMS.get(self._svc_code(product)) or []
            tracked = [m for m, _q, _b in bom if D.MATERIALS[m][4] == 'serial']
            if tracked:
                need = int(line.quantity or 1)
                if len(self.lots[tracked[0]]) < need:
                    continue  # hết trụ trong kho – dời lại
                lots = [self.lots[tracked[0]].pop(0) for _i in range(need)]
            # phục hình cần labo: nhận hàng / gắn trước khi ghi thủ thuật
            if ps.lab_order and self._svc_code(product) in self.LAB_BY_SERVICE:
                order = self.env['dmag.lab.order'].browse(ps.lab_order.id)
                if order.state in ('sent', 'in_progress', 'try_in'):
                    self.as_user(order, 'assistant').action_receive()
                if order.state == 'received':
                    self.as_user(order, 'assistant').action_fit()
            self._procedure(visit, doctor_key, plan_line=line, lots=lots)
        if ps.scenario == 'ortho':
            ps.ortho_visit = visit
        remaining = ps.todo_lines()
        day = self.to_local(when).date()
        if ps.scenario == 'ortho':
            ps.next_due = day + timedelta(days=self.rng.randint(26, 32))
        elif remaining:
            gap = 90 if ps.scenario == 'implant' else self.rng.randint(7, 14)
            ps.next_due = day + timedelta(days=gap)
        else:
            ps.next_due = False

    def _svc_code(self, product):
        return (product.default_code or '').replace('DM-', '').lower()

    def _treatment_clinical(self, visit, ps, doctor_key, when):
        rng = self.rng
        lines = ps.todo_lines()
        names = ', '.join(lines.filtered(lambda l: l.phase == min(lines.mapped('phase'))).mapped('display_name'))
        if ps.scenario == 'ortho' and ps.ortho_visit:
            self._record(visit, doctor_key, 'Tái khám chỉnh nha định kỳ.',
                         'Mắc cài ổn định, răng dịch chuyển đúng kế hoạch.', 'Đang điều trị chỉnh nha.',
                         ['diag_k07_3'], 'Thay dây cung, siết lực.', 'Vệ sinh kỹ quanh mắc cài, tránh đồ cứng dẻo.')
            self._procedure(visit, doctor_key, 'ortho_check')
            ps.next_due = self.to_local(when).date() + timedelta(days=rng.randint(26, 32))
            return
        scenario = D.SCENARIOS.get(ps.scenario, {})
        teeth = ps.teeth or ['']
        fmt = {'t%d' % i: t for i, t in enumerate(teeth)}
        fmt.setdefault('t0', '')
        fmt.setdefault('t1', '')
        self._record(visit, doctor_key, 'Đến điều trị theo kế hoạch.',
                     scenario.get('exam', 'Tình trạng ổn định.').format(**fmt),
                     scenario.get('assessment', 'Theo kế hoạch.').format(**fmt), scenario.get('diagnoses', ['diag_k03_6']),
                     'Thực hiện: %s.' % names, 'Tái khám theo hẹn. Liên hệ phòng khám nếu đau nhức kéo dài.')
        self._do_phase(visit, ps, doctor_key, when + timedelta(minutes=10))

    def _return_clinical(self, visit, ps, doctor_key, when):
        rng = self.rng
        if ps.decision == 'later' and ps.plan and ps.plan.state == 'presented':
            # khách quay lại đồng ý kế hoạch đã tư vấn
            self._record(visit, doctor_key, 'Quay lại sau khi cân nhắc kế hoạch điều trị.',
                         'Tình trạng như lần khám trước.', 'Theo kế hoạch đã tư vấn.',
                         D.SCENARIOS.get(ps.scenario, {}).get('diagnoses', ['diag_k03_6']),
                         'Tư vấn lại, bệnh nhân đồng ý phương án.', 'Hẹn lịch điều trị.')
            self._procedure(visit, doctor_key, 'exam')
            self.at(when + timedelta(minutes=10))
            self._accept(ps, visit)
            ps.decision = 'accept'
            return
        if ps.is_child:
            tooth = rng.choice(['54', '64', '74', '84'])
            self._chart(visit, ps, doctor_key, [('condition_caries', 0, ['O'])], [tooth])
            self._record(visit, doctor_key, 'Khám định kỳ cho bé.', 'Sâu răng sữa %s.' % tooth,
                         'Sâu răng sữa %s.' % tooth, ['diag_k02_1'], 'Trám GIC răng %s.' % tooth,
                         'Hạn chế đồ ngọt, chải răng có người lớn hỗ trợ.')
            self._procedure(visit, doctor_key, 'exam')
            self._procedure(visit, doctor_key, 'filling_kid', teeth=[tooth], surfaces=['O'])
            return
        if 'filling' in visit.service_ids.mapped('default_code') or \
                self.svc['filling'] in visit.service_ids:
            tooth = rng.choice(['14', '15', '24', '25', '34', '35', '44', '45', '17', '27', '37', '47'])
            surface = rng.choice([['O'], ['O', 'M'], ['O', 'D'], ['B']])
            self._chart(visit, ps, doctor_key, [('condition_caries', 0, surface)], [tooth])
            self._record(visit, doctor_key, 'Ê buốt khi ăn đồ lạnh.', 'Sâu ngà răng %s.' % tooth,
                         'Sâu ngà răng %s.' % tooth, ['diag_k02_1'], 'Trám Composite răng %s.' % tooth,
                         'Không ăn nhai mạnh 2 giờ đầu. Tái khám định kỳ 6 tháng.')
            self._procedure(visit, doctor_key, 'exam')
            self._procedure(visit, doctor_key, 'filling', teeth=[tooth], surfaces=surface)
            return
        simple = D.SIMPLE_VISITS['hygiene']
        self._chart(visit, ps, doctor_key, [('condition_calculus', 0, [])], ['31'])
        self._record(visit, doctor_key, simple[1], simple[2], simple[3], simple[4], 'Cạo vôi, đánh bóng hai hàm.',
                     'Chải răng 2 lần/ngày, dùng chỉ nha khoa. Tái khám sau 6 tháng.')
        self._procedure(visit, doctor_key, 'exam')
        self._procedure(visit, doctor_key, 'scaling')
        sub = self._active_subscription(ps.partner)
        if sub and sub._find_entitlement(self.svc['scaling']):
            proc = visit.procedure_ids.filtered(lambda p: p.product_id == self.svc['scaling'])[:1]
            if proc:
                self.try_('Dùng quyền lợi gói chăm sóc',
                          self.as_user(visit, 'receptionist').dmag_use_care_entitlement, proc.id)

    def _active_subscription(self, partner):
        if 'dmag.care.subscription' not in self.env:
            return False
        return self.env['dmag.care.subscription'].search([('partner_id', '=', partner.id),
                                                          ('state', '=', 'active')], limit=1)

    def _settle(self, visit, ps, when):
        """Thu tiền sau lượt khám: phần lớn thu đủ; ca lớn đặt cọc / trả góp; một số hẹn trả sau."""
        rng = self.rng
        visit.invalidate_recordset(['amount_due', 'payment_status'])
        if visit.payment_status == 'to_invoice':
            self.at(when)
            self.as_user(visit, 'receptionist')._create_and_post_invoices()
            visit.invalidate_recordset(['amount_due', 'payment_status'])
        due = visit.amount_due
        # Trả góp chỉnh nha: thu kỳ này vào hóa đơn trọn gói
        if ps.scenario == 'ortho' and ps.ortho_visit and ps.ortho_visit != visit:
            target = ps.ortho_visit
            target.invalidate_recordset(['amount_due', 'payment_status'])
            if target.amount_due > 0:
                self._pay(target, when, amount=min(2500000, target.amount_due), method='transfer')
            return
        if due <= 0:
            return
        option = ps.option
        deposit = option.deposit_amount if option else 0
        if due >= 10000000 and deposit:
            paid = self._pay(visit, when, amount=min(deposit, due))
            self.stats['partial_paid'] += 1
            if rng.random() < 0.5:
                self.schedule(when + timedelta(days=rng.randint(5, 20)), self._pay_rest, visit,
                              min(due - paid, max(due * 0.3, 1000000)))
            return
        if rng.random() < 0.07 and due >= 500000:
            half = round(due / 2, -3)
            self._pay(visit, when, amount=half)
            self.stats['partial_paid'] += 1
            self.schedule(when + timedelta(days=rng.randint(2, 6), hours=2), self._pay_rest, visit, False)
            return
        self._pay(visit, when)

    def _pay_rest(self, visit, amount):
        visit.invalidate_recordset(['amount_due', 'payment_status'])
        if visit.amount_due > 0:
            self._pay(visit, fields.Datetime.now(), amount=amount, method='transfer')

    def _lab_order(self, visit, ps, doctor_key, spec, when):
        work_type, material, cost = spec
        rng = self.rng
        lab = self.labs[2] if work_type == 'aligner' else rng.choice(self.labs[:2])
        self.at(when)
        lead = lab.dmag_lab_lead_days or 7
        teeth = [t for t in ps.teeth if t] if work_type != 'aligner' else []
        vals = {
            'patient_id': ps.partner.id, 'visit_id': visit.id, 'doctor_id': self.prac[doctor_key].id,
            'lab_partner_id': lab.id, 'work_type': work_type, 'material': material, 'cost': cost * max(len(teeth), 1),
            'shade': rng.choice(['A1', 'A2', 'A3', 'B1']) if work_type != 'aligner' else False,
            'impression_type': rng.choice(['scan', 'conventional']),
            'due_date': self.to_local(when).date() + timedelta(days=lead),
            'instructions': 'Chỉ định mẫu: %s, viền cổ kín, tiếp xúc bên vừa.' % dict(
                self.env['dmag.lab.order']._fields['work_type'].selection)[work_type],
            'company_id': self.company.id,
        }
        if teeth:
            vals['tooth_ids'] = [(6, 0, self.env['dmag.dental.tooth'].search([('code', 'in', teeth)]).ids)]
        order = self.M('dmag.lab.order', 'assistant').create(vals)
        order.action_send()
        ps.lab_order = order
        self.stats['lab_orders'] += 1
        sent = fields.Datetime.now()
        self.schedule(sent + timedelta(days=1, hours=2), self._lab_step, order, 'action_start')
        if rng.random() < 0.75:
            # labo trả đúng / sớm hạn; còn lại trễ hạn (hiện cảnh báo "Trễ hạn")
            self.schedule(sent + timedelta(days=max(lead - rng.randint(0, 2), 1), hours=4), self._lab_step, order,
                          'action_receive')

    def _lab_step(self, order, method):
        order = self.env['dmag.lab.order'].browse(order.id)
        allowed = {'action_start': ('sent',), 'action_receive': ('sent', 'in_progress', 'try_in')}
        if order.state in allowed[method]:
            getattr(self.as_user(order, 'assistant'), method)()

    def _cash_closing(self, day):
        """Chốt két cuối ngày 4 bước: lễ tân kiểm đếm → thu ngân nhận → quản lý xác nhận → khóa sổ."""
        opening = 2000000
        closing = self.M('dmag.cash.closing', 'receptionist').create({
            'date': day, 'shift': 'full', 'company_id': self.company.id, 'cash_opening': opening})
        diff = -50000 if self.rng.random() < 0.3 else 0
        vals = {'cash_counted': opening + closing.system_cash + diff, 'card_slip_total': closing.system_card}
        if diff:
            vals['diff_reason'] = 'Thối nhầm tiền thừa cho khách, đã liên hệ hoàn lại ' + D.SAMPLE
        closing.write(vals)
        closing.action_sign_receptionist()
        self.as_user(closing, 'consultant').action_sign_cashier()
        self.as_user(closing, 'manager').action_confirm()
        if day < self.today - timedelta(days=1):
            self.as_user(closing, 'manager').action_lock()
        self.stats['cash_closings'] += 1

    def _care_subscriptions(self, days):
        if not getattr(self, 'care_plans', None):
            return
        picks = [('lan', 1), ('tuan', 1), ('son', 0), ('quang', 0)]
        for idx, (key, plan_idx) in enumerate(picks):
            day = days[min(5 + idx * 7, len(days) - 1)]
            self.schedule(self.local_dt(day, 10, 15), self._subscribe, key, plan_idx)

    def _subscribe(self, key, plan_idx):
        partner = self.patients[key]
        Sub = self.M('dmag.care.subscription', 'receptionist')
        sub = Sub.create({'partner_id': partner.id, 'plan_id': self.care_plans[plan_idx].id,
                          'company_id': self.company.id, 'start_date': fields.Date.context_today(Sub)})
        sub.action_activate()
        sub.register_payment(self.rng.choice(['cash', 'card']))
        self.stats['care_subscriptions'] += 1

    # ======================================================================== today & future
    def _today_board(self):
        """Bảng điều phối hôm nay luôn có khách để demo ở MỌI giờ mở máy (kể cả ngoài giờ / ngày nghỉ theo Lịch làm
        việc) – riêng phần này bỏ qua kiểm tra giờ làm việc; lịch sử và lịch tương lai thì theo đúng lịch."""
        env = self.env
        self.env = env(context=dict(env.context, dmag_skip_opening_hours=True))
        try:
            return self._today_board_inner()
        finally:
            self.env = env

    def _today_board_inner(self):
        rng = self.rng
        now = self.now
        local_now = self.to_local(now)
        day_start = self.local_dt(self.today, 0, 5)
        day_end = self.local_dt(self.today, 23, 50)

        def clip(dt):
            return min(max(dt, day_start), day_end)

        self.run_events(now - timedelta(minutes=30))
        self.max_time = now - timedelta(minutes=1)

        treatment = [ps for ps in self.pstates if ps.next_due and ps.todo_lines()]
        fresh = [ps for ps in self.pstates if not ps.visits]
        returning = [ps for ps in self.pstates if ps.visits and not ps.next_due]
        rng.shuffle(treatment)
        rng.shuffle(returning)
        pool = treatment[:4] + fresh[:3] + returning
        used = set()

        def take(pred=lambda ps: True):
            for ps in pool:
                if ps.key not in used and pred(ps) and self.doctor_on_duty(ps.doctor_key, self.today):
                    used.add(ps.key)
                    return ps
            return False

        light = lambda ps: ps.scenario not in ('implant', 'wisdom', 'endo_crown')  # noqa: E731
        plan_board = [
            # (lệch phút so với bây giờ, trạng thái dừng, ghế)
            (-245, None, 0), (-185, None, 1), (-125, 'done_unpaid', 0),
            (-60, 'in_chair', 1), (-35, 'in_chair', 3),
            (-12, 'arrived', None), (4, 'arrived', None),
            (40, 'confirmed', 2), (95, 'confirmed', 0), (150, 'draft', 1),
        ]
        for offset, stop, chair_idx in plan_board:
            start = clip(now + timedelta(minutes=offset))
            ps = take(light) if stop in ('in_chair', 'arrived', 'confirmed', 'draft') else take()
            if not ps:
                continue
            kind = 'treatment' if ps.next_due and ps.todo_lines() else ('first' if not ps.visits else 'return')
            if kind == 'treatment' and stop in ('in_chair',):
                kind = 'return'
            # ghế dự kiến bận (ca trước kéo dài – tùy giờ mở máy) → thử ghế khác
            chairs = [chair_idx] + [i for i in range(len(self.chairs)) if i != chair_idx] if chair_idx is not None \
                else [None]
            for idx in chairs:
                try:
                    with self.env.cr.savepoint():
                        self._simulate_today(ps, kind, start, stop, idx)
                    break
                except ValidationError as exc:
                    _logger.info('DMAG demo: bảng hôm nay – ghế %s bận (%s), thử ghế khác', idx, exc)
        self.max_time = None
        self.stats['today_visits'] = self.env['dmag.dental.visit'].search_count([
            ('scheduled_start', '>=', self.local_dt(self.today, 0, 0)),
            ('scheduled_start', '<', self.local_dt(self.today + timedelta(days=1), 0, 0)),
            ('company_id', '=', self.company.id)])
        _logger.info('DMAG demo: bảng hôm nay (%s giờ địa phương) – %s lượt', local_now.strftime('%H:%M'),
                     self.stats['today_visits'])

    def _simulate_today(self, ps, kind, start, stop, chair_idx):
        """Lượt khám hôm nay dừng ở trạng thái ``stop`` – đồng hồ không vượt quá hiện tại."""
        chair = self.chairs[chair_idx] if chair_idx is not None else False
        original = self._chair_for
        self._chair_for = lambda _ps: chair  # noqa: E731 – ghế cố định cho bảng hôm nay (không trùng)
        try:
            if stop in ('draft', 'confirmed'):
                return self._simulate(ps, kind, start, final=False, stop_at=stop)
            # mọi thao tác (check-in, lên ghế, hoàn tất…) phải trước thời điểm hiện tại
            return self._simulate(ps, kind, start, final=False, stop_at=stop or 'paid')
        finally:
            self._chair_for = original

    def _future_bookings(self):
        rng = self.rng
        future_days = list(itertools.islice(self.working_days(self.today + timedelta(days=1),
                                                              self.today + timedelta(days=10)), 4))
        due = sorted([ps for ps in self.pstates if ps.next_due and ps.todo_lines()], key=lambda p: p.next_due)
        others = [ps for ps in self.pstates if ps not in due and not ps.is_child]
        rng.shuffle(others)
        queue = due + others
        for d_idx, day in enumerate(future_days):
            n = [6, 4, 3, 2][d_idx]
            starts = [m for m in self.open_starts(day, step=60) if m <= 18 * 60] or self.open_starts(day, step=60)
            hours = sorted(rng.sample(starts, min(n, len(starts))))
            chair_cycle = itertools.cycle(range(4))
            for minute in hours:
                if not queue:
                    return
                ps = next((p for p in queue if self.doctor_on_duty(p.doctor_key, day)), None)
                if not ps:
                    continue
                queue.remove(ps)
                start = self.local_dt(day, minute // 60, minute % 60) + timedelta(minutes=rng.choice([0, 30]))
                kind = 'treatment' if ps.next_due and ps.todo_lines() else 'return'
                codes, reason, plan = self._visit_plan(ps, kind)
                chair = self.chairs[next(chair_cycle)]
                booked_at = self.now - timedelta(hours=rng.randint(1, 72))
                self.at(booked_at)
                state_confirm = d_idx == 0 or rng.random() < 0.5
                for shift in (0, 90, 180, None):  # trùng ca nặng / ghế → thử giờ khác trong ngày
                    if shift is None:
                        self.try_('Đặt lịch tương lai', self._book, ps, start, codes, ps.doctor_key, chair, reason,
                                  plan, start - booked_at, state_confirm)
                        break
                    begin = start + timedelta(minutes=shift)
                    try:
                        with self.env.cr.savepoint():
                            self._book(ps, begin, codes, ps.doctor_key, chair, reason, plan, begin - booked_at,
                                       state_confirm)
                        break
                    except (UserError, ValidationError):
                        self.at(booked_at)
                        continue
        self.at(self.now)

    # ======================================================================== post processing
    def _journey_finalize(self):
        Rule = self.env['dmag.journey.rule']
        if hasattr(Rule, '_cron_run_time_rules'):
            Rule._cron_run_time_rules()
        Message = self.env['dmag.zns.message']
        queued = Message.search([('state', '=', 'queued'), ('next_try', '<=', fields.Datetime.now())])
        for message in queued:
            self.try_('Gửi ZNS giả lập', message._dmag_process)
        self.stats['zns_messages'] = Message.search_count([('id', '>', self.watermarks.get('dmag.zns.message', 0))])

    def _commission_statement(self):
        Statement = self.env['dmag.commission.statement']
        last_month = (self.today.replace(day=1) - timedelta(days=1)).replace(day=1)
        statements = Statement._generate(self.company, last_month)
        self.as_user(statements, 'director').action_confirm()
        self.stats['commission_statements'] = len(statements)

    def _pay_sheets(self):
        Sheet = self.env['dmag.pay3p.sheet']
        Assessment = self.env['dmag.competency.assessment']
        last_month = (self.today.replace(day=1) - timedelta(days=1)).replace(day=1)
        for key in ('doctor', 'doctor2', 'assistant', 'receptionist'):
            employee = self.users[key].employee_ids[:1]
            if not employee or not employee.dmag_profile_id:
                continue
            assessment = self.M('dmag.competency.assessment', 'manager').create({
                'employee_id': employee.id, 'date': last_month, 'note': 'Đánh giá năng lực mẫu ' + D.SAMPLE,
            } if 'note' in Assessment._fields else {'employee_id': employee.id, 'date': last_month})
            assessment.action_prefill()
            assessment.action_confirm()
        sheet = self.M('dmag.pay3p.sheet', 'manager').create({'date_from': last_month, 'company_id': self.company.id})
        sheet.action_generate_lines()
        sheet.action_review()
        self.as_user(sheet, 'director').action_approve()
        current = self.M('dmag.pay3p.sheet', 'manager').create({'date_from': self.today.replace(day=1),
                                                               'company_id': self.company.id})
        current.action_generate_lines()
        self.stats['pay_sheets'] = 2

    def _loyalty_finalize(self):
        partners = self.env['res.partner'].browse([p.id for p in self.patients.values()])
        if hasattr(partners, '_dmag_loyalty_recompute'):
            for partner in partners:
                partner._dmag_loyalty_recompute()

    def _portal_user(self):
        partner = self.patients[D.PORTAL_PATIENT]
        if not partner.email:
            partner.write({'email': '%s@nhakhoa-dmag.demo' % D.PORTAL_LOGIN})
        Users = self.env['res.users'].with_context(no_reset_password=True)
        if Users.with_context(active_test=False).search_count([('login', '=', D.PORTAL_LOGIN)]):
            return
        self.portal_user = Users.create({
            'name': partner.name, 'login': D.PORTAL_LOGIN, 'password': D.PASSWORD, 'partner_id': partner.id,
            'groups_id': [(6, 0, [self.env.ref('base.group_portal').id])], 'company_id': self.company.id,
            'company_ids': [(6, 0, self.company.ids)], 'tz': TZ_NAME, 'notification_type': 'email',
        })

    def _okr(self):
        """OKR Scale (module ngoài) – chỉ tạo khi đã cài, không bắt buộc."""
        if not ('okr.scale.cycle' in self.env and 'okr.scale.objective' in self.env
                and 'okr.scale.key.result' in self.env):
            return
        Cycle = self.env['okr.scale.cycle']
        quarter_start = self.today.replace(day=1, month=((self.today.month - 1) // 3) * 3 + 1)
        cycle = Cycle.create({'name': 'Quý %s/%s (demo)' % ((self.today.month - 1) // 3 + 1, self.today.year),
                              'date_start': quarter_start,
                              'date_end': quarter_start + relativedelta(months=3, days=-1), 'state': 'open'})
        objective = self.env['okr.scale.objective'].create({
            'name': 'Trải nghiệm không đau, không chờ ' + D.SAMPLE, 'cycle_id': cycle.id, 'level': 'company',
            'owner_id': self.users['director'].id})
        KR = self.env['okr.scale.key.result']
        for name, method, start, target in [('Thời gian chờ ≤ 10 phút', 'dmag_wait_time', 30, 10),
                                            ('Tỷ lệ chốt kế hoạch 60%', 'dmag_plan_acceptance', 0, 60),
                                            ('NPS ≥ 70', 'dmag_nps', 0, 70)]:
            kr = KR.create({'objective_id': objective.id, 'name': name, 'progress_method': method,
                            'start_value': start, 'target_value': target})
            if hasattr(kr, 'action_dmag_refresh'):
                kr.action_dmag_refresh()
        self.stats['okr'] = 1

    def _business_targets(self):
        """Mục tiêu kinh doanh mẫu do Giám đốc đặt & chốt (``dmag_dental_goals``): tháng trước, tháng này, quý, năm;
        mục tiêu riêng từng bác sĩ; nhóm theo 3 Objective; một đề xuất tháng sau chờ Giám đốc chốt.

        Mức mục tiêu lấy theo nhịp 30 ngày gần nhất của chính dữ liệu demo (+10–20 %) để bảng điều hành có đủ
        trạng thái Đúng tiến độ / Chậm / Nguy cơ.
        """
        if 'dmag.business.target' not in self.env:
            return
        engine = self.env['dmag.goal.engine']
        company = self.company
        month = self.today.replace(day=1)
        last_month = (month - timedelta(days=1)).replace(day=1)
        quarter = self.today.replace(day=1, month=((self.today.month - 1) // 3) * 3 + 1)
        year = self.today.replace(month=1, day=1)
        # Cơ sở: nhịp 30 ngày gần nhất của dữ liệu demo (≈ một tháng), không phải tháng trước (lịch sử demo mới
        # bắt đầu nên tháng trước thấp hơn nhịp hiện tại).
        base_from, base_to = self.today - timedelta(days=30), self.today - timedelta(days=1)
        scope = engine._scope(base_from, base_to, company)

        def actual(metric, doctor=None):
            sc = engine._scope(base_from, base_to, company, doctor) if doctor else scope
            return engine.compute_metric(metric, sc) or 0.0

        def up(value, step):
            return max(step, math.ceil(value / step) * step)

        revenue = up(actual('revenue') * 1.12, 10000000) if actual('revenue') else 250000000
        base = {
            'revenue': revenue,
            'collected': up(revenue * 0.9, 10000000),
            'gross_profit': up(revenue * 0.6, 5000000),
            'new_patients': up(actual('new_patients') * 1.15, 1) if actual('new_patients') else 12,
            'implant_cases': max(3, up(actual('implant_cases') * 1.2, 1)),
            'ortho_new': max(2, up(actual('ortho_new') + 1, 1)),
            'plan_acceptance': 65.0,
            'avg_wait': 12.0,
            'nps': 60.0,
            'show_up_rate': 88.0,
        }
        objectives = {
            'revenue': 'Tăng trưởng doanh thu bền vững', 'collected': 'Tăng trưởng doanh thu bền vững',
            'gross_profit': 'Tăng trưởng doanh thu bền vững', 'new_patients': 'Tăng trưởng doanh thu bền vững',
            'implant_cases': 'Mở rộng dịch vụ giá trị cao', 'ortho_new': 'Mở rộng dịch vụ giá trị cao',
            'plan_acceptance': 'Mở rộng dịch vụ giá trị cao',
            'avg_wait': 'Trải nghiệm không đau, không chờ', 'nps': 'Trải nghiệm không đau, không chờ',
            'show_up_rate': 'Trải nghiệm không đau, không chờ',
        }
        owners = {'revenue': 'director', 'collected': 'receptionist', 'gross_profit': 'director',
                  'new_patients': 'consultant', 'implant_cases': 'doctor', 'ortho_new': 'doctor2',
                  'plan_acceptance': 'consultant', 'avg_wait': 'manager', 'nps': 'manager', 'show_up_rate': 'receptionist'}
        notes = {
            'revenue': 'Lấp ghế chiều 13:30–16:30, gọi lại khách đang cân nhắc kế hoạch. ' + D.SAMPLE,
            'implant_cases': 'Tư vấn implant trong 48 giờ sau khám, trả góp 0 %. ' + D.SAMPLE,
            'avg_wait': 'Không xếp chồng 2 ca nặng, nhắn ZNS nhắc giờ hẹn. ' + D.SAMPLE,
        }
        vals_list = []

        def add(metric, value, period_type, date_from, doctor=None, objective=True):
            vals_list.append({
                'metric': metric, 'target_value': value, 'period_type': period_type, 'date_from': date_from,
                'company_id': company.id, 'practitioner_id': doctor.id if doctor else False,
                'objective': objectives.get(metric) if objective else False,
                'user_id': (doctor.user_id.id if doctor and doctor.user_id else self.users[owners[metric]].id),
                'note': notes.get(metric, False) if not doctor else False,
            })

        for date_from in (last_month, month):
            for metric, value in base.items():
                add(metric, value, 'month', date_from)
        sums = ('revenue', 'collected', 'gross_profit', 'new_patients', 'implant_cases', 'ortho_new')
        for metric in sums:
            add(metric, base[metric] * 3, 'quarter', quarter)
            add(metric, base[metric] * 12, 'year', year, objective=False)
        for metric in ('plan_acceptance', 'nps'):
            add(metric, base[metric], 'quarter', quarter)
        # Mục tiêu riêng từng bác sĩ: chia doanh thu theo tỷ trọng tháng trước
        doctors = [self.prac[k] for k in ('doctor', 'doctor2', 'doctor3') if self.prac.get(k)]
        shares = {d.id: actual('revenue', d) for d in doctors}
        total = sum(shares.values()) or 1.0
        for doctor in doctors:
            share = shares[doctor.id] / total if sum(shares.values()) else 1.0 / len(doctors)
            for date_from in (last_month, month):
                add('revenue', up(revenue * share, 5000000), 'month', date_from, doctor, objective=False)
                add('plan_acceptance', 65.0, 'month', date_from, doctor, objective=False)
        if self.prac.get('doctor'):
            add('implant_cases', base['implant_cases'], 'month', month, self.prac['doctor'], objective=False)
        if self.prac.get('doctor2'):
            add('ortho_new', base['ortho_new'], 'month', month, self.prac['doctor2'], objective=False)
        targets = self.M('dmag.business.target', 'director').create(vals_list)
        targets.action_confirm()
        # Đề xuất của Quản lý cho tháng sau – chờ Giám đốc chốt
        next_month = (month + timedelta(days=32)).replace(day=1)
        self.M('dmag.business.target', 'manager').create({
            'metric': 'revenue', 'target_value': up(revenue * 1.05, 10000000), 'period_type': 'month',
            'date_from': next_month, 'company_id': company.id, 'objective': objectives['revenue'],
            'user_id': self.users['director'].id, 'note': 'Đề xuất của quản lý – chờ Giám đốc chốt. ' + D.SAMPLE})
        self.stats['business_targets'] = len(targets) + 1

    # ======================================================================== Trợ lý AI
    def _ai_demo(self):
        """Trợ lý AI ở chế độ giả lập + dữ liệu mẫu tạo bằng CHÍNH các hàm nghiệp vụ AI (không chèn tay):

        * ~90 % bệnh nhân demo đồng ý hỗ trợ bằng AI (NĐ 13/2023), chế độ AI = giả lập;
        * hai lần hoàn tiền do lễ tân lập (tình huống cho AI-15);
        * hỏi đáp số liệu (AI-13), dự báo (AI-16), quét bất thường (AI-15, một cảnh báo đã có giải trình, một có AI giải
          thích), bản tin tuần (AI-14) → Trung tâm AI và Bảng điều hành có số liệu sử dụng & chi phí ước tính.
        """
        if 'dmag.ai.log' not in self.env:
            return
        company = self.company
        self._fix_booking_dates()
        # khách khám hôm nay được hỏi đồng ý AI ngay lúc check-in
        today_done = self.env['dmag.dental.visit'].search([
            ('company_id', '=', company.id), ('scheduled_start', '>=', self.local_dt(self.today, 0)),
            ('state', 'in', ('arrived', 'in_chair', 'done'))])
        today_done.mapped('patient_id').filtered(lambda p: not p.dmag_ai_consent).write({'dmag_ai_consent': True})
        self.stats['ai_consent'] = len(self.env['res.partner'].browse(
            [p.id for p in self.patients.values()]).filtered('dmag_ai_consent'))
        self.try_('Lịch rủi ro không đến', self._ai_risky_bookings)
        self.try_('Huấn luyện AI-08', self._ai_noshow_train)
        self._ai_refunds()
        self.try_('Phim X-quang mẫu', self._ai_xray_samples)
        self.try_('Theo dõi sau điều trị', self._ai_followups)
        self._ai_customer_samples()
        if 'dmag.ai.qa' in self.env:
            qa = self.env['dmag.ai.qa'].with_user(self.users['director']).with_company(company)
            for question in ('Tình hình tháng này ra sao?', 'Vì sao doanh thu tháng này chậm?',
                             'Bác sĩ nào chốt kế hoạch thấp nhất quý này?', 'Tỷ lệ khách không đến tháng này?',
                             'Dịch vụ nào mang lại doanh thu cao nhất 30 ngày qua?', 'Thực thu tháng trước bao nhiêu?'):
                self.try_('Hỏi đáp số liệu', qa.ask, question)
                self.stats['ai_questions'] += 1
        if 'dmag.ai.forecast' in self.env:
            self.try_('Dự báo', self.env['dmag.ai.forecast'].with_user(self.users['director']).with_company(
                company).get_forecast)
        if 'dmag.ai.anomaly' in self.env:
            Anomaly = self.env['dmag.ai.anomaly'].with_user(self.users['manager']).with_company(company)
            found = Anomaly._detect()
            self.stats['ai_anomalies'] = len(found)
            ranked = found.sorted(lambda a: (-a.severity_rank, a.id))
            if ranked:
                first = ranked[0]
                first.manager_note = ('Đã rà từng chứng từ cùng nhân sự liên quan: phần lớn có lý do (chương trình tri ân '
                                      'khách cũ), 2 trường hợp chưa có phiếu duyệt – đã nhắc nhở. ' + D.SAMPLE)
                self.try_('Giải trình bất thường', first.action_review)
            if len(ranked) > 1:
                self.try_('AI giải thích bất thường', ranked[1].action_ai_narrative)
        if 'dmag.ai.brief' in self.env:
            brief = self.env['dmag.ai.brief'].with_user(self.users['director']).with_company(company)
            self.try_('Bản tin tuần', brief._generate, trigger='cron')
            self.stats['ai_briefs'] = 1
        self.stats['ai_logs'] = self.env['dmag.ai.log'].search_count([('id', '>', self.watermarks.get('dmag.ai.log', 0))])

    def _ai_setup(self):
        """Trợ lý AI chạy giả lập; ~90 % bệnh nhân đồng ý xử lý bằng AI; thuốc đang dùng / mang thai cho AI-03."""
        company = self.company
        if 'dmag_ai_mode' in company._fields:
            self.remember(company, {'dmag_ai_mode': 'simulate'})
        if 'dmag_ai_zalo_reply_mode' in company._fields:
            # chủ phòng khám đã chốt (11/10/2026): trợ lý THAY nhân viên trả lời nhưng CHỈ từ dữ liệu đã nạp; ngoài dữ
            # liệu → báo lễ tân đang trực (Lịch nghỉ luân phiên), quá 15 phút → Quản lý
            self.remember(company, {'dmag_ai_zalo_reply_mode': 'grounded', 'dmag_ai_escalation_minutes': 15,
                                    'dmag_ai_escalation_user_id': self.users['manager'].id})
            if 'dmag_ai_duty_line_ids' in company._fields and not company.dmag_ai_duty_line_ids:
                company.write({'dmag_ai_duty_line_ids': [
                    (0, 0, {'user_id': self.users[key].id, 'sequence': seq, 'channel': 'all'})
                    for seq, key in enumerate(('receptionist', 'consultant'), start=1)]})
        if 'dmag_ai_consent' in self.env['res.partner']._fields:
            for key, partner in self.patients.items():
                if key not in D.AI_NO_CONSENT:
                    partner.write({'dmag_ai_consent': True})
        for key, vals in D.AI_PATIENT_EXTRA.items():
            partner = self.patients.get(key)
            if partner:
                partner.write({k: v for k, v in vals.items() if k in partner._fields})

    def _fix_booking_dates(self):
        """Ngày tạo lịch hẹn = lúc khách đặt (đồng hồ "đóng băng" không áp vào create_date của PostgreSQL)."""
        rows = [(at, vid) for vid, at in self.booked_at.items() if at]
        if not rows:
            return
        self.env.flush_all()
        for at, vid in rows:
            self.env.cr.execute('UPDATE dmag_dental_visit SET create_date = %s WHERE id = %s', (at, vid))
        self.env['dmag.dental.visit'].invalidate_model(['create_date'])
        self.booked_at = {}

    def _ai_risky_bookings(self):
        """2–4 lịch hôm nay / ngày mai có nguy cơ không đến cao: đặt online từ sớm, chưa xác nhận, từng bỏ hẹn."""
        risky = sorted([ps for ps in self.pstates if not ps.is_child],
                       key=lambda ps: (-ps.noshows, not self._is_online(ps.partner), ps.visits, ps.key))[:3]
        tomorrow = next(self.working_days(self.today + timedelta(days=1), self.today + timedelta(days=14)))
        today_open = self.clinic_schedule.is_open_day(self.today)
        slots = [(tomorrow, 14, 0), (tomorrow, 16, 30), (self.today, 17, 30) if today_open else (tomorrow, 17, 30)]
        for ps, (day, hour, minute) in zip(risky, slots):
            start = self.local_dt(day, hour, minute)
            if start <= fields.Datetime.now():
                start = self.local_dt(tomorrow, 9, 0)
            Visit = self.env['dmag.dental.visit']
            free = [c for c in self.chairs if not Visit.search_count([
                ('chair_id', '=', c.id), ('state', 'not in', ('cancel', 'no_show')),
                ('scheduled_start', '<', start + timedelta(minutes=60)),
                ('scheduled_start', '>', start - timedelta(minutes=60))])]
            for chair in free[:1]:  # ghế còn trống khung giờ đó
                if self.try_('Lịch rủi ro', self._book, ps, start,
                             ['scaling'] if 'scaling' in self.svc else ['exam'], ps.doctor_key, chair,
                             'Khách tự đặt qua Zalo OA ' + D.SAMPLE, False, timedelta(days=11 + len(ps.key) % 4),
                             False):
                    break
        self._fix_booking_dates()

    def _ai_noshow_train(self):
        Model = self.env.get('dmag.ai.noshow.model')
        if Model is None or not hasattr(Model, 'train'):
            return
        model = Model.with_company(self.company).train(self.company)
        upcoming = self.env['dmag.dental.visit'].search([('company_id', '=', self.company.id),
                                                         ('state', 'in', ('draft', 'confirmed')),
                                                         ('scheduled_start', '>=', fields.Datetime.now())])
        Model.with_company(self.company).score_visits(upcoming)
        self.stats['ai_noshow_samples'] = model.n_samples
        self.stats['ai_noshow_high'] = len(upcoming.filtered(lambda v: v.dmag_noshow_level == 'high'))

    def _ai_xray_samples(self):
        Clinical = self.env.get('dmag.ai.clinical')
        if Clinical is None or not hasattr(Clinical, 'ai06_add_sample'):
            return
        for key, sample in (('mai', 'xray_sample_1'), ('huongdo', 'xray_sample_2')):
            partner = self.patients.get(key)
            visit = self.env['dmag.dental.visit'].search([('patient_id', '=', partner.id), ('state', '!=', 'cancel')],
                                                         order='scheduled_start desc', limit=1) if partner else False
            if visit:
                Clinical.with_user(self.users['doctor']).with_company(self.company).ai06_add_sample(visit.id, sample)
                self.stats['ai_xray_samples'] += 1

    def _ai_followups(self):
        """Khách sau thủ thuật xâm lấn vài ngày trước trả lời câu hỏi theo dõi (đa số bình thường, một ca bất thường)."""
        if 'dmag.ai.followup' not in self.env:
            return
        Followup = self.env['dmag.ai.followup']
        since = fields.Datetime.now() - timedelta(days=7)
        todo = Followup.search([('visit_id.done_time', '>=', since), ('state', 'not in', ('answered', 'alert',
                                                                                          'closed'))],
                               order='due_at')
        due = todo.filtered(lambda f: f.due_at and f.due_at <= fields.Datetime.now())
        answers = [(2, 'none', 'mild', False, 'Hơi ê nhẹ, ăn uống bình thường.'),
                   (1, 'none', 'none', False, ''),
                   (8, 'heavy', 'severe', True, 'Vẫn chảy máu nhiều, má sưng to, sốt 38,5 độ, đau không ngủ được.'),
                   (3, 'light', 'mild', False, 'Rỉ máu ít khi đánh răng.')]
        for fu, ans in zip(due[:4], answers):
            if fu.state == 'scheduled' and hasattr(fu, 'action_send'):
                self.try_('Gửi câu hỏi theo dõi', fu.action_send)
            if self.try_('Trả lời theo dõi', fu.submit_answers, *ans[:4], free_text=ans[4], channel='portal') is not False:
                self.stats['ai_followup_answers'] += 1

    def _ai_refunds(self):
        """Lễ tân lập 2 hóa đơn điều chỉnh giảm (hoàn tiền cho khách) trong tuần – chứng từ đã ghi sổ bị hoàn."""
        Visit = self.env['dmag.dental.visit']
        since = fields.Datetime.now() - timedelta(days=12)
        visits = Visit.search([('company_id', '=', self.company.id), ('state', '=', 'done'),
                               ('scheduled_start', '>=', since)], order='scheduled_start')
        visits = visits.filtered(lambda v: v.payment_status == 'paid')
        moves = visits.mapped('invoice_ids').filtered(lambda m: m.move_type == 'out_invoice' and m.state == 'posted'
                                                      and 300000 <= m.amount_total <= 3000000)
        receptionist = self.users['receptionist']
        reasons = ['Hoàn tiền: khách đổi sang phương án khác ' + D.SAMPLE,
                   'Hoàn tiền: tính trùng dịch vụ cạo vôi ' + D.SAMPLE]
        for move, reason in zip(moves[:2], reasons):
            def refund(move=move, reason=reason):
                Move = self.env['account.move'].with_user(receptionist).sudo()
                rev = Move.browse(move.id)._reverse_moves([{'ref': reason, 'date': self.today,
                                                            'invoice_date': self.today}])
                rev.action_post()
                return rev
            if self.try_('Hoàn tiền mẫu', refund):
                self.stats['ai_refunds'] += 1

    def _ai_reply_scripts(self):
        """Bộ kịch bản trả lời chuẩn đã rà soát (module dmag_ai_customer nạp ở dạng nháp; giá / bảo hành / giờ làm việc
        / lịch trực bác sĩ lấy từ dữ liệu thật qua ô dữ liệu) – Giám đốc demo đọc và DUYỆT bằng nút thật."""
        Script = self.env['dmag.ai.reply.script']
        Script._load_samples(self.company)
        drafts = Script.search([('company_id', '=', self.company.id), ('state', '=', 'draft'),
                                ('code', 'not like', 'de_xuat_%')])
        # kịch bản mẫu nạp lúc cài module (trước khi có dịch vụ demo) → gắn dịch vụ báo giá theo danh mục demo
        from odoo.addons.dmag_ai_customer.models.reply_script_samples import SAMPLE_SCRIPTS
        words = {x['code']: x.get('services', []) for x in SAMPLE_SCRIPTS}
        Product = self.env['product.product']
        for script in drafts.filtered(lambda x: not x.service_ids and words.get(x.code)):
            services = Product.browse()
            for word in words[script.code]:
                services |= Product.search([('is_dental_service', '=', True), ('name', 'ilike', word)], limit=2)
            script.service_ids = [(6, 0, services.ids)]
        drafts.with_user(self.users['director']).with_company(self.company).action_approve()
        self.stats['ai_reply_scripts'] = len(drafts)

    def _ai_knowledge(self):
        """Kho tri thức trợ lý: Quản lý "Nạp lại dữ liệu" (bảng giá + bảo hành, Lịch làm việc 7 ngày, lịch trực bác sĩ,
        thông tin phòng khám, gói chăm sóc, kịch bản đã duyệt) và tải "Cẩm nang khách hàng" – Giám đốc duyệt tài liệu."""
        if 'dmag.ai.knowledge' not in self.env:
            return
        company = self.company
        KB = self.env['dmag.ai.knowledge'].with_user(self.users['manager']).with_company(company)
        res = KB.action_refresh_all()
        name, filename, text = D.KB_DOCUMENT
        Doc = self.env['dmag.ai.knowledge.document'].with_user(self.users['manager']).with_company(company)
        doc = Doc.create({'name': name, 'filename': filename, 'company_id': company.id,
                          'datas': base64.b64encode(text.encode('utf-8'))})
        doc.action_extract()
        doc.with_user(self.users['director']).action_approve()
        self.stats['ai_kb_master'] = res['master']
        self.stats['ai_kb_entries'] = self.env['dmag.ai.knowledge'].search_count([('company_id', '=', company.id)])

    def _ai_gap_chats(self, Conv):
        """Câu hỏi NGOÀI dữ liệu đã nạp: trợ lý gửi tin giữ chỗ + báo lễ tân đang trực; nhân viên trả lời → "Đề xuất
        thành kịch bản" (lễ tân / tư vấn đề xuất – Giám đốc duyệt một, còn lại chờ duyệt) và "Nạp vào kho tri thức";
        một câu quá hạn đã báo Quản lý, một câu còn chờ – vòng huấn luyện hiện đủ trên Hộp thư."""
        company = self.company
        Msg = self.env['dmag.ai.conversation.message']
        director = self.users['director']
        for uid, name, phone, question, staff_key, answer, actions in D.AI_GAP_CHATS:
            conv = Conv._get_or_create('zalo', external_user_id=uid, name=name, phone=phone)
            conv.receive_customer_message(question)
            gap = conv.gap_ids.sorted('id')[-1:]
            self.stats['ai_conversations'] += 1
            if not gap:
                self.warnings.append('Câu hỏi "%s" không vào hàng ngoài dữ liệu' % question[:40])
                continue
            if 'overdue' in actions:
                gap.write({'notified_at': fields.Datetime.now() - timedelta(minutes=27)})
                self.env['dmag.ai.kb.gap']._cron_escalate()
                continue
            if 'open' in actions or not staff_key:
                continue
            user = self.users[staff_key]
            reply = conv.with_user(user).with_company(company).staff_reply(answer)
            message = Msg.browse(reply['id']).with_user(user).with_company(company)
            if {'script_approved', 'script_draft'} & set(actions):
                res = message.action_promote_to_script()
                script = self.env['dmag.ai.reply.script'].browse(res['id'])
                if 'script_approved' in actions:
                    as_director = script.with_user(director).with_company(company)
                    as_director.write({'name': 'Xuất hóa đơn VAT cho công ty', 'code': 'hoa_don_vat',
                                       'keywords': 'hóa đơn, VAT, xuất hóa đơn, hóa đơn đỏ, mã số thuế',
                                       'quick_replies': 'Đặt lịch khám | Bảng giá'})
                    as_director.action_approve()
                self.stats['ai_script_proposals'] += 1
            if {'kb_approved', 'kb_draft'} & set(actions):
                card = gap.with_user(user).with_company(company).action_learn()
                if 'kb_approved' in actions:
                    self.env['dmag.ai.knowledge'].browse(card['id']).with_user(director).with_company(
                        company).action_approve()
        # kịch bản mới được duyệt → nạp lại vào kho tri thức
        self.env['dmag.ai.knowledge'].with_user(self.users['manager']).with_company(company).load_scripts(company)
        return True

    def _ai_customer_samples(self):
        """Tình huống mẫu cho các tính năng của ``dmag_ai_customer`` (nếu đã cài) – gọi hàm của chính module đó."""
        env = self.env
        if 'dmag.ai.reply.script' in env:
            self.try_('Kịch bản trả lời đã duyệt', self._ai_reply_scripts)
        if 'dmag.ai.knowledge' in env:
            self.try_('Kho tri thức trợ lý', self._ai_knowledge)
        if 'dmag.ai.conversation' in env and hasattr(env['dmag.ai.conversation'], '_get_or_create'):
            Conv = env['dmag.ai.conversation'].with_company(self.company)
            # Tin nhắn Zalo OA thật (đường webhook): câu trả lời của trợ lý chờ lễ tân duyệt; ca khẩn / khiếu nại chuyển người
            for uid, name, phone, messages in D.AI_ZALO_CHATS:
                def chat(uid=uid, name=name, phone=phone, messages=messages):
                    conv = Conv._get_or_create('zalo', external_user_id=uid, name=name, phone=phone)
                    for text in messages:
                        conv.receive_customer_message(text)
                    return conv
                if self.try_('Hội thoại Zalo mẫu', chat):
                    self.stats['ai_conversations'] += 1
            if 'dmag.ai.kb.gap' in env:
                self.try_('Câu hỏi ngoài dữ liệu & huấn luyện từ hộp thư', self._ai_gap_chats, Conv)
            if hasattr(Conv, 'simulator_start'):
                Sim = Conv.with_user(self.users['receptionist'])
                def simulate():
                    thread = Sim.simulator_start(name='Chị Hồng (mô phỏng)', phone='0901234567')
                    conv = Sim.browse(thread['id'])
                    for text in ('Chủ nhật phòng khám có làm việc không ạ?', 'Cạo vôi răng giá bao nhiêu vậy?',
                                 'Bác sĩ Yến làm những ngày nào ạ?', 'Cho mình đặt lịch cạo vôi chiều mai nhé'):
                        conv.simulator_send(text)
                    return conv
                if self.try_('Mô phỏng Zalo', simulate):
                    self.stats['ai_conversations'] += 1
        if 'dmag.ai.feedback' in env and hasattr(env['dmag.ai.feedback'], 'action_classify_backlog'):
            self.try_('Phân loại phản hồi', env['dmag.ai.feedback'].with_user(self.users['manager']).with_company(
                self.company).action_classify_backlog, 30)
        if 'dmag.ai.portal.assistant' in env and D.PORTAL_PATIENT in self.patients:
            partner = self.patients[D.PORTAL_PATIENT]
            self.try_('Trợ lý cổng bệnh nhân', env['dmag.ai.portal.assistant'].ask, partner,
                      'Vì sao em phải chữa tủy trước khi bọc răng sứ ạ?')
        if 'dmag.ai.care.draft' in env and hasattr(env['dmag.ai.care.draft'], 'generate_for_visit'):
            visit = env['dmag.dental.visit'].search([('company_id', '=', self.company.id), ('state', '=', 'done')],
                                                    order='scheduled_start desc', limit=1)
            if visit:
                self.try_('Nội dung chăm sóc', env['dmag.ai.care.draft'].with_user(self.users['consultant'])
                          .with_company(self.company).generate_for_visit, visit)
