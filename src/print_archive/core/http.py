from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Soup", "3.0")
from gi.repository import Gio, GLib, Soup

from .. import VERSION


HttpCallback = Callable[[int, bytes, Exception | None], None]


class HttpClient:
    def __init__(self, user_agent: str | None = None, *, timeout: int = 8) -> None:
        self.session = Soup.Session(
            user_agent=user_agent or f"PyCUPS/{VERSION}",
            timeout=timeout,
        )

    def request(
        self,
        method: str,
        url: str,
        callback: HttpCallback,
        *,
        headers: dict[str, str] | None = None,
    ) -> Gio.Cancellable:
        message = Soup.Message.new(method, url)
        if message is None:
            callback(0, b"", ValueError("Invalid request URL."))
            return Gio.Cancellable()
        for key, value in (headers or {}).items():
            message.get_request_headers().replace(key, value)
        cancellable = Gio.Cancellable()

        def finished(session: Soup.Session, result: Gio.AsyncResult, _data: object = None) -> None:
            try:
                response = session.send_and_read_finish(result)
                callback(message.get_status(), response.get_data(), None)
            except GLib.Error as error:
                callback(message.get_status(), b"", RuntimeError(str(error)))

        self.session.send_and_read_async(
            message,
            GLib.PRIORITY_DEFAULT,
            cancellable,
            finished,
            None,
        )
        return cancellable
