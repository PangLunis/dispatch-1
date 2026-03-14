"""Tests for ResourceRegistry, ManagedSQLiteReader, and ManagedSQLiteWriter."""

import asyncio
import os
import sqlite3
import tempfile
import threading
import time

import pytest

from assistant.resources import (
    ManagedSQLiteReader,
    ManagedSQLiteWriter,
    ResourceInfo,
    ResourceRegistry,
    _safe_cleanup,
)


# ── _safe_cleanup tests ──


class TestSafeCleanup:
    def test_wraps_normal_function(self):
        called = []
        fn = _safe_cleanup(lambda: called.append(1), "test")
        fn()
        assert called == [1]

    def test_swallows_exception(self):
        def blow_up():
            raise RuntimeError("boom")

        fn = _safe_cleanup(blow_up, "test")
        fn()  # should not raise

    def test_swallows_programming_error(self):
        """Simulate sqlite3.Connection.close() double-close."""
        def double_close():
            raise sqlite3.ProgrammingError("Cannot operate on a closed database.")

        fn = _safe_cleanup(double_close, "test-sqlite")
        fn()  # should not raise

    def test_swallows_process_lookup_error(self):
        """Simulate subprocess.Popen.terminate() on dead process."""
        def dead_process():
            raise ProcessLookupError("[Errno 3] No such process")

        fn = _safe_cleanup(dead_process, "test-proc")
        fn()  # should not raise


# ── ResourceRegistry tests ──


