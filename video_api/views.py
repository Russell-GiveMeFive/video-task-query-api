from typing import Optional

from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from .serializers import rebuild_response
from .services import UpstreamUnavailable, create_video_task, query_video_task


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


def _authorization_error() -> JsonResponse:
    return _error(
        401,
        "authorized_error",
        "login fail: Please carry the API secret key in the 'Authorization' field of the request header (1004)",
    )


def _get_bearer_authorization(request) -> Optional[str]:
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer ") or not authorization[7:].strip():
        return None
    return authorization


@require_POST
def create_video_generation(request) -> JsonResponse:
    authorization = _get_bearer_authorization(request)
    if authorization is None:
        return _authorization_error()

    if request.content_type != "application/json":
        return _error(
            400,
            "bad_request_error",
            "invalid params, Content-Type must be application/json (2013)",
        )

    try:
        upstream = create_video_task(request.body, authorization)
    except UpstreamUnavailable:
        return _error(500, "server_error", "upstream MiniMax API unavailable (1000)")

    return JsonResponse(
        upstream.data,
        status=upstream.status,
        safe=False,
        json_dumps_params=COMPACT_JSON_PARAMS,
    )


@require_GET
def query_video_generation(request, task_id: str) -> JsonResponse:
    authorization = _get_bearer_authorization(request)
    if authorization is None:
        return _authorization_error()

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
