import os
import math
import random
import smtplib
from decouple import config

def generateOTP(email):
    digits="0123456789"
    OTP=""
    for i in range(6):
        OTP+=digits[math.floor(random.random()*10)]
    otp = OTP + " is your OTP"
    msg= otp
    
    s = smtplib.SMTP('smtp.gmail.com', 587)
    s.starttls()
    host_email = config('EMAIL_HOST_USER')
    app_password = config('EMAIL_HOST_PASSWORD')
    s.login(host_email, app_password)
    s.sendmail('&&&&&&&&&&&', email,msg)
    a = input("Enter Your OTP >>: ")
    if a == OTP:
        print("Verified")
    else:
        print("Please Check your OTP again")
    return OTP

# def confirm_OTP(otp):
    