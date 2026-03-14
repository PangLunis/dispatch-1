"""
Centralized resource lifecycle management for the dispatch daemon.

Wraps AsyncExitStack with naming, monitoring, individual close/replace,
and proactive FD leak detection. All persistent resources (file handles,
SQLite connections, sockets, executors, subprocesses) are tracked here.

Usage in Manager.run():

    async with ResourceRegistry() as registry:
        reader = ManagedSQLiteReader('chat.db', CHAT_DB_PATH, registry)
        writer = ManagedSQLiteWriter('bus_writer', BUS_DB_PATH, registry)
        fh = await registry.open_file('search_log', log_path, 'a')
        ...

Design decisions:
- AsyncExitStack is the safety net (LIFO cleanup on exit, even on crash)
- close_and_remove() is the primary mechanism for mid-lifecycle resource swaps
- All cleanup callbacks are wrapped in try/except (sqlite3.Connection.close()
  is NOT idempotent — raises ProgrammingError on double-close)
- Registration must happen on the event loop thread (AsyncExitStack is not thread-safe)
- The Lock protects _resources dict reads from non-event-loop threads (health checks)
"""

import asyncio
import logging
import os
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger("resources")


@dataclass(frozen=True)
class ResourceInfo:
    """Metadata about a tracked resource."""
    name: str
    kind: str  # 'file', 'sqlite', 'socket', 'executor', 'subprocess', 'custom'
    resource: Any
    opened_at: float
    cleanup: Callable


def _safe_cleanup(fn: Callable, name: str) -> Callable:
    """Wrap a cleanup function in try/except.

    sqlite3.Connection.close() raises ProgrammingError on double-close.
    subprocess.Popen.terminate() raises ProcessLookupError on dead process.
    This wrapper makes all cleanup idempotent for the AsyncExitStack safety net.
    """
    def wrapper():
        try:
            fn()
        except Exception as e:
            logger.debug(f"Cleanup already done for {name}: {e}")
    return wrapper


