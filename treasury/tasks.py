import logging
from decimal import Decimal

from celery import shared_task
from django.template.loader import render_to_string
from django.utils import timezone

from accounts.models import UserNotification, TxModel, User
from treasury.models import TreasuryAccount, TreasuryTransfer
from treasury.controllers import Anchor
from roles.models import ActivityModel
from commons import Messaging

logger = logging.getLogger(__name__)

default_from_email = "notifications@picadailys.com"


@shared_task
def create_notification(user_id, title, message):
    try:
        user = User.objects.get(id=user_id)
        UserNotification.objects.create(user=user, title=title, message=message)
    except Exception as e:
        logger.warning("treasury create_notification task failed: %s", e)


@shared_task
def create_activity(user_id, title, description):
    try:
        user = User.objects.get(id=user_id)
        ActivityModel.objects.create(user=user, title=title, description=description)
    except Exception as e:
        logger.warning("treasury create_activity task failed: %s", e)


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
    anchor_account_id,
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
    transfer_type="EXTERNAL",
):
    try:
        user = User.objects.get(id=user_id)
        tx = TxModel.objects.get(id=tx_id)
        amount = Decimal(amount_str)

        new_balance = Decimal("0")
        if anchor_account_id:
            try:
                bal_resp = Anchor.get_balance(anchor_account_id)
                if bal_resp and Anchor.is_success(bal_resp):
                    kobo = bal_resp.json().get("data", {}).get("availableBalance", 0)
                    new_balance = Decimal(str(kobo)) / 100
                    TreasuryAccount.objects.filter(user=user).update(balance=new_balance)
            except Exception as e:
                logger.warning("post_transfer_update: could not sync balance: %s", e)

        TreasuryTransfer.objects.create(
            user=user,
            tx=tx,
            transfer_type=transfer_type,
            status="SUCCESS",
            beneficiary_account_number=beneficiary_account_number,
            beneficiary_name=beneficiary_name,
            sender_account_number=account_number,
            sender_name=sender_full_name,
            amount=amount_str,
            narration=narration,
            tx_reference=idempotency_key,
        )

        message = (
            f"Dear {sender_full_name},\n"
            f"Your transfer of ₦{amount_str} has been confirmed. "
            f"Available balance: ₦{new_balance}."
        )
        UserNotification.objects.create(user=user, title="Transfer", message=message)

        ActivityModel.objects.create(
            user=user,
            title="Transfer",
            description=f"{sender_full_name} transferred ₦{amount_str}. Balance: ₦{new_balance}.",
        )

        email_context = {
            "title": "Debit Alert",
            "rows": [
                {"label": "Amount", "value": f"₦{float(amount):,.2f}"},
                {"label": "Sender Name", "value": sender_full_name},
                {"label": "Sender Account", "value": account_number},
                {"label": "Receiver Name", "value": beneficiary_name or "N/A"},
                {"label": "Receiver Account", "value": beneficiary_account_number},
                {"label": "Narration", "value": narration or "No narration"},
                {"label": "Reference", "value": idempotency_key},
                {"label": "Datetime", "value": timezone.now().strftime("%d-%b-%Y %H:%M")},
                {"label": "Balance", "value": f"₦{float(new_balance):,.2f}"},
            ],
            "support_email": "notifications@picadailys.com",
            "picadailys_phone": "02012271894 02012271895",
        }
        email_body = render_to_string("picadailys_email.html", email_context)
        sms_msg = (
            f"Debit: Acct {account_number} | Amt: ₦{float(amount):,.2f} | "
            f"To: {beneficiary_account_number} | Bal: ₦{float(new_balance):,.2f} | "
            f"Ref: {idempotency_key}"
        )
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
        logger.exception("post_transfer_update failed for user %s: %s", user_id, e)


