from decimal import Decimal, ROUND_HALF_UP

VAT_RATE = Decimal("0.075")  # 7.5% VAT on NIP transfer fee
MERCHANT_FEE = Decimal("5.00")  # Picadailys flat fee per interbank transfer

# NIP interbank fee tiers (NIBSS standard)
NIP_TIERS = [
    (Decimal("5000"), Decimal("10.00")),
    (Decimal("50000"), Decimal("25.00")),
    (None, Decimal("50.00")),  # above ₦50,000
]


class TransferCharge:

    @staticmethod
    def nip_fee(amount) -> Decimal:
        """NIP transfer fee based on amount tier."""
        amount = Decimal(str(amount))
        for ceiling, fee in NIP_TIERS:
            if ceiling is None or amount <= ceiling:
                return fee

    @staticmethod
    def breakdown(amount) -> dict:
        """
        Returns the full charge breakdown for an interbank transfer.

        Example for ₦100:
            {
                "principal":     "100.00",
                "transfer_fee":  "10.00",
                "vat":           "0.75",
                "merchant_fee":  "5.00",
                "total":         "115.75"
            }
        """
        amount = Decimal(str(amount))
        nip = TransferCharge.nip_fee(amount)
        vat = (nip * VAT_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        total = (amount + nip + vat + MERCHANT_FEE).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        return {
            "principal": str(amount.quantize(Decimal("0.01"))),
            "transfer_fee": str(nip),
            "vat": str(vat),
            "merchant_fee": str(MERCHANT_FEE),
            "total": str(total),
        }
