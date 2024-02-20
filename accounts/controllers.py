from decouple import config

api_secret_key = config("MAPLERAD_SECRET_KEY")
base_url = config("MAPLERAD_BASE_URL")

headers = {
    "accept": "application/json",
    "content-Type": "application/json",
    "Authorization": "Bearer " + api_secret_key,
}
