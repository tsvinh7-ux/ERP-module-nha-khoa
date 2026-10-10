import base64
import hashlib
import hmac
import logging
import uuid
from datetime import datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .mysign_client import DEFAULT_PATHS, OID_RSA, OID_SHA256, MySignClient, MySignError

_logger = logging.getLogger(__name__)

try:
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa, utils as asym_utils
    from cryptography.x509.oid import NameOID
    try:
        from cryptography.hazmat.primitives.serialization import pkcs7
    except ImportError:  # cryptography < 3.2
        pkcs7 = None
except ImportError:  # pragma: no cover
    x509 = None
    pkcs7 = None

DIRECTOR = 'dmag_dental_base.group_dmag_director'


def parse_certificate(cert):
    """Đọc thông tin chứng thư X.509 (DER bytes, base64 hoặc PEM). Trả {} nếu không đọc được."""
    if not cert or x509 is None:
        return {}
    try:
        if isinstance(cert, str):
            cert = cert.strip()
            if cert.startswith('-----BEGIN'):
                obj = x509.load_pem_x509_certificate(cert.encode(), default_backend())
            else:
                obj = x509.load_der_x509_certificate(base64.b64decode(cert), default_backend())
        else:
            obj = x509.load_der_x509_certificate(cert, default_backend())
    except Exception:  # noqa: BLE001 – chứng thư sai định dạng: bỏ qua, không chặn luồng
        _logger.warning('Không đọc được chứng thư số', exc_info=True)
        return {}
    return {
        'subject': obj.subject.rfc4514_string(),
        'serial': format(obj.serial_number, 'X'),
        'valid_to': obj.not_valid_after.replace(tzinfo=None),
        'der': obj.public_bytes(serialization.Encoding.DER),
        'object': obj,
    }


def _parse_datetime(value):
    if not value:
        return False
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    text = str(value).strip().replace('T', ' ').rstrip('Z')
    for candidate in (text, text[:19], text[:10]):
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d/%m/%Y %H:%M:%S', '%d/%m/%Y', '%Y%m%d%H%M%S'):
            try:
                return datetime.strptime(candidate, fmt)
            except ValueError:
                continue
    return False


