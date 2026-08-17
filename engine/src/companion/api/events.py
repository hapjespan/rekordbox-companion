"""GET /api/events: one SSE channel for sync and enrichment progress (R4).

Plain `StreamingResponse` over `text/event-stream`, no extra dependency --
Starlette already supports this natively (research.md R4: "SSE is
one-directional, trivial over localhost"). `publish()` is the only seam
other modules need: `api/sync.py`'s `create_sync_session` calls it once per
track to emit `sync_progress` (T030). A future enrichment runner would call
it the same way for `enrichment_progress`/`apply_done` (contracts/api.md);
those event types aren't built yet, only the channel and `sync_progress` are
in this task's scope.

`publish()` is called from a WORKER THREAD, not the event loop (T030 review
finding): `create_sync_session` stays a plain sync `def`, which FastAPI runs
in its threadpool, specifically so the event loop remains free to flush
already-queued SSE bytes to the client WHILE a sync run is still in
progress -- an `async def` handler with no `await` points inside its
per-track loop would run to completion in one uninterrupted event-loop turn
and starve the SSE stream until the whole request finished, defeating "live
progress" entirely (this was tried and reverted). Each subscriber therefore
records the event loop it connected on (`asyncio.get_running_loop()`, always
called from `_stream()`, which only ever runs ON that loop) alongside its
queue, and `publish()` hands work back to that loop via
`loop.call_soon_threadsafe(...)` -- the one thread-safe way to touch an
asyncio primitive from another thread. This is correct whether `publish()`
runs on a worker thread (the real case) or, incidentally, on the loop itself.

In-memory, per-subscriber queues -- no persistence, no replay: a client that
opens the connection after an event fired simply misses it, which is correct
for a live progress bar (data-model.md's "Derived/in-memory" philosophy:
nothing here needs to survive a reconnect). One operator, one browser tab
expected (constraints.md), so no per-client filtering is needed; every
subscriber gets every event.
"""

import asyncio
import json

from fastapi import APIRouter
from starlette.responses import StreamingResponse

router = APIRouter()

_subscribers: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = []


def publish(event: str, data: dict) -> None:
    """Send `event` to every currently-connected SSE subscriber.

    Safe to call from any thread: each subscriber's own event loop is asked
    (via `call_soon_threadsafe`) to enqueue the message, rather than this
    function touching the queue directly.
    """
    for loop, queue in _subscribers:
        loop.call_soon_threadsafe(queue.put_nowait, (event, data))


async def _stream():
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    subscriber = (loop, queue)
    _subscribers.append(subscriber)
    try:
        while True:
            event, data = await queue.get()
            yield f"event: {event}\ndata: {json.dumps(data)}\n\n"
    finally:
        _subscribers.remove(subscriber)


@router.get("/events")
def get_events():
    return StreamingResponse(_stream(), media_type="text/event-stream")
