from prometheus_client import Counter, Histogram, Gauge
from app.core.config import settings


# Prometheus metrics

active_conversations = Gauge(
    "active_conversations_total",
    "Number of active conversations"
)

prompt_tokens = Counter(
    "prompt_tokens_total",
    "Total prompt tokens sent",
    ["provider", "model"]
)


chat_requests_total = Counter(
    "chat_requests_total",
    "Total chat requests",
    ["provider", "model"]
)

chat_latency_seconds = Histogram(
    "chat_latency_seconds", 
    "Chat request latency in seconds",
    ["provider"]
)

tokens_per_second = Gauge(
    "tokens_per_second",
    "Token generation speed",
    ["model"]
)


from langfuse import get_client

def record_metrics(provider: str, model: str, elapsed: float,
                   token_count: int, messages: list, full_response: str,
                   conversation_id: str):
    tps = token_count / elapsed if elapsed > 0 else 0

    # Prometheus
    chat_requests_total.labels(provider=provider, model=model).inc()
    chat_latency_seconds.labels(provider=provider).observe(elapsed)
    tokens_per_second.labels(model=model).set(tps)
    prompt_tokens.labels(provider=provider, model=model).inc(len(messages))

    # Langfuse v4 - correct API
    langfuse = get_client()
    with langfuse.start_as_current_observation(
        as_type="generation",
        name="chat_completion",
        model=model,
    ) as observation:
        observation.update(
            input={"messages": messages},
            output={"response": full_response},
            metadata={
                "provider": provider,
                "conversation_id": conversation_id,
                "latency_seconds": elapsed,
                "tokens_per_second": tps,
                "total_tokens": token_count
            }
        )