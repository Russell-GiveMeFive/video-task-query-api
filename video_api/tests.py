from unittest.mock import patch

from django.test import SimpleTestCase

from .services import UpstreamResponse


class QueryVideoGenerationTests(SimpleTestCase):
    path = "/v2/query/video_generation/424010985738629"

    def test_requires_bearer_auth(self):
        response = self.client.get(self.path)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["http_code"], "401")
        self.assertNotIn(b'": ', response.content)
        self.assertNotIn(b'", "', response.content)

    @patch("video_api.views.query_video_task")
    def test_rebuilds_success_response_and_drops_unknown_fields(self, query):
        query.return_value = UpstreamResponse(
            200,
            {
                "task": {
                    "id": "424010985738629",
                    "model": "MiniMax-H3",
                    "status": "succeeded",
                    "created_at": 1785125529,
                    "updated_at": 1785125946,
                    "content": {"url": "https://example.com/output.mp4", "unknown": True},
                    "resolution": "2K",
                    "duration": 5,
                    "usage": {
                        "total_seconds": 5,
                        "input_seconds": 0,
                        "output_seconds": 5,
                        "input_image_count": 0,
                    },
                    "ratio": "16:9",
                    "task_type": "generation",
                    "modality": "video",
                    "unknown": "drop me",
                }
            },
        )

        response = self.client.get(self.path, HTTP_AUTHORIZATION="Bearer test-key")

        self.assertEqual(response.status_code, 200)
        task = response.json()["task"]
        self.assertEqual(task["content"], {"url": "https://example.com/output.mp4"})
        self.assertEqual(task["usage"]["pre_discount_billing"], 4.0)
        self.assertNotIn("unknown", task)
        self.assertNotIn(b'": ', response.content)
        self.assertNotIn(b'", "', response.content)
        query.assert_called_once_with("424010985738629", "Bearer test-key")

    @patch("video_api.views.query_video_task")
    def test_bills_768p_seconds_and_only_images_over_five(self, query):
        query.return_value = UpstreamResponse(
            200,
            {
                "task": {
                    "id": "task-768p",
                    "model": "MiniMax-H3",
                    "status": "succeeded",
                    "resolution": "768P",
                    "duration": 99,
                    "usage": {"total_seconds": 10, "input_image_count": 8},
                    "task_type": "generation",
                    "modality": "video",
                }
            },
        )

        response = self.client.get(self.path, HTTP_AUTHORIZATION="Bearer test-key")

        # 10 秒 × 0.50 元 + (8 - 5) 张 × 0.20 元 = 5.60 元；duration 不参与计算。
        self.assertEqual(response.json()["task"]["usage"]["pre_discount_billing"], 5.6)

    @patch("video_api.views.query_video_task")
    def test_succeeded_generation_without_modality_returns_full_usage(self, query):
        query.return_value = UpstreamResponse(
            200,
            {
                "task": {
                    "id": "generation-without-modality",
                    "model": "MiniMax-H3",
                    "status": "succeeded",
                    "resolution": "2K",
                    "duration": 12,
                    "usage": {
                        "total_seconds": 12,
                        "input_seconds": 0,
                        "output_seconds": 12,
                        "input_image_count": 0,
                    },
                    "task_type": "generation",
                }
            },
        )

        response = self.client.get(self.path, HTTP_AUTHORIZATION="Bearer test-key")

        self.assertEqual(
            response.json()["task"]["usage"],
            {
                "total_seconds": 12,
                "input_seconds": 0,
                "output_seconds": 12,
                "input_image_count": 0,
                "pre_discount_billing": 9.6,
            },
        )

    @patch("video_api.views.query_video_task")
    def test_bills_succeeded_h3_context_ir_tokens(self, query):
        query.return_value = UpstreamResponse(
            200,
            {
                "task": {
                    "id": "context-ir",
                    "model": "MiniMax-H3",
                    "status": "succeeded",
                    "usage": {
                        "total_tokens": 1000000,
                        "prompt_tokens": 600000,
                        "completion_tokens": 400000,
                    },
                    "task_type": "h3_context_ir",
                    "modality": "text",
                }
            },
        )

        response = self.client.get(self.path, HTTP_AUTHORIZATION="Bearer test-key")

        self.assertEqual(
            response.json()["task"]["usage"],
            {
                "total_tokens": 1000000,
                "prompt_tokens": 600000,
                "completion_tokens": 400000,
                "pre_discount_billing": 12.68,
            },
        )

    @patch("video_api.views.query_video_task")
    def test_bills_regeneration_output_input_video_and_extra_images(self, query):
        query.return_value = UpstreamResponse(
            200,
            {
                "task": {
                    "id": "regeneration-task",
                    "model": "MiniMax-H3",
                    "status": "succeeded",
                    "resolution": "2K",
                    "usage": {
                        "total_seconds": 18,
                        "input_seconds": 8,
                        "output_seconds": 10,
                        "input_image_count": 7,
                    },
                    "task_type": "regeneration",
                }
            },
        )

        response = self.client.get(self.path, HTTP_AUTHORIZATION="Bearer test-key")

        # 输出 10 秒 × 0.30 + 输入视频 8 秒 × 0.30 + 超出免费额度 2 张 × 0.15 = 5.70 元。
        self.assertEqual(
            response.json()["task"]["usage"]["pre_discount_billing"],
            5.7,
        )

    @patch("video_api.views.query_video_task")
    def test_non_succeeded_video_only_returns_input_image_count(self, query):
        query.return_value = UpstreamResponse(
            200,
            {
                "task": {
                    "id": "failed-video",
                    "model": "MiniMax-H3",
                    "status": "failed",
                    "error": {"code": "1026", "message": "sensitive content"},
                    "resolution": "2K",
                    "duration": 5,
                    "usage": {
                        "total_seconds": 0,
                        "input_seconds": 0,
                        "output_seconds": 0,
                        "input_image_count": 0,
                    },
                    "task_type": "generation",
                    "modality": "video",
                }
            },
        )

        response = self.client.get(self.path, HTTP_AUTHORIZATION="Bearer test-key")

        self.assertEqual(
            response.json()["task"]["usage"],
            {"input_image_count": 0},
        )

    @patch("video_api.views.query_video_task")
    def test_running_video_only_returns_input_image_count(self, query):
        query.return_value = UpstreamResponse(
            200,
            {
                "task": {
                    "id": "running-video",
                    "model": "MiniMax-H3",
                    "status": "running",
                    "resolution": "768P",
                    "usage": {"total_seconds": 3, "input_image_count": 1},
                    "task_type": "generation",
                    "modality": "video",
                }
            },
        )

        response = self.client.get(self.path, HTTP_AUTHORIZATION="Bearer test-key")

        self.assertEqual(
            response.json()["task"]["usage"],
            {"input_image_count": 1},
        )

    @patch("video_api.views.query_video_task")
    def test_rebuilds_upstream_error_and_preserves_status(self, query):
        query.return_value = UpstreamResponse(
            429,
            {
                "type": "error",
                "error": {
                    "type": "rate_limit_error",
                    "message": "rate limit, please retry later (1002)",
                    "http_code": "429",
                    "extra": "drop me",
                },
                "request_id": "request-1",
                "extra": "drop me",
            },
        )

        response = self.client.get(self.path, HTTP_AUTHORIZATION="Bearer test-key")

        self.assertEqual(response.status_code, 429)
        self.assertEqual(
            response.json(),
            {
                "type": "error",
                "error": {
                    "type": "rate_limit_error",
                    "message": "rate limit, please retry later (1002)",
                    "http_code": "429",
                },
                "request_id": "request-1",
            },
        )
