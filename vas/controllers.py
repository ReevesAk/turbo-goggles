import logging
from datetime import datetime
from commons import Allocate
from accounts.models import TxModel, Rewards, UserNotification
from roles.models import ActivityModel

from django.db import transaction

from rest_framework import status
from rest_framework.response import Response

from banking.controllers import Account
from .helpers import VAS
from .models import (
    AirtimeTopup,
    # DataSubscription, ElectricityBill, WaecRegistration,
    # TvSubscription, HealthInsurance, VehicleInsurance, AccidentInsurance,
    # HomeCoverInsurance,
)

current_datetime = datetime.now()
req_id = current_datetime.strftime("%Y%m%d%H%M" + "picadailys")


def airtime(user, serializer, reason, user_data):
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

        UserNotification.objects.create(
            user=user,
            title="Airtime purchase.",
            message=f"This is to inform you that you have made a purchase of {amount} naira airtime on {phone}.",
        )

        ActivityModel.objects.create(
            user=user,
            title="Airtime purchase.",
            description=f"{user.first_name} {user.last_name} has made a purchase of {amount} naira airtime on {phone}..",
        )

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
            amount=user_data["amount"],
            phone=user_data["phone"],
        )

        response_data = {
            "status": "Success",
            "message": f"Recharge of {amount} was succesful and you have been awarded {new_rewards} rewards.",
            "data": airtime_response.json(),
        }

        return Response(data=response_data, status=status.HTTP_200_OK)
    else:
        response_data = {
            "data": airtime_response.json(),
            "message": "A refund will be issued.",
        }

        # initiate a credit refund to the customer after failed transaction.
        _ = Account.Credit(
            acct_no=user.accountNumber, amount=user["amount"], reason=reason
        )
        return Response(data=response_data, status=airtime_response.status_code)


def data(user, serializer, reason, user_data):
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

        UserNotification.objects.create(
            user=user,
            title="Data subscription.",
            message=f"This is to inform you that you have made a \
                purchase of {amount} naira data subscription on {phone}.",
        )

        ActivityModel.objects.create(
            user=user,
            title="Data subscription.",
            description=f"{user.first_name} {user.last_name} has made a purchase of {amount} naira data subscription on {phone}..",
        )

        # Check is user is a memeber then assign rewards.
        if user.active_role == "Member" and amount >= 100:
            new_rewards = Allocate.reward(amount=amount)
        else:
            new_rewards = 0

        try:
            with transaction.atomic():
                tx = TxModel.objects.filter(user=user).order_by("-id").first()
                tx.tx_id = data_response.json().get("transactionId", "")
                tx.tx_reference = data_instance.tx_reference
                tx.tx_type = "Data"
                tx.amount = user_data.get("amount", 0)
                tx.description = "Debit for data subscription."
                tx.rwd = new_rewards
                tx.save()

                rwd, _ = Rewards.objects.get_or_create(user=user)
                rwd.balance += new_rewards
                rwd.transaction = tx
                rwd.save()

        except Exception as e:
            logging.error(f"Database query error: {str(e)}")

        response_data = {
            "status": "Success",
            "message": f"Subscription of {amount} was succesful and you have been awarded {new_rewards} rewards.",
            "data": data_response.json(),
        }

        return Response(data=response_data, status=status.HTTP_200_OK)
    else:
        response_data = {
            "data": data_response.json(),
            "message": "A refund will be issued.",
        }

        # initiate a credit refund to the customer after failed transaction.
        _ = Account.Credit(
            acct_no=user.accountNumber, amount=user_data["amount"], reason=reason
        )
        return Response(data=response_data, status=data_response.status_code)


