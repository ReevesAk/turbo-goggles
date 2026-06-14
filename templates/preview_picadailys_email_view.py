from django.shortcuts import render


def preview_picadailys_email(request):
    context = {
        "title": "Preview",
        "rows": [],
        "support_email": "notifications@picadailys.com",
        "picadailys_phone": "02012271894 02012271895",
    }
    return render(request, "picadailys_email.html", context)
