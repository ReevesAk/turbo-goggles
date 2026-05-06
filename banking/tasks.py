# Standard library imports
import logging
import time
from datetime import date, timedelta
from decimal import Decimal

# Third-party imports
import schedule
from celery import shared_task
from django.template.loader import render_to_string
from django.utils import timezone

# Django app imports
from banking.helpers import generate_transaction_sms
from commons import Messaging

scheduled_charges = {}


default_from_email = "notifications@picadailys.com"


@shared_task
def send_transfer_notifications(
    user_id,
    phone_number,
    email,
    alert_type,
    sms_msg,
    email_subject,
    email_body,
    html_content=None,
):
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


@shared_task(autoretry_for=(Exception,), max_retries=3, default_retry_delay=10)
def post_transfer_update(
    user_id,
    tx_id,
    account_number,
    beneficiary_account_number,
    sender_full_name,
    amount_str,
    narration,
    idempotency_key,
    alert_type,
    phone_number,
    email,
):
    from accounts.models import UserNotification
    from banking.models import WalletModel, TransferModel
    from banking.controllers import Wallet
    from accounts.models import TxModel
    from roles.models import ActivityModel
    from accounts.models import User

    try:
        user = User.objects.get(id=user_id)
        tx = TxModel.objects.get(id=tx_id)
        amount = Decimal(amount_str)

        new_balance = Decimal("0")
        try:
            post_sync = Wallet.getWalletDetails(account_number)
            if post_sync and hasattr(post_sync, "json"):
                post_data = post_sync.json()
                if post_data.get("status") == "SUCCESS":
                    new_balance = Decimal(
                        str(post_data["data"].get("availableBalance", 0))
                    )
                    WalletModel.objects.filter(user=user).update(balance=new_balance)
        except Exception as e:
            logging.warning(f"post_transfer_update: could not sync balance: {e}")

        TransferModel.objects.create(
            user=user,
            tx=tx,
            beneficiary_account_number=beneficiary_account_number,
            sender_name=sender_full_name,
            amount=amount_str,
            available_balance=new_balance,
        )

        message = f"Dear {sender_full_name},\nYour transfer of ₦{amount_str} has been confirmed. Your available balance is ₦{new_balance}."
        UserNotification.objects.create(user=user, title="Bank Transfer", message=message)
        ActivityModel.objects.create(
            user=user,
            title="Bank Transfer",
            description=f"{sender_full_name} made a transfer of ₦{amount_str}. Available balance is ₦{new_balance}.",
        )

        amount_val = float(amount)
        balance_val = float(new_balance)
        sms_msg = generate_transaction_sms(
            transaction_type="DEBIT",
            account_number=account_number,
            amount=amount_val,
            balance=balance_val,
            description=f"Transfer to {beneficiary_account_number}",
            reference=idempotency_key,
        )
        email_context = {
            "title": "Debit Alert",
            "rows": [
                {"label": "Amount", "value": f"₦{amount_val:,.2f}"},
                {"label": "Account Number", "value": account_number},
                {"label": "Narration", "value": narration or "No narration provided"},
                {"label": "Reference", "value": idempotency_key},
                {"label": "Datetime", "value": timezone.now().strftime("%d-%b-%Y %H:%M")},
                {"label": "Transaction Type", "value": "Debit"},
                {"label": "Balance", "value": f"₦{balance_val:,.2f}"},
            ],
            "support_email": "notifications@picadailys.com",
            "picadailys_phone": "02012271894 02012271895",
        }
        email_body = render_to_string("picadailys_email.html", email_context)
        send_transfer_notifications.delay(
            user_id,
            phone_number[1:] if phone_number else None,
            email,
            alert_type,
            sms_msg,
            "Debit Alert",
            email_body,
            email_body,
        )
    except Exception as e:
        logging.exception(f"post_transfer_update failed for user {user_id}: {e}")


# def charge_cards_every_30_days():
#     today = date.today()
#     cards = Cards.objects.filter(auto_approve=True)  # Filter eligible cards
#     for card in cards:
#         # Check if a scheduled charge exists for this card
#         if card.id not in scheduled_charges:
#             # First time for this card - calculate next execution date
#             next_charge_date = card.created_at + timedelta(days=30)
#             scheduled_charges[card.id] = next_charge_date
#             if scheduled_charges[card.id] <= today:
#                 try:
#                     fx_resp = Forex.generate_quote()
#                     if fx_resp.status_code == 200:
#                         fx_rate = fx_resp.json()["data"]["rate"]

#                         dollars = 1
#                         naira_value = dollars / fx_rate

#                     # Inititate a debit on the customer's account for card creation.
#                     debit_response = Account.Debit(
#                         amount=naira_value, reason="Debit for card maintenance."
#                     )
#                     if debit_response == 200:
#                         # UserNotification.objects.create(
#                         #     user=authenticated_user,
#                         #     title="Reset Wallet Pin.",
#                         #     message="Wallet pin reset was successful.",
#                         # )

#                         # ActivityModel.objects.create(
#                         #     user=user,
#                         #     title="Reset Wallet Pin.",
#                         #     description=f"{user.first_name} {user.last_name} has reset their wallet pin."
#                         # )
#                         logging.info(msg="Cards successfully charged for maintenance.")
#                         # send_mail(
#                         #     subject="Card Charge Successful",
#                         #     message=f"Card charge for {card.user.email} was successful.",
#                         #     recipient_list=[card.user.email],
#                         #     fail_silently=False,
#                         # )
#                     else:
#                         logging.error(msg="Cards charge error")
#                         # send_mail(
#                         #     subject="Card Charge Failed",
#                         #     message=f"Card charge for {card.user.email} failed. Please check card details.",
#                         #     recipient_list=[card.user.email],
#                         #     fail_silently=False,
#                         # )
#                 except Exception as e:
#                     logging.error("Card charge error:", e)


# # Schedule the task to run every 30 days
# schedule.every(30).days.do(charge_cards_every_30_days)

# while True:
#     schedule.run_pending()
#     time.sleep(1)
