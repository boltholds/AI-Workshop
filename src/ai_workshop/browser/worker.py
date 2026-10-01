from __future__ import annotations

from concurrent.futures import Future
from queue import Queue
from threading import Event, Thread
from typing import Any, Callable

from ai_workshop.browser.engine import BrowserEngine

_STOP = object()


class BrowserWorker:
    def __init__(self, engine_factory: Callable[[], BrowserEngine]):
        self._engine_factory = engine_factory
        self._queue: Queue[Any] = Queue()
        self._ready = Event()
        self._thread: Thread | None = None
        self._startup_error: BaseException | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._ready.clear()
        self._startup_error = None
        self._thread = Thread(target=self._run, name="ai-workshop-browser", daemon=True)
        self._thread.start()
        self._ready.wait()
        if self._startup_error is not None:
            self._thread = None
            raise RuntimeError("browser worker failed to start") from self._startup_error

    def stop(self) -> None:
        if self._thread is None:
            return
        self._queue.put(_STOP)
        self._thread.join(timeout=15)
        self._thread = None

    def call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        if self._thread is None:
            raise RuntimeError("browser worker is not started")
        future: Future[Any] = Future()
        self._queue.put((future, method, args, kwargs))
        return future.result()

    def _run(self) -> None:
        engine = None
        try:
            engine = self._engine_factory()
            engine.start()
        except BaseException as exc:
            self._startup_error = exc
            self._ready.set()
            return
        self._ready.set()
        try:
            while True:
                item = self._queue.get()
                if item is _STOP:
                    break
                future, method, args, kwargs = item
                try:
                    future.set_result(getattr(engine, method)(*args, **kwargs))
                except BaseException as exc:
                    future.set_exception(exc)
        finally:
            engine.stop()