class TestResourceRegistry:
    @pytest.mark.asyncio
    async def test_basic_lifecycle(self):
        """Registry opens and closes cleanly."""
        async with ResourceRegistry() as reg:
            assert reg.get_open_count() == 0

    @pytest.mark.asyncio
    async def test_open_file(self, tmp_path):
        """open_file registers and tracks the file handle."""
        test_file = tmp_path / "test.log"
        test_file.touch()

        async with ResourceRegistry() as reg:
            fh = await reg.open_file("test_log", str(test_file), "a")
            assert reg.get_open_count() == 1
            fh.write("hello\n")
            fh.flush()

            info = reg.get_resource("test_log")
            assert info is not None
            assert info.kind == "file"
            assert info.name == "test_log"

        # After exit, file should be closed
        assert fh.closed

    @pytest.mark.asyncio
    async def test_connect_sqlite(self, tmp_path):
        """connect_sqlite registers and tracks the connection."""
        db_path = tmp_path / "test.db"

        async with ResourceRegistry() as reg:
            conn = reg.connect_sqlite("test_db", str(db_path))
            assert reg.get_open_count() == 1

            # Verify connection works
            conn.execute("CREATE TABLE t (id INTEGER)")
            conn.execute("INSERT INTO t VALUES (1)")
            assert conn.execute("SELECT * FROM t").fetchone() == (1,)

            info = reg.get_resource("test_db")
            assert info is not None
            assert info.kind == "sqlite"

        # After exit, connection should be closed (via safe cleanup)
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")

    @pytest.mark.asyncio
    async def test_register_custom(self):
        """register() tracks custom resources."""
        closed = []

        async with ResourceRegistry() as reg:
            reg.register("my_thing", object(), lambda: closed.append(True))
            assert reg.get_open_count() == 1

        assert closed == [True]

    @pytest.mark.asyncio
    async def test_close_and_remove(self, tmp_path):
        """close_and_remove closes one resource without affecting others."""
        db1 = tmp_path / "a.db"
        db2 = tmp_path / "b.db"

        async with ResourceRegistry() as reg:
            conn1 = reg.connect_sqlite("db_a", str(db1))
            conn2 = reg.connect_sqlite("db_b", str(db2))
            assert reg.get_open_count() == 2

            reg.close_and_remove("db_a")
            assert reg.get_open_count() == 1
            assert reg.get_resource("db_a") is None
            assert reg.get_resource("db_b") is not None

            # conn1 should be closed
            with pytest.raises(sqlite3.ProgrammingError):
                conn1.execute("SELECT 1")

            # conn2 should still work
            conn2.execute("SELECT 1")

    @pytest.mark.asyncio
    async def test_close_and_remove_nonexistent(self):
        """close_and_remove on unknown name is a no-op."""
        async with ResourceRegistry() as reg:
            reg.close_and_remove("does_not_exist")  # should not raise

    @pytest.mark.asyncio
    async def test_replace(self, tmp_path):
        """replace() closes old resource and registers new one."""
        db_path = tmp_path / "replace.db"
        closed = []

        async with ResourceRegistry() as reg:
            reg.register("thing", "old", lambda: closed.append("old"))
            assert reg.get_open_count() == 1

            reg.replace("thing", "new", lambda: closed.append("new"))
            assert reg.get_open_count() == 1
            assert closed == ["old"]

            info = reg.get_resource("thing")
            assert info.resource == "new"

    @pytest.mark.asyncio
    async def test_double_close_safety_net(self, tmp_path):
        """AsyncExitStack safety net handles double-close via _safe_cleanup."""
        db_path = tmp_path / "double.db"

        async with ResourceRegistry() as reg:
            conn = reg.connect_sqlite("dc_test", str(db_path))
            # Manually close before __aexit__
            reg.close_and_remove("dc_test")
            # conn is now closed; __aexit__ will also call safe cleanup — should not raise

    @pytest.mark.asyncio
    async def test_get_status(self, tmp_path):
        """get_status returns structured resource info."""
        db_path = tmp_path / "status.db"

        async with ResourceRegistry() as reg:
            reg.connect_sqlite("status_db", str(db_path))

            status = reg.get_status()
            assert status['total'] == 1
            assert status['fd_tracked'] == 1
            assert status['fd_baseline'] >= 0
            assert len(status['resources']) == 1
            assert status['resources'][0]['name'] == "status_db"
            assert status['resources'][0]['kind'] == "sqlite"
            assert status['resources'][0]['age_seconds'] >= 0

    @pytest.mark.asyncio
    async def test_check_fd_leaks_no_leak(self):
        """check_fd_leaks returns empty when no leaks."""
        async with ResourceRegistry() as reg:
            warnings = reg.check_fd_leaks(threshold=100)
            assert warnings == []

    @pytest.mark.asyncio
    async def test_fd_baseline_calibration(self):
        """Baseline FD count is recorded on entry."""
        async with ResourceRegistry() as reg:
            assert reg._baseline_fd_count > 0

    @pytest.mark.asyncio
    async def test_thread_safety_of_reads(self):
        """get_status and get_open_count are safe from non-event-loop threads."""
        async with ResourceRegistry() as reg:
            reg.register("x", object(), lambda: None)

            results = []

            def reader():
                for _ in range(100):
                    results.append(reg.get_open_count())
                    reg.get_status()

            threads = [threading.Thread(target=reader) for _ in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert all(r == 1 for r in results)

    @pytest.mark.asyncio
    async def test_event_loop_thread_assertion(self):
        """Mutation from a non-event-loop thread raises RuntimeError."""
        async with ResourceRegistry() as reg:
            error_raised = threading.Event()

            def try_register():
                try:
                    reg.register("bad", object(), lambda: None)
                except RuntimeError:
                    error_raised.set()

            t = threading.Thread(target=try_register)
            t.start()
            t.join()
            assert error_raised.is_set()

    @pytest.mark.asyncio
    async def test_multiple_resources_lifo_cleanup(self):
        """Resources are cleaned up in LIFO order via AsyncExitStack."""
        order = []

        async with ResourceRegistry() as reg:
            reg.register("first", None, lambda: order.append("first"))
            reg.register("second", None, lambda: order.append("second"))
            reg.register("third", None, lambda: order.append("third"))

        # LIFO order
        assert order == ["third", "second", "first"]


# ── ManagedSQLiteReader tests ──


class TestManagedSQLiteReader:
    @pytest.mark.asyncio
    async def test_basic_read(self, tmp_path):
        """Reader can execute queries."""
        db_path = tmp_path / "reader.db"
        # Create and populate the database first
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE items (id INTEGER, name TEXT)")
        conn.execute("INSERT INTO items VALUES (1, 'hello')")
        conn.execute("INSERT INTO items VALUES (2, 'world')")
        conn.commit()
        conn.close()

        async with ResourceRegistry() as reg:
            reader = ManagedSQLiteReader("test_reader", db_path, reg)

            rows = await reader.execute("SELECT * FROM items ORDER BY id")
            assert rows == [(1, 'hello'), (2, 'world')]

    @pytest.mark.asyncio
    async def test_execute_one(self, tmp_path):
        """execute_one returns single row."""
        db_path = tmp_path / "one.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE t (v INTEGER)")
        conn.execute("INSERT INTO t VALUES (42)")
        conn.commit()
        conn.close()

        async with ResourceRegistry() as reg:
            reader = ManagedSQLiteReader("one_reader", db_path, reg)

            row = await reader.execute_one("SELECT v FROM t")
            assert row == (42,)

            none_row = await reader.execute_one("SELECT v FROM t WHERE v = 999")
            assert none_row is None

    @pytest.mark.asyncio
    async def test_read_only_enforcement(self, tmp_path):
        """Reader connection has PRAGMA query_only=ON — writes should fail."""
        db_path = tmp_path / "readonly.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE t (v INTEGER)")
        conn.commit()
        conn.close()

        async with ResourceRegistry() as reg:
            reader = ManagedSQLiteReader("ro_reader", db_path, reg)

            with pytest.raises(Exception):  # sqlite3.OperationalError
                await reader.execute("INSERT INTO t VALUES (1)")

    @pytest.mark.asyncio
    async def test_registers_two_resources(self, tmp_path):
        """Reader registers both the connection and the executor."""
        db_path = tmp_path / "reg.db"
        sqlite3.connect(str(db_path)).close()  # create file

        async with ResourceRegistry() as reg:
            ManagedSQLiteReader("rtest", db_path, reg)
            # Should register: connection + executor
            assert reg.get_open_count() == 2
            assert reg.get_resource("rtest") is not None
            assert reg.get_resource("rtest_executor") is not None

    @pytest.mark.asyncio
    async def test_concurrent_reads(self, tmp_path):
        """Multiple concurrent reads are serialized on the single thread."""
        db_path = tmp_path / "concurrent.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE t (v INTEGER)")
        for i in range(100):
            conn.execute("INSERT INTO t VALUES (?)", (i,))
        conn.commit()
        conn.close()

        async with ResourceRegistry() as reg:
            reader = ManagedSQLiteReader("conc_reader", db_path, reg)

            # Fire off many concurrent reads
            tasks = [
                reader.execute("SELECT COUNT(*) FROM t")
                for _ in range(20)
            ]
            results = await asyncio.gather(*tasks)
            assert all(r == [(100,)] for r in results)

    @pytest.mark.asyncio
    async def test_custom_pragmas(self, tmp_path):
        """Custom pragmas are applied."""
        db_path = tmp_path / "pragmas.db"
        sqlite3.connect(str(db_path)).close()

        async with ResourceRegistry() as reg:
            reader = ManagedSQLiteReader(
                "pragma_reader", db_path, reg,
                pragmas={"read_uncommitted": "1"},
            )
            row = await reader.execute_one("PRAGMA read_uncommitted")
            assert row == (1,)

    @pytest.mark.asyncio
    async def test_execute_sync(self, tmp_path):
        """execute_sync works for direct access."""
        db_path = tmp_path / "sync.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE t (v INTEGER)")
        conn.execute("INSERT INTO t VALUES (7)")
        conn.commit()
        conn.close()

        async with ResourceRegistry() as reg:
            reader = ManagedSQLiteReader("sync_reader", db_path, reg)
            rows = reader.execute_sync("SELECT v FROM t")
            assert rows == [(7,)]


