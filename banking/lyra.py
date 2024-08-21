import json
import hashlib
from base64 import b64decode
import requests
from Crypto.Cipher import AES
from Crypto import Cipher
from Crypto.Util.Padding import pad
from decouple import config


# Load the AES key and ID from environment variables
ACCESS_KEY = config('AES_ACCESS_KEY')
AES_ID = config('AES_ID')
AES_KEY = config('AES_KEY')
AES_IV = config('AES_IV')
SESSION_KEY = config("SESSION_KEY")


def sha512_to_hex(key: str) -> str:
    """Convert a key to its SHA-512 hex digest."""
    sha512_hash = hashlib.sha512()
    sha512_hash.update(key.encode('utf-8'))
    hex_digest = sha512_hash.hexdigest()
    return hex_digest

a_key_hex = sha512_to_hex(ACCESS_KEY)
aes_key = b64decode(AES_KEY)
aes_iv = b64decode(AES_IV)

# Define the resource URL and headers
headers = {
    "X-Access-Key": a_key_hex,
    "X-Access-Id": AES_ID,
    "X-Session-Key": "2500ae173bc2f16ba8c5d914659953831219a316f818b5348882c9a2a7d3714ec75958098ad2f5726dcec29ed56780f22dfc3951dce5ef7cbfc1fd6446918c254b3509e600249ad56f5f0193ceeec50e062c8a79563bcdc055c118ce6c546bcac69e81ddecd9d17370fcfc2aff3cad383fd7606d99add672dbcca84831cc0d38a698b17d24334f682fcd3e816d16b82a87c745c5c3d4bbdad1a23a98823c54d8f418429348d797887610828cad54b8169ee11f57912e5cf7f3af2aa0ff1f4646862d12e383e96ab5e48f09467b83c3da859ca30d21d1106b87177d3d6954a3da3106212a42d78463964bda56f01ab58a0290890153cf5f0b46a8085efb0e608e"
}

def decrypt(cipher_text):
    cipher = AES.new(key=aes_key, mode=AES.MODE_CBC, iv=aes_iv)
    decrypted_data = cipher.decrypt(cipher_text)

    padding_length = decrypted_data[-1]
    decrypted_data = decrypted_data[:-padding_length]

    resp = json.loads(decrypted_data.decode('utf-8'))
    return resp

def encrypt(json_data:dict):
    # Serialize data to JSON string
    data_str = json.dumps(json_data)

    # Encrypt the data
    cipher = AES.new(aes_key, AES.MODE_CBC, aes_iv)
    padded_data = pad(data_str.encode('utf-8'), AES.block_size)
    encrypted_data = cipher.encrypt(padded_data)

    # Convert encrypted data to hexadecimal
    encrypted_data_hex = encrypted_data.hex()
    return encrypted_data_hex
