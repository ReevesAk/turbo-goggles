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
    "X-Session-Key": SESSION_KEY
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
