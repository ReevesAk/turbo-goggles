from decimal import Decimal, ROUND_HALF_UP

VAT_RATE = Decimal("0.075")  # 7.5% VAT
TRANSFER_FEE = Decimal("10.00")  # Flat NIP transfer fee
MERCHANT_FEE = Decimal("5.00")  # Picadailys flat merchant fee


class TransferCharge:

    @staticmethod
    def breakdown(amount) -> dict:
        """
        Returns charge breakdown for an interbank transfer.

        Exposed to frontend:
          - transfer_fee: NIP fee + merchant fee (₦10 + ₦5 = ₦15)
          - vat:          VAT on both fees (₦0.75 + ₦0.38 = ₦1.13)
          - total:        principal + transfer_fee + vat

        Internal only (not exposed):
          - merchant_fee, vat_on_transfer, vat_on_merchant

        SMS/Email alerts use principal only.
        """
        amount = Decimal(str(amount))

        vat_on_transfer = (TRANSFER_FEE * VAT_RATE).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        vat_on_merchant = (MERCHANT_FEE * VAT_RATE).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        combined_fee = TRANSFER_FEE + MERCHANT_FEE
        combined_vat = vat_on_transfer + vat_on_merchant
        total_charges = combined_fee + combined_vat
        total = (amount + total_charges).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        return {
            "principal": str(amount.quantize(Decimal("0.01"))),
            "transfer_fee": str(combined_fee),
            "vat": str(combined_vat.quantize(Decimal("0.01"))),
            "total_charges": str(total_charges.quantize(Decimal("0.01"))),
            "total": str(total),
        }