def electricity(user, serializer, reason, user_data):
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

        UserNotification.objects.create(
            user=user,
            title="Electricity payment.",
            message=f"This is to inform you that your payment of {amount} \
                for electricity is successful.",
        )

        ActivityModel.objects.create(
            user=user,
            title="Electricity payment.",
            description=f"{user.first_name} {user.last_name} has made a payment of {amount} for electricity bill.",
        )

        # Check is user is a memeber then assign rewards.
        if user.active_role == "Member" and amount >= 100:
            new_rewards = Allocate.reward(amount=amount)
        else:
            new_rewards = 0

        try:
            with transaction.atomic():
                tx = TxModel.objects.filter(user=user).order_by("-id").first()
                tx.tx_id = electricity_response.json().get("transactionId", "")
                tx.tx_reference = electricity_instance.tx_reference
                tx.tx_type = "Electricity"
                tx.amount = user_data.get("amount", 0)
                tx.description = "Debit for electricity payment."
                tx.rwd = new_rewards
                tx.save()

                rwd, _ = Rewards.objects.get_or_create(user=user)
                rwd.balance += new_rewards
                rwd.transaction = tx
                rwd.save()

        except Exception as e:
            logging.error(f"Database query error: {str(e)}")

        response_data = {
            "status": "Success",
            "message": f"Payment of {amount} was succesful and you have been awarded {new_rewards} rewards.",
            "data": electricity_response.json(),
        }

        return Response(data=response_data, status=status.HTTP_200_OK)
    else:
        response_data = {
            "data": electricity_response.json(),
            "message": "A refund will be issued.",
        }

        # initiate a credit refund to the customer after failed transaction.
        _ = Account.Credit(
            acct_no=user.accountNumber, amount=user["amount"], reason=reason
        )
        return Response(data=response_data, status=electricity_response.status_code)


def NewTvSub(user, serializer, reason, user_data):
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
        # Save TvSubscription and get the auto-generated tx_reference
        new_tv_sub_instance = serializer.save()
        tx_reference = new_tv_sub_instance.tx_reference
        amount = user_data["amount"]

        # Create a UserNotification and ActivityModel entry
        UserNotification.objects.create(
            user=user,
            title="New TV subscription.",
            message=f"This is to inform you that your payment of {amount} for TV subscription is successful.",
        )
        ActivityModel.objects.create(
            user=user,
            title="New TV subscription.",
            description=f"{user.first_name} {user.last_name} made a payment of {amount} for a new Cable TV subscription.",
        )

        # Assign rewards if user is a member
        new_rewards = (
            Allocate.reward(amount=amount)
            if user.active_role == "Member" and amount >= 100
            else 0
        )

        # Use the same tx_reference for TxModel
        try:
            with transaction.atomic():
                tx = TxModel.objects.filter(user=user).order_by("-id").first()
                tx.tx_reference = tx_reference  # Set the same tx_reference
                tx.tx_type = "Leisure"
                tx.amount = amount
                tx.description = "Debit for new TV subscription payment."
                tx.rwd = new_rewards
                tx.save()

                # Update rewards
                rwd, _ = Rewards.objects.get_or_create(user=user)
                rwd.balance += new_rewards
                rwd.transaction = tx
                rwd.save()

        except Exception as e:
            logging.error(f"Database query error: {str(e)}")

        response_data = {
            "status": "Success",
            "message": f"TV subscription of {amount} was successful and you have been awarded {new_rewards} rewards.",
            "data": new_tv_response.json(),
        }
        return Response(data=response_data, status=status.HTTP_200_OK)

    # Handle failed subscription response
    else:
        response_data = {
            "data": new_tv_response.json(),
            "message": "A refund will be issued.",
        }
        Account.Credit(acct_no=user.accountNumber, amount=amount, reason=reason)
        return Response(response_data, status=new_tv_response.status_code)


def RenewTvSub(user, serializer, reason, user_data):
    renew_tv_response = VAS.renewTvSub(
        req_id=req_id,
        service_id=user_data["serviceID"],
        amount=user_data["amount"],
        phone=user_data["phone"],
        billersCode=user_data["billersCode"],
        subscription_type="change",
    )
    if renew_tv_response.status_code == 200:
        renew_tv_sub_instance = serializer.save()
        tx_reference = renew_tv_sub_instance.tx_reference
        amount = user_data["amount"]

        UserNotification.objects.create(
            user=user,
            title="Renew Tv subscription.",
            message=f"This is to inform you that your payment of {amount} \
                to renew tv subscription is successful.",
        )

        billersCode = user_data["billersCode"]
        ActivityModel.objects.create(
            user=user,
            title="Renew Tv subscription.",
            description=f"{user.first_name} {user.last_name} just made a payment of {amount} for Cable TV renewal on {billersCode}.",
        )

        # Check is user is a memeber then assign rewards.
        if user.active_role == "Member" and amount >= 100:
            new_rewards = Allocate.reward(amount=amount)
        else:
            new_rewards = 0

        try:
            with transaction.atomic():
                tx = TxModel.objects.filter(user=user).order_by("-id").first()
                tx.tx_id = renew_tv_response.json().get("transactionId", "")
                tx.tx_reference = tx_reference
                tx.tx_type = "Leisure"
                tx.amount = user_data.get("amount", 0)
                tx.description = "Debit for tv subscription renewal."
                tx.rwd = new_rewards
                tx.save()

                rwd, _ = Rewards.objects.get_or_create(user=user)
                rwd.balance += new_rewards
                rwd.transaction = tx
                rwd.save()

        except Exception as e:
            logging.error(f"Database query error: {str(e)}")

        response_data = {
            "status": "Success",
            "message": f"Tv subscription of {amount} was succesful and you have been awarded {new_rewards} rewards.",
            "data": renew_tv_response.json(),
        }

        return Response(data=response_data, status=status.HTTP_200_OK)
    else:
        response_data = {
            "data": renew_tv_response.json(),
            "message": "A refund will be issued.",
        }

        # initiate a credit refund to the customer after failed transaction.
        _ = Account.Credit(
            acct_no=user.accountNumber, amount=user["amount"], reason=reason
        )
        return Response(response_data, status=renew_tv_response.status_code)


