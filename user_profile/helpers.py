import random

from django.db import transaction
from django.core.exceptions import ValidationError

from user_profile.models import MemberSurvey
from accounts.models import UserNotification
from roles.models import ActivityModel

from accounts.models import Rewards


class MysteryBox:
    @staticmethod
    def open(user):
        current_user = Rewards.objects.get(user=user)
        current_user.balance -= 100.0
        current_user.save()

        form = ["airtime", "data"]
        items = ["100", "200", "300", "350", "500"]

        assign_gift_randomly = random.choice(items)
        assign_form_randomly = random.choice(form)
        return assign_gift_randomly, assign_form_randomly


class VariationCodes:
    @staticmethod
    def get(service_id, amount):
        mapping = None

        match service_id:
            case "mtn-data":
                mtn_mapping = {
                    "100": "mtn-10mb-100",
                    "200": "mtn-50mb-200",
                    "500": "mtn-xtra-500",
                }
                mapping = mtn_mapping

            case "airtel-data":
                airtel_mapping = {
                    "100": "airt-100",
                    "200": "airt-200",
                    "500": "airt-500",
                }
                mapping = airtel_mapping

            case "glo-data":
                glo_mapping = {"100": "glo100", "200": "glo200", "500": "glo500"}
                mapping = glo_mapping

            case "etisalat-data":
                nine_mobile_mapping = {
                    "100": "eti-100",
                    "200": "eti-200",
                    "500": "eti-500",
                }
                mapping = nine_mobile_mapping

        # Get the corresponding variation code for the given amount
        variation_code = mapping.get(amount)

        return variation_code


class MemberSurveyService:
    @staticmethod
    @transaction.atomic
    def complete_member_survey(*, user, serializer):
        """
        Handles full member survey completion flow safely.
        """

        # 🔒 Lock user row to prevent race conditions
        user = type(user).objects.select_for_update().get(pk=user.pk)

        # ❌ Idempotency check
        if MemberSurvey.objects.filter(user=user).exists():
            raise ValidationError("Survey already completed.")

        # ✅ Save survey
        survey = serializer.save(user=user)

        # 🔔 Notify user
        UserNotification.objects.create(
            user=user,
            title="Member Survey",
            message="Survey completed successfully!",
        )

        # 🧾 Activity log
        ActivityModel.objects.create(
            user=user,
            title="Member Survey",
            description=f"{user.first_name} {user.last_name} completed member survey.",
        )

        # 🏁 Update user state
        user.has_done_survey = True
        user.save(update_fields=["has_done_survey"])

        return survey
