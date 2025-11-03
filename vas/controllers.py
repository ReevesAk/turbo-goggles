import logging
import pytz
import random
import string
from datetime import datetime
from commons import Allocate
from accounts.models import TxModel, Rewards

from django.db import transaction

from .helpers import VAS
from .models import (
    AirtimeTopup,
    DataSubscription,
    ElectricityBill,
    TvSubscription,
    WaecRegistration,
)

current_datetime = datetime.now()
random_string = "".join(random.choices(string.ascii_letters + string.digits, k=5))
req_id = current_datetime.strftime("%Y%m%d%H%M") + "picadailys" + random_string


def generate_request_id():
    """Generate a valid request ID for VTPass."""
    # Get the current time in Africa/Lagos timezone
    lagos_tz = pytz.timezone("Africa/Lagos")
    current_time = datetime.now(lagos_tz)
    timestamp = current_time.strftime("%Y%m%d%H%M")
    random_string = "".join(random.choices(string.ascii_letters + string.digits, k=8))
    request_id = f"{timestamp}{random_string}"
    return request_id


def airtime(user, guest_id, serializer, reason, user_data):
    req_id = generate_request_id()
    airtime_response = VAS.aritime(
        service_id=user_data["serviceID"],
        req_id=req_id,
        amount=user_data["amount"],
        phone=user_data.get("phone"),
    )

    if airtime_response.status_code == 200:
        if user:
            airtime_instance = serializer.save(user=user)
        else:
            airtime_instance = serializer.save(guest_id=guest_id)
        amount = user_data["amount"]
        phone = user_data["phone"]

        # Check if user is a member then assign rewards.
        if user:
            if user.active_role == "Member" and amount >= 100:
                new_rewards = Allocate.reward(amount=amount)
            else:
                new_rewards = 0

            try:
                with transaction.atomic():
                    # Create a new transaction entry
                    tx = TxModel.objects.create(
                        user=user,
                        tx_id=airtime_response.json().get("transactionId", ""),
                        tx_reference=airtime_instance.tx_reference,
                        tx_type="Airtime",
                        amount=user_data.get("amount", 0),
                        description="Debit for airtime purchase.",
                        rwd=new_rewards,
                    )

                    rwd, _ = Rewards.objects.get_or_create(user=user)
                    rwd.balance += new_rewards
                    rwd.transaction = tx  # Assuming this is a ForeignKey to TxModel
                    rwd.save()

            except Exception as e:
                logging.error(f"Database query error: {str(e)}")

            AirtimeTopup.objects.create(
                user=user,
                serviceID=user_data["serviceID"],
                request_id=req_id,
                amount=amount,
                phone=phone,
            )

            return airtime_response.json()
    else:
        # initiate a credit refund to the customer after failed transaction.
        _ = Account.Credit(
            acct_no=user.accountNumber, amount=user["amount"], reason=reason
        )
        return airtime_response.json()


def data(user, guest_id, serializer, reason, user_data):
    req_id = generate_request_id()
    data_response = VAS.data(
        req_id=req_id,
        service_id=user_data["serviceID"],
        amount=user_data["amount"],
        phone=user_data["phone"],
        billersCode=user_data["billersCode"],
        variation_code=user_data["variation_code"],
    )
    if data_response.status_code == 200:
        if user:
            data_instance = serializer.save(user=user)
        else:
            data_instance = serializer.save(guest_id=guest_id)
        amount = user_data["amount"]
        phone = user_data["phone"]

        # Check is user is a memeber then assign rewards.
        if user:
            if user.active_role == "Member" and amount >= 100:
                new_rewards = Allocate.reward(amount=amount)
            else:
                new_rewards = 0

            try:
                with transaction.atomic():
                    tx = TxModel.objects.create(
                        user=user,
                        tx_id=data_response.json().get("transactionId", ""),
                        tx_reference=data_instance.tx_reference,
                        tx_type="Data",
                        amount=user_data.get("amount", 0),
                        description="Debit for data subscription.",
                        rwd=new_rewards,
                    )

                    rwd, _ = Rewards.objects.get_or_create(user=user)
                    rwd.balance += new_rewards
                    rwd.transaction = tx
                    rwd.save()

            except Exception as e:
                logging.error(f"Database query error: {str(e)}")

            DataSubscription.objects.create(
                user=user,
                request_id=req_id,
                serviceID=user_data["serviceID"],
                amount=amount,
                phone=phone,
            )

            return data_response.json()
    else:
        # initiate a credit refund to the customer after failed transaction.
        _ = Account.Credit(
            acct_no=user.accountNumber, amount=user_data["amount"], reason=reason
        )
        return data_response.json()


