"""
URL configuration for picadailys project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include, reverse_lazy
from django.views.generic import TemplateView

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)


urlpatterns = [
    path("admin/", admin.site.urls),
    # OpenAPI schema
    path("v1/schema/", SpectacularAPIView.as_view(), name="schema"),
    # Scalar — primary docs
    path(
        "v1/scalar/",
        TemplateView.as_view(
            template_name="scalar.html",
            extra_context={"schema_url": reverse_lazy("schema")},
        ),
        name="scalar-ui",
    ),
    # Swagger UI (served locally via sidecar)
    path("v1/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    # ReDoc fallback
    path("v1/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    # Account creation endpoint.
    path("v1/accounts/", include("accounts.urls")),
    # Partners endpoints.
    path("v1/partners/", include("partners.urls")),
    # Gamification endpoints.
    path("v1/gamification/", include("gamification.urls")),
    # Brand Adverts endpoints.
    path("v1/adverts/", include("adverts.urls")),
    # VAS endpoints.
    path("v1/vas/", include("vas.urls")),
    # FMCG endpoints.
    path("v1/fmcg/", include("fmcg.urls")),
    # User Profile and settings endpoints.
    path("v1/user_profile/", include("user_profile.urls")),
    # User Profile and settings endpoints.
    path("v1/roles/", include("roles.urls")),
    # Self service endpoints.
    path("v1/self_service/", include("self_service.urls")),
    # Providus banking endpoints.
    path("v1/banking/", include("banking.urls")),
    # Treasury (Anchor) endpoints.
    path("v1/treasury/", include("treasury.urls")),
    # Support endpoints.
    path("v1/support/", include("support.urls")),
    # Waitlist endpoints.
    path("v1/waitlist/", include("waitlist.urls")),
    # Web endpoints.
    path("v1/web/", include("web.urls")),
]
