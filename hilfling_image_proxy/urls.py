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

from django.urls import path
from .shared import views as shared_views

urlpatterns = [
    path("api/photos/upload", shared_views.photo_upload_view, name="photo-upload"),
    path("api/photos/<str:photo_id>", shared_views.photo_delete_view, name="photo-delete"),

    #image hosting
    path("media/metadata/<path:path>", shared_views.photo_metadata_view, name="photo-metadata"),
    path("media/<path:path>", shared_views.serve_image_view, name="serve-image"),
]