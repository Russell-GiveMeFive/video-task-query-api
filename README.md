# MiniMax Video Generation V2 API (Django)

用 Django 封装 MiniMax V2 视频任务创建与查询接口，接口路径、HTTP method、输入和响应结构与官方文档保持一致。

## 启动

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py runserver
```

## 调用

创建视频生成任务：

```bash
curl --request POST \
  --url http://127.0.0.1:8778/v2/video_generation \
  --header "Authorization: Bearer $MINIMAX_API_KEY" \
  --header "Content-Type: application/json" \
  --data '{
    "model": "MiniMax-H3",
    "content": [{"type": "text", "text": "一个男孩在海边打篮球"}],
    "resolution": "2K",
    "duration": 5,
    "ratio": "16:9"
  }'
```

查询视频生成任务：

```bash
curl -H "Authorization: Bearer $MINIMAX_API_KEY" \
  http://127.0.0.1:8778/v2/query/video_generation/424010985738629
```

本服务不会保存 API Key。它会把 `Authorization` 请求头透传给 MiniMax。创建接口将请求 JSON 原样转发，并原样保留上游 JSON 字段和 HTTP 状态码；查询接口会将上游 JSON 按 OpenAPI schema 拆解、白名单过滤后重新装载。

接口会完整保留上游返回的所有 `usage` 字段，包括后续新增的模态用量字段。对于成功的视频任务，`task.usage` 还会增加人民币元计价的 `pre_discount_billing`。

MiniMax-H3：

```text
视频费用 = total_seconds × 分辨率单价（2K：0.80 元/秒；768P：0.50 元/秒）
图片费用 = max(input_image_count - 5, 0) × 0.20 元/张
pre_discount_billing = 视频费用 + 图片费用
after_discount_billing = pre_discount_billing × 0.8（保留 2 位小数）
```

MiniMax-H3-Fast 仅支持 `480P` 计费：

```text
pre_discount_billing = output_seconds × 0.30
                     + input_seconds × 0.30
                     + max(input_image_count - 5, 0) × 0.20
after_discount_billing = pre_discount_billing × 0.8（保留 2 位小数）
```

H3-Context-IR：

```text
pre_discount_billing = prompt_tokens × 5.80 / 1,000,000
                     + completion_tokens × 23.00 / 1,000,000
after_discount_billing = pre_discount_billing × 0.8（保留 6 位小数）
```

视频再生成：

```text
pre_discount_billing = output_seconds × 0.30
                     + input_seconds × 0.30
                     + max(input_image_count - 5, 0) × 0.15
after_discount_billing = pre_discount_billing × 0.8（保留 2 位小数）
```

可选环境变量：

- `MINIMAX_API_BASE_URL`：默认 `https://api.minimaxi.com`
- `MINIMAX_API_TIMEOUT`：上游请求超时秒数，默认 `30`
- `DJANGO_SECRET_KEY`、`DJANGO_DEBUG`、`DJANGO_ALLOWED_HOSTS`：标准部署配置

## 测试

```bash
python manage.py test
```

## Docker

构建镜像：

```bash
docker buildx build --platform linux/amd64 --load -t minimax-video-query-api .
```

启动容器：

```bash
docker run --rm -p 8778:8778 \
  -e DJANGO_SECRET_KEY="replace-with-a-random-secret" \
  minimax-video-query-api
```

接口调用时，MiniMax API Key 仍通过请求的 `Authorization` header 传入，不需要放进镜像或容器环境变量。
