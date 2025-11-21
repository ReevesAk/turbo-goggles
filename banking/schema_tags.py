from drf_spectacular.utils import extend_schema


def apply_tag(tag_name, view_classes):
    """
    Automatically assigns the same Spectacular OpenAPI tag
    to all provided view classes.
    """
    for view in view_classes:
        extend_schema(tags=[tag_name])(view)
