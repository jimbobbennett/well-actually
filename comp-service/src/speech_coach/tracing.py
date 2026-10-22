import json
import os

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter
from opentelemetry.trace import StatusCode


def decision_span(span):
    """Copy a completed classifier span with validated, typed dashboard fields."""
    attributes = span.attributes or {}
    if attributes.get("openinference.span.kind") != "LLM" or span.status.status_code == StatusCode.ERROR:
        return span

    # OpenInference exposes the first assistant message separately from output.value.
    content = attributes.get("llm.output_messages.0.message.content")
    finish_reason = attributes.get("llm.finish_reason")
    if finish_reason is None:
        # Older instrumentors include the finish reason only in the response envelope.
        try:
            response = json.loads(attributes.get("output.value", ""))
            choice = response["choices"][0]
            finish_reason = choice["finish_reason"]
            content = choice["message"]["content"]
        except (ValueError, TypeError, KeyError, IndexError):
            return span
    if finish_reason != "stop" or not isinstance(content, str):
        return span

    from .llm import Decision

    try:
        decision = Decision.parse(content)
    except (ValueError, TypeError):
        # Match application validation: invalid/incomplete decisions are not metrics.
        return span
    return ReadableSpan(
        name=span.name,
        context=span.context,
        parent=span.parent,
        resource=span.resource,
        attributes={
            **attributes,
            "output.condescending": decision.condescending,
            "output.reexplaining": decision.reexplaining,
            "output.confidence": float(decision.confidence),
        },
        events=span.events,
        links=span.links,
        kind=span.kind,
        status=span.status,
        start_time=span.start_time,
        end_time=span.end_time,
        instrumentation_scope=span.instrumentation_scope,
    )


class DecisionSpanExporter(SpanExporter):
    """Enrich the original LLM span without emitting a duplicate span."""

    def __init__(self, exporter):
        self.exporter = exporter

    def export(self, spans):
        return self.exporter.export(tuple(decision_span(span) for span in spans))

    def shutdown(self):
        return self.exporter.shutdown()

    def force_flush(self, timeout_millis=30000):
        return self.exporter.force_flush(timeout_millis)


def setup_tracing(testing_mode: bool = False):
    """Enable Arize only when all tracing settings are present."""
    names = ("ARIZE_SPACE_ID", "ARIZE_API_KEY", "ARIZE_PROJECT_NAME")
    missing = [name for name in names if not os.getenv(name)]
    if missing:
        return None

    from arize.otel import (
        ARIZE_PROJECT_NAME_ATTR, BatchSpanProcessor, GRPCSpanExporter,
        PROJECT_NAME, Resource, TracerProvider,
    )
    from openinference.instrumentation.openai import OpenAIInstrumentor
    from opentelemetry import trace

    project_name = "speech-coach-test" if testing_mode else os.environ["ARIZE_PROJECT_NAME"]
    provider = TracerProvider(
        space_id=os.environ["ARIZE_SPACE_ID"],
        api_key=os.environ["ARIZE_API_KEY"],
        project_name=project_name,
        resource=Resource.create({
            PROJECT_NAME: project_name,
            ARIZE_PROJECT_NAME_ATTR: project_name,
            "arize.project.type": "application",
        }),
        verbose=False,
    )
    # Adding a processor replaces this provider's default exporter through Arize's
    # public API, so only the enriched copy of each span is sent.
    provider.add_span_processor(BatchSpanProcessor(span_exporter=DecisionSpanExporter(
        GRPCSpanExporter(
            space_id=os.environ["ARIZE_SPACE_ID"], api_key=os.environ["ARIZE_API_KEY"],
            headers={"x-project-name": project_name},
        )
    )))
    trace.set_tracer_provider(provider)
    OpenAIInstrumentor().instrument(tracer_provider=provider)
    return provider
