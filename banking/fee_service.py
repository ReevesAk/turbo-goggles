from decimal import Decimal, ROUND_HALF_UP

INTERBANK_FEE_RATE = Decimal("0.007")  # 0.7%
INTERBANK_FEE_CAP = Decimal("300.00")


class TransferFeeService:

    @staticmethod
    def calculate_fee(amount) -> Decimal:
        """0.7% of amount, capped at ₦300."""
        amount = Decimal(str(amount))
        fee = (amount * INTERBANK_FEE_RATE).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        return min(fee, INTERBANK_FEE_CAP)

    @staticmethod
    def breakdown(amount) -> dict:
        """
        Returns principal, fee, and total debit for a given transfer amount.

        Example for ₦5,000:
            {"principal": "5000.00", "fee": "35.00", "total": "5035.00"}

        Example for ₦100,000:
            {"principal": "100000.00", "fee": "300.00", "total": "100300.00"}
        """
        amount = Decimal(str(amount))
        fee = TransferFeeService.calculate_fee(amount)
        total = amount + fee
        return {
            "principal": str(amount.quantize(Decimal("0.01"))),
            "fee": str(fee),
            "total": str(total.quantize(Decimal("0.01"))),
        }
