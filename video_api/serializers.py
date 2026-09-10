from decimal import Decimal, InvalidOperation
from typing import Optional


TASK_FIELDS = (
    "id",
    "model",
    "status",
    "created_at",
    "updated_at",
    "resolution",
    "duration",
    "ratio",
    "task_type",
    "modality",
)
CONTENT_FIELDS = ("url", "prompt")
TASK_ERROR_FIELDS = ("code", "message")
OAI_ERROR_FIELDS = ("type", "message", "http_code")
VIDEO_TASK_TYPES = ("generation", "regeneration")
VIDEO_PRICES_PER_SECOND = {
    "2K": Decimal("0.80"),
    "768P": Decimal("0.50"),
}
FREE_IMAGE_COUNT = 5
IMAGE_PRICE = Decimal("0.20")
FAST_MODEL = "MiniMax-H3-Fast"
FAST_RESOLUTION = "480P"
FAST_SECOND_PRICE = Decimal("0.30")
MAX_MODEL = "MiniMax-H3-Max"
MAX_VIDEO_PRICES_PER_SECOND = {
    "480P": Decimal("0.33"),
    "768P": Decimal("0.50"),
}
REGENERATION_SECOND_PRICE = Decimal("0.30")
REGENERATION_IMAGE_PRICE = Decimal("0.15")
CONTEXT_IR_PROMPT_TOKEN_PRICE = Decimal("5.80") / Decimal("1000000")
CONTEXT_IR_COMPLETION_TOKEN_PRICE = Decimal("23.00") / Decimal("1000000")
DISCOUNT_RATE = Decimal("0.8")
VIDEO_BILLING_QUANTUM = Decimal("0.01")
CONTEXT_IR_BILLING_QUANTUM = Decimal("0.000001")


def rebuild_response(payload: object) -> dict:
    if not isinstance(payload, dict):
        return {}
    if "task" in payload:
        task = payload.get("task")
        return {"task": rebuild_task(task) if isinstance(task, dict) else task}
    return rebuild_oai_error(payload)


def rebuild_task(source: dict) -> dict:
    result = _pick(source, TASK_FIELDS)
    if "error" in source:
        result["error"] = _pick_object(source["error"], TASK_ERROR_FIELDS)
    if "content" in source:
        result["content"] = _pick_object(source["content"], CONTENT_FIELDS)
    source_usage = source.get("usage")
    task_type = source.get("task_type")
    is_video_task = task_type in VIDEO_TASK_TYPES
    if is_video_task and isinstance(source_usage, dict):
        result["usage"] = dict(source_usage)
        if source.get("status") == "succeeded":
            billing = calculate_pre_discount_billing(source, result["usage"])
            if billing is not None:
                result["usage"]["pre_discount_billing"] = billing
                result["usage"]["after_discount_billing"] = (
                    calculate_after_discount_billing(billing, VIDEO_BILLING_QUANTUM)
                )
    elif (
        task_type == "h3_context_ir"
        and source.get("status") == "succeeded"
        and isinstance(source_usage, dict)
    ):
        result["usage"] = dict(source_usage)
        billing = calculate_context_ir_billing(result["usage"])
        if billing is not None:
            result["usage"]["pre_discount_billing"] = billing
            result["usage"]["after_discount_billing"] = (
                calculate_after_discount_billing(
                    billing,
                    CONTEXT_IR_BILLING_QUANTUM,
                )
            )
    return result


def calculate_after_discount_billing(billing: float, quantum: Decimal) -> float:
    amount = Decimal(str(billing)) * DISCOUNT_RATE
    return float(amount.quantize(quantum))


def calculate_pre_discount_billing(task: dict, usage: dict) -> Optional[float]:
    """按任务类型计算视频任务折扣前费用，单位为人民币元。"""
    model = task.get("model")
    if model == FAST_MODEL:
        if task.get("task_type") != "generation" or task.get("resolution") != FAST_RESOLUTION:
            return None
        return calculate_fast_billing(usage)

    if model == MAX_MODEL:
        if task.get("task_type") not in VIDEO_TASK_TYPES:
            return None
        price_per_second = MAX_VIDEO_PRICES_PER_SECOND.get(task.get("resolution"))
        if price_per_second is None:
            return None
        return calculate_max_billing(usage, price_per_second)

    if model != "MiniMax-H3":
        return None
    if task.get("task_type") == "regeneration":
        return calculate_regeneration_billing(usage)
    if task.get("task_type") != "generation":
        return None

    resolution = task.get("resolution")
    price_per_second = VIDEO_PRICES_PER_SECOND.get(resolution)
    if price_per_second is None:
        return None

    try:
        total_seconds = Decimal(str(usage.get("total_seconds", 0)))
        input_image_count = int(usage.get("input_image_count", 0))
    except (InvalidOperation, TypeError, ValueError):
        return None

    if total_seconds < 0 or input_image_count < 0:
        return None

    billable_image_count = max(input_image_count - FREE_IMAGE_COUNT, 0)
    amount = (
        total_seconds * price_per_second
        + Decimal(billable_image_count) * IMAGE_PRICE
    )
    return float(amount.quantize(Decimal("0.01")))


