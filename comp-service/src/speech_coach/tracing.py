import os


def setup_tracing(testing_mode: bool = False):
    """Enable Arize only when all tracing settings are present."""
    names = ("ARIZE_SPACE_ID", "ARIZE_API_KEY", "ARIZE_PROJECT_NAME")
    if not all(os.getenv(name) for name in names):
        return None

    from arize.otel import register
    from openinference.instrumentation.openai import OpenAIInstrumentor

    provider = register(
        space_id=os.environ["ARIZE_SPACE_ID"],
        api_key=os.environ["ARIZE_API_KEY"],
        project_name="speech-coach-test" if testing_mode else os.environ["ARIZE_PROJECT_NAME"],
    )
    OpenAIInstrumentor().instrument(tracer_provider=provider)
    return provider