class DmagEsignProvider(models.Model):
    """Nhà cung cấp ký số từ xa (cấu hình theo phòng khám)."""
    _name = 'dmag.esign.provider'
    _description = 'Nhà cung cấp ký số'
    _order = 'sequence, id'
    _check_company_auto = True

    name = fields.Char('Tên', required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Phòng khám', required=True,
                                 default=lambda self: self.env.company, index=True)
    provider_type = fields.Selection([
        ('mysign', 'Viettel MySign (ký từ xa)'),
        ('mock', 'Giả lập (demo / kiểm thử)'),
    ], string='Loại', required=True, default='mysign')
    base_url = fields.Char('Địa chỉ máy chủ API', help='Ví dụ: https://remotesigning.viettel.vn (theo hợp đồng Viettel-CA).')
    client_id = fields.Char('Client ID', groups=DIRECTOR)
    client_secret = fields.Char('Client secret', groups=DIRECTOR)
    profile_id = fields.Char('Profile / Service ID', help='Mã gói dịch vụ do Viettel-CA cấp (nếu có).')
    timeout = fields.Integer('Thời gian chờ HTTP (giây)', default=30)
    request_ttl = fields.Integer('Hạn chờ bác sĩ xác nhận (phút)', default=10,
                                 help='Quá hạn mà bác sĩ chưa xác nhận trên ứng dụng MySign → yêu cầu hết hạn.')
    token_path = fields.Char('Endpoint lấy token', default=DEFAULT_PATHS['token'])
    certificate_path = fields.Char('Endpoint danh sách chứng thư', default=DEFAULT_PATHS['certificates'])
    sign_path = fields.Char('Endpoint ký hash', default=DEFAULT_PATHS['sign'])
    status_path = fields.Char('Endpoint trạng thái giao dịch', default=DEFAULT_PATHS['status'])
    hash_algo = fields.Char('OID thuật toán băm', default=OID_SHA256)
    sign_algo = fields.Char('OID thuật toán ký', default=OID_RSA)
    mock_require_approval = fields.Boolean(
        'Giả lập chờ xác nhận', help='Bật: yêu cầu ở trạng thái "Chờ bác sĩ xác nhận" cho đến khi kiểm tra trạng thái '
                                     '(mô phỏng bấm duyệt trên điện thoại). Tắt: ký ngay.')
    secret_set = fields.Boolean('Đã nhập secret', compute='_compute_secret_set', compute_sudo=True)

    @api.depends('client_secret')
    def _compute_secret_set(self):
        for provider in self:
            provider.secret_set = bool(provider.client_secret)

    @api.model
    def _dmag_get_provider(self, company=None):
        company = company or self.env.company
        return self.sudo().search([('company_id', '=', company.id)], limit=1)

    # ------------------------------------------------------------------ dispatch
    def _esign_fetch_certificate(self, practitioner):
        """Lấy chứng thư của bác sĩ từ nhà cung cấp và lưu vào hồ sơ bác sĩ."""
        self.ensure_one()
        info = getattr(self, '_%s_fetch_certificate' % self.provider_type)(practitioner)
        vals = {
            'mysign_credential_id': info.get('credential_id') or practitioner.mysign_credential_id,
            'mysign_cert_subject': info.get('subject'),
            'mysign_cert_serial': info.get('serial'),
            'mysign_cert_valid_to': info.get('valid_to') or False,
        }
        practitioner.sudo().write(vals)
        return info

    def _esign_send(self, request):
        self.ensure_one()
        return getattr(self, '_%s_send' % self.provider_type)(request)

    def _esign_poll(self, request):
        self.ensure_one()
        return getattr(self, '_%s_poll' % self.provider_type)(request)

    # ------------------------------------------------------------------ MySign
    def _mysign_client(self, practitioner):
        self.ensure_one()
        provider = self.sudo()
        if not provider.base_url or not provider.client_id or not provider.client_secret:
            raise UserError(_('Nhà cung cấp ký số "%s" chưa cấu hình đủ địa chỉ API / Client ID / Client secret.', self.name))
        if not practitioner.mysign_user_id:
            raise UserError(_('Bác sĩ %s chưa khai báo tài khoản MySign (mã người dùng / CCCD).', practitioner.name))
        return MySignClient(
            provider.base_url, provider.client_id, provider.client_secret, practitioner.mysign_user_id,
            profile_id=provider.profile_id, timeout=provider.timeout,
            paths={'token': provider.token_path, 'certificates': provider.certificate_path,
                   'sign': provider.sign_path, 'status': provider.status_path},
            hash_algo=provider.hash_algo, sign_algo=provider.sign_algo)

    def _mysign_fetch_certificate(self, practitioner, client=None):
        client = client or self._mysign_client(practitioner)
        try:
            creds = client.list_certificates()
        except MySignError as exc:
            raise UserError(str(exc)) from exc
        if not creds:
            raise UserError(_('Tài khoản MySign của bác sĩ %s chưa có chứng thư số.', practitioner.name))
        cred = next((c for c in creds if c.get('credential_id') == practitioner.mysign_credential_id), creds[0])
        parsed = parse_certificate(cred['certificates'][0]) if cred.get('certificates') else {}
        return {
            'credential_id': cred.get('credential_id'),
            'subject': parsed.get('subject') or cred.get('subject'),
            'serial': parsed.get('serial') or cred.get('serial'),
            'valid_to': parsed.get('valid_to') or _parse_datetime(cred.get('valid_to')),
            'certificate': parsed.get('der'),
            'chain': cred.get('certificates') or [],
        }

    def _mysign_send(self, request):
        practitioner = request.signer_id
        client = self._mysign_client(practitioner)
        cert = self._mysign_fetch_certificate(practitioner, client)
        if cert.get('valid_to') and cert['valid_to'] < fields.Datetime.now():
            return {'state': 'error', 'message': _('Chứng thư số MySign của bác sĩ đã hết hạn (%s).', cert['valid_to'])}
        try:
            res = client.sign_hash(cert['credential_id'], bytes.fromhex(request.document_hash),
                                   request.name, request.document_name,
                                   description=_('DMAG: ký %s', request.document_name))
        except MySignError as exc:
            return {'state': 'error', 'message': str(exc)}
        res.update({
            'credential_id': cert['credential_id'],
            'certificate': cert.get('certificate'),
            'subject': cert.get('subject'), 'serial': cert.get('serial'), 'valid_to': cert.get('valid_to'),
            'signature_format': 'pkcs1',
        })
        return res

    def _mysign_poll(self, request):
        client = self._mysign_client(request.signer_id)
        try:
            res = client.get_status(request.transaction_id)
        except MySignError as exc:
            return {'state': 'error', 'message': str(exc)}
        res['signature_format'] = 'pkcs1'
        return res

    # ------------------------------------------------------------------ Mock
    def _mock_fetch_certificate(self, practitioner):
        key, cert = self._mock_keypair(practitioner)
        parsed = parse_certificate(cert) if cert else {}
        return {
            'credential_id': 'MOCK-%s' % practitioner.id,
            'subject': parsed.get('subject') or 'CN=%s (giả lập)' % practitioner.name,
            'serial': parsed.get('serial') or 'MOCK%06d' % practitioner.id,
            'valid_to': parsed.get('valid_to') or fields.Datetime.now() + timedelta(days=365),
        }

    def _mock_keypair(self, practitioner):
        """Khóa + chứng thư tự ký sinh tại chỗ (chỉ để demo / kiểm thử – KHÔNG có giá trị pháp lý)."""
        if x509 is None:
            return None, None
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        name = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, practitioner.name or 'DMAG'),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'DMAG MOCK CA (khong co gia tri phap ly)'),
            x509.NameAttribute(NameOID.COUNTRY_NAME, 'VN'),
        ])
        now = datetime.utcnow()
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                .public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=365))
                .sign(key, hashes.SHA256(), default_backend()))
        return key, cert.public_bytes(serialization.Encoding.DER)

    def _mock_send(self, request):
        if self.mock_require_approval:
            return {'state': 'waiting', 'transaction_id': 'MOCK-%s' % uuid.uuid4().hex[:12]}
        return self._mock_sign(request)

    def _mock_poll(self, request):
        return self._mock_sign(request)

    def _mock_sign(self, request):
        content = request._get_document_content()
        digest = bytes.fromhex(request.document_hash)
        key, cert_der = self._mock_keypair(request.signer_id)
        res = {'state': 'signed', 'transaction_id': request.transaction_id or 'MOCK-%s' % uuid.uuid4().hex[:12],
               'credential_id': 'MOCK-%s' % request.signer_id.id}
        if key is None:
            secret = self.env['ir.config_parameter'].sudo().get_param('database.secret', '')
            res.update(signature=hmac.new(secret.encode(), digest, hashlib.sha256).digest(),
                       signature_format='hmac', subject='HMAC (giả lập)', serial='HMAC',
                       valid_to=fields.Datetime.now() + timedelta(days=365))
            return res
        parsed = parse_certificate(cert_der)
        res.update(certificate=cert_der, subject=parsed['subject'], serial=parsed['serial'],
                   valid_to=parsed['valid_to'])
        if pkcs7 is not None:
            res['signature'] = (pkcs7.PKCS7SignatureBuilder().set_data(content)
                                .add_signer(parsed['object'], key, hashes.SHA256())
                                .sign(serialization.Encoding.DER,
                                      [pkcs7.PKCS7Options.DetachedSignature, pkcs7.PKCS7Options.Binary]))
            res['signature_format'] = 'cms'
        else:
            res['signature'] = key.sign(digest, padding.PKCS1v15(), asym_utils.Prehashed(hashes.SHA256()))
            res['signature_format'] = 'pkcs1'
        return res

    # ------------------------------------------------------------------ actions
    def action_test_connection(self):
        """Đăng nhập thử để kiểm tra client_id / secret (dùng tài khoản MySign của người đang thao tác)."""
        self.ensure_one()
        if self.provider_type == 'mock':
            message = _('Nhà cung cấp giả lập luôn sẵn sàng.')
        else:
            practitioner = self.env['dmag.dental.visit']._current_practitioner()
            if not practitioner:
                raise UserError(_('Tài khoản của bạn chưa gắn hồ sơ bác sĩ có mã MySign để thử kết nối.'))
            try:
                self._mysign_client(practitioner).login()
            except MySignError as exc:
                raise UserError(str(exc)) from exc
            message = _('Kết nối MySign thành công.')
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'message': message, 'type': 'success', 'sticky': False}}
