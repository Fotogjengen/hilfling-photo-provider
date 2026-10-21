from django.urls import path

from .photos import views

urlpatterns = [
    path("api/photos/upload", views.photo_upload_view, name="photo-upload"),
    path("api/user-uploads/upload", views.user_upload_view, name="user-upload"),

    # backend-only, authorised by a service token
    path("api/provider-internal/photos/relocate", views.photo_relocate_view, name="photo-relocate"),
    path("api/provider-internal/photos/delete", views.photo_delete_view, name="photo-delete"),

    # image hosting
    path("media/metadata/<path:path>", views.photo_metadata_view, name="photo-metadata"),
    path("media/<path:path>", views.serve_image_view, name="serve-image"),
]
