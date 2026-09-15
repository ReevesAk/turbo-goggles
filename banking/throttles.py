from rest_framework.throttling import ScopedRateThrottle

from accounts.models import TxModel


class IdempotentTransferThrottle(ScopedRateThrottle):
    """
    A retry that reuses an already-seen Idempotency-Key is a safe no-op
    for the caller, so it shouldn't burn a slot in the transfer rate limit.
    """

    def allow_request(self, request, view):
        idempotency_key = request.headers.get("Idempotency-Key")
        user = getattr(request, "user", None)
        if (
            idempotency_key
            and user
            and user.is_authenticated
            and TxModel.objects.filter(user=user, tx_reference=idempotency_key).exists()
        ):
            return True
        return super().allow_request(request, view)
