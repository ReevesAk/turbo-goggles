from django.db import models

from accounts.models import User

TITLE = (
    ("0", "OTHERS"),
    ("1", "MR"),
    ("2", "MRS"),
    ("3", "MESSRS"),
    ("4", "MISS"),
    ("5", "MS"),
    ("6", "PROF"),
    ("7", "JUSTICE"),
    ("8", "JUDGE"),
    ("9", "DR"),
    ("10", "ENG."),
    ("11", "HAJ"),
    ("12", "SHEIKH"),
    ("13", "ALHAJI"),
    ("14", "OBA"),
    ("15", "ARCH"),
    ("16", "BARRISTER"),
    ("17", "REVEREND"),
    ("18", "MONSIGNOR"),
    ("19", "HIS BISHOP"),
    ("20", "PATRIARCH"),
    ("21", "BROTHER"),
    ("22", "HER MAJESTY"),
    ("23", "H.R.H."),
    ("24", "HONOURABLE"),
    ("25", "SENATOR"),
    ("26", "H.EX."),
    ("27", "HIS MAJESTY"),
    ("28", "MR & MRS"),
    ("29", "REV FR"),
    ("30", "AIR VICE MASHAL"),
    ("31", "ARC"),
    ("32", "ARCH BISHOP"),
    ("33", "BISHOP"),
    ("34", "CAPTAIN"),
    ("35", "CHIEF"),
    ("36", "CHIEF (DR)"),
    ("37", "CHIEF (MRS)"),
    ("38", "COLONEL"),
    ("39", "DAME"),
    ("40", "DEACON"),
    ("41", "DEACONESS"),
    ("42", "GENERAL"),
    ("43", "HIGH PRIEST"),
    ("44", "KING"),
    ("45", "LADY"),
    ("46", "LOLO"),
    ("47", "MAJOR"),
    ("48", "MALLAM"),
    ("49", "OTUNBA"),
    ("50", "PASTOR"),
    ("51", "PASTOR (MRS)"),
    ("52", "PRINCE"),
    ("53", "PRINCESS"),
    ("54", "QUEEN"),
    ("55", "SIR"),
    ("56", "SIR & LADY"),
    ("57", "ENGR DR."),
    ("58", "CARDINAL"),
    ("99", "OTHERS"),
)

MARITAL_STATUS = (
    ("1", "Single"),
    ("2", "Married"),
    ("3", "Divorced"),
    ("4", "Widow"),
    ("4", "Widower"),
    ("5", "Seperated"),
)

NGN_ID_TYPE = (
    ("NIN", "NIN"),
    ("PASSPORT", "PASSPORT"),
    ("VOTERS_CARD", "VOTERS_CARD"),
    ("DRIVERS_LICENSE", "DRIVERS_LICENSE"),
)

USD_ID_TYPE = (
    ("PASSPORT", "PASSPORT"),
    ("VOTERS_CARD", "VOTERS_CARD"),
    ("DRIVERS_LICENSE", "DRIVERS_LICENSE"),
)

CARD_BRAND = (("VISA", "VISA"), ("MASTERCARD", "MASTERCARD"), ("VERVE", "VERVE"))

CURRENCY = (
    ("NGN", "NGN"),
    ("USD", "USD"),
)

SEX = (
    ("1", "Male"),
    ("2", "Female"),
)

RELIGION = (
    ("1", "Christianity"),
    ("2", "Islam"),
    ("3", "Others"),
    ("4", "Hindu")
)


class BVNData(models.Model):
    user = models.OneToOneField(to=User, on_delete=models.CASCADE)
    bvn = models.CharField(max_length=155, null=True, unique=True)
    first_name = models.CharField(max_length=155, null=True)
    last_name = models.CharField(max_length=155, null=True)
    date_of_birth = models.CharField(max_length=155, null=True)
    phone_number = models.CharField(max_length=15, null=True)


class AccountCreation(models.Model):
    user = models.OneToOneField(to=User, on_delete=models.CASCADE)
    customer_numnber = models.CharField(max_length=50, null=True)
    account_number = models.CharField(max_length=100, null=True)
    acct_name = models.CharField(max_length=100, null=True)
    sex = models.CharField(max_length=6, choices=SEX, null=True)
    title = models.CharField(max_length=50, choices=TITLE, null=True)
    marital_status = models.CharField(max_length=50, choices=MARITAL_STATUS, null=True)
    lga = models.CharField(max_length=100, null=True)
    state = models.CharField(max_length=100, null=True)
    religion = models.CharField(max_length=100, choices=RELIGION, null=True)
    nin = models.CharField(max_length=100, null=True)
    address = models.CharField(max_length=150, null=True)
    utility = models.CharField(max_length=255, null=True)
    passport = models.CharField(max_length=255, null=True)
    identity = models.CharField(max_length=150, null=True)
    signature = models.CharField(max_length=255, null=True)
    pin = models.CharField(max_length=155, null=True)


class ForexModel(models.Model):
    user = models.ForeignKey(to=User, on_delete=models.CASCADE)
    source_currency = models.CharField(
        choices=CURRENCY, default="NGN", max_length=50, null=True
    )
    target_currency = models.CharField(
        choices=CURRENCY, default="USD", max_length=50, null=True
    )
    rate = models.CharField(max_length=150, null=True)
    reference = models.CharField(max_length=150, null=True)
    amount = models.FloatField(null=True)


class BankingNotificationModel(models.Model):
    accountNumber = models.CharField(max_length=100, null=True)
    reference = models.CharField(max_length=150, null=True)
    narration = models.TextField(null=True)
    dateTime = models.CharField(max_length=150, null=True)
    amount = models.FloatField(null=True)
    transactiontype = models.CharField(max_length=50, null=True)
    accountBalance = models.FloatField(null=True)
