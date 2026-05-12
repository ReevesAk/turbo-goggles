import requests
import csv
from io import BytesIO, StringIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
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

from .models import WalletModel

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
            wallet = WalletModel.objects.get(user=user)
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


def cloudinary_to_base64(url, quality=40, max_size=(700, 700)):
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

    account = WalletModel.objects.filter(user=user).first()

    if use_biometrics:
        verified = Biometrics.authenticate(user.phone_number)
        if not verified:
            return False, Response(
                encrypt({"status": "fail", "error": "Biometric verification failed"}),
                status=status.HTTP_403_FORBIDDEN,
            )

    elif account and account.pin:
        verified = Pin.verify(user=user, pin=pin, hashed_pin=account.pin)
        if not verified:
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
        f"Bal: NGN{balance:.2f}",
    ]
    if transaction_type.upper() == "DEBIT":
        msg = f"If not you, contact support immediately. Call {support_phone}."
        lines.append(msg)
    return "\n".join(lines)


class ExportStatement:

    @staticmethod
    def to_csv(transactions):
        buffer = StringIO()
        writer = csv.writer(buffer)

        writer.writerow(
            ["Date", "Reference", "Type", "Amount", "Description", "Status"]
        )

        for tx in transactions:
            writer.writerow(
                [
                    tx.date.strftime("%Y-%m-%d %H:%M"),
                    tx.tx_reference,
                    tx.tx_type,
                    tx.amount,
                    tx.description,
                    tx.status,
                ]
            )

        return buffer.getvalue()

    @staticmethod
    def to_pdf(transactions):
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
        light_green = colors.HexColor("#E8F5E9")
        mid_grey = colors.HexColor("#757575")
        light_grey = colors.HexColor("#F5F5F5")

        title_style = ParagraphStyle(
            "title", parent=styles["Normal"],
            fontSize=20, fontName="Helvetica-Bold",
            textColor=brand_green, spaceAfter=2,
        )
        subtitle_style = ParagraphStyle(
            "subtitle", parent=styles["Normal"],
            fontSize=9, fontName="Helvetica",
            textColor=mid_grey, spaceAfter=0,
        )
        ref_style = ParagraphStyle(
            "ref", parent=styles["Normal"],
            fontSize=7, fontName="Helvetica",
            textColor=mid_grey, wordWrap="CJK",
        )

        elements = []

        # Header
        elements.append(Paragraph("Picadailys", title_style))
        elements.append(Paragraph("Account Statement", subtitle_style))
        elements.append(Spacer(1, 0.25 * inch))

        # Divider
        divider_data = [[""]]
        divider = Table(divider_data, colWidths=[doc.width])
        divider.setStyle(TableStyle([
            ("LINEABOVE", (0, 0), (-1, 0), 1.5, brand_green),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        elements.append(divider)
        elements.append(Spacer(1, 0.2 * inch))

        # Table header
        col_widths = [1.0 * inch, 2.6 * inch, 1.5 * inch, 0.9 * inch, 0.8 * inch]
        header = [
            Paragraph("<b>Date</b>", styles["Normal"]),
            Paragraph("<b>Reference</b>", styles["Normal"]),
            Paragraph("<b>Type</b>", styles["Normal"]),
            Paragraph("<b>Amount (₦)</b>", styles["Normal"]),
            Paragraph("<b>Status</b>", styles["Normal"]),
        ]
        table_data = [header]

        for tx in transactions:
            status_text = tx.status or "—"
            status_color = (
                colors.HexColor("#2E7D32") if status_text == "SUCCESS"
                else colors.HexColor("#C62828") if status_text == "FAILED"
                else colors.HexColor("#E65100")
            )
            row = [
                Paragraph(tx.date.strftime("%d %b %Y"), styles["Normal"]),
                Paragraph(tx.tx_reference or "—", ref_style),
                Paragraph(tx.tx_type or "—", styles["Normal"]),
                Paragraph(f"{float(tx.amount):,.2f}", styles["Normal"]),
                Paragraph(
                    f'<font color="{status_color.hexval()}">{status_text}</font>',
                    styles["Normal"]
                ),
            ]
            table_data.append(row)

        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
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
            ("ALIGN", (3, 0), (3, -1), "RIGHT"),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 0.3 * inch))

        # Footer note
        footer_style = ParagraphStyle(
            "footer", parent=styles["Normal"],
            fontSize=7, fontName="Helvetica",
            textColor=mid_grey,
        )
        elements.append(Paragraph(
            "This statement is auto-generated by Picadailys. "
            "For queries, contact support@picadailys.com or call 02012271894 / 02012271895.",
            footer_style,
        ))

        doc.build(elements)
        return buffer.getvalue()


def get_asset_id(file):
    url = "https://api.yournotify.com/assets"

    headers = {"Authorization": yournotify_api_key}

    try:
        with open(file, "rb") as pdf_file:
            files = {"file": ("statement.pdf", pdf_file, "application/pdf")}

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
