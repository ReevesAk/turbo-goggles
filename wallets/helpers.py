import random
import string


def generate_random_string(length):
    characters = string.ascii_letters + string.digits  # Letters and digits
    result = "".join(random.choice(characters) for _ in range(length))
    return result


def insert_hyphens(input_string, hyphen_frequency):
    return "-".join(
        [
            input_string[i : i + hyphen_frequency]
            for i in range(0, len(input_string), hyphen_frequency)
        ]
    )
