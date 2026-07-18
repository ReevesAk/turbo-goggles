"""
blog/views.py

API endpoints for the Blog module.
"""

import logging

from django.db.models import Q
from rest_framework import generics, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter, inline_serializer
from drf_spectacular.types import OpenApiTypes
import rest_framework.serializers as s

from roles.models import ActivityModel
from security import encrypt

from .models import Blog
from permissions import IsAdmin
from .serializers import BlogDetailSerializer, BlogListSerializer, BlogSerializer
from modules.response_mixings import StandardResponseMixin, Pagination

logger = logging.getLogger(__name__)


class AdminPagination(PageNumberPagination):
    page_size = 10


# ==========================================
# Public / User-facing endpoints
# ==========================================


@extend_schema(
    summary="List public blog posts",
    tags=["Blog"],
    description="Returns a paginated list of published blog posts. Supports filtering by category, tag, and free-text search.",
    parameters=[
        OpenApiParameter(
            name="category",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Filter posts by category (case-insensitive)",
            required=False,
        ),
        OpenApiParameter(
            name="tag",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Filter posts by tag",
            required=False,
        ),
        OpenApiParameter(
            name="search",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Search in title, excerpt, and content",
            required=False,
        ),
        OpenApiParameter(
            name="page",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            description="Page number for pagination",
            required=False,
        ),
        OpenApiParameter(
            name="page_size",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            description="Number of results per page (max 50)",
            required=False,
        ),
    ],
    responses={
        200: inline_serializer(
            "BlogListResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": s.DictField(),
            },
        ),
        400: inline_serializer(
            "BlogListError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class BlogListView(StandardResponseMixin, generics.ListAPIView):
    """
    GET /blogs/

    Public marketing-blog listing. Returns paginated, PUBLISHED posts
    only. Supports `category`, `tag`, and free-text `search`.
    """

    serializer_class = BlogListSerializer
    permission_classes = [AllowAny]
    pagination_class = Pagination

    def get_queryset(self):
        qs = Blog.objects.filter(status=Blog.Status.PUBLISHED)

        category = self.request.query_params.get("category")
        if category:
            qs = qs.filter(category__iexact=category)

        tag = self.request.query_params.get("tag")
        if tag:
            qs = qs.filter(tags__contains=[tag])

        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(
                Q(title__icontains=search)
                | Q(excerpt__icontains=search)
                | Q(content__icontains=search)
            )

        return qs.distinct()

    def list(self, request, *args, **kwargs):
        logger.info(
            "Public blog list requested. Filters: %s", dict(request.query_params)
        )
        return self.paginated_response(
            self.get_queryset(),
            BlogListSerializer,
            request,
            "Blog posts retrieved successfully.",
        )


@extend_schema(
    summary="Retrieve a single blog post",
    tags=["Blog"],
    description="Retrieves a single published blog post by slug. Increments the view count for the post. Returns 404 for drafts, archived, or nonexistent posts.",
    parameters=[
        OpenApiParameter(
            name="slug",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.PATH,
            description="The slug of the blog post",
            required=True,
        ),
    ],
    responses={
        200: inline_serializer(
            "BlogDetailResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": s.DictField(),
            },
        ),
        404: inline_serializer(
            "BlogDetailNotFound",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class BlogDetailView(StandardResponseMixin, generics.RetrieveAPIView):
    """
    GET /blogs/<slug>/

    Retrieves a single PUBLISHED post by slug. Increments view count.
    Returns 404 for drafts, archived, or nonexistent posts.
    """

    serializer_class = BlogDetailSerializer
    permission_classes = [AllowAny]
    lookup_field = "slug"

    def get_queryset(self):
        return Blog.objects.filter(status=Blog.Status.PUBLISHED)

    def retrieve(self, request, *args, **kwargs):
        try:
            blog = self.get_queryset().get(slug=kwargs["slug"])
            blog.update_view_count()
        except Blog.DoesNotExist:
            logger.info("Blog not found or not published: slug=%s", kwargs["slug"])
            return self.error_response(
                message="Blog post not found.", status_code=status.HTTP_404_NOT_FOUND
            )

        data = BlogDetailSerializer(blog).data
        return self.success_response(
            message="Blog post retrieved successfully.", data=data, should_encrypt=False
        )


# ==============================
# Admin endpoints
# ==============================


@extend_schema(
    summary="Create a new blog post",
    tags=["Blog Admin"],
    description="Creates a new blog post. Only authenticated admins can create posts. Supports file uploads for featured images.",
    request=BlogSerializer,
    responses={
        201: inline_serializer(
            "BlogCreateResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": s.DictField(),
            },
        ),
        400: inline_serializer(
            "BlogCreateError",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "errors": s.DictField(),
            },
        ),
        401: inline_serializer(
            "BlogCreateUnauthorized",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class BlogCreateView(StandardResponseMixin, generics.GenericAPIView):
    """POST /blogs/admin/create/"""

    serializer_class = BlogSerializer
    permission_classes = [IsAuthenticated, IsAdmin]
    parser_classes = [MultiPartParser, JSONParser]

    def post(self, request, *args, **kwargs):
        logger.info("User %s attempting to create a blog post.", request.user.id)

        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            logger.warning("Blog creation failed validation: %s", serializer.errors)
            return self.error_response(
                message="Validation error occurred.",
                status_code=status.HTTP_400_BAD_REQUEST,
                errors=serializer.errors,
            )

        blog = serializer.save()

        ActivityModel.objects.create(
            user=request.user,
            title="Blog Post Created",
            description=f"{request.user.first_name} {request.user.last_name} created a draft: '{blog.title}'.",
        )
        logger.info("Blog created: id=%s by user=%s", blog.id, request.user.id)

        data = BlogSerializer(blog).data
        return self.success_response(
            message="Blog post created successfully.",
            data=data,
            status_code=status.HTTP_201_CREATED,
        )


@extend_schema(
    summary="List all blog posts (admin)",
    tags=["Blog Admin"],
    description="Returns a paginated list of all blog posts regardless of status. Only accessible to admins. Supports filtering by status, category, and tag.",
    parameters=[
        OpenApiParameter(
            name="status",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Filter by post status (draft, published, archived)",
            required=False,
        ),
        OpenApiParameter(
            name="category",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Filter by category (case-insensitive)",
            required=False,
        ),
        OpenApiParameter(
            name="tag",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Filter by tag",
            required=False,
        ),
        OpenApiParameter(
            name="page",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            description="Page number for pagination",
            required=False,
        ),
        OpenApiParameter(
            name="page_size",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            description="Number of results per page",
            required=False,
        ),
    ],
    responses={
        200: inline_serializer(
            "BlogAdminListResponse",
            fields={
                "status": s.CharField(),
                "count": s.IntegerField(),
                "data": s.ListField(),
            },
        ),
        401: inline_serializer(
            "BlogAdminListUnauthorized",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class BlogAdminListView(StandardResponseMixin, generics.ListAPIView):
    """
    GET /blogs/admin/
    """

    serializer_class = BlogSerializer
    permission_classes = [IsAuthenticated, IsAdmin]
    pagination_class = AdminPagination

    def get_queryset(self):
        qs = Blog.objects.all().order_by("-created_at")

        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)

        category = self.request.query_params.get("category")
        if category:
            qs = qs.filter(category__icontains=category)

        tag = self.request.query_params.get("tag")
        if tag:
            qs = qs.filter(tags__contains=[tag])

        return qs

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return Response(
                data=encrypt(
                    {
                        "status": "success",
                        "count": queryset.count(),
                        "data": serializer.data,
                    }
                ),
                status=status.HTTP_200_OK,
            )
        serializer = self.get_serializer(queryset, many=True)
        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "count": queryset.count(),
                    "data": serializer.data,
                }
            ),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="Retrieve, update, or delete a blog post (admin)",
    tags=["Blog Admin"],
    description="GET retrieves a blog post regardless of status. PATCH partially updates any field including status. DELETE permanently removes the post. Only accessible to admins.",
    parameters=[
        OpenApiParameter(
            name="pk",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.PATH,
            description="Primary key of the blog post",
            required=True,
        ),
    ],
    responses={
        200: inline_serializer(
            "BlogAdminDetailResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": s.DictField(),
            },
        ),
        400: inline_serializer(
            "BlogAdminDetailError",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "errors": s.DictField(),
            },
        ),
        401: inline_serializer(
            "BlogAdminDetailUnauthorized",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        404: inline_serializer(
            "BlogAdminDetailNotFound",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class BlogAdminDetailView(StandardResponseMixin, generics.GenericAPIView):
    """
    GET/PATCH/DELETE /blogs/admin/<pk>/

    GET retrieves a post regardless of status. PATCH partially updates
    any field, including `status` -- this is how a post is moved
    between Draft, Published, and Archived. DELETE removes the post
    permanently.
    """

    serializer_class = BlogSerializer
    permission_classes = [IsAuthenticated, IsAdmin]
    parser_classes = [MultiPartParser, JSONParser]
    queryset = Blog.objects.all()
    lookup_field = "pk"

    def get_object(self, pk):
        try:
            return self.queryset.get(pk=pk)
        except Blog.DoesNotExist:
            return None

    def get(self, request, pk, *args, **kwargs):
        blog = self.get_object(pk)
        if not blog:
            return self.error_response(
                message="Blog post not found.", status_code=status.HTTP_404_NOT_FOUND
            )
        data = BlogSerializer(blog).data
        return self.success_response(
            message="Blog post retrieved successfully.", data=data
        )

    def patch(self, request, pk, *args, **kwargs):
        blog = self.get_object(pk)
        if not blog:
            return self.error_response(
                message="Blog post not found.", status_code=status.HTTP_404_NOT_FOUND
            )

        serializer = self.get_serializer(blog, data=request.data, partial=True)
        if not serializer.is_valid():
            return self.error_response(
                message="Validation error occurred.",
                status_code=status.HTTP_400_BAD_REQUEST,
                errors=serializer.errors,
            )

        blog = serializer.save()
        logger.info("Blog updated: id=%s by user=%s", blog.id, request.user.id)

        ActivityModel.objects.create(
            user=request.user,
            title="Blog Post Updated",
            description=f"{request.user.first_name} {request.user.last_name} updated '{blog.title}' (status={blog.status}).",
        )

        data = BlogSerializer(blog).data
        return self.success_response(
            message="Blog post updated successfully.", data=data
        )

    def delete(self, request, pk, *args, **kwargs):
        blog = self.get_object(pk)
        if not blog:
            return self.error_response(
                message="Blog post not found.", status_code=status.HTTP_404_NOT_FOUND
            )

        title = blog.title
        blog.delete()

        ActivityModel.objects.create(
            user=request.user,
            title="Blog Post Deleted",
            description=f"{request.user.first_name} {request.user.last_name} deleted the post '{title}'.",
        )
        logger.info("Blog deleted: title=%r by user=%s", title, request.user.id)

        return self.success_response(message="Blog post deleted successfully.")