@shared_task(autoretry_for=(Exception,), max_retries=3, default_retry_delay=10)
def post_treasury_vas_update(
    user_id,
    anchor_account_id,
    amount_str,
    tx_reference,
    service_type,
    phone,
    network,
    alert_type,
    phone_number,
    email,
):
    try:
        user = User.objects.get(id=user_id)

        new_balance = Decimal("0")
        if anchor_account_id:
            try:
                bal_resp = Anchor.get_balance(anchor_account_id)
                if bal_resp and Anchor.is_success(bal_resp):
                    kobo = bal_resp.json().get("data", {}).get("availableBalance", 0)
                    new_balance = Decimal(str(kobo)) / 100
                    TreasuryAccount.objects.filter(user=user).update(balance=new_balance)
            except Exception as e:
                logger.warning("post_treasury_vas_update: balance sync failed: %s", e)

        support_email = "support@picadailys.com"
        sms_msg = (
            f"{service_type.title()}: Acct {anchor_account_id} | "
            f"Amt: ₦{float(amount_str):,.2f} | Phone: {phone} | "
            f"Bal: ₦{float(new_balance):,.2f} | Ref: {tx_reference}\n"
            f"If unauthorized contact: {support_email}"
        )
        email_subject = f"{service_type.title()} Purchase Confirmation"
        email_context = {
            "title": email_subject,
            "rows": [
                {"label": "Amount", "value": f"₦{float(amount_str):,.2f}"},
                {"label": "Phone", "value": phone or ""},
                {"label": "Network", "value": network or ""},
                {"label": "Reference", "value": tx_reference},
                {"label": "Transaction Type", "value": service_type.title()},
                {"label": "Balance", "value": f"₦{float(new_balance):,.2f}"},
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
        logger.exception("post_treasury_vas_update failed for user %s: %s", user_id, e)


@shared_task(autoretry_for=(Exception,), max_retries=3, default_retry_delay=10)
def post_beneficiary_credit(
    beneficiary_user_id,
    beneficiary_anchor_account_id,
    beneficiary_account_number,
    sender_name,
    amount_str,
    narration,
    tx_reference,
    alert_type,
    phone_number,
    email,
):
    """
    Immediately credits User B after a confirmed internal transfer.
    Fetches the authoritative balance from Anchor so the webhook reconciliation
    is idempotent (it finds the TxModel we create here and skips).
    """
    try:
        user = User.objects.get(id=beneficiary_user_id)

        new_balance = Decimal("0")
        if beneficiary_anchor_account_id:
            try:
                bal_resp = Anchor.get_balance(beneficiary_anchor_account_id)
                if bal_resp and Anchor.is_success(bal_resp):
                    kobo = bal_resp.json().get("data", {}).get("availableBalance", 0)
                    new_balance = Decimal(str(kobo)) / 100
                    TreasuryAccount.objects.filter(user=user).update(balance=new_balance)
            except Exception as e:
                logger.warning("post_beneficiary_credit: balance sync failed: %s", e)

        # get_or_create so re-runs are idempotent; webhook will also hit this and skip
        TxModel.objects.get_or_create(
            user=user,
            tx_reference=tx_reference,
            defaults={
                "tx_type": "Wallet Credit",
                "amount": amount_str,
                "description": narration or f"Transfer from {sender_name}",
                "status": "SUCCESS",
            },
        )

        UserNotification.objects.create(
            user=user,
            title="Credit Alert",
            message=f"Your account has been credited with ₦{amount_str}. {narration or ''}".strip(),
        )
        ActivityModel.objects.create(
            user=user,
            title="Wallet Credit",
            description=f"{getattr(user, 'full_name', str(user))}'s account credited ₦{amount_str} from {sender_name}. Balance: ₦{new_balance}.",
        )

        email_context = {
            "title": "Credit Alert",
            "rows": [
                {"label": "Amount", "value": f"₦{float(amount_str):,.2f}"},
                {"label": "Account Number", "value": beneficiary_account_number},
                {"label": "Sender", "value": sender_name},
                {"label": "Narration", "value": narration or "Transfer"},
                {"label": "Reference", "value": tx_reference},
                {"label": "Balance After", "value": f"₦{float(new_balance):,.2f}"},
            ],
            "support_email": "notifications@picadailys.com",
            "picadailys_phone": "02012271894 02012271895",
        }
        email_body = render_to_string("picadailys_email.html", email_context)
        sms_msg = (
            f"Credit: Acct {beneficiary_account_number} | Amt: ₦{float(amount_str):,.2f} | "
            f"From: {sender_name} | Bal: ₦{float(new_balance):,.2f} | Ref: {tx_reference}"
        )
        send_transfer_notifications.delay(
            beneficiary_user_id,
            phone_number[1:] if phone_number else None,
            email,
            alert_type,
            sms_msg,
            "Credit Alert",
            email_body,
            email_body,
        )
    except Exception as e:
        logger.exception("post_beneficiary_credit failed for user %s: %s", beneficiary_user_id, e)
