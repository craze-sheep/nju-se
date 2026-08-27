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


def test_request_response_passes_previous_response_id() -> None:
    client = FakeClient()

    response = request_response(
        client,
        model="gpt-test",
        input="hello",
        tools=[{"type": "function", "name": "demo"}],
        instructions="be helpful",
        previous_response_id="prev-1",
    )

    assert response.id == "resp-1"
    assert client.responses.calls[0]["previous_response_id"] == "prev-1"
    assert client.responses.calls[0]["model"] == "gpt-test"