def electricity(user, guest_id, serializer, reason, user_data):
    req_id = generate_request_id()
    electricity_response = VAS.electricity(
        req_id=req_id,
        service_id=user_data["serviceID"],
        amount=user_data["amount"],
        phone=user_data["phone"],
        billersCode=user_data["billersCode"],
        variation_code=user_data["variation_code"],
    )
    if electricity_response.status_code == 200:
        if user:
            electricity_instance = serializer.save(user=user)
        else:
            electricity_instance = serializer.save(guest_id=guest_id)
        amount = user_data["amount"]

        # Check is user is a memeber then assign rewards.
        if user:
            if user.active_role == "Member" and amount >= 100:
                new_rewards = Allocate.reward(amount=amount)
            else:
                new_rewards = 0

            try:
                with transaction.atomic():
                    tx = TxModel.objects.create(
                        user=user,
                        tx_id=electricity_response.json().get("transactionId", ""),
                        tx_reference=electricity_instance.tx_reference,
                        tx_type="Electricity",
                        amount=user_data.get("amount", 0),
                        description="Debit for electricity payment.",
                        rwd=new_rewards,
                    )

                    rwd, _ = Rewards.objects.get_or_create(user=user)
                    rwd.balance += new_rewards
                    rwd.transaction = tx
                    rwd.save()

            except Exception as e:
                logging.error(f"Database query error: {str(e)}")

            ElectricityBill.objects.create(
                user=user,
                serviceID=user_data["serviceID"],
                request_id=req_id,
                amount=amount,
                variation_code=user_data["variation_code"],
                phone=user_data["phone"],
            )

            return electricity_response.json()
    else:
        # initiate a credit refund to the customer after failed transaction.
        _ = Account.Credit(
            acct_no=user.accountNumber, amount=user["amount"], reason=reason
        )
        return electricity_response.json()


def NewTvSub(user, guest_id, serializer, reason, user_data):
    req_id = generate_request_id()
    new_tv_response = VAS.newTvSub(
        req_id=req_id,
        service_id=user_data["serviceID"],
        amount=user_data["amount"],
        phone=user_data["phone"],
        billersCode=user_data["billersCode"],
        variation_code=user_data["variation_code"],
        subscription_type="change",
        quantity=user_data["quantity"],
    )

    if new_tv_response.status_code == 200:
        if user:
            new_tv_sub_instance = serializer.save(user=user)
        else:
            new_tv_sub_instance = serializer.save(guest_id=guest_id)
        tx_reference = new_tv_sub_instance.tx_reference
        amount = user_data["amount"]

        # Assign rewards if user is a member
        if user:
            new_rewards = (
                Allocate.reward(amount=amount)
                if user.active_role == "Member" and amount >= 100
                else 0
            )

            # Use the same tx_reference for TxModel
            try:
                with transaction.atomic():
                    tx = TxModel.objects.create(
                        user=user,
                        tx_id=new_tv_response.json().get("transactionId", ""),
                        tx_reference=tx_reference,
                        tx_type="Cable Subscription",
                        amount=amount,
                        description="Debit for new TV subscription payment.",
                        rwd=new_rewards,
                    )

                    # Update rewards
                    rwd, _ = Rewards.objects.get_or_create(user=user)
                    rwd.balance += new_rewards
                    rwd.transaction = tx
                    rwd.save()

            except Exception as e:
                logging.error(f"Database query error: {str(e)}")

            TvSubscription.objects.create(
                user=user,
                serviceID=user_data["serviceID"],
                subscription_type="change",
                request_id=req_id,
                quantity=user_data["serviceID"],
                amount=amount,
                phone=user_data["phone"],
            )

            return new_tv_response.json()

    # Handle failed subscription response
    else:
        _ = Account.Credit(acct_no=user.accountNumber, amount=amount, reason=reason)
        return new_tv_response.json()


