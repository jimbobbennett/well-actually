import json
import unittest
from unittest.mock import patch

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Status, StatusCode

from speech_coach.tracing import DecisionSpanExporter, setup_tracing


class RoutingTests(unittest.TestCase):
    def test_live_and_testing_project_routing_reaches_exported_span(self):
        for testing_mode, expected in ((False, "configured-project"), (True, "speech-coach-test")):
            sink = InMemorySpanExporter()
            with self.subTest(testing_mode=testing_mode), patch.dict("os.environ", {
                "ARIZE_SPACE_ID": "test-space", "ARIZE_API_KEY": "test-key",
                "ARIZE_PROJECT_NAME": "configured-project",
            }, clear=True), patch("arize.otel.GRPCSpanExporter", return_value=sink) as exporter, \
                    patch("opentelemetry.trace.set_tracer_provider"), \
                    patch("openinference.instrumentation.openai.OpenAIInstrumentor"):
                provider = setup_tracing(testing_mode)
                try:
                    self.assertEqual(exporter.call_args.kwargs["headers"], {"x-project-name": expected})
                    with provider.get_tracer("routing-test").start_as_current_span("check"):
                        pass
                    self.assertTrue(provider.force_flush())
                    spans = sink.get_finished_spans()
                    self.assertEqual(len(spans), 1)
                    self.assertEqual(spans[0].resource.attributes["arize.project.name"], expected)
                    self.assertEqual(spans[0].resource.attributes["arize.project.type"], "application")
                finally:
                    provider.shutdown()


class DecisionSpanTests(unittest.TestCase):
    def setUp(self):
        self.sink = InMemorySpanExporter()
        self.provider = TracerProvider()
        self.provider.add_span_processor(SimpleSpanProcessor(DecisionSpanExporter(self.sink)))
        self.tracer = self.provider.get_tracer("verification")
        self.addCleanup(self.provider.shutdown)

    def emit(self, content, finish="stop", failed=False, kind="LLM", envelope=False):
        with self.tracer.start_as_current_span("classifier") as span:
            original_id = span.get_span_context().span_id
            span.set_attribute("openinference.span.kind", kind)
            span.set_attribute("llm.token_count.total", 42)
            if envelope:
                span.set_attribute("output.value", json.dumps({"choices": [
                    {"finish_reason": finish, "message": {"content": content}}
                ]}))
            else:
                span.set_attribute("llm.finish_reason", finish)
                span.set_attribute("llm.output_messages.0.message.content", content)
            if failed:
                span.set_status(Status(StatusCode.ERROR))
        return original_id, self.sink.get_finished_spans()[-1]

    def test_typed_fields_preserve_original_span(self):
        content = '{"condescending":true,"reexplaining":false,"confidence":0.91}'
        original_id, span = self.emit(content)
        self.assertEqual(len(self.sink.get_finished_spans()), 1)
        self.assertEqual(span.context.span_id, original_id)
        self.assertIs(span.attributes["output.condescending"], True)
        self.assertIs(span.attributes["output.reexplaining"], False)
        self.assertEqual(span.attributes["output.confidence"], 0.91)
        self.assertIs(type(span.attributes["output.confidence"]), float)
        self.assertEqual(span.attributes["llm.token_count.total"], 42)
        self.assertEqual(span.attributes["llm.output_messages.0.message.content"], content)

    def test_response_envelope_fallback(self):
        _, span = self.emit('{"condescending":false,"reexplaining":false,"confidence":1}', envelope=True)
        self.assertIs(span.attributes["output.condescending"], False)
        self.assertEqual(span.attributes["output.confidence"], 1.0)

    def test_invalid_incomplete_failed_and_non_llm_spans_are_not_enriched(self):
        valid = '{"condescending":true,"reexplaining":true,"confidence":0.91}'
        for content, options in (
            ("invalid JSON", {}),
            ('{"condescending":"true","reexplaining":false,"confidence":0.9}', {}),
            ('{"condescending":true,"reexplaining":false,"confidence":2}', {}),
            (valid, {"finish": "length"}),
            (valid, {"failed": True}),
            (valid, {"kind": "TOOL"}),
        ):
            with self.subTest(content=content, options=options):
                _, span = self.emit(content, **options)
                self.assertNotIn("output.confidence", span.attributes)


if __name__ == "__main__":
    unittest.main()