# ── ManagedSQLiteWriter tests ──


class TestManagedSQLiteWriter:
    @pytest.mark.asyncio
    async def test_basic_write(self, tmp_path):
        """Writer can create tables and insert data."""
        db_path = tmp_path / "writer.db"

        async with ResourceRegistry() as reg:
            writer = ManagedSQLiteWriter("test_writer", db_path, reg)

            await writer.execute("CREATE TABLE items (id INTEGER, name TEXT)")
            await writer.execute("INSERT INTO items VALUES (1, 'hello')")

            # Read back
            rows = writer.execute_sync("SELECT * FROM items")
            assert rows == [(1, 'hello')]

    @pytest.mark.asyncio
    async def test_executemany(self, tmp_path):
        """executemany batches inserts."""
        db_path = tmp_path / "many.db"

        async with ResourceRegistry() as reg:
            writer = ManagedSQLiteWriter("many_writer", db_path, reg)
            await writer.execute("CREATE TABLE t (v INTEGER)")
            await writer.executemany(
                "INSERT INTO t VALUES (?)",
                [(i,) for i in range(50)],
            )
            rows = writer.execute_sync("SELECT COUNT(*) FROM t")
            assert rows == [(50,)]

    @pytest.mark.asyncio
    async def test_executescript(self, tmp_path):
        """executescript runs multi-statement SQL."""
        db_path = tmp_path / "script.db"

        async with ResourceRegistry() as reg:
            writer = ManagedSQLiteWriter("script_writer", db_path, reg)
            await writer.executescript("""
                CREATE TABLE a (v INTEGER);
                CREATE TABLE b (v TEXT);
                INSERT INTO a VALUES (1);
                INSERT INTO b VALUES ('x');
            """)
            assert writer.execute_sync("SELECT * FROM a") == [(1,)]
            assert writer.execute_sync("SELECT * FROM b") == [('x',)]

    @pytest.mark.asyncio
    async def test_concurrent_writes_serialized(self, tmp_path):
        """Multiple concurrent writes are serialized on the single thread."""
        db_path = tmp_path / "serial.db"

        async with ResourceRegistry() as reg:
            writer = ManagedSQLiteWriter("serial_writer", db_path, reg)
            await writer.execute("CREATE TABLE t (v INTEGER)")

            tasks = [
                writer.execute("INSERT INTO t VALUES (?)", (i,))
                for i in range(50)
            ]
            await asyncio.gather(*tasks)

            rows = writer.execute_sync("SELECT COUNT(*) FROM t")
            assert rows == [(50,)]

    @pytest.mark.asyncio
    async def test_reader_writer_concurrent(self, tmp_path):
        """Reader and writer on same DB work concurrently via WAL."""
        db_path = tmp_path / "rw.db"
        # Pre-create schema
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE t (v INTEGER)")
        conn.commit()
        conn.close()

        async with ResourceRegistry() as reg:
            reader = ManagedSQLiteReader("rw_reader", db_path, reg)
            writer = ManagedSQLiteWriter("rw_writer", db_path, reg)

            # Write some data
            for i in range(10):
                await writer.execute("INSERT INTO t VALUES (?)", (i,))

            # Read it back concurrently
            rows = await reader.execute("SELECT COUNT(*) FROM t")
            assert rows[0][0] == 10

    @pytest.mark.asyncio
    async def test_registers_two_resources(self, tmp_path):
        """Writer registers both the connection and the executor."""
        db_path = tmp_path / "wreg.db"

        async with ResourceRegistry() as reg:
            ManagedSQLiteWriter("wtest", db_path, reg)
            assert reg.get_open_count() == 2
            assert reg.get_resource("wtest") is not None
            assert reg.get_resource("wtest_executor") is not None