def calculate_fast_billing(usage: dict) -> Optional[float]:
    """计算 MiniMax-H3-Fast（480P）视频任务费用。"""
    try:
        input_seconds = Decimal(str(usage.get("input_seconds", 0)))
        output_seconds = Decimal(str(usage.get("output_seconds", 0)))
        input_image_count = int(usage.get("input_image_count", 0))
    except (InvalidOperation, TypeError, ValueError):
        return None

    if input_seconds < 0 or output_seconds < 0 or input_image_count < 0:
        return None

    billable_image_count = max(input_image_count - FREE_IMAGE_COUNT, 0)
    amount = (
        (input_seconds + output_seconds) * FAST_SECOND_PRICE
        + Decimal(billable_image_count) * IMAGE_PRICE
    )
    return float(amount.quantize(Decimal("0.01")))


def calculate_max_billing(usage: dict, price_per_second: Decimal) -> Optional[float]:
    """计算 MiniMax-H3-Max 视频任务费用。"""
    try:
        input_seconds = Decimal(str(usage.get("input_seconds", 0)))
        output_seconds = Decimal(str(usage.get("output_seconds", 0)))
        input_image_count = int(usage.get("input_image_count", 0))
    except (InvalidOperation, TypeError, ValueError):
        return None

    if input_seconds < 0 or output_seconds < 0 or input_image_count < 0:
        return None

    billable_image_count = max(input_image_count - FREE_IMAGE_COUNT, 0)
    amount = (
        (input_seconds + output_seconds) * price_per_second
        + Decimal(billable_image_count) * IMAGE_PRICE
    )
    return float(amount.quantize(Decimal("0.01")))


def calculate_regeneration_billing(usage: dict) -> Optional[float]:
    try:
        input_seconds = Decimal(str(usage.get("input_seconds", 0)))
        output_seconds = Decimal(str(usage.get("output_seconds", 0)))
        input_image_count = int(usage.get("input_image_count", 0))
    except (InvalidOperation, TypeError, ValueError):
        return None

    if input_seconds < 0 or output_seconds < 0 or input_image_count < 0:
        return None

    billable_image_count = max(input_image_count - FREE_IMAGE_COUNT, 0)
    amount = (
        (input_seconds + output_seconds) * REGENERATION_SECOND_PRICE
        + Decimal(billable_image_count) * REGENERATION_IMAGE_PRICE
    )
    return float(amount.quantize(Decimal("0.01")))


def calculate_context_ir_billing(usage: dict) -> Optional[float]:
    try:
        prompt_tokens = Decimal(str(usage["prompt_tokens"]))
        completion_tokens = Decimal(str(usage["completion_tokens"]))
    except (InvalidOperation, KeyError, TypeError, ValueError):
        return None

    if prompt_tokens < 0 or completion_tokens < 0:
        return None

    amount = (
        prompt_tokens * CONTEXT_IR_PROMPT_TOKEN_PRICE
        + completion_tokens * CONTEXT_IR_COMPLETION_TOKEN_PRICE
    )
    return float(amount.quantize(Decimal("0.000001")))


def rebuild_oai_error(source: dict) -> dict:
    result = {}
    if "type" in source:
        result["type"] = source["type"]
    if "error" in source:
        result["error"] = _pick_object(source["error"], OAI_ERROR_FIELDS)
    if "request_id" in source:
        result["request_id"] = source["request_id"]
    return result


def _pick(source: dict, fields: tuple[str, ...]) -> dict:
    return {field: source[field] for field in fields if field in source}


def _pick_object(value: object, fields: tuple[str, ...]) -> object:
    return _pick(value, fields) if isinstance(value, dict) else value
