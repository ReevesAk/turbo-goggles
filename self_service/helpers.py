import string
import random


class ProductTagmanager:
    def generate(service_type):
        letters_and_digits = string.ascii_letters + string.digits
        tag = "".join(random.choice(letters_and_digits) for i in range(10))
        return service_type + tag
