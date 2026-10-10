import uuid
from collections.abc import Awaitable, Callable

import pytest

from pushtalk.messages.processing import ProcessingContext
from pushtalk.worker import tasks


@pytest.fixture
def jobs(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Replaces the infrastructure with a recorder; processing always hits a dead database."""
    calls: list[str] = []

    async def fake_context(job: Callable[[ProcessingContext], Awaitable[None]]) -> None:
        name = job.__code__.co_names[0] if job.__code__.co_names else "job"
        calls.append(name)
        if name == "process_message":
            raise ConnectionError("database unavailable")

    monkeypatch.setattr(tasks, "_with_context", fake_context)
    return calls


def test_infrastructure_errors_retry_then_fail_the_message(jobs: list[str]) -> None:
    tasks.process_message_task.apply(args=(str(uuid.uuid4()),))

    assert jobs == ["process_message"] * (tasks.MAX_RETRIES + 1) + ["fail_message"]
