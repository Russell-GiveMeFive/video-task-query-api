from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .serializers import rebuild_response
from .services import UpstreamUnavailable, query_video_task


COMPACT_JSON_PARAMS = {"separators": (",", ":")}


def _error(status: int, error_type: str, message: str) -> JsonResponse:
    return JsonResponse(
        {
            "type": "error",
            "error": {
                "type": error_type,
                "message": message,
                "http_code": str(status),
            },
        },
        status=status,
        json_dumps_params=COMPACT_JSON_PARAMS,
    )


@require_GET
def query_video_generation(request, task_id: str) -> JsonResponse:
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer ") or not authorization[7:].strip():
        return _error(
            401,
            "authorized_error",
            "login fail: Please carry the API secret key in the 'Authorization' field of the request header (1004)",
        )

    try:
        upstream = query_video_task(task_id, authorization)
    except UpstreamUnavailable:
        return _error(500, "server_error", "upstream MiniMax API unavailable (1000)")

    return JsonResponse(
        rebuild_response(upstream.data),
        status=upstream.status,
        safe=False,
        json_dumps_params=COMPACT_JSON_PARAMS,
    )
