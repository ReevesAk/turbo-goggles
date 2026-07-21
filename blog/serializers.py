"""
blog/serializers.py

Serializers for the Blog module.
"""

import logging

from cloudinary import uploader as cloud
from rest_framework import serializers

from .models import Blog

logger = logging.getLogger(__name__)


# ==========================================
# Public / User-facing serializers
# ==========================================


class BlogListSerializer(serializers.ModelSerializer):
    """
    Serializer for the public blog listing endpoint.

    Excludes ``content`` to keep the listing payload light; use
    BlogDetailSerializer for the full body.
    """

    class Meta:
        model = Blog
        fields = [
            "id",
            "title",
            "slug",
            "excerpt",
            "featured_image",
            "category",
            "view_count",
            "tags",
            "authors",
            "published_at",
        ]
        read_only_fields = fields


class BlogDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for the public single-post endpoint, including full
    content and SEO metadata.
    """

    class Meta:
        model = Blog
        fields = [
            "id",
            "title",
            "slug",
            "excerpt",
            "content",
            "featured_image",
            "og_image",
            "view_count",
            "meta_title",
            "meta_description",
            "category",
            "tags",
            "authors",
            "published_at",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


# ==========================================
# ContentAdmin-facing serializer
# ==========================================


class BlogSerializer(serializers.ModelSerializer):
    """
    Single serializer used for every ContentAdmin operation: create,
    list, retrieve, and update.
    """

    featured_image_upload = serializers.ImageField(write_only=True, required=False)
    og_image_upload = serializers.ImageField(write_only=True, required=False)

    class Meta:
        model = Blog
        fields = [
            "id",
            "title",
            "slug",
            "excerpt",
            "content",
            "category",
            "authors",
            "tags",
            "featured_image",
            "featured_image_upload",
            "og_image",
            "og_image_upload",
            "status",
            "view_count",
            "meta_title",
            "meta_description",
            "published_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "slug", "published_at", "created_at", "updated_at"]

    def _upload(self, file):
        result = cloud.upload(file)
        return result["url"]

    def validate_title(self, value):
        value = value.strip()
        if len(value) < 5:
            raise serializers.ValidationError(
                "Title must be at least 5 characters long."
            )
        return value

    def validate_meta_description(self, value):
        if value and len(value) > 160:
            raise serializers.ValidationError(
                "meta_description should be 160 characters or fewer for SEO."
            )
        return value

    def validate(self, attrs):
        featured_upload = attrs.pop("featured_image_upload", None)
        og_upload = attrs.pop("og_image_upload", None)

        if featured_upload:
            try:
                attrs["featured_image"] = self._upload(featured_upload)
            except Exception as exc:
                raise serializers.ValidationError(
                    {"featured_image_upload": f"Upload failed: {exc}"}
                )

        if og_upload:
            try:
                attrs["og_image"] = self._upload(og_upload)
            except Exception as exc:
                raise serializers.ValidationError(
                    {"og_image_upload": f"Upload failed: {exc}"}
                )

        logger.info("Blog write attempt: title=%r", attrs.get("title", "")[:80])
        return super().validate(attrs)

    def create(self, validated_data):
        validated_data.setdefault("featured_image", "")
        validated_data.setdefault("og_image", "")

        blog = Blog.objects.create(**validated_data)
        logger.info("Blog created: id=%s title=%r", blog.id, blog.title)
        return blog

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()

        logger.info(
            "Blog updated: id=%s title=%r status=%s",
            instance.id,
            instance.title,
            instance.status,
        )
        return instance