def international_topup(user, serializer, reason, user_data):
    intl_topup_response = VAS.intl_topup(
        service_id=user_data["serviceID"],
        amount=user_data["amount"],
        phone=user_data["phone"],
        billersCode=user_data["billersCode"],
        operator_id=user_data["operator_id"],
        variation_code=user_data["variation_code"],
        country_code=user_data["country_code"],
        email=user_data["email"],
        product_type_id=user_data["product_type_id"],
    )
    if intl_topup_response.status_code == 200:
        intl_topup_instnace = serializer.save()
        amount = user_data["amount"]

        UserNotification.objects.create(
            user=user,
            title="International airtime recharge.",
            message=f"This is to inform you that your payment of {amount} \
                for international airtime topup is successful.",
        )

        # Check is user is a memeber then assign rewards.
        if user.active_role == "Member" and amount >= 100:
            new_rewards = Allocate.reward(amount=amount)
        else:
            new_rewards = 0

        try:
            with transaction.atomic():
                tx, _ = TxModel.objects.get_or_create(user=user)
                tx.tx_id = intl_topup_response.json().get("transactionId", "")
                tx.tx_reference = intl_topup_instnace.tx_reference
                tx.tx_type = "Airtime"
                tx.amount = user_data.get("amount", 0)
                tx.description = "Debit for international airtime recharge."
                tx.rwd = new_rewards
                tx.save()

                rwd, _ = Rewards.objects.get_or_create(user=user)
                rwd.balance += new_rewards
                rwd.transaction = tx
                rwd.save()

        except Exception as e:
            logging.error(f"Database query error: {str(e)}")

        response_data = {
            "status": "Success",
            "message": f"Topup of {amount} was succesful and you have been awarded {new_rewards} rewards",
            "data": intl_topup_response.json(),
        }

        return Response(data=response_data, status=status.HTTP_200_OK)
    else:
        response_data = {
            "data": intl_topup_response.json(),
            "message": "A refund will be issued.",
        }

        # initiate a credit refund to the customer after failed transaction.
        _ = Account.Credit(
            acct_no=user.accountNumber, amount=user["amount"], reason=reason
        )
        return Response(data=response_data, status=intl_topup_response.status_code)


def waec_reg(user, serializer, reason, user_data):
    waec_response = VAS.waec_reg(
        service_id=user_data["serviceID"],
        phone=user_data["phone"],
        variation_code=user_data["variation_code"],
        quantity=user_data["quantity"],
    )
    if waec_response.status_code == 200:
        waec_payment_instance = serializer.save()
        amount = waec_response.json()["amount"]

        UserNotification.objects.create(
            user=user,
            title="Waec registration.",
            message=f"This is to inform you that your payment of {amount} \
                for WAEC registration is successful.",
        )

        # Check is user is a memeber then assign rewards.
        if user.active_role == "Member" and amount >= 100:
            new_rewards = Allocate.reward(amount=amount)
        else:
            new_rewards = 0

        try:
            with transaction.atomic():
                tx, _ = TxModel.objects.get_or_create(user=user)
                tx.tx_id = waec_response.json().get("transactionId", "")
                tx.tx_reference = waec_payment_instance.tx_reference
                tx.amount = user_data.get("amount", 0)
                tx.tx_type = "Education"
                tx.description = "Debit for waec registration."
                tx.rwd = new_rewards
                tx.save()

                rwd, _ = Rewards.objects.get_or_create(user=user)
                rwd.balance += new_rewards
                rwd.transaction = tx
                rwd.save()

        except Exception as e:
            logging.error(f"Database query error: {str(e)}")

        response_data = {
            "status": "Success",
            "message": f"Waec registration of {amount} was succesful and you have been awarded {new_rewards} rewards.",
            "data": waec_response.json(),
        }

        return Response(data=response_data, status=status.HTTP_200_OK)
    else:
        response_data = {
            "data": waec_response.json(),
            "message": "A refund will be issued.",
        }

        # initiate a credit refund to the customer after failed transaction.
        _ = Account.Credit(
            acct_no=user.accountNumber, amount=user["amount"], reason=reason
        )
        return Response(response_data, status=waec_response.status_code)


