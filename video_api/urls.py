from django.urls import path

from .views import create_video_generation, query_video_generation


urlpatterns = [
    path(
        "v2/video_generation",
        create_video_generation,
        name="video-generation-v2-create",
    ),
    path(
        "v2/query/video_generation/<str:task_id>",
        query_video_generation,
        name="video-generation-v2-query",
    ),
]
