from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
import multiprocessing as mp
from typing import Any, Callable


class Worker:
    def __init__(self, max_workers: int = 1, max_processes: int = 0) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._process_executor = None
        if max_processes and max_processes > 0:
            context = mp.get_context("spawn")
            self._process_executor = ProcessPoolExecutor(
                max_workers=max_processes, mp_context=context
            )

    def submit(self, fn: Callable[..., Any], *args: Any, **kwargs: Any):
        return self._executor.submit(fn, *args, **kwargs)

    def submit_cpu(self, fn: Callable[..., Any], *args: Any, **kwargs: Any):
        if self._process_executor is None:
            return self.submit(fn, *args, **kwargs)
        return self._process_executor.submit(fn, *args, **kwargs)
