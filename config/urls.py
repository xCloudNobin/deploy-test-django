from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from config.health import health_live, health_ready

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("health/live", health_live, name="health-live"),
    path("health/ready", health_ready, name="health-ready"),
    path("", include("taskboard.urls")),
]
