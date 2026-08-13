import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from django.conf import settings


@dataclass(frozen=True)
class UpstreamResponse:
    status: int
    data: object


class UpstreamUnavailable(Exception):
    pass


def query_video_task(task_id: str, authorization: str) -> UpstreamResponse:
    encoded_task_id = quote(task_id, safe="")
    url = f"{settings.MINIMAX_API_BASE_URL}/v2/query/video_generation/{encoded_task_id}"
    request = Request(
        url,
        headers={"Authorization": authorization, "Accept": "application/json"},
        method="GET",
    )

    try:
        with urlopen(request, timeout=settings.MINIMAX_API_TIMEOUT) as response:
            return UpstreamResponse(response.status, _decode_json(response.read()))
    except HTTPError as exc:
        return UpstreamResponse(exc.code, _decode_json(exc.read()))
    except (URLError, TimeoutError, OSError) as exc:
        raise UpstreamUnavailable(str(exc)) from exc


def _decode_json(body: bytes) -> object:
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpstreamUnavailable("MiniMax returned a non-JSON response") from exc

