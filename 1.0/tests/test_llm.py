from types import SimpleNamespace

from nju_agent.config import Settings
from nju_agent.llm import request_response


class FakeResponses:
    def __init__(self) -> None:
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output=[], output_text="", id="resp-1")


class FakeClient:
    def __init__(self) -> None:
        self.responses = FakeResponses()


def test_request_response_passes_request_arguments() -> None:
    client = FakeClient()

    response = request_response(
        client,
        model="gpt-test",
        input="hello",
        tools=[{"type": "function", "name": "demo"}],
        instructions="be helpful",
    )

    assert response.id == "resp-1"
    assert client.responses.calls[0]["model"] == "gpt-test"
    assert client.responses.calls[0]["input"] == "hello"
