from unittest.mock import patch

from django.test import SimpleTestCase

from .services import UpstreamResponse, create_video_task


class CreateVideoTaskServiceTests(SimpleTestCase):
    @patch("video_api.services.urlopen")
    def test_posts_raw_json_to_documented_upstream_url(self, urlopen):
        response = urlopen.return_value.__enter__.return_value
        response.status = 200
        response.read.return_value = b'{"task_id":"424010985738629"}'
        body = b'{"model":"MiniMax-H3"}'

        result = create_video_task(body, "Bearer test-key")

        self.assertEqual(result.data, {"task_id": "424010985738629"})
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.minimaxi.com/v2/video_generation")
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.data, body)
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key")
        self.assertEqual(request.get_header("Content-type"), "application/json")


class CreateVideoGenerationTests(SimpleTestCase):
    path = "/v2/video_generation"

    def test_requires_bearer_auth(self):
        response = self.client.post(
            self.path,
            data={"model": "MiniMax-H3"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["http_code"], "401")

    def test_requires_application_json(self):
        response = self.client.post(
            self.path,
            data="not-json",
            content_type="text/plain",
            HTTP_AUTHORIZATION="Bearer test-key",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["type"], "bad_request_error")

    @patch("video_api.views.create_video_task")
    def test_forwards_request_body_and_returns_documented_response(self, create):
        create.return_value = UpstreamResponse(200, {"task_id": "424010985738629"})
        body = (
            b'{"model":"MiniMax-H3","content":[{"type":"text",'
            b'"text":"a boy plays basketball by the sea"}],"resolution":"2K",'
            b'"duration":5,"ratio":"16:9"}'
        )

        response = self.client.post(
            self.path,
            data=body,
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer test-key",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"task_id": "424010985738629"})
        self.assertNotIn(b'": ', response.content)
        create.assert_called_once_with(body, "Bearer test-key")

    @patch("video_api.views.create_video_task")
    def test_preserves_upstream_error_status_and_body(self, create):
        error = {
            "type": "error",
            "error": {
                "type": "rate_limit_error",
                "message": "rate limit, please retry later (1002)",
                "http_code": "429",
            },
            "request_id": "request-1",
        }
        create.return_value = UpstreamResponse(429, error)

        response = self.client.post(
            self.path,
            data=b"{}",
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer test-key",
        )

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json(), error)


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
        self.assertEqual(response.json()["task"]["usage"]["after_discount_billing"], 4.48)

    @patch("video_api.views.query_video_task")
    def test_bills_h3_fast_480p_input_output_seconds_and_reference_images(self, query):
        query.return_value = UpstreamResponse(
            200,
            {
                "task": {
                    "id": "task-fast",
                    "model": "MiniMax-H3-Fast",
                    "status": "succeeded",
                    "resolution": "480P",
                    "usage": {
                        "total_seconds": 99,
                        "input_seconds": 8,
                        "output_seconds": 10,
                        "input_image_count": 7,
                    },
                    "task_type": "generation",
                }
            },
        )

        response = self.client.get(self.path, HTTP_AUTHORIZATION="Bearer test-key")

        # 输入 8 秒 + 输出 10 秒均按 0.30 元/秒，超出免费额度 2 张图按 0.20 元/张。
        self.assertEqual(response.json()["task"]["usage"]["pre_discount_billing"], 5.8)
        self.assertEqual(response.json()["task"]["usage"]["after_discount_billing"], 4.64)

    @patch("video_api.views.query_video_task")
    def test_h3_fast_only_bills_480p(self, query):
        query.return_value = UpstreamResponse(
            200,
            {
                "task": {
                    "id": "task-fast-768p",
                    "model": "MiniMax-H3-Fast",
                    "status": "succeeded",
                    "resolution": "768P",
                    "usage": {"input_seconds": 1, "output_seconds": 2, "input_image_count": 6},
                    "task_type": "generation",
                }
            },
        )

        response = self.client.get(self.path, HTTP_AUTHORIZATION="Bearer test-key")

        self.assertNotIn("pre_discount_billing", response.json()["task"]["usage"])

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
                "after_discount_billing": 7.68,
            },
        )

    @patch("video_api.views.query_video_task")
    def test_preserves_all_upstream_usage_fields_and_adds_billing(self, query):
        query.return_value = UpstreamResponse(
            200,
            {
                "task": {
                    "id": "431702145348008",
                    "model": "MiniMax-H3",
                    "status": "succeeded",
                    "created_at": 1786950279,
                    "updated_at": 1786950681,
                    "content": {"url": "https://example.com/output_aigc.mp4"},
                    "resolution": "2K",
                    "duration": 5,
                    "usage": {
                        "total_seconds": 11,
                        "input_seconds": 6,
                        "output_seconds": 5,
                        "input_image_count": 0,
                        "total_tokens": 573578,
                        "prompt_tokens": 313188,
                        "completion_tokens": 260390,
                        "input_audio_seconds": 9,
                    },
                    "ratio": "adaptive",
                    "task_type": "generation",
                }
            },
        )

        response = self.client.get(self.path, HTTP_AUTHORIZATION="Bearer test-key")

        self.assertEqual(
            response.json()["task"]["usage"],
            {
                "total_seconds": 11,
                "input_seconds": 6,
                "output_seconds": 5,
                "input_image_count": 0,
                "total_tokens": 573578,
                "prompt_tokens": 313188,
                "completion_tokens": 260390,
                "input_audio_seconds": 9,
                "pre_discount_billing": 8.8,
                "after_discount_billing": 7.04,
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
                "after_discount_billing": 10.144,
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
        self.assertEqual(
            response.json()["task"]["usage"]["after_discount_billing"],
            4.56,
        )

    @patch("video_api.views.query_video_task")
    def test_non_succeeded_video_preserves_full_usage(self, query):
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
            {
                "total_seconds": 0,
                "input_seconds": 0,
                "output_seconds": 0,
                "input_image_count": 0,
            },
        )

    @patch("video_api.views.query_video_task")
    def test_running_video_preserves_full_usage(self, query):
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
            {"total_seconds": 3, "input_image_count": 1},
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
