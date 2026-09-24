import re
import requests
import csv
import mimetypes
import os
from decimal import Decimal
from io import BytesIO, StringIO
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from PIL import Image
import base64
from decouple import config

from django.contrib.auth.hashers import check_password
from django.utils import timezone
from datetime import timedelta

from .models import WalletModel, FundWithCard

# Third party imports.
from rest_framework.response import Response
from rest_framework import status

from commons import Biometrics
from security import encrypt

yournotify_api_key = config("YOURNOTIFY_API_KEY")


class Pin:
    @staticmethod
    def verify(user, pin, hashed_pin):
        try:
            wallet = WalletModel.objects.get(user=user, walletType="INDIVIDUAL")
        except WalletModel.DoesNotExist:
            return Response(
                data={"message": "Invalid wallet ID"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if wallet is locked
        if wallet.pin_locked_until and wallet.pin_locked_until > timezone.now():
            return Response(
                data={"message": "PIN entry locked. Try again later."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not hashed_pin:
            return False

        is_pin_correct = check_password(pin, hashed_pin)

        if is_pin_correct:
            # Reset attempts on success
            wallet.pin_attempts = 0
            wallet.pin_locked_until = None
            wallet.save(update_fields=["pin_attempts", "pin_locked_until"])
            return True
        else:
            wallet.pin_attempts = (wallet.pin_attempts or 0) + 1
            if wallet.pin_attempts >= 4:
                # Lock for 30 minutes (customize as needed)
                wallet.pin_locked_until = timezone.now() + timedelta(minutes=30)
                wallet.save(update_fields=["pin_attempts", "pin_locked_until"])
                return Response(
                    data={
                        "message": "Too many wrong PIN attempts. Locked for 30 minutes."
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
            else:
                wallet.save(update_fields=["pin_attempts"])
                return False


def cloudinary_to_bytes(url):
    """Downloads a file from Cloudinary and returns (bytes, content_type)."""
    response = requests.get(url)
    response.raise_for_status()
    content_type = response.headers.get(
        "Content-Type", "application/octet-stream"
    ).split(";")[0]
    return response.content, content_type


def cloudinary_to_base64(url, quality=85, max_size=(700, 700)):
    """
    Downloads an image from Cloudinary, compresses it, and returns base64 string.
    """

    response = requests.get(url)
    response.raise_for_status()

    img = Image.open(BytesIO(response.content))

    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    img.thumbnail(max_size)

    # save to memory buffer
    buffer = BytesIO()
    img.save(buffer, format="JPEG", quality=quality)
    buffer.seek(0)

    # encode to base64
    return base64.b64encode(buffer.read()).decode("utf-8")


def verify_wallet_auth(user, payment_option, pin=None, use_biometrics=False):
    if payment_option != "WALLET":
        return True, None

    account = WalletModel.objects.filter(user=user, walletType="INDIVIDUAL").first()

    if use_biometrics:
        verified = Biometrics.authenticate(user.phone_number)
        if not verified:
            return False, Response(
                encrypt({"status": "fail", "error": "Biometric verification failed"}),
                status=status.HTTP_403_FORBIDDEN,
            )

    elif account and account.pin:
        verified = Pin.verify(user=user, pin=pin, hashed_pin=account.pin)
        if verified is not True:
            return False, Response(
                encrypt({"status": "fail", "error": "Invalid PIN"}),
                status=status.HTTP_403_FORBIDDEN,
            )

    else:
        return False, Response(
            encrypt({"status": "fail", "error": "Account or PIN not found"}),
            status=status.HTTP_404_NOT_FOUND,
        )

    return True, None


def verify_card_payment(card_reference, amount, user):
    """
    Validates a confirmed, unspent PayWithCard payment belonging to `user`
    and reserves it against a purchase before the request proceeds.
    Reservation happens here (before the caller talks to the provider) so
    a reference can't be spent twice by concurrent requests, and the user
    scope stops one user from spending a payment reference that isn't
    theirs.

    Returns (funding_or_None, error_response_or_None).
    """
    if not card_reference:
        return None, Response(
            encrypt({"status": "fail", "message": "card_reference is required."}),
            status=status.HTTP_400_BAD_REQUEST,
        )

    funding = FundWithCard.objects.filter(
        txn_reference=card_reference, status="success", is_processed=False, user=user
    ).first()
    if not funding:
        return None, Response(
            encrypt(
                {
                    "status": "fail",
                    "message": "Invalid, unconfirmed, or already-used payment reference.",
                }
            ),
            status=status.HTTP_400_BAD_REQUEST,
        )

    if Decimal(str(funding.amount)) < Decimal(str(amount)):
        return None, Response(
            encrypt(
                {
                    "status": "fail",
                    "message": "Card payment does not cover the purchase amount.",
                }
            ),
            status=status.HTTP_400_BAD_REQUEST,
        )

    funding.is_processed = True
    funding.save(update_fields=["is_processed"])

    return funding, None


def generate_transaction_sms(
    transaction_type,
    account_number,
    amount,
    balance,
    description,
    reference,
):
    masked_account = f"******{str(account_number)[-4:]}"
    support_phone = "02012271894"

    lines = [
        f"{transaction_type.upper()} ALERT",
        f"Acct: {masked_account}",
        f"Amt: NGN{amount:.2f}",
        f"Desc: {description}",
        f"Date: {timezone.now().strftime('%d-%b-%Y %H:%M')}",
        f"Bal: NGN{balance:,.2f}",
    ]
    if transaction_type.upper() == "DEBIT":
        msg = f"If not you, contact support immediately. Call {support_phone}."
        lines.append(msg)
    return "\n".join(lines)


# tx_type values that represent money coming into the wallet. Everything else
# (transfers out, bill/airtime/data purchases, etc.) is treated as a debit.
CREDIT_TX_TYPES = {
    "Card Funding",
    "Funding of wallet",
    "Points Redemption to Wallet",
    "Wallet Credit",
}


def is_credit_tx(tx_type):
    return tx_type in CREDIT_TX_TYPES


def describe_transaction(tx):
    """
    Builds a statement-friendly description, e.g. "Fund Transfer to Michael Olise"
    or "Payment received from Onana", using the counterparty name on the linked
    transfer where available. Falls back to the raw description/tx_type.
    """
    transfers = tx.transfers.all()
    transfer = transfers[0] if transfers else None
    credit = is_credit_tx(tx.tx_type)

    if transfer:
        if credit and transfer.sender_name:
            return f"Payment received from {transfer.sender_name}"
        if not credit and transfer.beneficiary_name:
            return f"Fund Transfer to {transfer.beneficiary_name}"

    if tx.tx_type == "Wallet Credit" and tx.description:
        match = re.search(r"Credit from (.+?) \(", tx.description)
        if match:
            return f"Payment received from {match.group(1)}"

    return tx.description or tx.tx_type or "Transaction"


def summarize_transactions(transactions):
    """Returns (total_credit, total_debit, net) for a list/queryset of TxModel rows."""
    total_credit = 0
    total_debit = 0
    for tx in transactions:
        amount = float(tx.amount or 0)
        if is_credit_tx(tx.tx_type):
            total_credit += amount
        else:
            total_debit += amount
    return total_credit, total_debit, total_credit - total_debit


class ExportStatement:

    @staticmethod
    def to_csv(
        transactions,
        account_name=None,
        account_number=None,
        start_date=None,
        end_date=None,
    ):
        total_credit, total_debit, net = summarize_transactions(transactions)

        buffer = StringIO()
        writer = csv.writer(buffer)

        writer.writerow(["Picadailys Account Statement"])
        if account_name:
            writer.writerow(["Account Name", account_name])
        if account_number:
            writer.writerow(["Account Number", account_number])
        if start_date and end_date:
            writer.writerow(["Period", f"{start_date} to {end_date}"])
        writer.writerow(["Total Credit", f"{total_credit:,.2f}"])
        writer.writerow(["Total Debit", f"{total_debit:,.2f}"])
        writer.writerow(["Net Movement", f"{net:,.2f}"])
        writer.writerow([])

        writer.writerow(
            [
                "Date",
                "Reference",
                "Type",
                "Direction",
                "Amount",
                "Description",
                "Status",
            ]
        )

        for tx in transactions:
            writer.writerow(
                [
                    tx.date.strftime("%Y-%m-%d %H:%M"),
                    tx.tx_reference,
                    tx.tx_type,
                    "Credit" if is_credit_tx(tx.tx_type) else "Debit",
                    tx.amount,
                    describe_transaction(tx),
                    tx.status,
                ]
            )

        return buffer.getvalue()

    @staticmethod
    def to_pdf(
        transactions,
        account_name=None,
        account_number=None,
        start_date=None,
        end_date=None,
    ):
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            leftMargin=0.6 * inch,
            rightMargin=0.6 * inch,
            topMargin=0.7 * inch,
            bottomMargin=0.7 * inch,
        )

        styles = getSampleStyleSheet()
        brand_green = colors.HexColor("#2E7D32")
        mid_grey = colors.HexColor("#757575")
        light_grey = colors.HexColor("#F5F5F5")

        title_style = ParagraphStyle(
            "title",
            parent=styles["Normal"],
            fontSize=20,
            leading=24,
            fontName="Helvetica-Bold",
            textColor=brand_green,
            spaceAfter=6,
        )
        subtitle_style = ParagraphStyle(
            "subtitle",
            parent=styles["Normal"],
            fontSize=9,
            leading=13,
            fontName="Helvetica",
            textColor=mid_grey,
            spaceAfter=4,
        )
        ref_style = ParagraphStyle(
            "ref",
            parent=styles["Normal"],
            fontSize=7,
            fontName="Helvetica",
            textColor=mid_grey,
            wordWrap="CJK",
        )
        info_style = ParagraphStyle(
            "info",
            parent=styles["Normal"],
            fontSize=9,
            leading=13,
            fontName="Helvetica",
            textColor=colors.HexColor("#333333"),
            spaceAfter=1,
        )

        total_credit, total_debit, net = summarize_transactions(transactions)

        elements = []

        # Header
        elements.append(Paragraph("Picadailys", title_style))
        elements.append(Paragraph("Account Statement", subtitle_style))
        if account_name:
            elements.append(Paragraph(f"Account Name: {account_name}", info_style))
        if account_number:
            elements.append(Paragraph(f"Account Number: {account_number}", info_style))
        if start_date and end_date:
            elements.append(
                Paragraph(f"Period: {start_date} to {end_date}", info_style)
            )
        elements.append(Paragraph(f"Transactions: {len(transactions)}", info_style))
        elements.append(Spacer(1, 0.2 * inch))

        # Divider
        divider_data = [[""]]
        divider = Table(divider_data, colWidths=[doc.width])
        divider.setStyle(
            TableStyle(
                [
                    ("LINEABOVE", (0, 0), (-1, 0), 1.5, brand_green),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        elements.append(divider)
        elements.append(Spacer(1, 0.2 * inch))

        # Summary totals
        summary_data = [
            [
                Paragraph("<b>Total Credit</b>", styles["Normal"]),
                Paragraph("<b>Total Debit</b>", styles["Normal"]),
                Paragraph("<b>Net Movement</b>", styles["Normal"]),
            ],
            [
                Paragraph(
                    f'<font color="#2E7D32">+ NGN {total_credit:,.2f}</font>',
                    styles["Normal"],
                ),
                Paragraph(
                    f'<font color="#C62828">- NGN {total_debit:,.2f}</font>',
                    styles["Normal"],
                ),
                Paragraph(f"NGN {net:,.2f}", styles["Normal"]),
            ],
        ]
        summary_table = Table(summary_data, colWidths=[doc.width / 3.0] * 3)
        summary_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), light_grey),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E0E0E0")),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ]
            )
        )
        elements.append(summary_table)
        elements.append(Spacer(1, 0.25 * inch))

        # Table header
        col_widths = [
            0.75 * inch,
            0.95 * inch,
            0.9 * inch,
            0.8 * inch,
            0.85 * inch,
            1.55 * inch,
            0.9 * inch,
        ]
        header_style = ParagraphStyle(
            "tableHeader",
            parent=styles["Normal"],
            textColor=colors.white,
            fontName="Helvetica-Bold",
            fontSize=9,
        )
        header = [
            Paragraph("Date", header_style),
            Paragraph("Reference", header_style),
            Paragraph("Type", header_style),
            Paragraph("Direction", header_style),
            Paragraph("Amount (NGN)", header_style),
            Paragraph("Description", header_style),
            Paragraph("Status", header_style),
        ]
        table_data = [header]

        for tx in transactions:
            status_text = tx.status or "—"
            status_color = (
                colors.HexColor("#2E7D32")
                if status_text == "SUCCESS"
                else (
                    colors.HexColor("#C62828")
                    if status_text == "FAILED"
                    else colors.HexColor("#E65100")
                )
            )
            credit = is_credit_tx(tx.tx_type)
            direction_color = "#2E7D32" if credit else "#C62828"
            row = [
                Paragraph(tx.date.strftime("%d %b %Y"), styles["Normal"]),
                Paragraph(tx.tx_reference or "—", ref_style),
                Paragraph(tx.tx_type or "—", styles["Normal"]),
                Paragraph(
                    f'<font color="{direction_color}">{"Credit" if credit else "Debit"}</font>',
                    styles["Normal"],
                ),
                Paragraph(f"{float(tx.amount):,.2f}", styles["Normal"]),
                Paragraph(describe_transaction(tx), ref_style),
                Paragraph(
                    f'<font color="{status_color.hexval()}">{status_text}</font>',
                    styles["Normal"],
                ),
            ]
            table_data.append(row)

        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    # Header row
                    ("BACKGROUND", (0, 0), (-1, 0), brand_green),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 9),
                    ("TOPPADDING", (0, 0), (-1, 0), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                    # Data rows
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 1), (-1, -1), 8),
                    ("TOPPADDING", (0, 1), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
                    # Alternating row colors
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, light_grey]),
                    # Grid
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E0E0E0")),
                    ("LINEBELOW", (0, 0), (-1, 0), 1.5, brand_green),
                    # Alignment
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (3, 0), (3, -1), "CENTER"),
                    ("ALIGN", (4, 0), (4, -1), "RIGHT"),
                ]
            )
        )
        elements.append(table)
        elements.append(Spacer(1, 0.3 * inch))

        # Footer note
        footer_style = ParagraphStyle(
            "footer",
            parent=styles["Normal"],
            fontSize=7,
            fontName="Helvetica",
            textColor=mid_grey,
        )
        elements.append(
            Paragraph(
                "This statement is auto-generated by Picadailys. "
                "For queries, contact support@picadailys.com or call 02012271894 / 02012271895.",
                footer_style,
            )
        )

        doc.build(elements)
        return buffer.getvalue()


def get_asset_id(file):
    url = "https://api.yournotify.com/assets"

    headers = {"Authorization": yournotify_api_key}

    filename = "statement" + os.path.splitext(file)[1]
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    try:
        with open(file, "rb") as attachment:
            files = {"file": (filename, attachment, content_type)}

            response = requests.post(url, headers=headers, files=files)

        if response.status_code == 200:
            data = response.json()

            if data.get("status") == "success":
                return {"success": True, "media_id": data["data"][0]["id"]}

            return {"success": False, "message": data.get("message", "Upload failed")}

        return {
            "success": False,
            "message": f"HTTP Error: {response.status_code}",
            "response": response.text,
        }

    except Exception as e:
        return {"success": False, "message": str(e)}
