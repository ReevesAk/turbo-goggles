from django.utils.translation import gettext as _
from rest_framework.exceptions import APIException
from rest_framework import status


class Customexceptions(APIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = _('Not Found.')
    default_code = 'not_found'

    @classmethod
    def not_found(cls, item_not_found):
        return cls(
            detail=_("The requested item '{}' was not found.").format(item_not_found),
            code='item_not_found',
        )
    
    @staticmethod
    def server_error(cls, item_error):
        return cls(
            detail=_("The requested item '{}' encountered a server error.").format(item_error),
            code='server_error',
        )

    