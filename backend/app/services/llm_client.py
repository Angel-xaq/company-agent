"""OpenAI 兼容 LLM 客户端封装（当前模型 deepseek-flash）。"""

from collections.abc import Generator
from typing import Any

from openai import OpenAI

from app.config import settings

_client: OpenAI | None = None


def is_configured() -> bool:
    return bool(settings.LLM_KEY.strip())


def _get_client() -> OpenAI:
    global _client
    if not is_configured():
        raise RuntimeError("未配置 LLM_KEY")
    if _client is None:
        _client = OpenAI(
            api_key=settings.LLM_KEY,
            base_url=settings.LLM_BASE_URL or None,
            timeout=settings.LLM_TIMEOUT,
        )
    return _client


def _base_kwargs(
    messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "model": settings.LLM_MODEL,
        "messages": messages,
        "temperature": settings.LLM_TEMPERATURE,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    return kwargs


def chat_completion(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    """非流式调用，保留给需要完整响应的场景。"""
    client = _get_client()
    response = client.chat.completions.create(**_base_kwargs(messages, tools))
    message = response.choices[0].message

    tool_calls: list[dict[str, Any]] = []
    for tool_call in message.tool_calls or []:
        tool_calls.append(
            {
                "id": tool_call.id,
                "type": "function",
                "function": {
                    "name": tool_call.function.name,
                    "arguments": tool_call.function.arguments,
                },
            }
        )

    usage: dict[str, Any] = {}
    if response.usage is not None:
        usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        }

    return message.content or "", tool_calls, usage


def chat_completion_stream(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> Generator[dict[str, Any], None, None]:
    """流式调用。

    事件类型：
    - {"type": "delta", "content": "..."}  文本增量
    - {"type": "done", "tool_calls": [...]} 本轮结束，聚合后的工具调用
    """
    client = _get_client()
    kwargs = _base_kwargs(messages, tools)
    kwargs["stream"] = True
    stream = client.chat.completions.create(**kwargs)

    aggregated: dict[int, dict[str, Any]] = {}

    for chunk in stream:
        choices = getattr(chunk, "choices", None) or []
        if not choices:
            continue
        delta = choices[0].delta
        if delta is None:
            continue

        content = getattr(delta, "content", None)
        if isinstance(content, str) and content:
            yield {"type": "delta", "content": content}

        for tool_call in getattr(delta, "tool_calls", None) or []:
            index = getattr(tool_call, "index", 0) or 0
            item = aggregated.setdefault(
                index,
                {
                    "id": "",
                    "type": "function",
                    "function": {"name": "", "arguments": ""},
                },
            )
            if getattr(tool_call, "id", None):
                item["id"] = tool_call.id
            function = getattr(tool_call, "function", None)
            if function is not None:
                name = getattr(function, "name", None)
                if name:
                    item["function"]["name"] += str(name)
                arguments = getattr(function, "arguments", None)
                if arguments:
                    item["function"]["arguments"] += str(arguments)

    yield {
        "type": "done",
        "tool_calls": [aggregated[index] for index in sorted(aggregated)],
    }
