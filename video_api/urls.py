from django.urls import path

from .views import query_video_generation


urlpatterns = [
    path(
        "v2/query/video_generation/<str:task_id>",
        query_video_generation,
        name="video-generation-v2-query",
    ),
]

