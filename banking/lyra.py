import json
import hashlib
from base64 import b64decode
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from decouple import config


# Load the AES key and IV from environment.
AES_KEY = config("AES_KEY")
AES_IV = config("AES_IV")


def sha512_to_hex(key: str) -> str:
    """Convert a key to its SHA-512 hex digest."""
    sha512_hash = hashlib.sha512()
    sha512_hash.update(key.encode("utf-8"))
    hex_digest = sha512_hash.hexdigest()
    return hex_digest


aes_key = b64decode(AES_KEY)
aes_iv = b64decode(AES_IV)


def decrypt(cipher_text):
    cipher = AES.new(key=aes_key, mode=AES.MODE_CBC, iv=aes_iv)
    decrypted_data = cipher.decrypt(cipher_text)

    padding_length = decrypted_data[-1]
    decrypted_data = decrypted_data[:-padding_length]

    resp = json.loads(decrypted_data.decode("utf-8"))
    return resp


def encrypt(json_data: dict):
    # Serialize data to JSON string
    data_str = json.dumps(json_data)

    # Encrypt the data
    cipher = AES.new(aes_key, AES.MODE_CBC, aes_iv)
    padded_data = pad(data_str.encode("utf-8"), AES.block_size)
    encrypted_data = cipher.encrypt(padded_data)

    # Convert encrypted data to hexadecimal
    encrypted_data_hex = encrypted_data.hex()
    return encrypted_data_hex
