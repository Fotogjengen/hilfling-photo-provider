"""
URL configuration for hilfling_image_proxy project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
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

from django.conf import settings
from django.conf.urls.static import static
from django.urls import re_path, path
from .shared import views as shared_views

urlpatterns = [
    path("photos/upload", shared_views.photo_upload_view, name="photo-upload"),
]

if settings.DEBUG and hasattr(settings, "MEDIA_URL"):
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Enable the proxy if needed
# Extended description in /dev/views.py
if getattr(settings, "ENABLE_PROXY", False):
    from .dev import views as dev_views

    urlpatterns.extend([
        path("auth/login", dev_views.login_view, name="login"),
        re_path(r"^(?P<path>.*)$", dev_views.proxy_view, name="proxy"),
    ])