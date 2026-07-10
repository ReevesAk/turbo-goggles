"""
blog/models.py

Data model for the Blog module.
"""

import uuid
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.db.models import F


class Blog(models.Model):

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Core content
    authors = models.JSONField(default=list, null=True, blank=True)
    title = models.CharField(max_length=255)
    category = models.CharField(max_length=255, null=True, blank=True)
    slug = models.SlugField(max_length=280, unique=True, blank=True, db_index=True)
    excerpt = models.CharField(max_length=300, blank=True)
    content = models.TextField()
    tags = models.JSONField(default=list, null=True, blank=True)

    # views
    view_count = models.PositiveIntegerField(default=0)

    # Images
    featured_image = models.CharField(max_length=300, blank=True, default="")
    og_image = models.CharField(max_length=300, blank=True, default="")

    # SEO metadata
    meta_title = models.CharField(max_length=70, blank=True)
    meta_description = models.CharField(max_length=160, blank=True)

    # Status and Timestamp
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True
    )
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-published_at", "-created_at"]
        indexes = [models.Index(fields=["status", "published_at"])]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)
            slug = base_slug
            counter = 1
            while Blog.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                counter += 1
                slug = f"{base_slug}-{counter}"
            self.slug = slug

        if self.status == self.Status.PUBLISHED and self.published_at is None:
            self.published_at = timezone.now()

        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("blog:detail", kwargs={"slug": self.slug})

    def update_view_count(self):
        Blog.objects.filter(pk=self.pk).update(view_count=F("view_count") + 1)
        self.refresh_from_db(fields=["view_count"])
