from rest_framework.views import exception_handler as drf_exception_handler


def custom_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)

    if response is None:
        return response

    # Permission classes in permissions.py raise ValidationError("some string"),
    # which DRF coerces into a single-item list (["some string"]). Every other
    # endpoint in this codebase returns a plain encrypted string as the body,
    # so unwrap that single-item-list case back to match.
    if isinstance(response.data, list) and len(response.data) == 1:
        response.data = response.data[0]
    elif isinstance(response.data, dict) and list(response.data.keys()) == ["detail"]:
        response.data = response.data["detail"]

    return response
