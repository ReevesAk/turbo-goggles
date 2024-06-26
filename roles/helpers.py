import logging
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from decouple import config


def sendMail(content, subject):
    message = Mail(
        from_email="care@picadailys.com",
        to_emails="career@picadailys.com",
        subject=subject,
        html_content=content,
    )

    try:
        sg = SendGridAPIClient(config("SENDGRID_API_KEY"))
        response = sg.send(message)
        logging.info(response.status_code)
    except Exception as e:
        logging.error(e.message)
