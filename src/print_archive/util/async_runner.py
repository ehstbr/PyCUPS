from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable, TypeVar


T = TypeVar("T")


class AsyncRunner:
    """Run blocking CUPS/PDF work away from GTK's main thread."""

    def __init__(self, idle_add: Callable[..., object], max_workers: int = 2) -> None:
        self._idle_add = idle_add
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="print-archive")

    def submit(
        self,
        operation: Callable[[], T],
        on_success: Callable[[T], object],
        on_error: Callable[[BaseException], object],
    ) -> Future[T]:
        future = self._executor.submit(operation)

        def finished(done: Future[T]) -> None:
            error = done.exception()
            if error is None:
                self._idle_add(on_success, done.result())
            else:
                self._idle_add(on_error, error)

        future.add_done_callback(finished)
        return future

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

