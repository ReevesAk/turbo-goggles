from django.shortcuts import render
from datetime import datetime

def preview_picadailys_email(request):
    context = {
        "title": "Wallet Credit Notification",
        "message": "Your wallet has been credited successfully!",
        "rows": [
            {"label": "Amount", "value": "₦5,000.00"},
            {"label": "Account Number", "value": "1101315778"},
            {"label": "Sender", "value": "Opay Nigeria"},
            {"label": "Source Bank", "value": "Opay"},
            {"label": "Source Account", "value": "1234567890"},
            {"label": "Narration", "value": "Test transaction"},
            {"label": "Reference", "value": "A26041639759"},
        ],
        "year": datetime.now().year,
    }
    return render(request, "picadailys_email.html", context)
