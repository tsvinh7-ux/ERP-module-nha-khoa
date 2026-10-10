"""Bộ điều hợp (adapter) API ký số từ xa Viettel MySign / Viettel-CA Remote Signing.

Toàn bộ chi tiết giao thức (đường dẫn endpoint, tên trường payload, mã trạng thái)
được gom vào file này để chỉnh lại khi có tài liệu API chính thức theo hợp đồng.

Luồng (theo hướng dẫn tích hợp công khai của Viettel-CA – **CẦN XÁC NHẬN**):

1. ``POST {base}/vtss/service/ras/v1/login`` – client_id, client_secret, user_id (mã MySign /
   CCCD của bác sĩ), profile_id → ``access_token``.
2. ``POST {base}/vtss/service/certificates/info`` – liệt kê chứng thư (credentialID, chuỗi
   chứng thư, hiệu lực) của người dùng.
3. ``POST {base}/vtss/service/signHash`` – credentialID, hash (base64), hashAlgo/signAlgo (OID),
   ``async=1`` → MySign đẩy thông báo lên điện thoại bác sĩ → trả ``transactionId``.
4. ``POST {base}/vtss/service/requests/status`` – hỏi trạng thái giao dịch → chữ ký
   (PKCS#1 trên DigestInfo SHA-256, hoặc CMS tùy cấu hình hợp đồng).
"""
import base64
import logging

_logger = logging.getLogger(__name__)

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

DEFAULT_PATHS = {
    'token': '/vtss/service/ras/v1/login',
    'certificates': '/vtss/service/certificates/info',
    'sign': '/vtss/service/signHash',
    'status': '/vtss/service/requests/status',
}

OID_SHA256 = '2.16.840.1.101.3.4.2.1'
OID_RSA = '1.2.840.113549.1.1.1'

# Ánh xạ mã trạng thái giao dịch MySign → trạng thái DMAG (CẦN XÁC NHẬN với Viettel-CA)
STATUS_MAP = {
    'signed': {'1', 'SUCCESS', 'SIGNED', 'COMPLETED', 'DONE', 'APPROVED', 'OK'},
    'rejected': {'2', 'REJECT', 'REJECTED', 'DENIED', 'CANCEL', 'CANCELED', 'CANCELLED', 'REFUSED'},
    'expired': {'3', 'EXPIRED', 'TIMEOUT', 'TIME_OUT'},
    'waiting': {'0', 'PENDING', 'WAITING', 'PROCESSING', 'IN_PROGRESS', 'CREATED', 'SENT'},
}


class MySignError(Exception):
    """Lỗi gọi API MySign (mạng, HTTP, nghiệp vụ)."""


def _pick(data, *keys):
    """Lấy giá trị đầu tiên có mặt trong ``data`` hoặc ``data['data']`` (API trả không đồng nhất)."""
    scopes = [data]
    if isinstance(data, dict) and isinstance(data.get('data'), dict):
        scopes.append(data['data'])
    for scope in scopes:
        if not isinstance(scope, dict):
            continue
        for key in keys:
            if scope.get(key) not in (None, ''):
                return scope[key]
    return None


def map_status(raw):
    value = str(raw if raw is not None else '').strip().upper()
    for state, codes in STATUS_MAP.items():
        if value in codes:
            return state
    return 'waiting' if not value else 'error'


