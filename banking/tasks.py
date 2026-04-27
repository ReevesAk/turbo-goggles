
# Standard library imports
import logging
import time
from datetime import date, timedelta

# Third-party imports

import schedule
from celery import shared_task


# Django app imports
from banking.helpers import generate_transaction_sms
from commons import Messaging
from .controllers import Forex, Account
from .models import Cards

scheduled_charges = {}



default_from_email = "notifications@picadailys.com"

@shared_task
def send_transfer_notifications(user_id, phone_number, email, alert_type, sms_msg, email_subject, email_body, html_content=None):
    if alert_type in ("SMS", "Both") and phone_number:
        Messaging.send_sms(phone_number, sms_msg)
    if alert_type in ("Email", "Both") and email:
        Messaging.send_email(
            email=email,
            html_content=html_content or email_body,
            sender_email=default_from_email,
            subject=email_subject,
            body=email_body,
        )

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
                        # UserNotification.objects.create(
                        #     user=authenticated_user,
                        #     title="Reset Wallet Pin.",
                        #     message="Wallet pin reset was successful.",
                        # )

                        # ActivityModel.objects.create(
                        #     user=user,
                        #     title="Reset Wallet Pin.",
                        #     description=f"{user.first_name} {user.last_name} has reset their wallet pin."
                        # )
                        logging.info(msg="Cards successfully charged for maintenance.")
                        # send_mail(
                        #     subject="Card Charge Successful",
                        #     message=f"Card charge for {card.user.email} was successful.",
                        #     recipient_list=[card.user.email],
                        #     fail_silently=False,
                        # )
                    else:
                        logging.error(msg="Cards charge error")
                        # send_mail(
                        #     subject="Card Charge Failed",
                        #     message=f"Card charge for {card.user.email} failed. Please check card details.",
                        #     recipient_list=[card.user.email],
                        #     fail_silently=False,
                        # )
                except Exception as e:
                    logging.error("Card charge error:", e)


# Schedule the task to run every 30 days
schedule.every(30).days.do(charge_cards_every_30_days)

while True:
    schedule.run_pending()
    time.sleep(1)
