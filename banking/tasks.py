import logging
import schedule, time
from datetime import date, timedelta

from django.core.mail import send_mail

from .controllers import Forex, Account
from .models import Cards

scheduled_charges = {}

def charge_cards_every_30_days():
    today = date.today()
    cards = Cards.objects.filter(auto_approve=True)  # Filter eligible cards
    for card in cards:
        # Check if a scheduled charge exists for this card
        if card.id not in scheduled_charges:
            # First time for this card - calculate next execution date
            next_charge_date = card.created_at + timedelta(days=30)
            scheduled_charges[card.id] = next_charge_date
            if scheduled_charges[card.id] <= today:
                try:
                    fx_resp = Forex.generate_quote()
                    if fx_resp.status_code == 200:
                        fx_rate = fx_resp.json()["data"]["rate"]

                        dollars = 1
                        naira_value = dollars / fx_rate

                    # Inititate a debit on the customer's account for card creation.
                    debit_response = Account.Debit(
                        amount=naira_value, reason="Debit for card maintenance."
                    )
                    if debit_response == 200:
                        logging.info(msg="Cards successfully charged for maintenance.")
                        send_mail(
                            subject="Card Charge Successful",
                            message=f"Card charge for {card.user.email} was successful.",
                            recipient_list=[card.user.email],
                            fail_silently=False
                        )
                    else:
                        logging.error(msg="Cards charge error")
                        send_mail(
                            subject="Card Charge Failed",
                            message=f"Card charge for {card.user.email} failed. Please check card details.",
                            recipient_list=[card.user.email],
                            fail_silently=False
                        )
                except Exception as e:
                    logging.error("Card charge error:", e)

# Schedule the task to run every 30 days
schedule.every(30).days.do(charge_cards_every_30_days)

while True:
    schedule.run_pending()
    time.sleep(1)
