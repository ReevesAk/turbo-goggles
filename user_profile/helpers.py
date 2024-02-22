import random

from accounts.models import Rewards

class MysteryBox():
    @staticmethod
    def open(user):
        current_user = Rewards.objects.get(user=user)
        current_user.balance -= 100.0
        current_user.save()
        
        items = ["cat", "dog", "mouse"]
        assign_randomly = random.choice(items)
        return assign_randomly
