from django.urls import include, path


urlpatterns = [path("", include("video_api.urls"))]

