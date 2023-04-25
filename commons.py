import os
import math
import random
import smtplib

def generateOTP(email):
    digits="0123456789"
    OTP=""
    for i in range(6):
        OTP+=digits[math.floor(random.random()*10)]
    otp = OTP + " is your OTP"
    msg= otp
    
    s = smtplib.SMTP('smtp.gmail.com', 587)
    s.starttls()
    os.environ.get("")
    s.login("akwareeves@gmail.com", "obtlmutntqbcjayy")
    s.sendmail('&&&&&&&&&&&', email,msg)
    a = input("Enter Your OTP >>: ")
    if a == OTP:
        print("Verified")
    else:
        print("Please Check your OTP again")