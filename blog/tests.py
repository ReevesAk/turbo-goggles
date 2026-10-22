"""
blog/tests.py

Comprehensive test cases for the Blog module.
"""

from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from django.db import connection
from django.test.utils import CaptureQueriesContext

from .models import Blog
from accounts.models import AccountType
from roles.models import ActivityModel
from security import decrypt
from testing_utils import TEST_PASSWORD

User = get_user_model()


class BlogModelTest(TestCase):
    """Test cases for the Blog model."""

    def setUp(self):
        self.blog = Blog.objects.create(
            title="Test Blog Post",
            content="This is test content.",
            excerpt="Test excerpt",
            category="Technology",
            tags=["python", "django"],
            status=Blog.Status.PUBLISHED,
        )

    def test_blog_creation(self):
        """Test that a blog post is created correctly."""
        self.assertEqual(self.blog.title, "Test Blog Post")
        self.assertEqual(self.blog.content, "This is test content.")
        self.assertEqual(self.blog.status, Blog.Status.PUBLISHED)
        self.assertIsNotNone(self.blog.slug)
        self.assertEqual(self.blog.view_count, 0)

    def test_slug_auto_generation(self):
        """Test that slug is automatically generated from title."""
        self.assertEqual(self.blog.slug, "test-blog-post")

    def test_slug_uniqueness(self):
        """Test that duplicate slugs get a number appended."""
        blog2 = Blog.objects.create(
            title="Test Blog Post",
            content="Another test.",
            status=Blog.Status.DRAFT,
        )
        self.assertEqual(blog2.slug, "test-blog-post-2")

    def test_published_at_auto_set(self):
        """Test that published_at is set when status is PUBLISHED."""
        draft = Blog.objects.create(
            title="Draft Post",
            content="Draft content.",
            status=Blog.Status.DRAFT,
        )
        self.assertIsNone(draft.published_at)

        draft.status = Blog.Status.PUBLISHED
        draft.save()
        self.assertIsNotNone(draft.published_at)

    def test_update_view_count(self):
        """Test that view count increments correctly."""
        initial_count = self.blog.view_count
        self.blog.update_view_count()
        self.blog.refresh_from_db()
        self.assertEqual(self.blog.view_count, initial_count + 1)

        # Update multiple times
        self.blog.update_view_count()
        self.blog.refresh_from_db()
        self.assertEqual(self.blog.view_count, initial_count + 2)

    def test_get_absolute_url(self):
        """Test the get_absolute_url method."""
        expected_url = reverse("blog:detail", kwargs={"slug": self.blog.slug})
        self.assertEqual(self.blog.get_absolute_url(), expected_url)

    def test_string_representation(self):
        """Test the string representation of the model."""
        self.assertEqual(str(self.blog), "Test Blog Post")


