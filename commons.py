import math
import random

def generateOTP(OTP) :
    digits = "0123456789"
    OTP = ""
    for i in range(6) :
        OTP += digits[math.floor(random.random() * 10)]
        return OTP

def upload_to(instance, filename):
    return 'profile/{filename}'.format(filename=filename)
