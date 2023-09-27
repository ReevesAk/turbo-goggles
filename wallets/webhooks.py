import hmac
import hashlib
import json
from decouple import config
import requests

wb_key = config("WEBHOOK_SECRET_KEY")


def encrypt_webhook_data():
    webhook_secret_key = wb_key
    payload = "The webhook payload"

    # encode the webhook key and save it in a variable
    key = webhook_secret_key.encode("utf-8")

    # convert the payload into serialized json
    message = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    # encrypt the payload
    encrypted_data = hmac.new(key, message, hashlib.sha512).hexdigest()

    # get the signature from the header
    signature = requests.headers["signature"]

    # check signature authencity
    if signature == encrypted_data:
        print("process")
    else:
        print("discard!")