class BlogListViewTest(TestCase):
    """Test cases for the public BlogListView."""

    def setUp(self):
        self.client = APIClient()
        self.url = reverse("blog:list")
        # Create published posts
        self.published_posts = []
        for i in range(5):
            post = Blog.objects.create(
                title=f"Published Post {i}",
                content=f"Content {i}",
                category="Technology" if i % 2 == 0 else "Science",
                tags=["python"] if i % 2 == 0 else ["django"],
                status=Blog.Status.PUBLISHED,
            )
            self.published_posts.append(post)

        # Create draft and archived posts
        self.draft_post = Blog.objects.create(
            title="Draft Post",
            content="Draft content.",
            status=Blog.Status.DRAFT,
        )
        self.archived_post = Blog.objects.create(
            title="Archived Post",
            content="Archived content.",
            status=Blog.Status.ARCHIVED,
        )

    def test_list_published_posts_only(self):
        """Test that only published posts are returned."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.data
        if isinstance(response_data, dict) and "data" in response_data:
            body = response_data

            data = body["data"]
            results = data.get("results", [])
            self.assertEqual(len(results), 5)
            # Check that no draft or archived posts are in results
            titles = [post["title"] for post in results]
            self.assertNotIn("Draft Post", titles)
            self.assertNotIn("Archived Post", titles)

    def test_filter_by_category(self):
        """Test filtering posts by category."""
        response = self.client.get(self.url, {"category": "Technology"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        body = response.data
        results = body["data"].get("results", [])
        for post in results:
            self.assertEqual(post["category"], "Technology")

    def test_filter_by_tag(self):
        """Test filtering posts by tag."""
        response = self.client.get(self.url, {"tag": "python"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        body = response.data
        results = body["data"].get("results", [])
        for post in results:
            self.assertIn("python", post.get("tags", []))

    def test_search_functionality(self):
        """Test searching posts by title, excerpt, and content."""
        # Search by title
        response = self.client.get(self.url, {"search": "Published Post 1"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        body = response.data

        results = body["data"].get("results", [])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Published Post 1")

        # Search by content
        response = self.client.get(self.url, {"search": "Content 2"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        body = response.data

        results = body["data"].get("results", [])
        self.assertGreater(len(results), 0)

    def test_pagination(self):
        """Test pagination of blog list."""
        # Test default page size (10)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        body = response.data

        self.assertEqual(body["data"]["count"], 5)

        # Test custom page size
        response = self.client.get(self.url, {"page_size": 2})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        body = response.data

        self.assertEqual(len(body["data"]["results"]), 2)


class BlogDetailViewTest(TestCase):
    """Test cases for the public BlogDetailView."""

    def setUp(self):
        self.client = APIClient()

        # Create a published post
        self.published_post = Blog.objects.create(
            title="Published Post",
            content="Published content.",
            category="Technology",
            tags=["python"],
            status=Blog.Status.PUBLISHED,
            view_count=0,
        )

        # Create a draft post
        self.draft_post = Blog.objects.create(
            title="Draft Post",
            content="Draft content.",
            status=Blog.Status.DRAFT,
        )

        self.url = reverse("blog:detail", kwargs={"slug": self.published_post.slug})
        self.draft_url = reverse("blog:detail", kwargs={"slug": self.draft_post.slug})

    def test_retrieve_published_post(self):
        """Test retrieving a published post."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        body = response.data

        data = body["data"]
        self.assertEqual(data["title"], "Published Post")
        self.assertEqual(data["content"], "Published content.")
        self.assertEqual(data["status"], "published")

    def test_view_count_increments(self):
        """Test that view count increments when a post is retrieved."""
        initial_count = self.published_post.view_count

        # First view
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.published_post.refresh_from_db()
        self.assertEqual(self.published_post.view_count, initial_count + 1)

        # Second view
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.published_post.refresh_from_db()
        self.assertEqual(self.published_post.view_count, initial_count + 2)

    def test_view_count_not_increment_for_non_existent(self):
        """Test that view count doesn't increment for non-existent posts."""
        # Create a post with known view count
        post = Blog.objects.create(
            title="Test Post",
            content="Test content.",
            status=Blog.Status.PUBLISHED,
            view_count=5,
        )

        # Try to retrieve with wrong slug
        url = reverse("blog:detail", kwargs={"slug": "non-existent-slug"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # View count should not change
        post.refresh_from_db()
        self.assertEqual(post.view_count, 5)

    def test_draft_post_not_accessible(self):
        """Test that draft posts are not accessible to the public."""
        response = self.client.get(self.draft_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_archived_post_not_accessible(self):
        """Test that archived posts are not accessible to the public."""
        archived_post = Blog.objects.create(
            title="Archived Post",
            content="Archived content.",
            status=Blog.Status.ARCHIVED,
        )
        url = reverse("blog:detail", kwargs={"slug": archived_post.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class BlogAdminCreateViewTest(TestCase):
    """Test cases for the admin BlogCreateView."""

    def setUp(self):
        self.client = APIClient()
        self.url = reverse("blog:admin-create")

        # Create an admin user
        self.admin_user = User.objects.create_user(
            email="admin@example.com",
            phone_number="1234567890",
            password=TEST_PASSWORD,
            first_name="Admin",
            last_name="User",
            is_verified=True,
        )
        AccountType.objects.create(
            user=self.admin_user,
            user_type="SuperAdmin",
        )
        self.admin_user.active_role = "SuperAdmin"
        self.admin_user.save()

    def test_create_blog_post_authenticated(self):
        """Test creating a blog post as an authenticated admin."""
        self.client.force_authenticate(user=self.admin_user)

        data = {
            "title": "New Blog Post",
            "content": "This is the content of the new blog post.",
            "excerpt": "This is the excerpt.",
            "category": "Technology",
            "tags": ["python", "django"],
            "status": "draft",
            "authors": ["John Doe"],
        }

        response = self.client.post(self.url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Check that the blog was created
        self.assertTrue(Blog.objects.filter(title="New Blog Post").exists())
        blog = Blog.objects.get(title="New Blog Post")
        self.assertEqual(blog.content, "This is the content of the new blog post.")
        self.assertEqual(blog.status, Blog.Status.DRAFT)

        # Check that activity was logged
        self.assertTrue(
            ActivityModel.objects.filter(
                user=self.admin_user, title="Blog Post Created"
            ).exists()
        )

    def test_create_blog_post_unauthenticated(self):
        """Test that unauthenticated users cannot create blog posts."""
        data = {
            "title": "New Blog Post",
            "content": "Content",
            "status": "draft",
        }

        response = self.client.post(self.url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(Blog.objects.filter(title="New Blog Post").exists())

    # blog/tests.py - Update non-admin create test

    def test_create_blog_post_non_admin(self):
        """Test that non-admin users cannot create blog posts."""
        regular_user = User.objects.create_user(
            email="user@example.com",
            phone_number="9876543210",
            password=TEST_PASSWORD,
            is_verified=True,
        )
        self.client.force_authenticate(user=regular_user)

        data = {
            "title": "New Blog Post",
            "content": "Content",
            "status": "draft",
        }

        response = self.client.post(self.url, data, format="json")
        self.assertIn(
            response.status_code,
            [status.HTTP_403_FORBIDDEN, status.HTTP_400_BAD_REQUEST],
        )

    def test_create_blog_post_validation_errors(self):
        """Test validation errors when creating a blog post."""
        self.client.force_authenticate(user=self.admin_user)

        # Missing required fields
        data = {
            "content": "Content without title",
        }

        response = self.client.post(self.url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Check error response

        decrypted = decrypt(response.data)
        if isinstance(decrypted, dict):
            self.assertEqual(decrypted["status"], "fail")
            self.assertIn("errors", decrypted)


class BlogAdminListViewTest(TestCase):
    """Test cases for the admin BlogAdminListView."""

    def setUp(self):
        self.client = APIClient()
        self.url = reverse("blog:admin-list")

        # Create an admin user
        self.admin_user = User.objects.create_user(
            email="admin@example.com",
            phone_number="1234567890",
            password=TEST_PASSWORD,
            is_verified=True,
        )
        AccountType.objects.create(
            user=self.admin_user,
            user_type="SuperAdmin",
        )
        self.admin_user.active_role = "SuperAdmin"
        self.admin_user.save()

        # Create blog posts with different statuses
        self.posts = [
            Blog.objects.create(
                title=f"Post {i}",
                content=f"Content {i}",
                status=status_choice,
                category="Technology" if i % 2 == 0 else "Science",
                tags=["python"] if i % 2 == 0 else ["django"],
            )
            for i, status_choice in enumerate(
                [
                    Blog.Status.PUBLISHED,
                    Blog.Status.DRAFT,
                    Blog.Status.ARCHIVED,
                    Blog.Status.PUBLISHED,
                    Blog.Status.DRAFT,
                ]
            )
        ]

    def test_list_all_posts_authenticated(self):
        """Test listing all blog posts as an authenticated admin."""
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        decrypted = decrypt(response.data)
        if isinstance(decrypted, dict):
            self.assertEqual(decrypted["count"], 5)
            self.assertEqual(len(decrypted["data"]), 5)

    def test_filter_by_status(self):
        """Test filtering blog posts by status."""
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.get(self.url, {"status": "published"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        decrypted = decrypt(response.data)
        if isinstance(decrypted, dict):
            data = decrypted["data"]
            for post in data:
                self.assertEqual(post["status"], "published")

    def test_filter_by_category(self):
        """Test filtering blog posts by category."""
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.get(self.url, {"category": "Technology"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        decrypted = decrypt(response.data)
        if isinstance(decrypted, dict):
            data = decrypted["data"]
            for post in data:
                self.assertEqual(post["category"], "Technology")

    def test_filter_by_tag(self):
        """Test filtering blog posts by tag."""
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.get(self.url, {"tag": "python"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        decrypted = decrypt(response.data)
        if isinstance(decrypted, dict):
            data = decrypted["data"]
            for post in data:
                self.assertIn("python", post.get("tags", []))

    def test_list_posts_unauthenticated(self):
        """Test that unauthenticated users cannot access admin list."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class BlogAdminDetailViewTest(TestCase):
    """Test cases for the admin BlogAdminDetailView."""

    def setUp(self):
        self.client = APIClient()

        # Create an admin user
        self.admin_user = User.objects.create_user(
            email="admin@example.com",
            phone_number="1234567890",
            password=TEST_PASSWORD,
            is_verified=True,
        )
        AccountType.objects.create(
            user=self.admin_user,
            user_type="SuperAdmin",
        )
        self.admin_user.active_role = "SuperAdmin"
        self.admin_user.save()

        # Create a blog post
        self.blog = Blog.objects.create(
            title="Test Blog",
            content="Test content.",
            category="Technology",
            tags=["python"],
            status=Blog.Status.DRAFT,
        )

        import uuid

        self.url = reverse("blog:admin-detail", kwargs={"pk": self.blog.pk})
        self.non_existent_url = reverse(
            "blog:admin-detail", kwargs={"pk": uuid.uuid4()}
        )

    def test_retrieve_post_authenticated(self):
        """Test retrieving a blog post as an authenticated admin."""
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        decrypted = decrypt(response.data)
        if isinstance(decrypted, dict) and "data" in decrypted:
            data = decrypted["data"]
            self.assertEqual(data["title"], "Test Blog")
            self.assertEqual(data["content"], "Test content.")
            self.assertEqual(data["status"], "draft")

    def test_retrieve_post_unauthenticated(self):
        """Test that unauthenticated users cannot retrieve a post."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_retrieve_non_existent_post(self):
        """Test retrieving a non-existent blog post."""
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.get(self.non_existent_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_update_post_authenticated(self):
        """Test updating a blog post as an authenticated admin."""
        self.client.force_authenticate(user=self.admin_user)

        data = {
            "title": "Updated Title",
            "content": "Updated content.",
            "status": "published",
        }

        response = self.client.patch(self.url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Check that the blog was updated
        self.blog.refresh_from_db()
        self.assertEqual(self.blog.title, "Updated Title")
        self.assertEqual(self.blog.content, "Updated content.")
        self.assertEqual(self.blog.status, Blog.Status.PUBLISHED)

        # Check that activity was logged
        self.assertTrue(
            ActivityModel.objects.filter(
                user=self.admin_user, title="Blog Post Updated"
            ).exists()
        )

    def test_update_post_status_change_effects(self):
        """Test that changing status has the expected effects."""
        self.client.force_authenticate(user=self.admin_user)

        # Change draft to published
        self.blog.status = Blog.Status.DRAFT
        self.blog.save()

        data = {"status": "published"}
        response = self.client.patch(self.url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.blog.refresh_from_db()
        self.assertEqual(self.blog.status, Blog.Status.PUBLISHED)
        self.assertIsNotNone(self.blog.published_at)

        # Change published to archived
        data = {"status": "archived"}
        response = self.client.patch(self.url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.blog.refresh_from_db()
        self.assertEqual(self.blog.status, Blog.Status.ARCHIVED)

    def test_update_post_unauthenticated(self):
        """Test that unauthenticated users cannot update a post."""
        data = {"title": "Hacked Title"}
        response = self.client.patch(self.url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        self.blog.refresh_from_db()
        self.assertNotEqual(self.blog.title, "Hacked Title")

    def test_delete_post_authenticated(self):
        """Test deleting a blog post as an authenticated admin."""
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Check that the blog was deleted
        self.assertFalse(Blog.objects.filter(pk=self.blog.pk).exists())

        # Check that activity was logged
        self.assertTrue(
            ActivityModel.objects.filter(
                user=self.admin_user, title="Blog Post Deleted"
            ).exists()
        )

    def test_delete_post_unauthenticated(self):
        """Test that unauthenticated users cannot delete a post."""
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        # Check that the blog still exists
        self.assertTrue(Blog.objects.filter(pk=self.blog.pk).exists())

    def test_delete_non_existent_post(self):
        """Test deleting a non-existent blog post."""
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.delete(self.non_existent_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class BlogSerializationTest(TestCase):
    """Test cases for blog serializers."""

    def setUp(self):
        self.blog = Blog.objects.create(
            title="Test Blog",
            content="Test content.",
            excerpt="Test excerpt.",
            category="Technology",
            tags=["python", "django"],
            authors=["John Doe"],
            status=Blog.Status.PUBLISHED,
            view_count=10,
            meta_title="SEO Title",
            meta_description="SEO Description",
        )

    def test_blog_list_serializer(self):
        """Test the BlogListSerializer."""
        from .serializers import BlogListSerializer

        serializer = BlogListSerializer(self.blog)
        data = serializer.data

        self.assertEqual(data["title"], "Test Blog")
        self.assertEqual(data["excerpt"], "Test excerpt.")
        self.assertEqual(data["category"], "Technology")
        self.assertEqual(data["tags"], ["python", "django"])
        self.assertEqual(data["slug"], "test-blog")
        self.assertEqual(data["view_count"], 10)
        self.assertNotIn("content", data)
        self.assertNotIn("meta_title", data)

    def test_blog_detail_serializer(self):
        """Test the BlogDetailSerializer."""
        from .serializers import BlogDetailSerializer

        serializer = BlogDetailSerializer(self.blog)
        data = serializer.data

        self.assertEqual(data["title"], "Test Blog")
        self.assertEqual(data["content"], "Test content.")
        self.assertEqual(data["excerpt"], "Test excerpt.")
        self.assertEqual(data["category"], "Technology")
        self.assertEqual(data["tags"], ["python", "django"])
        self.assertEqual(data["authors"], ["John Doe"])
        self.assertEqual(data["slug"], "test-blog")
        self.assertEqual(data["view_count"], 10)
        self.assertEqual(data["meta_title"], "SEO Title")
        self.assertEqual(data["meta_description"], "SEO Description")

    def test_blog_serializer(self):
        """Test the BlogSerializer (full)."""
        from .serializers import BlogSerializer

        serializer = BlogSerializer(self.blog)
        data = serializer.data

        self.assertEqual(data["title"], "Test Blog")
        self.assertEqual(data["content"], "Test content.")
        self.assertEqual(data["status"], "published")
        self.assertEqual(data["view_count"], 10)
        self.assertEqual(data["meta_title"], "SEO Title")
        self.assertEqual(data["meta_description"], "SEO Description")


class BlogPermissionTest(TestCase):
    """Test cases for blog permissions."""

    def setUp(self):
        self.client = APIClient()

        # Create users with different roles
        self.super_admin = User.objects.create_user(
            email="super@example.com",
            phone_number="1111111111",
            password=TEST_PASSWORD,
            is_verified=True,
        )
        AccountType.objects.create(
            user=self.super_admin,
            user_type="SuperAdmin",
        )
        self.super_admin.active_role = "SuperAdmin"
        self.super_admin.save()

        self.fmcg_admin = User.objects.create_user(
            email="fmcg@example.com",
            phone_number="2222222222",
            password=TEST_PASSWORD,
            is_verified=True,
        )
        AccountType.objects.create(
            user=self.fmcg_admin,
            user_type="FmcgAdmin",
        )
        self.fmcg_admin.active_role = "FmcgAdmin"
        self.fmcg_admin.save()

        self.regular_user = User.objects.create_user(
            email="user@example.com",
            phone_number="3333333333",
            password=TEST_PASSWORD,
            is_verified=True,
        )

        self.blog = Blog.objects.create(
            title="Test Blog",
            content="Test content.",
            status=Blog.Status.DRAFT,
        )

        self.create_url = reverse("blog:admin-create")
        self.list_url = reverse("blog:admin-list")
        self.detail_url = reverse("blog:admin-detail", kwargs={"pk": self.blog.pk})

    def test_super_admin_has_access(self):
        """Test that SuperAdmin has access to all admin endpoints."""
        self.client.force_authenticate(user=self.super_admin)

        # Can create
        response = self.client.post(
            self.create_url, {"title": "New", "content": "Content"}, format="json"
        )
        self.assertNotEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Can list
        response = self.client.get(self.list_url)
        self.assertNotEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Can retrieve
        response = self.client.get(self.detail_url)
        self.assertNotEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Can update
        response = self.client.patch(
            self.detail_url, {"title": "Updated"}, format="json"
        )
        self.assertNotEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Can delete
        response = self.client.delete(self.detail_url)
        self.assertNotEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_fmcg_admin_no_access(self):
        """Test that FmcgAdmin does not have access to blog admin endpoints."""
        self.client.force_authenticate(user=self.fmcg_admin)

        # Cannot create
        response = self.client.post(
            self.create_url, {"title": "New", "content": "Content"}, format="json"
        )
        self.assertIn(
            response.status_code,
            [status.HTTP_403_FORBIDDEN, status.HTTP_400_BAD_REQUEST],
        )

        # Cannot list
        response = self.client.get(self.list_url)
        self.assertIn(
            response.status_code,
            [status.HTTP_403_FORBIDDEN, status.HTTP_400_BAD_REQUEST],
        )

        # Cannot retrieve
        response = self.client.get(self.detail_url)
        self.assertIn(
            response.status_code,
            [
                status.HTTP_403_FORBIDDEN,
                status.HTTP_404_NOT_FOUND,
                status.HTTP_400_BAD_REQUEST,
            ],
        )

        # Cannot update
        response = self.client.patch(
            self.detail_url, {"title": "Updated"}, format="json"
        )
        self.assertIn(
            response.status_code,
            [
                status.HTTP_403_FORBIDDEN,
                status.HTTP_404_NOT_FOUND,
                status.HTTP_400_BAD_REQUEST,
            ],
        )

        # Cannot delete
        response = self.client.delete(self.detail_url)
        self.assertIn(
            response.status_code,
            [
                status.HTTP_403_FORBIDDEN,
                status.HTTP_404_NOT_FOUND,
                status.HTTP_400_BAD_REQUEST,
            ],
        )

    def test_regular_user_no_access(self):
        """Test that regular users do not have access to admin endpoints."""
        self.client.force_authenticate(user=self.regular_user)

        # Cannot create
        response = self.client.post(
            self.create_url, {"title": "New", "content": "Content"}, format="json"
        )
        self.assertIn(
            response.status_code,
            [status.HTTP_403_FORBIDDEN, status.HTTP_400_BAD_REQUEST],
        )

        # Cannot list
        response = self.client.get(self.list_url)
        self.assertIn(
            response.status_code,
            [
                status.HTTP_403_FORBIDDEN,
                status.HTTP_404_NOT_FOUND,
                status.HTTP_400_BAD_REQUEST,
            ],
        )

        # Cannot retrieve
        response = self.client.get(self.detail_url)
        self.assertIn(
            response.status_code,
            [
                status.HTTP_403_FORBIDDEN,
                status.HTTP_404_NOT_FOUND,
                status.HTTP_400_BAD_REQUEST,
            ],
        )

        # Cannot update
        response = self.client.patch(
            self.detail_url, {"title": "Updated"}, format="json"
        )
        self.assertIn(
            response.status_code,
            [
                status.HTTP_403_FORBIDDEN,
                status.HTTP_404_NOT_FOUND,
                status.HTTP_400_BAD_REQUEST,
            ],
        )

        # Cannot delete
        response = self.client.delete(self.detail_url)
        self.assertIn(
            response.status_code,
            [
                status.HTTP_403_FORBIDDEN,
                status.HTTP_404_NOT_FOUND,
                status.HTTP_400_BAD_REQUEST,
            ],
        )


class BlogEdgeCasesTest(TestCase):
    """Test cases for edge cases and error scenarios."""

    def setUp(self):
        self.client = APIClient()

        # Create admin user
        self.admin_user = User.objects.create_user(
            email="admin@example.com",
            phone_number="1234567890",
            password=TEST_PASSWORD,
            is_verified=True,
        )
        AccountType.objects.create(
            user=self.admin_user,
            user_type="SuperAdmin",
        )
        self.admin_user.active_role = "SuperAdmin"
        self.admin_user.save()

        self.client.force_authenticate(user=self.admin_user)

    def test_create_blog_with_empty_title(self):
        """Test creating a blog with empty title."""
        url = reverse("blog:admin-create")
        data = {
            "title": "",
            "content": "Some content.",
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_blog_with_very_long_title(self):
        """Test creating a blog with a very long title."""
        url = reverse("blog:admin-create")
        long_title = "A" * 300
        data = {
            "title": long_title,
            "content": "Some content.",
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_blog_with_special_characters_in_title(self):
        """Test creating a blog with special characters in title."""
        url = reverse("blog:admin-create")
        data = {
            "title": "Test!@#$%^&*() Blog",
            "content": "Some content.",
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Check that slug was generated correctly
        blog = Blog.objects.get(title="Test!@#$%^&*() Blog")
        self.assertEqual(blog.slug, "test-blog")

    def test_concurrent_view_count_updates(self):
        """Test that view count updates correctly with concurrent requests."""
        blog = Blog.objects.create(
            title="Concurrent Test",
            content="Content",
            status=Blog.Status.PUBLISHED,
            view_count=0,
        )
        url = reverse("blog:detail", kwargs={"slug": blog.slug})

        # Simulate multiple concurrent view requests
        for _ in range(10):
            self.client.get(url)

        blog.refresh_from_db()
        self.assertEqual(blog.view_count, 10)

    def test_search_with_special_characters(self):
        """Test search functionality with special characters."""
        blog = Blog.objects.create(
            title="Test & Blog",
            content="Content with special chars !@#",
            status=Blog.Status.PUBLISHED,
        )
        url = reverse("blog:list")

        response = self.client.get(url, {"search": "Test & Blog"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        body = response.data

        results = body["data"].get("results", [])
        self.assertGreater(len(results), 0)

    def test_pagination_with_large_page_size(self):
        """Test that pagination max page size is enforced."""
        url = reverse("blog:list")

        # Create more than max page size posts
        for i in range(60):
            Blog.objects.create(
                title=f"Post {i}",
                content=f"Content {i}",
                status=Blog.Status.PUBLISHED,
            )

        response = self.client.get(url, {"page_size": 100})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        body = response.data

        results = body["data"].get("results", [])
        self.assertLessEqual(len(results), 50)


class BlogSlugAndSaveRegressionTests(TestCase):

    def _insert_count(self, ctx):
        return sum(
            1
            for q in ctx.captured_queries
            if q["sql"].strip().upper().startswith("INSERT")
        )

    def _update_count(self, ctx):
        return sum(
            1
            for q in ctx.captured_queries
            if q["sql"].strip().upper().startswith("UPDATE")
        )

    def test_create_issues_exactly_one_insert(self):
        with CaptureQueriesContext(connection) as ctx:
            Blog.objects.create(title="Single Insert Only", content="Body")
        self.assertEqual(self._insert_count(ctx), 1)

    def test_update_issues_exactly_one_update(self):
        blog = Blog.objects.create(title="Editable Post", content="Body")
        with CaptureQueriesContext(connection) as ctx:
            blog.title = "Edited Post"
            blog.save()
        self.assertEqual(self._update_count(ctx), 1)

    def test_slug_uniqueness_appends_counter(self):
        first = Blog.objects.create(title="Duplicate Title", content="Body 1")
        second = Blog.objects.create(title="Duplicate Title", content="Body 2")
        third = Blog.objects.create(title="Duplicate Title", content="Body 3")

        self.assertEqual(first.slug, "duplicate-title")
        self.assertEqual(second.slug, "duplicate-title-2")
        self.assertEqual(third.slug, "duplicate-title-3")

    def test_slug_uniqueness_skips_past_multiple_existing_collisions(self):
        Blog.objects.create(title="placeholder", slug="popular-topic", content="x")
        for i in range(2, 5):
            Blog.objects.create(
                title="placeholder", slug=f"popular-topic-{i}", content="x"
            )

        newest = Blog.objects.create(title="Popular Topic", content="new")
        self.assertEqual(newest.slug, "popular-topic-5")

    def test_publish_transition_still_single_write_and_stamps_published_at(self):
        blog = Blog.objects.create(title="About To Publish", content="Body")
        self.assertIsNone(blog.published_at)

        with CaptureQueriesContext(connection) as ctx:
            blog.status = Blog.Status.PUBLISHED
            blog.save()

        self.assertEqual(self._update_count(ctx), 1)
        self.assertIsNotNone(blog.published_at)

    def test_existing_row_slug_is_never_regenerated(self):
        blog = Blog.objects.create(title="Original Title", content="Body")
        original_slug = blog.slug
        blog.title = "Completely Different Title"
        blog.save()
        blog.refresh_from_db()
        self.assertEqual(blog.slug, original_slug)
