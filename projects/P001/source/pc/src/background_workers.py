from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QThread, Signal


class FunctionWorkerThread(QThread):
    result_ready = Signal(object)
    error_occurred = Signal(str)
    progress_changed = Signal(str)

    def __init__(
        self,
        fn: Callable[..., Any],
        *args: Any,
        progress_keyword: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs
        self._progress_keyword = progress_keyword

    def run(self) -> None:
        try:
            kwargs = dict(self._kwargs)
            if self._progress_keyword:
                kwargs[self._progress_keyword] = self.progress_changed.emit
            result = self._fn(*self._args, **kwargs)
        except Exception as exc:  # pragma: no cover - UI thread reports this
            self.error_occurred.emit(str(exc))
            return
        self.result_ready.emit(result)