def RenewTvSub(user, guest_id, serializer, reason, user_data):
    req_id = generate_request_id()
    renew_tv_response = VAS.renewTvSub(
        req_id=req_id,
        service_id=user_data["serviceID"],
        amount=user_data["amount"],
        phone=user_data["phone"],
        billersCode=user_data["billersCode"],
        subscription_type="renew",
    )
    if renew_tv_response.status_code == 200:
        if user:
            renew_tv_sub_instance = serializer.save(user=user)
        else:
            renew_tv_sub_instance = serializer.save(guest_id=guest_id)
        tx_reference = renew_tv_sub_instance.tx_reference
        amount = user_data["amount"]

        # Check is user is a memeber then assign rewards.
        if user:
            if user.active_role == "Member" and amount >= 100:
                new_rewards = Allocate.reward(amount=amount)
            else:
                new_rewards = 0

            try:
                with transaction.atomic():
                    tx = TxModel.objects.create(
                        user=user,
                        tx_id=renew_tv_response.json().get("transactionId", ""),
                        tx_reference=tx_reference,
                        tx_type="Cable Subscription",
                        amount=user_data.get("amount", 0),
                        description="Debit for tv subscription renewal.",
                        rwd=new_rewards,
                    )

                    rwd, _ = Rewards.objects.get_or_create(user=user)
                    rwd.balance += new_rewards
                    rwd.transaction = tx
                    rwd.save()

            except Exception as e:
                logging.error(f"Database query error: {str(e)}")

            TvSubscription.objects.create(
                user=user,
                serviceID=user_data["serviceID"],
                subscription_type="renew",
                request_id=req_id,
                quantity=user_data["serviceID"],
                amount=amount,
                phone=user_data["phone"],
            )

            return renew_tv_response.json()

    else:
        _ = Account.Credit(
            acct_no=user.accountNumber, amount=user["amount"], reason=reason
        )
        return renew_tv_response.json()


def waec_reg(user, guest_id, serializer, reason, user_data):
    waec_response = VAS.waec_reg(
        service_id=user_data["serviceID"],
        phone=user_data["phone"],
        variation_code=user_data["variation_code"],
        quantity=user_data["quantity"],
    )
    if waec_response.status_code == 200:
        if user:
            waec_payment_instance = serializer.save(user=user)
        else:
            waec_payment_instance = serializer.save(guest_id=guest_id)
        tx_reference = waec_payment_instance.tx_reference
        amount = waec_response.json()["amount"]

        # UserNotification.objects.create(
        #     user=user,
        #     title="Waec registration.",
        #     message=f"This is to inform you that your payment of {amount} \
        #         for WAEC registration is successful.",
        # )

        # ActivityModel.objects.create(
        #     user=user,
        #     title="Waec registration",
        #     description=f"{user.first_name} {user.last_name} just made a payment of {amount} for waec registration.",
        # )

        # Check is user is a memeber then assign rewards.
        if user:
            if user.active_role == "Member" and amount >= 100:
                new_rewards = Allocate.reward(amount=amount)
            else:
                new_rewards = 0

            try:
                with transaction.atomic():
                    tx = TxModel.objects.create(
                        user=user,
                        tx_id=waec_response.json().get("transactionId", ""),
                        tx_reference=tx_reference,
                        amount=user_data.get("amount", 0),
                        tx_type="Education",
                        description="Debit for waec registration.",
                        rwd=new_rewards,
                    )

                    rwd, _ = Rewards.objects.get_or_create(user=user)
                    rwd.balance += new_rewards
                    rwd.transaction = tx
                    rwd.save()

            except Exception as e:
                logging.error(f"Database query error: {str(e)}")

            WaecRegistration.objects.create(
                user=user,
                serviceID=user_data["serviceID"],
                request_id=req_id,
                quantity=user_data["serviceID"],
                amount=amount,
                phone=user_data["phone"],
            )

            return waec_response.json()

    else:
        # initiate a credit refund to the customer after failed transaction.
        _ = Account.Credit(
            acct_no=user.accountNumber, amount=user["amount"], reason=reason
        )
        return waec_response.json()
