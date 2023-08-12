import random
import string

import redis

from decouple import config


class OTPManager:
    """Manage user OTP."""


    redis_url = config('REDIS_URL')

    redis = redis.from_url(redis_url)

    def generate_token(self, num: int = 6) -> str:
        """Generate random token."""
        characters = string.digits
        return "".join(random.choice(characters) for _ in range(num))

    def create_otp(self, user_id: str, expires: int = 300):
        """Create OTP"""
        otp = self.generate_token()
        while self.redis.exists(otp):
            otp = self.generate_token()
        self.redis.set(otp, user_id, ex=expires)
        return otp

    def validate_user_otp(self, otp: str):
        """Check that otp is valid."""
        if self.redis.exists(otp):
            user_id = self.redis.get(otp).decode("utf-8")
            self.delete_user_otp(otp)
            return user_id
        return None

    def delete_user_otp(self, otp: str):
        """Delete user OTP."""
        if self.redis.exists(otp):
            self.redis.delete(otp)


otp_manager = OTPManager()
