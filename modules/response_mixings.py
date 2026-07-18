from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from security import encrypt


class Pagination(PageNumberPagination):
    """Public-facing pagination: 10 posts/page by default, capped at 50."""

    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 50


class StandardResponseMixin:
    """
    Small DRY helper so every view in this module returns the same
    encrypted `{status, message, data}` / `{status, message}` envelope
    used throughout the codebase.
    """

    def success_response(
        self, message, data=None, status_code=status.HTTP_200_OK, should_encrypt=True
    ):
        body = {"status": "success", "message": message}
        if data is not None:
            body["data"] = data

        # Response for encrypted requests
        if should_encrypt:
            return Response(data=encrypt(body), status=status_code)

        return Response(data=body, status=status_code)

    def error_response(
        self,
        message,
        status_code=status.HTTP_400_BAD_REQUEST,
        errors=None,
        should_encrypt=True,
    ):
        body = {"status": "fail", "message": message}
        if errors is not None:
            body["errors"] = errors

        # Response for encrypted requests
        if should_encrypt:
            return Response(data=encrypt(body), status=status_code)

        return Response(data=body, status=status_code)

    def paginated_response(self, queryset, serializer_class, request, message):
        paginator = Pagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        data = serializer_class(page, many=True).data
        return self.success_response(
            message,
            {
                "results": data,
                "count": paginator.page.paginator.count,
                "next": paginator.get_next_link(),
                "previous": paginator.get_previous_link(),
            },
            should_encrypt=False,
        )
