import logging
import pytz
import random
import string
from datetime import datetime
from commons import Allocate
from accounts.models import TxModel, Rewards, UserNotification
from roles.models import ActivityModel

from django.db import transaction

from banking.controllers import Account
from .helpers import VAS
from .models import (
    AirtimeTopup,
    DataSubscription,
    ElectricityBill,
    TvSubscription,
    WaecRegistration,
    HealthInsurance,
    VehicleInsurance,
    AccidentInsurance,
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


def airtime(user, serializer, reason, user_data):
    req_id = generate_request_id()
    airtime_response = VAS.aritime(
        service_id=user_data["serviceID"],
        req_id=req_id,
        amount=user_data["amount"],
        phone=user_data.get("phone"),
    )

    if airtime_response.status_code == 200:
        airtime_instance = serializer.save()
        amount = user_data["amount"]
        phone = user_data["phone"]

        # Check is user is a member then assign rewards.
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


def data(user, serializer, reason, user_data):
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
        data_instance = serializer.save()
        amount = user_data["amount"]
        phone = user_data["phone"]

        # Check is user is a memeber then assign rewards.
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


def electricity(user, serializer, reason, user_data):
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
        electricity_instance = serializer.save()
        amount = user_data["amount"]

        # Check is user is a memeber then assign rewards.
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


def NewTvSub(user, serializer, reason, user_data):
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
        new_tv_sub_instance = serializer.save()
        tx_reference = new_tv_sub_instance.tx_reference
        amount = user_data["amount"]

        # Assign rewards if user is a member
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


def RenewTvSub(user, serializer, reason, user_data):
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
        renew_tv_sub_instance = serializer.save()
        tx_reference = renew_tv_sub_instance.tx_reference
        amount = user_data["amount"]

        # Check is user is a memeber then assign rewards.
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


def waec_reg(user, serializer, reason, user_data):
    waec_response = VAS.waec_reg(
        service_id=user_data["serviceID"],
        phone=user_data["phone"],
        variation_code=user_data["variation_code"],
        quantity=user_data["quantity"],
    )
    if waec_response.status_code == 200:
        waec_payment_instance = serializer.save()
        tx_reference = waec_payment_instance.tx_reference
        amount = waec_response.json()["amount"]

        UserNotification.objects.create(
            user=user,
            title="Waec registration.",
            message=f"This is to inform you that your payment of {amount} \
                for WAEC registration is successful.",
        )

        ActivityModel.objects.create(
            user=user,
            title="Waec registration",
            description=f"{user.first_name} {user.last_name} just made a payment of {amount} for waec registration.",
        )

        # Check is user is a memeber then assign rewards.
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


def MotorInsurance(user, serializer, reason, user_data):
    vehicle_insurance_response = VAS.vehicle_insurance(
        service_id="ui-insure",
        phone=user_data["phone"],
        variation_code=user_data["variation_code"],
        billersCode=user_data["variation_code"],
        Insured_Name=user_data["insured_name"],
        Engine_Number=user_data["engine_number"],
        Chasis_Number=user_data["chasis_number"],
        Plate_Number=user_data["plate_number"],
        Vehicle_Make=user_data["vehicle_make"],
        Vehicle_Color=user_data["vehicle_color"],
        Vehicle_Model=user_data["vehicle_model"],
        Year_of_Make=user_data["year_of_make"],
        Contact_Address=user_data["contact_address"],
    )
    if vehicle_insurance_response.status_code == 200:
        vehicle_insurance_instance = serializer.save()
        amount = vehicle_insurance_response.json()["amount"]

        UserNotification.objects.create(
            user=user,
            title="Vehicle Insurance",
            message=f"This is to inform you that your payment of {amount} \
                for vehicle insurance is successful.",
        )

        ActivityModel.objects.create(
            user=user,
            title="Vehicle Insurance",
            description=f"{user.first_name} {user.last_name} just made a payment of {amount} for vehicle insurance.",
        )

        # Check is user is a memeber then assign rewards.
        if user.active_role == "Member" and amount >= 100:
            new_rewards = Allocate.reward(amount=amount)
        else:
            new_rewards = 0

        try:
            with transaction.atomic():
                tx = TxModel.objects.create(
                    user=user,
                    tx_id=vehicle_insurance_response.json().get("transactionId", ""),
                    tx_reference=vehicle_insurance_instance.tx_reference,
                    tx_type="Insurance",
                    amount=user_data.get("amount", 0),
                    description="Debit for vehicular insurance.",
                    rwd=new_rewards,
                )

                rwd, _ = Rewards.objects.get_or_create(user=user)
                rwd.balance += new_rewards
                rwd.transaction = tx
                rwd.save()

        except Exception as e:
            logging.error(f"Database query error: {str(e)}")

        VehicleInsurance.objects.create(
            user=user,
            serviceID=user_data["serviceID"],
            request_id=req_id,
            quantity=user_data["serviceID"],
            amount=amount,
            phone=user_data["phone"],
            billersCode=user_data["variation_code"],
            Insured_Name=user_data["insured_name"],
            Engine_Number=user_data["engine_number"],
            Chasis_Number=user_data["chasis_number"],
            Plate_Number=user_data["plate_number"],
            Vehicle_Make=user_data["vehicle_make"],
            Vehicle_Color=user_data["vehicle_color"],
            Vehicle_Model=user_data["vehicle_model"],
            Year_of_Make=user_data["year_of_make"],
            Contact_Address=user_data["contact_address"],
        )

        return vehicle_insurance_response.json()
    else:
        # initiate a credit refund to the customer after failed transaction.
        _ = Account.Credit(
            accNo=user.accountNumber, amount=user["amount"], reason=reason
        )
        return vehicle_insurance_response.json()


def Accident_Insurance(user, serializer, reason, user_data):
    accident_insurance_response = VAS.accident_insurance(
        service_id="personal-accident-insurance",
        phone=user_data["phone"],
        variation_code=user_data["variation_code"],
        billersCode=user_data["variation_code"],
        phone_no=user_data["phone"],
        full_name=user_data["full_name"],
        address=user_data["address"],
        dob=user_data["dob"],
        next_kin_name=user_data["next_kin_name"],
        next_kin_phone=user_data["next_kin_phone"],
        business_occupation=user_data["business_occupation"],
    )
    if accident_insurance_response.status_code == 200:
        accident_insurance_instance = serializer.save()
        amount = accident_insurance_response.json()["amount"]

        UserNotification.objects.create(
            user=user,
            title="Accident inssurance.",
            message=f"This is to inform you that your payment of {amount} \
                for accident inssurance is successful.",
        )

        ActivityModel.objects.create(
            user=user,
            title="Accident inssurance",
            description=f"{user.first_name} {user.last_name} just made a payment of {amount} for accident insurance.",
        )

        # Check is user is a memeber then assign rewards.
        if user.active_role == "Member" and amount >= 100:
            new_rewards = Allocate.reward(amount=amount)
        else:
            new_rewards = 0

        try:
            with transaction.atomic():
                tx = TxModel.objects.create(
                    user=user,
                    tx_id=accident_insurance_response.json().get("transactionId", ""),
                    tx_reference=accident_insurance_instance.tx_reference,
                    tx_type="Insurance",
                    amount=user_data.get("amount", 0),
                    description="Debit for accident insurance.",
                    rwd=new_rewards,
                )

                rwd, _ = Rewards.objects.get_or_create(user=user)
                rwd.balance += new_rewards
                rwd.transaction = tx
                rwd.save()

        except Exception as e:
            logging.error(f"Database query error: {str(e)}")

        AccidentInsurance.objects.create(
            user=user,
            service_id=user_data["serviceID"],
            phone=user_data["phone"],
            variation_code=user_data["variation_code"],
            billersCode=user_data["variation_code"],
            phone_no=user_data["phone"],
            full_name=user_data["full_name"],
            address=user_data["address"],
            dob=user_data["dob"],
            next_kin_name=user_data["next_kin_name"],
            next_kin_phone=user_data["next_kin_phone"],
            business_occupation=user_data["business_occupation"],
        )

        return accident_insurance_response.json()
    else:
        # initiate a credit refund to the customer after failed transaction.
        _ = Account.Credit(
            accNo=user.accountNumber, amount=user["amount"], reason=reason
        )
        return accident_insurance_response.json()


def Health_Insurance(uploaded_passport_url, user, serializer, reason, user_data):
    health_insurance_response = VAS.health_insurance(
        service_id=user_data["serviceID"],
        phone=user_data["phone"],
        variation_code=user_data["variation_code"],
        billersCode=user_data["variation_code"],
        phone_no=user_data["phone"],
        full_name=user_data["full_name"],
        address=user_data["address"],
        date_of_birth=user_data["date_of_birth"],
        selected_hospital=user_data["selected_hospital"],
        Passport_Photo=uploaded_passport_url,
        extra_info=user_data["extra_info"],
    )
    if health_insurance_response.status_code == 200:
        health_insurance_instance = serializer.save()
        amount = health_insurance_response.json()["amount"]

        UserNotification.objects.create(
            user=user,
            title="Health insurance.",
            message=f"This is to inform you that your payment of {amount} \
                for health insurance is successful.",
        )

        ActivityModel.objects.create(
            user=user,
            title="Health insurance",
            description=f"{user.first_name} {user.last_name} just made a payment of {amount} for health insurance.",
        )

        # Check is user is a memeber then assign rewards.
        if user.active_role == "Member" and amount >= 100:
            new_rewards = Allocate.reward(amount=amount)
        else:
            new_rewards = 0

        try:
            with transaction.atomic():
                tx = TxModel.objects.create(
                    user=user,
                    tx_id=health_insurance_response.json().get("transactionId", ""),
                    tx_reference=health_insurance_instance.tx_reference,
                    tx_type="Health",
                    amount=user_data.get("amount", 0),
                    description="Debit for health insurance.",
                    rwd=new_rewards,
                )

                rwd, _ = Rewards.objects.get_or_create(user=user)
                rwd.balance += new_rewards
                rwd.transaction = tx
                rwd.save()

        except Exception as e:
            logging.error(f"Database query error: {str(e)}")

        HealthInsurance.objects.create(
            user=user,
            service_id=user_data["serviceID"],
            phone=user_data["phone"],
            variation_code=user_data["variation_code"],
            billersCode=user_data["variation_code"],
            phone_no=user_data["phone"],
            full_name=user_data["full_name"],
            address=user_data["address"],
            date_of_birth=user_data["date_of_birth"],
            selected_hospital=user_data["selected_hospital"],
            Passport_Photo=uploaded_passport_url,
            extra_info=user_data["extra_info"],
        )

        return health_insurance_response.json()

    else:
        # initiate a credit refund to the customer after failed transaction.
        _ = Account.Credit(
            accNo=user.accountNumber, amount=user["amount"], reason=reason
        )
        return health_insurance_response.json()
