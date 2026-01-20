"""Execution helpers for background work."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
import multiprocessing as mp
from typing import Any, Callable, Optional


class Worker:
    """Thread and process pools for background work."""

    def __init__(self, max_workers: int = 1, max_processes: int = 0) -> None:
        """Initialize executors.

        Parameters
        ----------
        max_workers
            Number of thread pool workers.
        max_processes
            Number of process pool workers (0 disables process pool).

        Returns
        -------
        None
            This method does not return a value.
        """

        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._process_executor: Optional[ProcessPoolExecutor] = None
        if max_processes and max_processes > 0:
            context = mp.get_context("spawn")
            self._process_executor = ProcessPoolExecutor(
                max_workers=max_processes, mp_context=context
            )

    def submit(self, fn: Callable[..., Any], *args: Any, **kwargs: Any):
        """Run work in the thread pool.

        Parameters
        ----------
        fn
            Callable to execute.
        *args
            Positional arguments to pass to ``fn``.
        **kwargs
            Keyword arguments to pass to ``fn``.

        Returns
        -------
        concurrent.futures.Future
            Future for the submitted work.
        """
        return self._executor.submit(fn, *args, **kwargs)

    def submit_cpu(self, fn: Callable[..., Any], *args: Any, **kwargs: Any):
        """Run CPU work in the process pool when configured.

        Parameters
        ----------
        fn
            Callable to execute.
        *args
            Positional arguments to pass to ``fn``.
        **kwargs
            Keyword arguments to pass to ``fn``.

        Returns
        -------
        concurrent.futures.Future
            Future for the submitted work.
        """
        if self._process_executor is None:
            return self.submit(fn, *args, **kwargs)
        return self._process_executor.submit(fn, *args, **kwargs)
