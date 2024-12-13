import json
import binascii
from base64 import b64decode, b64encode
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from decouple import config


# Load the AES key and IV from environment.
AES_KEY = config("AES_KEY")
AES_IV = config("AES_IV")


aes_key = b64decode(AES_KEY)
aes_iv = b64decode(AES_IV)


def decrypt(cipher_text):
    try:
        # Decode Base64 data to bytes
        byte_data = b64decode(cipher_text)
        cipher = AES.new(aes_key, AES.MODE_CBC, aes_iv)

        # Decrypt the data
        decrypted_padded = cipher.decrypt(byte_data)
        decrypted_data = unpad(decrypted_padded, AES.block_size)

        try:
            resp = json.loads(decrypted_data.decode("utf-8"))
            return resp
        except UnicodeDecodeError as e:
            print(f"Error decoding to UTF-8: {e}")
            # Return raw bytes if decoding fails
            return decrypted_data

    except Exception as e:
        raise ValueError(f"Decryption failed: {e}")


def encrypt(json_data: dict):
    data_str = json.dumps(json_data)

    try:
        # Encrypt the data
        cipher = AES.new(aes_key, AES.MODE_CBC, aes_iv)
        padded_data = pad(data_str.encode('utf-8'), AES.block_size)
        encrypted_data = cipher.encrypt(padded_data)

        # Convert encrypted data to hexadecimal format
        encrypted_data_hex = encrypted_data.hex()

        byte_data = binascii.unhexlify(encrypted_data_hex)

        # Step 2: Encode bytes to Base64
        base64_encoded = b64encode(byte_data)

        # Convert Base64 bytes to string
        base64_string = base64_encoded.decode('utf-8')

        return base64_string

    except Exception as e:
        raise ValueError(f"Encryption failed: {e}")