# ── Integration tests ──


class TestResourceRegistryIntegration:
    @pytest.mark.asyncio
    async def test_full_daemon_simulation(self, tmp_path):
        """Simulate daemon resource setup and teardown."""
        chat_db = tmp_path / "chat.db"
        bus_db = tmp_path / "bus.db"
        log_file = tmp_path / "daemon.log"

        # Pre-create databases
        for db in [chat_db, bus_db]:
            conn = sqlite3.connect(str(db))
            conn.execute("CREATE TABLE t (v INTEGER)")
            conn.commit()
            conn.close()

        cleanup_order = []

        async with ResourceRegistry() as reg:
            # Simulate daemon resource setup
            chat_reader = ManagedSQLiteReader("chat.db", chat_db, reg)
            bus_reader = ManagedSQLiteReader("bus_reader", bus_db, reg)
            bus_writer = ManagedSQLiteWriter("bus_writer", bus_db, reg)
            fh = await reg.open_file("daemon_log", str(log_file), "a")

            # 6 resources: 3 connections + 3 executors + 1 file
            assert reg.get_open_count() == 7

            # Simulate some work
            await bus_writer.execute("INSERT INTO t VALUES (1)")
            rows = await bus_reader.execute("SELECT * FROM t")
            assert rows == [(1,)]

            rows = await chat_reader.execute("SELECT * FROM t")
            assert rows == [(0,)] or rows == []  # chat.db has no data

            fh.write("test log line\n")
            fh.flush()

            # Simulate mid-lifecycle resource replacement
            reg.close_and_remove("daemon_log")
            assert reg.get_open_count() == 6

            new_fh = await reg.open_file("daemon_log", str(log_file), "a")
            assert reg.get_open_count() == 7

        # All resources should be cleaned up after exit

    @pytest.mark.asyncio
    async def test_exception_during_use(self, tmp_path):
        """Resources are cleaned up even if an exception occurs."""
        db_path = tmp_path / "exc.db"
        closed = []

        with pytest.raises(ValueError):
            async with ResourceRegistry() as reg:
                reg.register("cleanup_test", None, lambda: closed.append(True))
                raise ValueError("simulated crash")

        assert closed == [True]

    @pytest.mark.asyncio
    async def test_health_check_status(self, tmp_path):
        """Health check provides useful monitoring data."""
        db_path = tmp_path / "health.db"
        sqlite3.connect(str(db_path)).close()

        async with ResourceRegistry() as reg:
            ManagedSQLiteReader("health_db", db_path, reg)

            status = reg.get_status()
            assert status['total'] == 2  # connection + executor
            assert status['fd_baseline'] > 0
            assert status['fd_actual'] > 0

            # No leaks in a test environment
            warnings = reg.check_fd_leaks(threshold=100)
            assert warnings == []