def VehicleInsurance(user, serializer, reason, user_data):
    vehicle_insurance_response = VAS.vehicle_insurance(
        service_id=user_data["serviceID"],
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

        # Check is user is a memeber then assign rewards.
        if user.active_role == "Member" and amount >= 100:
            new_rewards = Allocate.reward(amount=amount)
        else:
            new_rewards = 0

        try:
            with transaction.atomic():
                tx, _ = TxModel.objects.get_or_create(user=user)
                tx.tx_id = vehicle_insurance_response.json().get("transactionId", "")
                tx.tx_reference = vehicle_insurance_instance.tx_reference
                tx.tx_type = "Insurance"
                tx.amount = user_data.get("amount", 0)
                tx.description = "Debit for vehicular insurance."
                tx.rwd = new_rewards
                tx.save()

                rwd, _ = Rewards.objects.get_or_create(user=user)
                rwd.balance += new_rewards
                rwd.transaction = tx
                rwd.save()

        except Exception as e:
            logging.error(f"Database query error: {str(e)}")

        response_data = {
            "status": "Success",
            "message": f"Vehicle insurance of {amount} was succesful and you have been awarded {new_rewards} rewards.",
            "data": vehicle_insurance_response.json(),
        }

        return Response(data=response_data, status=status.HTTP_200_OK)
    else:
        response_data = {
            "data": vehicle_insurance_response.json(),
            "message": "A refund will be issued.",
        }

        # initiate a credit refund to the customer after failed transaction.
        _ = Account.Credit(
            accNo=user.accountNumber, amount=user["amount"], reason=reason
        )
        return Response(
            data=response_data,
            status=vehicle_insurance_response.status_code,
        )


def AccidentInsurance(user, serializer, reason, user_data):
    accident_insurance_response = VAS.accident_insurance(
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
    if accident_insurance_response.status_code == 200:
        accident_insurance_instance = serializer.save()
        amount = accident_insurance_response.json()["amount"]

        UserNotification.objects.create(
            user=user,
            title="Accident inssurance.",
            message=f"This is to inform you that your payment of {amount} \
                for accident inssurance is successful.",
        )

        # Check is user is a memeber then assign rewards.
        if user.active_role == "Member" and amount >= 100:
            new_rewards = Allocate.reward(amount=amount)
        else:
            new_rewards = 0

        try:
            with transaction.atomic():
                tx, _ = TxModel.objects.get_or_create(user=user)
                tx.tx_id = accident_insurance_response.json().get("transactionId", "")
                tx.tx_reference = accident_insurance_instance.tx_reference
                tx.tx_type = "Insurance"
                tx.amount = user_data.get("amount", 0)
                tx.description = "Debit for accident insurance."
                tx.rwd = new_rewards
                tx.save()

                rwd, _ = Rewards.objects.get_or_create(user=user)
                rwd.balance += new_rewards
                rwd.transaction = tx
                rwd.save()

        except Exception as e:
            logging.error(f"Database query error: {str(e)}")

        response_data = {
            "status": "Success",
            "message": f"Accident insurance of {amount} was succesful and you have been awarded {new_rewards} rewards.",
            "data": accident_insurance_response.json(),
        }
        return Response(data=response_data, status=status.HTTP_200_OK)
    else:
        response_data = {
            "data": accident_insurance_response.json(),
            "message": "A refund will be issued.",
        }

        # initiate a credit refund to the customer after failed transaction.
        _ = Account.Credit(
            accNo=user.accountNumber, amount=user["amount"], reason=reason
        )
        return Response(
            response_data,
            status=accident_insurance_response.status_code,
        )


def HomeCoverInsurance(user, serializer, reason, user_data):
    home_cover_insurance_response = VAS.home_cover_insurance(
        service_id=user_data["serviceID"],
        phone=user_data["phone"],
        variation_code=user_data["variation_code"],
        billersCode=user_data["variation_code"],
        phone_no=user_data["phone"],
        full_name=user_data["full_name"],
        address=user_data["address"],
        dob=user_data["date_of_birth"],
        type_building=user_data["type_building"],
        business_occupation=user_data["business_occupation"],
    )
    if home_cover_insurance_response.status_code == 200:
        home_insurance_instance = serializer.save()
        amount = home_cover_insurance_response.json()["amount"]

        UserNotification.objects.create(
            user=user,
            title="Home cover insurance registration.",
            message=f"This is to inform you that your payment of {amount} \
                for home cover insurance is successful.",
        )

        # Check is user is a memeber then assign rewards.
        if user.active_role == "Member" and amount >= 100:
            new_rewards = Allocate.reward(amount=amount)
        else:
            new_rewards = 0

        try:
            with transaction.atomic():
                tx, _ = TxModel.objects.get_or_create(user=user)
                tx.tx_id = home_cover_insurance_response.json().get("transactionId", "")
                tx.tx_reference = home_insurance_instance.tx_reference
                tx.amount = user_data.get("amount", 0)
                tx.tx_type = "Insurance"
                tx.description = "Debit for home cover insurance."
                tx.rwd = new_rewards
                tx.save()

                rwd, _ = Rewards.objects.get_or_create(user=user)
                rwd.balance += new_rewards
                rwd.transaction = tx
                rwd.save()

        except Exception as e:
            logging.error(f"Database query error: {str(e)}")

        response_data = {
            "status": "Success",
            "message": f"Home cover insurance of {amount} was succesful and you have been awarded {new_rewards} rewards.",
            "data": home_cover_insurance_response.json(),
        }

        return Response(data=response_data, status=status.HTTP_200_OK)
    else:
        response_data = {
            "data": home_cover_insurance_response.json(),
            "message": "A refund will be issued.",
        }

        # initiate a credit refund to the customer after failed transaction.
        credit_response = Account.Credit(
            acct_no=user.accountNumber,
            amount=user["amount"],
            reason="Refund for failed home cover insurance.",
        )
        if credit_response.status_code == 200:
            response = {
                "data": home_cover_insurance_response.json(),
                "message": "Wallet refunded.",
            }
            return Response(data=response, status=credit_response.status_code)
        else:
            return Response(
                data="A refund will be issued shortly",
                status=credit_response.status_code,
            )


def HealthInsurance(uploaded_passport_url, user, serializer, user_data):
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

        # Check is user is a memeber then assign rewards.
        if user.active_role == "Member" and amount >= 100:
            new_rewards = Allocate.reward(amount=amount)
        else:
            new_rewards = 0

        try:
            with transaction.atomic():
                tx, _ = TxModel.objects.get_or_create(user=user)
                tx.tx_id = health_insurance_response.json().get("transactionId", "")
                tx.tx_reference = health_insurance_instance.tx_reference
                tx.tx_type = "Health"
                tx.amount = user_data.get("amount", 0)
                tx.description = "Debit for health insurance."
                tx.rwd = new_rewards
                tx.save()

                rwd, _ = Rewards.objects.get_or_create(user=user)
                rwd.balance += new_rewards
                rwd.transaction = tx
                rwd.save()

        except Exception as e:
            logging.error(f"Database query error: {str(e)}")

        response_data = {
            "status": "Success",
            "message": f"Health insurance of {amount} was succesful and you have been awarded {new_rewards} rewards.",
            "data": health_insurance_response.json(),
        }

        return Response(data=response_data, status=status.HTTP_200_OK)
    else:
        response_data = {
            "data": health_insurance_response.json(),
            "message": "A refund will be issued.",
        }

        # initiate a credit refund to the customer after failed transaction.
        credit_response = Account.Credit(
            acct_no=user.accountNumber,
            amount=user["amount"],
            reason="Refund for failed health insurance.",
        )
        if credit_response.status_code == 200:
            response = {
                "data": health_insurance_response.json(),
                "message": "Wallet refunded.",
            }
            return Response(data=response, status=credit_response.status_code)
        else:
            return Response(
                data="A refund will be issued shortly",
                status=credit_response.status_code,
            )
