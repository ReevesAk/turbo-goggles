import base64
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from decouple import config


def _aes_params():
    # Called at runtime, not import time, so env vars are guaranteed to be loaded.
    key = base64.b64decode(config("AES_KEY"))
    iv = base64.b64decode(config("AES_IV"))
    return key, iv


def encrypt_field(value: str) -> str:
    if not value:
        return value
    key, iv = _aes_params()
    cipher = AES.new(key, AES.MODE_CBC, iv)
    ct = cipher.encrypt(pad(value.encode(), AES.block_size))
    return base64.b64encode(ct).decode()


def decrypt_field(value: str) -> str:
    if not value:
        return value
    try:
        key, iv = _aes_params()
        ct = base64.b64decode(value)
        cipher = AES.new(key, AES.MODE_CBC, iv)
        return unpad(cipher.decrypt(ct), AES.block_size).decode()
    except Exception:
        return value  # passthrough: plaintext value not yet migrated
