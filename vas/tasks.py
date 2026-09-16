# Standard library imports
import logging
from datetime import timedelta

# Third-party imports
from celery import shared_task
from django.utils import timezone


@shared_task
def reconcile_pending_vas_transactions():
    """Sweep TxModel rows stuck PENDING for data purchases and resolve them
    against 9PSB's status endpoint.

    VAS has no webhook back into the app (unlike bank transfers, see
    banking.tasks.reconcile_pending_transfers) - VAS.confirm_status already
    polls patiently inside the request, but if 9PSB is still lagging past
    that window, DataSubscriptionView parks the transaction as PENDING and
    nothing revisits it. This sweep is that revisit: it re-runs the same
    success side effects (TxModel write, cashback reward, wallet sync/
    notification) the synchronous view would have run had 9PSB answered in
    time.

    Airtime is deliberately not covered yet - AirTimeTopUp's success side
    effects haven't been extracted into a reusable function the way
    DataSubscriptionView's were (see complete_data_purchase in
    vas/utility.py). Do that first, then add "Airtime" to tx_type__in below
    and branch on tx.tx_type the same way.
    """
    from accounts.models import TxModel
    from .helpers import VAS
    from .utility import complete_data_purchase

    cutoff = timezone.now() - timedelta(minutes=15)
    stuck = TxModel.objects.filter(
        status="PENDING",
        tx_type="Data",
        date__lt=cutoff,
    ).select_related("user")

    token = VAS.authenticate()
    if not token:
        logging.error("reconcile_pending_vas_transactions: VAS authentication failed.")
        return

    resolved = 0
    for tx in stuck:
        try:
            status_resp = VAS.status(tx_ref=tx.tx_reference, bearer_token=token)
            if not status_resp or not VAS.is_success(status_resp):
                continue

            complete_data_purchase(
                user=tx.user,
                tx_reference=tx.tx_reference,
                amount=tx.amount,
                phone=tx.phone_number,
                network=tx.network,
                is_task=tx.is_task,
                task_id=tx.task_id,
            )
            resolved += 1
        except Exception as e:
            logging.error(
                f"reconcile_pending_vas_transactions: error resolving tx "
                f"{tx.id} ({tx.tx_reference}): {e}"
            )

    logging.info(
        f"VAS reconciliation sweep: resolved {resolved} of {stuck.count()} stuck transactions."
    )
