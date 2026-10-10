import base64
import json
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from odoo.addons.dmag_dental_clinic.tests.common import DentalCommon


class FakeResponse:
    def __init__(self, data, status=200):
        self._data = data
        self.status_code = status
        self.text = json.dumps(data)

    def json(self):
        return self._data


@tagged('post_install', '-at_install')
class TestEsign(DentalCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls.env['dmag.esign.provider'].create({
            'name': 'Giả lập', 'provider_type': 'mock', 'sequence': 1,
            'client_id': 'cid', 'client_secret': 'super-secret',
        })

    def _signed_ready_visit(self, doctor_env=None):
        visit = self._visit()
        visit.action_check_in()
        visit.action_start()
        visit.write({'chief_complaint': 'Đau răng 36', 'examination': 'Sâu ngà 36', 'assessment': 'K02.1'})
        return visit

    def test_sign_visit_with_mock(self):
        visit = self._signed_ready_visit()
        visit.action_sign_record()
        self.assertEqual(visit.record_state, 'signed')
        req = visit.esign_request_id
        self.assertTrue(req)
        self.assertEqual(req.state, 'signed')
        self.assertEqual(visit.esign_state, 'signed')
        self.assertEqual(req.signer_id, self.doctor)
        self.assertEqual(len(req.document_hash), 64)
        self.assertTrue(req.unsigned_attachment_id.datas)
        self.assertTrue(req.signature_attachment_id.datas)
        self.assertEqual(req.signature_attachment_id.res_model, 'dmag.dental.visit')
        self.assertEqual(req.signature_attachment_id.res_id, visit.id)
        self.assertTrue(req.certificate_serial)
        self.assertIn(req.signature_format, ('cms', 'pkcs1', 'hmac'))
        # Tài liệu ký là bản dựng bệnh án SOAP
        self.assertIn(b'36', base64.b64decode(req.unsigned_attachment_id.datas))
        msg = visit.message_ids.filtered(lambda m: req.signature_attachment_id in m.attachment_ids)
        self.assertTrue(msg, 'Chữ ký số phải được đính lên chatter lượt khám')
        self.assertTrue(req.log_ids.filtered(lambda l: l.event == 'signed'))
        self.assertEqual(visit.esign_request_count, 1)

    def test_mock_waiting_then_poll(self):
        self.provider.mock_require_approval = True
        visit = self._signed_ready_visit()
        visit.action_sign_record()
        self.assertEqual(visit.esign_state, 'waiting')
        visit.action_esign_check_status()
        self.assertEqual(visit.esign_state, 'signed')

    def test_expire_pending_by_cron(self):
        self.provider.mock_require_approval = True
        visit = self._signed_ready_visit()
        visit.action_sign_record()
        req = visit.esign_request_id
        req.sudo().write({'expire_at': fields.Datetime.now() - timedelta(minutes=1)})
        self.env['dmag.esign.request']._cron_poll_pending()
        self.assertEqual(req.state, 'expired')
        self.assertEqual(visit.esign_state, 'expired')
        self.provider.mock_require_approval = False
        visit.action_esign_resend()
        self.assertEqual(req.state, 'signed')

    def test_expired_certificate_blocks_signing(self):
        self.doctor.mysign_cert_valid_to = fields.Datetime.now() - timedelta(days=1)
        self.assertEqual(self.doctor.mysign_cert_state, 'expired')
        visit = self._signed_ready_visit()
        with self.assertRaises(UserError):
            visit.action_sign_record()
        visit.invalidate_recordset()
        self.assertEqual(visit.record_state, 'draft')
        self.assertFalse(visit.esign_request_id)

    def test_secret_not_readable_by_doctor(self):
        provider = self.provider.with_user(self.doctor_user2)
        self.assertEqual(provider.name, 'Giả lập')
        with self.assertRaises(AccessError):
            provider.read(['client_secret'])
        with self.assertRaises(AccessError):
            provider.write({'base_url': 'https://evil.example'})
        self.assertTrue(provider.secret_set)

    def test_doctor_signs_own_record_cannot_edit_request(self):
        visit = self._visit(doctor_id=self.doctor2.id)
        visit.action_check_in()
        visit.action_start()
        visit.write({'chief_complaint': 'Ê buốt'})
        visit = visit.with_user(self.doctor_user2)
        visit.action_sign_record()
        req = visit.esign_request_id
        self.assertEqual(req.state, 'signed')
        self.assertEqual(req.signer_id, self.doctor2)
        with self.assertRaises(AccessError):
            req.write({'document_hash': '00'})
        with self.assertRaises(AccessError):
            req.unlink()

    def test_mysign_adapter_flow(self):
        """Luồng MySign với HTTP giả: login → chứng thư → signHash (async) → chờ → trạng thái → chữ ký PKCS#1."""
        try:
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import padding, utils as asym_utils
        except ImportError:
            self.skipTest('cryptography không có')
        mysign = self.env['dmag.esign.provider'].create({
            'name': 'MySign', 'provider_type': 'mysign', 'sequence': 0,
            'base_url': 'https://mysign.test', 'client_id': 'cid', 'client_secret': 'sec', 'profile_id': 'P1',
        })
        self.doctor.mysign_user_id = '001090000001'
        key, cert_der = mysign._mock_keypair(self.doctor)
        visit = self._signed_ready_visit()
        state = {'digest': None}
        calls = []

        def fake_post(url, json=None, headers=None, timeout=None):
            calls.append(url)
            if url.endswith('/ras/v1/login'):
                self.assertEqual(json['user_id'], '001090000001')
                return FakeResponse({'access_token': 'TOKEN'})
            self.assertEqual(headers['Authorization'], 'Bearer TOKEN')
            if url.endswith('/certificates/info'):
                return FakeResponse([{'credential_id': 'CRED1', 'cert': {
                    'certificates': [base64.b64encode(cert_der).decode()], 'status': 'VALID'}}])
            if url.endswith('/signHash'):
                state['digest'] = base64.b64decode(json['hash'][0])
                self.assertEqual(json['credentialID'], 'CRED1')
                return FakeResponse({'transactionId': 'TX-1', 'status': 'PENDING'})
            if url.endswith('/requests/status'):
                sig = key.sign(state['digest'], padding.PKCS1v15(), asym_utils.Prehashed(hashes.SHA256()))
                return FakeResponse({'transactionId': 'TX-1', 'status': 'SUCCESS',
                                     'signatures': [base64.b64encode(sig).decode()]})
            return FakeResponse({'error': 404, 'message': 'not found'}, 404)

        with patch('odoo.addons.dmag_esign_mysign.models.mysign_client.requests.post', side_effect=fake_post):
            visit.action_sign_record()
            req = visit.esign_request_id
            self.assertEqual(req.provider_id, mysign)
            self.assertEqual(req.state, 'waiting')
            self.assertEqual(req.transaction_id, 'TX-1')
            self.assertEqual(state['digest'].hex(), req.document_hash)
            self.env['dmag.esign.request']._cron_poll_pending()
        self.assertEqual(req.state, 'signed')
        self.assertEqual(req.signature_format, 'pkcs1')
        manifest = json.loads(base64.b64decode(req.signature_attachment_id.datas))
        self.assertEqual(manifest['sha256'], req.document_hash)
        self.assertTrue(manifest['certificate'])
        self.assertIn('khớp chứng thư', ' '.join(req.log_ids.mapped('message')))
        self.assertEqual(visit.esign_state, 'signed')

    def test_mysign_rejected(self):
        mysign = self.env['dmag.esign.provider'].create({
            'name': 'MySign', 'provider_type': 'mysign', 'sequence': 0,
            'base_url': 'https://mysign.test', 'client_id': 'cid', 'client_secret': 'sec',
        })
        self.doctor.mysign_user_id = '001090000001'
        visit = self._signed_ready_visit()

        def fake_post(url, json=None, headers=None, timeout=None):
            if url.endswith('/ras/v1/login'):
                return FakeResponse({'access_token': 'T'})
            if url.endswith('/certificates/info'):
                return FakeResponse({'data': {'credentials': [{'credentialID': 'C', 'validTo': '2099-01-01'}]}})
            if url.endswith('/signHash'):
                return FakeResponse({'transactionId': 'TX-2', 'status': 'PENDING'})
            return FakeResponse({'transactionId': 'TX-2', 'status': 'REJECTED'})

        with patch('odoo.addons.dmag_esign_mysign.models.mysign_client.requests.post', side_effect=fake_post):
            visit.action_sign_record()
            self.assertEqual(visit.esign_request_id.provider_id, mysign)
            visit.action_esign_check_status()
        self.assertEqual(visit.esign_state, 'rejected')
        # Bệnh án vẫn đã ký trong hệ thống; có thể gửi lại ký số
        self.assertEqual(visit.record_state, 'signed')

    def test_no_provider_does_not_block(self):
        self.provider.active = False
        visit = self._signed_ready_visit()
        visit.action_sign_record()
        self.assertEqual(visit.record_state, 'signed')
        self.assertEqual(visit.esign_state, 'none')
