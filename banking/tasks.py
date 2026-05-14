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
    beneficiary_name=None,
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
            beneficiary_name=beneficiary_name,
            sender_name=sender_full_name,
            sender_account_number=account_number,
            amount=amount_str,
            available_balance=new_balance,
        )

        message = f"Dear {sender_full_name},\nYour transfer of ₦{amount_str} has been confirmed. Your available balance is ₦{new_balance}."
        UserNotification.objects.create(
            user=user, title="Bank Transfer", message=message
        )
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
                {"label": "Sender Name", "value": sender_full_name},
                {"label": "Sender Account", "value": account_number},
                {"label": "Receiver Name", "value": beneficiary_name or "N/A"},
                {"label": "Receiver Account", "value": beneficiary_account_number},
                {"label": "Narration", "value": narration or "No narration provided"},
                {"label": "Reference", "value": idempotency_key},
                {
                    "label": "Datetime",
                    "value": timezone.now().strftime("%d-%b-%Y %H:%M"),
                },
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


@shared_task(autoretry_for=(Exception,), max_retries=3, default_retry_delay=10)
def post_vas_update(
    user_id,
    account_number,
    amount_str,
    tx_reference,
    service_type,
    phone,
    network,
    alert_type,
    phone_number,
    email,
):
    from accounts.models import User
    from banking.models import WalletModel
    from banking.controllers import Wallet
    from gamification.points import Points
    from gamification.utils import NextBee

    try:
        user = User.objects.get(id=user_id)

        balance = 0.0
        if account_number:
            try:
                enquiry_resp = Wallet.getWalletDetails(account_number)
                if enquiry_resp and hasattr(enquiry_resp, "json"):
                    enquiry_data = enquiry_resp.json()
                    if isinstance(enquiry_data, dict):
                        bal = enquiry_data.get("data", {}).get("availableBalance")
                        if bal is not None:
                            balance = float(bal)
                            WalletModel.objects.filter(user=user).update(
                                balance=balance
                            )
            except Exception as e:
                logging.warning(f"post_vas_update: could not sync balance: {e}")

        if getattr(user, "has_done_survey", False):
            try:
                points = Points.determine(
                    activity_type="service_purchase", level=user.level
                )
                NextBee.member_activity(
                    member_email=user.email, activityId="8474", numericValue=str(points)
                )
                Points.refresh_user_points(user)
            except Exception as e:
                logging.warning(f"post_vas_update: points update failed: {e}")

        support_email = "support@picadailys.com"
        sms_msg = generate_transaction_sms(
            transaction_type=service_type,
            account_number=account_number or "",
            amount=float(amount_str),
            balance=balance,
            description=f"{service_type.title()} purchase for {phone}",
            reference=tx_reference,
        )
        sms_msg += f"\nIf you did not authorize this transaction, contact support: {support_email}"

        email_subject = f"{service_type.title()} Purchase Confirmation"
        email_context = {
            "title": email_subject,
            "rows": [
                {"label": "Amount", "value": f"₦{float(amount_str):,.2f}"},
                {"label": "Account Number", "value": account_number or ""},
                {"label": "Phone", "value": phone or ""},
                {"label": "Network", "value": network or ""},
                {"label": "Reference", "value": tx_reference},
                {
                    "label": "Datetime",
                    "value": timezone.now().strftime("%d-%b-%Y %H:%M"),
                },
                {"label": "Transaction Type", "value": service_type.title()},
                {"label": "Balance", "value": f"₦{balance:,.2f}"},
            ],
            "support_email": support_email,
            "picadailys_phone": "02012271894 02012271895",
        }
        email_body = render_to_string("picadailys_email.html", email_context)
        send_transfer_notifications.delay(
            user_id,
            phone_number[1:] if phone_number else None,
            email,
            alert_type,
            sms_msg,
            email_subject,
            email_body,
            email_body,
        )
    except Exception as e:
        logging.exception(f"post_vas_update failed for user {user_id}: {e}")


@shared_task(autoretry_for=(Exception,), max_retries=5, default_retry_delay=30)
def resolve_pending_transfer(
    tx_id,
    user_id,
    account_number,
    external_tx_reference,
    beneficiary_account_number,
    sender_full_name,
    amount_str,
    narration,
    idempotency_key,
    alert_type,
    phone_number,
    email,
    beneficiary_name=None,
):
    from accounts.models import TxModel
    from banking.controllers import Transfers

    try:
        tx = TxModel.objects.get(id=tx_id)

        if tx.status != "PENDING":
            return

        resp = Transfers.complete_transfer(transactionId=external_tx_reference)
        if resp is None:
            raise Exception("No response from complete_transfer, will retry.")

        resp_data = resp.json() if hasattr(resp, "json") else {}
        tx_status = resp_data.get("status", "").upper()

        if tx_status == "SUCCESS":
            tx.status = "SUCCESS"
            tx.save(update_fields=["status"])
            post_transfer_update.delay(
                user_id=user_id,
                tx_id=tx_id,
                account_number=account_number,
                beneficiary_account_number=beneficiary_account_number,
                sender_full_name=sender_full_name,
                amount_str=amount_str,
                narration=narration,
                idempotency_key=idempotency_key,
                alert_type=alert_type,
                phone_number=phone_number,
                email=email,
                beneficiary_name=beneficiary_name,
            )
        elif tx_status in ("FAILED", "REVERSED", "REJECTED"):
            tx.status = "FAILED"
            tx.save(update_fields=["status"])
        else:
            raise Exception(f"Transfer still pending ({tx_status}), will retry.")

    except TxModel.DoesNotExist:
        logging.error(f"resolve_pending_transfer: TxModel {tx_id} not found.")
    except Exception as e:
        logging.warning(f"resolve_pending_transfer: {e}")
        raise


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
