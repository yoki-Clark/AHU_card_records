import os
import json
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

_KEY_FILE = '.encryption_key'
_SALT_FILE = '.encryption_salt'


def _get_or_create_key():
    if os.path.exists(_KEY_FILE) and os.path.exists(_SALT_FILE):
        with open(_SALT_FILE, 'rb') as f:
            salt = f.read()
        with open(_KEY_FILE, 'rb') as f:
            key = f.read()
        return Fernet(key)

    salt = os.urandom(16)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,
    )
    seed = os.urandom(32)
    key = base64.urlsafe_b64encode(kdf.derive(seed))

    with open(_SALT_FILE, 'wb') as f:
        f.write(salt)
    with open(_KEY_FILE, 'wb') as f:
        f.write(key)
    try:
        os.chmod(_KEY_FILE, 0o600)
    except OSError:
        pass

    return Fernet(key)


def encrypt_config(file_path, sensitive_keys=('headers', 'Cookie', 'synjones-auth')):
    if not os.path.exists(file_path):
        return False
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    fernet = _get_or_create_key()
    modified = False
    headers = data.get('headers', {})
    if isinstance(headers, dict):
        for key in list(headers.keys()):
            if key in sensitive_keys:
                val = headers[key]
                if isinstance(val, str) and not val.startswith('ENC:'):
                    encrypted = fernet.encrypt(val.encode('utf-8'))
                    headers[key] = 'ENC:' + base64.urlsafe_b64encode(encrypted).decode('ascii')
                    modified = True
    if modified:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    return modified


def decrypt_headers(headers):
    if not isinstance(headers, dict):
        return headers
    fernet = _get_or_create_key()
    result = {}
    for key, val in headers.items():
        if isinstance(val, str) and val.startswith('ENC:'):
            try:
                encrypted = base64.urlsafe_b64decode(val[4:].encode('ascii'))
                result[key] = fernet.decrypt(encrypted).decode('utf-8')
            except Exception:
                result[key] = val
        else:
            result[key] = val
    return result


def load_user_config(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    data['headers'] = decrypt_headers(data.get('headers', {}))
    return data
