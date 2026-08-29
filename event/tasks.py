"""
Celery tasks for the event/ticketing module.
"""

import logging

from celery import shared_task

from .models import TicketCode

logger = logging.getLogger(__name__)


@shared_task
def generate_ticket_qr_async(ticket_code_id: str) -> None:
    """Async task to generate and upload QR code for a ticket."""
    from .models import generate_ticket_qr_image_and_upload

    try:
        ticket_code = TicketCode.objects.get(id=ticket_code_id)
        qr_url = generate_ticket_qr_image_and_upload(str(ticket_code.token))
        if qr_url:
            TicketCode.objects.filter(id=ticket_code_id).update(qr_image_url=qr_url)
            logger.info("QR code uploaded for ticket %s", ticket_code_id)
        else:
            logger.warning("QR code upload failed for ticket %s", ticket_code_id)
    except TicketCode.DoesNotExist:
        logger.error("TicketCode %s not found for QR generation", ticket_code_id)