class MySignClient:
    """Gọi API MySign. Không phụ thuộc ORM để dễ kiểm thử / thay thế."""

    def __init__(self, base_url, client_id, client_secret, user_id, profile_id=None,
                 timeout=30, paths=None, hash_algo=OID_SHA256, sign_algo=OID_RSA):
        if requests is None:
            raise MySignError('Thiếu thư viện python "requests" trên máy chủ.')
        self.base_url = (base_url or '').rstrip('/')
        self.client_id = client_id
        self.client_secret = client_secret
        self.user_id = user_id
        self.profile_id = profile_id
        self.timeout = timeout or 30
        self.paths = dict(DEFAULT_PATHS, **{k: v for k, v in (paths or {}).items() if v})
        self.hash_algo = hash_algo or OID_SHA256
        self.sign_algo = sign_algo or OID_RSA
        self._token = None

    # ------------------------------------------------------------------ transport
    def _post(self, key, payload, auth=True):
        url = self.base_url + self.paths[key]
        headers = {'Content-Type': 'application/json'}
        if auth:
            headers['Authorization'] = 'Bearer %s' % self.login()
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
        except requests.RequestException as exc:
            raise MySignError('Không kết nối được MySign (%s): %s' % (url, exc)) from exc
        if resp.status_code >= 400:
            raise MySignError('MySign trả lỗi HTTP %s tại %s: %s' % (resp.status_code, self.paths[key], resp.text[:500]))
        try:
            data = resp.json()
        except ValueError as exc:
            raise MySignError('MySign trả dữ liệu không phải JSON tại %s.' % self.paths[key]) from exc
        code = _pick(data, 'error', 'errorCode', 'error_code')
        if code not in (None, 0, '0', 'SUCCESS', False):
            message = _pick(data, 'error_description', 'message', 'errorMessage', 'msg') or ''
            raise MySignError('MySign báo lỗi %s: %s' % (code, message))
        return data

    # ------------------------------------------------------------------ API
    def login(self):
        if self._token:
            return self._token
        data = self._post('token', {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'user_id': self.user_id,
            'profile_id': self.profile_id,
        }, auth=False)
        token = _pick(data, 'access_token', 'accessToken', 'token')
        if not token:
            raise MySignError('MySign không trả access_token – kiểm tra client_id / client_secret / mã người dùng.')
        self._token = token
        return token

    def list_certificates(self):
        data = self._post('certificates', {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'profile_id': self.profile_id,
            'user_id': self.user_id,
            'certificates': 'chain',
            'certInfo': True,
            'authInfo': True,
        })
        items = data if isinstance(data, list) else (
            _pick(data, 'credentials', 'certificates', 'items', 'data') or [])
        if isinstance(items, dict):
            items = [items]
        result = []
        for item in items:
            cert = item.get('cert') if isinstance(item.get('cert'), dict) else item
            chain = cert.get('certificates') or item.get('certificates') or []
            if isinstance(chain, str):
                chain = [chain]
            result.append({
                'credential_id': item.get('credential_id') or item.get('credentialID') or item.get('credentialId'),
                'certificates': chain,
                'subject': cert.get('subjectDN') or cert.get('subject'),
                'serial': cert.get('serialNumber') or cert.get('serial'),
                'valid_from': cert.get('validFrom') or cert.get('valid_from'),
                'valid_to': cert.get('validTo') or cert.get('valid_to'),
                'status': cert.get('status') or item.get('status'),
            })
        return result

    def sign_hash(self, credential_id, digest, doc_id, doc_name, description=None):
        data = self._post('sign', {
            'credentialID': credential_id,
            'numSignatures': 1,
            'description': description or doc_name,
            'documents': [{'document_id': doc_id, 'document_name': doc_name}],
            'hash': [base64.b64encode(digest).decode()],
            'hashAlgo': self.hash_algo,
            'signAlgo': self.sign_algo,
            'async': 1,
        })
        return self._parse_sign_result(data)

    def get_status(self, transaction_id):
        data = self._post('status', {'transactionId': transaction_id, 'transaction_id': transaction_id})
        return self._parse_sign_result(data, transaction_id)

    @staticmethod
    def _parse_sign_result(data, transaction_id=None):
        signatures = _pick(data, 'signatures', 'signature')
        if isinstance(signatures, str):
            signatures = [signatures]
        raw_status = _pick(data, 'status', 'transactionStatus', 'state')
        state = 'signed' if signatures else map_status(raw_status)
        return {
            'state': state,
            'raw_status': raw_status,
            'transaction_id': _pick(data, 'transactionId', 'transaction_id', 'tranId', 'sad') or transaction_id,
            'signature': base64.b64decode(signatures[0]) if signatures else None,
            'message': _pick(data, 'message', 'error_description', 'msg'),
        }
