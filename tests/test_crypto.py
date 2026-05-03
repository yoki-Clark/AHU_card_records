import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
import json
import tempfile
import shutil
from app.crypto_utils import encrypt_config, decrypt_headers


class TestCryptoRoundtrip(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.tmpdir, 'config_test.json')

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_encrypt_decrypt_roundtrip(self):
        original = {
            "user_id": "G12345678",
            "user_name": "测试用户",
            "headers": {
                "Accept": "*/*",
                "Cookie": "JSESSIONID=abc123; CASTGC=TGT-def456",
                "synjones-auth": "bearer eyJhbGciOiJIUzI1NiJ9.secret_token",
                "User-Agent": "Mozilla/5.0",
                "Host": "ycard.ahu.edu.cn"
            },
            "update_time": "2026-04-28 22:42:39"
        }
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(original, f, indent=4, ensure_ascii=False)

        result = encrypt_config(self.config_path)
        self.assertTrue(result)

        with open(self.config_path, 'r', encoding='utf-8') as f:
            encrypted_data = json.load(f)

        for key in ('Cookie', 'synjones-auth'):
            self.assertTrue(
                encrypted_data['headers'][key].startswith('ENC:'),
                f"Expected {key} to be encrypted"
            )
        self.assertEqual(encrypted_data['headers']['Accept'], original['headers']['Accept'])
        self.assertEqual(encrypted_data['headers']['User-Agent'], original['headers']['User-Agent'])
        self.assertEqual(encrypted_data['headers']['Host'], original['headers']['Host'])

        decrypted = decrypt_headers(encrypted_data['headers'])
        for key in original['headers']:
            self.assertEqual(decrypted[key], original['headers'][key])

    def test_encrypt_no_sensitive_keys(self):
        data = {
            "user_id": "G12345678",
            "user_name": "test",
            "headers": {
                "Accept": "*/*",
                "Host": "example.com"
            },
            "update_time": "2026-01-01 00:00:00"
        }
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

        result = encrypt_config(self.config_path)
        self.assertFalse(result)

    def test_decrypt_plain_headers(self):
        plain = {"Accept": "*/*", "Host": "example.com"}
        result = decrypt_headers(plain)
        self.assertEqual(result, plain)

    def test_decrypt_non_dict(self):
        result = decrypt_headers("not a dict")
        self.assertEqual(result, "not a dict")

    def test_double_encrypt_noop(self):
        original = {
            "user_id": "G12345678",
            "user_name": "test",
            "headers": {
                "Cookie": "test=value",
            },
            "update_time": "2026-01-01 00:00:00"
        }
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(original, f)

        encrypt_config(self.config_path)
        result2 = encrypt_config(self.config_path)
        self.assertFalse(result2)


if __name__ == '__main__':
    unittest.main()
