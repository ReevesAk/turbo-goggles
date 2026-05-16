from decimal import Decimal, ROUND_HALF_UP


VAT_RATE = Decimal("0.075")       # 7.5% VAT
TRANSFER_FEE = Decimal("10.00")   # Flat NIP transfer fee
MERCHANT_FEE = Decimal("5.00")    # Picadailys flat merchant fee


class TransferCharge:

    @staticmethod
    def breakdown(amount) -> dict:
        """
        Full charge breakdown for an interbank transfer.

        VAT applies to both the transfer fee and the merchant fee.

        Example for any amount:
            transfer_fee=10.00, vat_on_transfer=0.75,
            merchant_fee=5.00,  vat_on_merchant=0.38,
            total_charges=16.13
        """
        amount = Decimal(str(amount))

        vat_on_transfer = (TRANSFER_FEE * VAT_RATE).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        vat_on_merchant = (MERCHANT_FEE * VAT_RATE).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        total_charges = TRANSFER_FEE + vat_on_transfer + MERCHANT_FEE + vat_on_merchant
        total = (amount + total_charges).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        return {
            "principal":        str(amount.quantize(Decimal("0.01"))),
            "transfer_fee":     str(TRANSFER_FEE),
            "vat_on_transfer":  str(vat_on_transfer),
            "merchant_fee":     str(MERCHANT_FEE),
            "vat_on_merchant":  str(vat_on_merchant),
            "total_charges":    str(total_charges.quantize(Decimal("0.01"))),
            "total":            str(total),
        }
