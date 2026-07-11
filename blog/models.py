"""
blog/models.py

Data model for the Blog module.
"""

import uuid

from django.db import IntegrityError, models, transaction
from django.db.models import F
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify


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

    # Views
    view_count = models.PositiveIntegerField(default=0)

    # Images
    featured_image = models.CharField(max_length=300, blank=True, default="")
    og_image = models.CharField(max_length=300, blank=True, default="")

    # SEO metadata
    meta_title = models.CharField(max_length=70, blank=True)
    meta_description = models.CharField(max_length=160, blank=True)

    # Status and timestamps
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
            self.slug = slugify(self.title)

        if self.status == self.Status.PUBLISHED and self.published_at is None:
            self.published_at = timezone.now()

        if self._state.adding:
            self._save_new_with_unique_slug(*args, **kwargs)
        else:
            super().save(*args, **kwargs)

    def _save_new_with_unique_slug(self, *args, **kwargs):

        base_slug = self.slug
        counter = 1
        max_attempts = 100

        for _ in range(max_attempts):
            try:
                with transaction.atomic():
                    super().save(*args, **kwargs)
                return
            except IntegrityError:
                counter += 1
                self.slug = f"{base_slug}-{counter}"

        raise IntegrityError(
            f"Could not generate a unique slug for '{self.title}' after "
            f"{max_attempts} attempts."
        )

    def get_absolute_url(self):
        return reverse("blog:detail", kwargs={"slug": self.slug})

    def update_view_count(self):
        Blog.objects.filter(pk=self.pk).update(view_count=F("view_count") + 1)
        self.refresh_from_db(fields=["view_count"])