class ResourceRegistry:
    """Centralized resource lifecycle manager for the daemon.

    IMPORTANT: All mutation methods (open_file, connect_sqlite, register,
    close_and_remove, replace) must be called from the event loop thread.
    AsyncExitStack is not thread-safe.

    The _lock protects _resources dict for read access from non-event-loop
    threads (e.g., health check queries).
    """

    def __init__(self):
        self._stack = AsyncExitStack()
        self._resources: dict[str, ResourceInfo] = {}
        self._lock = threading.Lock()  # protects _resources reads from other threads
        self._baseline_fd_count: int = 0

    def _assert_event_loop_thread(self):
        """Assert we're on the event loop thread. Raises RuntimeError if not."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            raise RuntimeError(
                "ResourceRegistry mutation must be called from the event loop thread"
            )

    async def __aenter__(self):
        await self._stack.__aenter__()
        # Calibrate FD baseline before any resources are opened
        try:
            self._baseline_fd_count = len(os.listdir('/dev/fd'))
        except OSError:
            self._baseline_fd_count = 0
        return self

    async def __aexit__(self, *exc):
        # LIFO cleanup via AsyncExitStack (safety net)
        # All callbacks are wrapped in _safe_cleanup so double-close is harmless
        return await self._stack.__aexit__(*exc)

    # === Wrapper functions: open + register is atomic ===

    async def open_file(self, name: str, path: str | Path, mode: str = 'r') -> Any:
        """Open a file and register it. Must be called from event loop thread."""
        self._assert_event_loop_thread()
        fh = open(path, mode)
        cleanup = _safe_cleanup(fh.close, name)
        self._stack.callback(cleanup)
        with self._lock:
            self._resources[name] = ResourceInfo(name, 'file', fh, time.time(), fh.close)
        return fh

    def connect_sqlite(self, name: str, path: str | Path, **kwargs) -> sqlite3.Connection:
        """Open a SQLite connection and register it. Must be called from event loop thread."""
        self._assert_event_loop_thread()
        conn = sqlite3.connect(str(path), check_same_thread=False, **kwargs)
        cleanup = _safe_cleanup(conn.close, name)
        self._stack.callback(cleanup)
        with self._lock:
            self._resources[name] = ResourceInfo(name, 'sqlite', conn, time.time(), conn.close)
        return conn

    def register(self, name: str, resource: Any, cleanup: Callable):
        """Register a resource with a custom cleanup function.

        For subprocesses, executors, sockets, etc. that don't fit typed wrappers.
        Must be called from event loop thread.
        """
        self._assert_event_loop_thread()
        safe = _safe_cleanup(cleanup, name)
        self._stack.callback(safe)
        with self._lock:
            self._resources[name] = ResourceInfo(name, 'custom', resource, time.time(), cleanup)

    async def register_async_cleanup(self, name: str, resource: Any, cleanup: Callable):
        """Register a resource with an async cleanup function.

        For resources needing async teardown (e.g., asyncio.Server.wait_closed()).
        Must be called from event loop thread.
        """
        self._assert_event_loop_thread()

        async def safe_async_cleanup():
            try:
                await cleanup()
            except Exception as e:
                logger.debug(f"Async cleanup already done for {name}: {e}")

        self._stack.push_async_callback(lambda *_: safe_async_cleanup())
        with self._lock:
            self._resources[name] = ResourceInfo(name, 'custom', resource, time.time(), cleanup)

    def close_and_remove(self, name: str):
        """Close and remove a single resource by name.

        For reconnection, socket drops, resource replacement.
        The cleanup callback remains in AsyncExitStack but is wrapped in
        _safe_cleanup, so the double-close on __aexit__ is harmless.
        """
        with self._lock:
            info = self._resources.pop(name, None)
        if info:
            try:
                info.cleanup()
            except Exception as e:
                logger.warning(f"Error closing resource {name}: {e}")

    def replace(self, name: str, new_resource: Any, new_cleanup: Callable):
        """Close old resource and register new one. For reconnection.

        Must be called from event loop thread.
        """
        self.close_and_remove(name)
        self.register(name, new_resource, new_cleanup)

    # === Monitoring ===

    def get_open_count(self) -> int:
        """Number of tracked resources."""
        with self._lock:
            return len(self._resources)

    def get_status(self) -> dict:
        """Full status for health checks. Thread-safe read."""
        with self._lock:
            resources = list(self._resources.values())
        now = time.time()
        try:
            fd_actual = len(os.listdir('/dev/fd'))
        except OSError:
            fd_actual = -1
        return {
            'total': len(resources),
            'resources': [
                {'name': r.name, 'kind': r.kind, 'age_seconds': round(now - r.opened_at, 1)}
                for r in resources
            ],
            'fd_actual': fd_actual,
            'fd_baseline': self._baseline_fd_count,
            'fd_tracked': len(resources),
        }

    def check_fd_leaks(self, threshold: int = 20) -> list[str]:
        """Compare tracked count vs /dev/fd/ actual count using baseline calibration.

        Returns list of warning strings (empty = healthy).
        """
        try:
            actual = len(os.listdir('/dev/fd'))
        except OSError:
            return []
        tracked = self.get_open_count()
        expected = self._baseline_fd_count + tracked
        delta = actual - expected
        warnings = []
        if delta > threshold:
            warnings.append(
                f"FD leak suspected: {actual} actual FDs, {expected} expected "
                f"(baseline={self._baseline_fd_count} + tracked={tracked}), "
                f"{delta} unaccounted"
            )
        return warnings

    def get_resource(self, name: str) -> Optional[ResourceInfo]:
        """Get a specific resource by name. Thread-safe read."""
        with self._lock:
            return self._resources.get(name)


class ManagedSQLiteReader:
    """Single shared read-only SQLite connection with a dedicated executor thread.

    All queries are serialized on one thread — no contention, no check_same_thread issues.
    The connection is registered with the ResourceRegistry for lifecycle tracking.

    Usage:
        reader = ManagedSQLiteReader('chat.db', '/path/to/chat.db', registry)
        rows = await reader.execute("SELECT * FROM messages WHERE ROWID > ?", (100,))
    """

    def __init__(
        self,
        name: str,
        path: str | Path,
        registry: ResourceRegistry,
        pragmas: Optional[dict[str, str]] = None,
    ):
        self.name = name
        self._conn = registry.connect_sqlite(name, path, isolation_level=None)
        # Default read-optimized pragmas
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA query_only=ON")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA cache_size=-64000")  # 64MB
        # Apply custom pragmas
        if pragmas:
            for key, val in pragmas.items():
                self._conn.execute(f"PRAGMA {key}={val}")
        # Dedicated single-thread executor
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"{name}-reader")
        registry.register(
            f'{name}_executor', self._executor,
            lambda: self._executor.shutdown(wait=False),
        )

    @property
    def connection(self) -> sqlite3.Connection:
        """Direct access to the underlying connection (for advanced use)."""
        return self._conn

    async def execute(self, sql: str, params: tuple = ()) -> list:
        """Run a read query on the dedicated thread. Returns list of rows."""
        def _query():
            return self._conn.execute(sql, params).fetchall()
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, _query)

    async def execute_one(self, sql: str, params: tuple = ()) -> Optional[tuple]:
        """Run a read query, return first row or None."""
        results = await self.execute(sql, params)
        return results[0] if results else None

    def execute_sync(self, sql: str, params: tuple = ()) -> list:
        """Synchronous query for use within the executor thread (e.g., from run_in_executor callbacks)."""
        return self._conn.execute(sql, params).fetchall()


class ManagedSQLiteWriter:
    """Single write connection with a dedicated executor thread.

    Serializes all writes on one thread. WAL mode allows concurrent
    readers on separate connections.

    Usage:
        writer = ManagedSQLiteWriter('bus_writer', '/path/to/bus.db', registry)
        await writer.execute("INSERT INTO records VALUES (?)", (data,))
    """

    def __init__(
        self,
        name: str,
        path: str | Path,
        registry: ResourceRegistry,
        pragmas: Optional[dict[str, str]] = None,
    ):
        self.name = name
        self._conn = registry.connect_sqlite(name, path, isolation_level=None)
        # Default write-optimized pragmas
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA cache_size=-64000")  # 64MB
        # Apply custom pragmas
        if pragmas:
            for key, val in pragmas.items():
                self._conn.execute(f"PRAGMA {key}={val}")
        # Dedicated single-thread executor
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"{name}-writer")
        registry.register(
            f'{name}_executor', self._executor,
            lambda: self._executor.shutdown(wait=False),
        )

    @property
    def connection(self) -> sqlite3.Connection:
        """Direct access to the underlying connection (for advanced use)."""
        return self._conn

    async def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """Run a write query on the dedicated thread."""
        def _write():
            return self._conn.execute(sql, params)
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, _write)

    async def executemany(self, sql: str, params_list: list) -> sqlite3.Cursor:
        """Run a batch write on the dedicated thread."""
        def _write():
            return self._conn.executemany(sql, params_list)
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, _write)

    async def executescript(self, sql: str):
        """Run a SQL script on the dedicated thread."""
        def _write():
            return self._conn.executescript(sql)
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, _write)

    def execute_sync(self, sql: str, params: tuple = ()) -> list:
        """Synchronous query for use within the executor thread. Returns list of rows."""
        return self._conn.execute(sql, params).fetchall()
