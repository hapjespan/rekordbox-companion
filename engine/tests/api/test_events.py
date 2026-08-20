"""T030: GET /api/events (SSE, R4) and the publish() seam it exposes.

`publish()` hands off via `loop.call_soon_threadsafe(...)` (T030 review
finding: it must be safe to call from a worker thread, since
`create_sync_session` is a plain sync `def` run in FastAPI's threadpool, not
`async def` -- see api/sync.py's docstring for why). That means a published
item isn't in the queue synchronously after `publish()` returns; every test
below awaits at least one loop tick (`asyncio.sleep(0)`) before reading it.
"""

import asyncio

import pytest

from companion.api.events import _stream, _subscribers, get_events, publish


@pytest.mark.anyio
async def test_publish_delivers_to_every_current_subscriber():
    loop = asyncio.get_running_loop()
    queue_a: asyncio.Queue = asyncio.Queue()
    queue_b: asyncio.Queue = asyncio.Queue()
    subscriber_a = (loop, queue_a)
    subscriber_b = (loop, queue_b)
    _subscribers.extend([subscriber_a, subscriber_b])
    try:
        publish("sync_progress", {"session_id": 1, "done": 1, "total": 2})
        await asyncio.sleep(0)  # let call_soon_threadsafe's callback run

        assert queue_a.get_nowait() == ("sync_progress", {"session_id": 1, "done": 1, "total": 2})
        assert queue_b.get_nowait() == ("sync_progress", {"session_id": 1, "done": 1, "total": 2})
    finally:
        _subscribers.remove(subscriber_a)
        _subscribers.remove(subscriber_b)


@pytest.mark.anyio
async def test_publish_with_no_subscribers_does_not_raise():
    publish("sync_progress", {"session_id": 1, "done": 1, "total": 1})


@pytest.mark.anyio
async def test_publish_from_a_worker_thread_reaches_the_event_loops_subscriber():
    # The real call pattern: create_sync_session runs in FastAPI's
    # threadpool, publish()ing from a thread other than the one running
    # `_stream()`'s event loop.
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    subscriber = (loop, queue)
    _subscribers.append(subscriber)
    try:
        await asyncio.to_thread(publish, "sync_progress", {"session_id": 1, "done": 1, "total": 1})

        message = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert message == ("sync_progress", {"session_id": 1, "done": 1, "total": 1})
    finally:
        _subscribers.remove(subscriber)


@pytest.mark.anyio
async def test_stream_yields_a_published_event_as_sse_text():
    gen = _stream()
    # `_stream()` registers its queue with `_subscribers` on first iteration
    # (an async generator body doesn't run until first advanced), so start
    # it, then publish, then read the one chunk it yields.
    task = asyncio.ensure_future(gen.__anext__())
    await asyncio.sleep(0)  # let the generator register its subscriber
    publish("sync_progress", {"session_id": 1, "done": 1, "total": 1})

    chunk = await asyncio.wait_for(task, timeout=1.0)

    assert chunk == 'event: sync_progress\ndata: {"session_id": 1, "done": 1, "total": 1}\n\n'
    await gen.aclose()


@pytest.mark.anyio
async def test_stream_removes_its_queue_from_subscribers_on_close():
    before = len(_subscribers)
    gen = _stream()
    task = asyncio.ensure_future(gen.__anext__())
    await asyncio.sleep(0)
    assert len(_subscribers) == before + 1

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert len(_subscribers) == before


def test_get_events_returns_an_event_stream_response():
    # Checked without an actual HTTP round-trip: the body is an infinite
    # generator that only ever yields on publish(), so driving it through a
    # live TestClient connection with nothing publishing would hang forever.
    response = get_events()

    assert response.media_type == "text/event-stream"


@pytest.fixture
def anyio_backend():
    return "asyncio"
