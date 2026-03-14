"""
Tests for the consumer framework: ConsumerConfig, ConsumerRunner, BatchConfig, and actions.

Covers:
- actions: call_function, produce, produce_batch, log, multi, noop, dead_letter
- BatchConfig: validation, window_seconds, window_count, both
- ConsumerConfig: filter, no filter, batching, retries, error_action
- ConsumerRunner: run_once, run_forever, stop flush, multi-consumer, error handling
"""

import json
import logging
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bus import Bus, Record
from bus.consumers import (
    BatchConfig,
    ConsumerConfig,
    ConsumerRunner,
    _BatchState,
    actions,
)


@pytest.fixture
def bus(tmp_path):
    """Create a Bus with a temp database."""
    db = tmp_path / "test_bus.db"
    b = Bus(db_path=db)
    yield b
    b.close()


@pytest.fixture
def bus_with_topic(bus):
    """Bus with a 'test' topic pre-created."""
    bus.create_topic("test", partitions=1)
    return bus


def make_record(topic="test", partition=0, offset=0, key=None, value=None, payload=None, type=None, source=None, headers=None):
    """Helper to make a Record for testing."""
    return Record(
        topic=topic,
        partition=partition,
        offset=offset,
        timestamp=int(time.time() * 1000),
        key=key,
        type=type,
        source=source,
        payload=payload or value or {"msg": "hello"},
        headers=headers,
    )


# ─── BatchConfig tests ───────────────────────────────────────


class TestBatchConfig:
    def test_valid_window_seconds(self):
        bc = BatchConfig(window_seconds=60)
        assert bc.window_seconds == 60
        assert bc.window_count == 0

    def test_valid_window_count(self):
        bc = BatchConfig(window_count=10)
        assert bc.window_seconds == 0
        assert bc.window_count == 10

    def test_valid_both(self):
        bc = BatchConfig(window_seconds=30, window_count=5)
        assert bc.window_seconds == 30
        assert bc.window_count == 5

    def test_invalid_both_zero(self):
        with pytest.raises(ValueError, match="must have"):
            BatchConfig(window_seconds=0, window_count=0)

    def test_invalid_negative(self):
        with pytest.raises(ValueError, match="must have"):
            BatchConfig(window_seconds=-1, window_count=0)


# ─── Actions tests ────────────────────────────────────────────


class TestActions:

    def test_call_function_receives_records(self):
        received = []
        action = actions.call_function(lambda rs: received.extend(rs))
        records = [make_record(offset=0), make_record(offset=1)]
        action(records)
        assert len(received) == 2
        assert received[0].offset == 0
        assert received[1].offset == 1

    def test_call_function_empty_records(self):
        received = []
        action = actions.call_function(lambda rs: received.extend(rs))
        action([])
        assert received == []

    def test_call_function_exception_propagates(self):
        def fail(records):
            raise RuntimeError("boom")
        action = actions.call_function(fail)
        with pytest.raises(RuntimeError, match="boom"):
            action([make_record()])

    def test_produce_sends_to_topic(self, bus_with_topic):
        bus = bus_with_topic
        bus.create_topic("output", partitions=1)
        action = actions.produce(bus, "output", lambda r: {**r.value, "enriched": True})
        records = [make_record(key="k1", value={"price": 100})]
        action(records)

        consumer = bus.consumer(group_id="verify", topics=["output"])
        out = consumer.poll(timeout_ms=50)
        assert len(out) == 1
        assert out[0].value == {"price": 100, "enriched": True}
        assert out[0].key == "k1"
        consumer.close()

    def test_produce_multiple_records(self, bus_with_topic):
        bus = bus_with_topic
        bus.create_topic("output", partitions=1)
        action = actions.produce(bus, "output", lambda r: {"n": r.offset})
        records = [make_record(offset=i) for i in range(5)]
        action(records)

        consumer = bus.consumer(group_id="verify", topics=["output"])
        out = consumer.poll(timeout_ms=50)
        assert len(out) == 5
        consumer.close()

    def test_produce_batch_sends_transformed(self, bus_with_topic):
        bus = bus_with_topic
        bus.create_topic("summary", partitions=1)
        action = actions.produce_batch(
            bus, "summary",
            lambda rs: [{"count": len(rs), "total": sum(r.value.get("n", 0) for r in rs)}],
        )
        records = [make_record(value={"n": i}) for i in range(3)]
        action(records)

        consumer = bus.consumer(group_id="verify", topics=["summary"])
        out = consumer.poll(timeout_ms=50)
        assert len(out) == 1
        assert out[0].value == {"count": 3, "total": 3}
        consumer.close()

    def test_log_action_logs(self, caplog):
        action = actions.log(level="info")
        records = [make_record(key="k1", value={"test": True})]
        with caplog.at_level(logging.INFO, logger="bus.consumers"):
            action(records)
        assert "k1" in caplog.text
        assert "test" in caplog.text

    def test_log_with_template(self, caplog):
        action = actions.log(template=lambda r: f"GOT:{r.key}")
        with caplog.at_level(logging.INFO, logger="bus.consumers"):
            action([make_record(key="mykey")])
        assert "GOT:mykey" in caplog.text

    def test_multi_runs_all_actions(self):
        calls = []
        a1 = actions.call_function(lambda rs: calls.append("a1"))
        a2 = actions.call_function(lambda rs: calls.append("a2"))
        a3 = actions.call_function(lambda rs: calls.append("a3"))
        action = actions.multi(a1, a2, a3)
        action([make_record()])
        assert calls == ["a1", "a2", "a3"]

    def test_multi_stops_on_error(self):
        calls = []

        def fail(rs):
            raise RuntimeError("fail")

        a1 = actions.call_function(lambda rs: calls.append("a1"))
        a2 = actions.call_function(fail)
        a3 = actions.call_function(lambda rs: calls.append("a3"))
        action = actions.multi(a1, a2, a3)
        with pytest.raises(RuntimeError):
            action([make_record()])
        assert calls == ["a1"]  # a3 never ran

    def test_noop_does_nothing(self):
        action = actions.noop()
        action([make_record()])  # should not raise

    def test_noop_with_empty(self):
        action = actions.noop()
        action([])

    def test_dead_letter_sends_to_dlq(self, bus_with_topic):
        bus = bus_with_topic
        action = actions.dead_letter(bus, topic="dlq")
        original = make_record(key="bad", payload={"broken": True})
        action([original])

        consumer = bus.consumer(group_id="verify", topics=["dlq"])
        out = consumer.poll(timeout_ms=50)
        assert len(out) == 1
        assert out[0].payload["original_topic"] == "test"
        assert out[0].payload["original_key"] == "bad"
        assert out[0].payload["original_payload"] == {"broken": True}
        assert out[0].key == "bad"
        assert out[0].type == "dead_letter"
        assert "error_time" in out[0].payload
        consumer.close()

    def test_dead_letter_multiple_records(self, bus_with_topic):
        bus = bus_with_topic
        action = actions.dead_letter(bus)
        records = [make_record(offset=i, key=f"k{i}") for i in range(3)]
        action(records)

        consumer = bus.consumer(group_id="verify", topics=["dead-letters"])
        out = consumer.poll(timeout_ms=50)
        assert len(out) == 3
        consumer.close()


# ─── ConsumerConfig tests ─────────────────────────────────────


class TestConsumerConfig:
    def test_minimal_config(self):
        cc = ConsumerConfig(topic="t", group="g", action=actions.noop())
        assert cc.topic == "t"
        assert cc.group == "g"
        assert cc.filter is None
        assert cc.batch is None
        assert cc.max_retries == 0
        assert cc.error_action is None

    def test_full_config(self):
        cc = ConsumerConfig(
            topic="t",
            group="g",
            action=actions.noop(),
            filter=lambda r: True,
            batch=BatchConfig(window_seconds=30),
            max_retries=3,
            error_action=actions.noop(),
        )
        assert cc.max_retries == 3
        assert cc.batch.window_seconds == 30


# ─── _BatchState tests ────────────────────────────────────────


class TestBatchState:
    def test_initial_state(self):
        bs = _BatchState()
        assert bs.records == []
        assert bs.window_start == 0.0

    def test_reset(self):
        bs = _BatchState()
        bs.records = [make_record()]
        bs.window_start = 100.0
        bs.reset()
        assert bs.records == []
        assert bs.window_start > 0


# ─── ConsumerRunner integration tests ─────────────────────────


class TestConsumerRunnerBasic:
    """Tests for ConsumerRunner with real Bus (integration tests)."""

    def test_run_once_no_records(self, bus_with_topic):
        bus = bus_with_topic
        received = []
        runner = ConsumerRunner(bus, [
            ConsumerConfig(
                topic="test",
                group="g1",
                action=actions.call_function(lambda rs: received.extend(rs)),
            ),
        ])
        results = runner.run_once()
        assert results == {"g1": 0}
        assert received == []
        runner.stop()

    def test_run_once_processes_records(self, bus_with_topic):
        bus = bus_with_topic
        producer = bus.producer()
        producer.send("test", value={"msg": "hello"}, key="k1")
        producer.send("test", value={"msg": "world"}, key="k2")
        producer.flush()

        received = []
        runner = ConsumerRunner(bus, [
            ConsumerConfig(
                topic="test",
                group="g1",
                action=actions.call_function(lambda rs: received.extend(rs)),
            ),
        ])
        results = runner.run_once()
        assert results == {"g1": 2}
        assert len(received) == 2
        assert received[0].value == {"msg": "hello"}
        assert received[1].value == {"msg": "world"}
        runner.stop()

    def test_run_once_with_filter(self, bus_with_topic):
        bus = bus_with_topic
        producer = bus.producer()
        producer.send("test", value={"type": "a", "n": 1})
        producer.send("test", value={"type": "b", "n": 2})
        producer.send("test", value={"type": "a", "n": 3})
        producer.flush()

        received = []
        runner = ConsumerRunner(bus, [
            ConsumerConfig(
                topic="test",
                group="g1",
                filter=lambda r: r.value.get("type") == "a",
                action=actions.call_function(lambda rs: received.extend(rs)),
            ),
        ])
        results = runner.run_once()
        assert results == {"g1": 2}
        assert len(received) == 2
        assert all(r.value["type"] == "a" for r in received)
        runner.stop()

    def test_filter_all_out_still_commits(self, bus_with_topic):
        """When filter removes all records, offsets should still be committed."""
        bus = bus_with_topic
        producer = bus.producer()
        producer.send("test", value={"type": "x"})
        producer.flush()

        received = []
        runner = ConsumerRunner(bus, [
            ConsumerConfig(
                topic="test",
                group="g1",
                filter=lambda r: False,  # filter everything out
                action=actions.call_function(lambda rs: received.extend(rs)),
            ),
        ])
        runner.run_once()
        assert received == []

        # Produce more and verify old ones don't reappear
        producer.send("test", value={"type": "y"})
        producer.flush()
        runner.run_once()
        assert received == []  # still filtered
        runner.stop()

    def test_no_filter_passes_all(self, bus_with_topic):
        bus = bus_with_topic
        producer = bus.producer()
        for i in range(5):
            producer.send("test", value={"n": i})
        producer.flush()

        received = []
        runner = ConsumerRunner(bus, [
            ConsumerConfig(
                topic="test",
                group="g1",
                action=actions.call_function(lambda rs: received.extend(rs)),
            ),
        ])
        runner.run_once()
        assert len(received) == 5
        runner.stop()

    def test_offsets_committed_after_dispatch(self, bus_with_topic):
        """After run_once, re-polling should not return the same records."""
        bus = bus_with_topic
        producer = bus.producer()
        producer.send("test", value={"n": 1})
        producer.flush()

        received = []
        runner = ConsumerRunner(bus, [
            ConsumerConfig(
                topic="test",
                group="g1",
                action=actions.call_function(lambda rs: received.extend(rs)),
            ),
        ])
        runner.run_once()
        assert len(received) == 1

        # Second run_once should not see the same record
        runner.run_once()
        assert len(received) == 1  # still 1, not 2

        # New record should be seen
        producer.send("test", value={"n": 2})
        producer.flush()
        runner.run_once()
        assert len(received) == 2
        assert received[1].value == {"n": 2}
        runner.stop()


class TestConsumerRunnerBatching:

    def test_batch_by_count(self, bus_with_topic):
        bus = bus_with_topic
        producer = bus.producer()
        dispatches = []

        runner = ConsumerRunner(bus, [
            ConsumerConfig(
                topic="test",
                group="g1",
                batch=BatchConfig(window_count=3),
                action=actions.call_function(lambda rs: dispatches.append(list(rs))),
            ),
        ])

        # Send 2 records — should NOT dispatch yet
        producer.send("test", value={"n": 1})
        producer.send("test", value={"n": 2})
        producer.flush()
        runner.run_once()
        assert len(dispatches) == 0

        # Send 1 more — should dispatch batch of 3
        producer.send("test", value={"n": 3})
        producer.flush()
        runner.run_once()
        assert len(dispatches) == 1
        assert len(dispatches[0]) == 3
        runner.stop()

    def test_batch_by_time(self, bus_with_topic):
        bus = bus_with_topic
        producer = bus.producer()
        dispatches = []

        runner = ConsumerRunner(bus, [
            ConsumerConfig(
                topic="test",
                group="g1",
                batch=BatchConfig(window_seconds=1),
                action=actions.call_function(lambda rs: dispatches.append(list(rs))),
            ),
        ])

        producer.send("test", value={"n": 1})
        producer.flush()
        runner.run_once()
        assert len(dispatches) == 0

        # Manipulate window_start to simulate time passing
        state = runner._batch_states["g1"]
        state.window_start = time.monotonic() - 2  # 2 seconds ago

        runner.run_once()
        assert len(dispatches) == 1
        assert len(dispatches[0]) == 1
        runner.stop()

    def test_batch_count_threshold_exact(self, bus_with_topic):
        """Batch flushes exactly at the count threshold."""
        bus = bus_with_topic
        producer = bus.producer()
        dispatches = []

        runner = ConsumerRunner(bus, [
            ConsumerConfig(
                topic="test",
                group="g1",
                batch=BatchConfig(window_count=2),
                action=actions.call_function(lambda rs: dispatches.append(list(rs))),
            ),
        ])

        producer.send("test", value={"n": 1})
        producer.send("test", value={"n": 2})
        producer.flush()
        runner.run_once()
        assert len(dispatches) == 1
        assert len(dispatches[0]) == 2
        runner.stop()

    def test_batch_both_thresholds_count_first(self, bus_with_topic):
        """When both thresholds set, count triggers first."""
        bus = bus_with_topic
        producer = bus.producer()
        dispatches = []

        runner = ConsumerRunner(bus, [
            ConsumerConfig(
                topic="test",
                group="g1",
                batch=BatchConfig(window_seconds=3600, window_count=2),
                action=actions.call_function(lambda rs: dispatches.append(list(rs))),
            ),
        ])

        producer.send("test", value={"n": 1})
        producer.send("test", value={"n": 2})
        producer.flush()
        runner.run_once()
        assert len(dispatches) == 1
        runner.stop()

    def test_batch_both_thresholds_time_first(self, bus_with_topic):
        """When both thresholds set, time triggers first."""
        bus = bus_with_topic
        producer = bus.producer()
        dispatches = []

        runner = ConsumerRunner(bus, [
            ConsumerConfig(
                topic="test",
                group="g1",
                batch=BatchConfig(window_seconds=1, window_count=100),
                action=actions.call_function(lambda rs: dispatches.append(list(rs))),
            ),
        ])

        producer.send("test", value={"n": 1})
        producer.flush()
        runner.run_once()
        assert len(dispatches) == 0

        # Simulate time passing
        state = runner._batch_states["g1"]
        state.window_start = time.monotonic() - 2

        runner.run_once()  # no new records, but window expired
        assert len(dispatches) == 1
        runner.stop()

    def test_batch_with_filter(self, bus_with_topic):
        """Filter applies before batching."""
        bus = bus_with_topic
        producer = bus.producer()
        dispatches = []

        runner = ConsumerRunner(bus, [
            ConsumerConfig(
                topic="test",
                group="g1",
                filter=lambda r: r.value.get("keep"),
                batch=BatchConfig(window_count=2),
                action=actions.call_function(lambda rs: dispatches.append(list(rs))),
            ),
        ])

        # 3 records but only 2 pass filter
        producer.send("test", value={"keep": True, "n": 1})
        producer.send("test", value={"keep": False, "n": 2})
        producer.send("test", value={"keep": True, "n": 3})
        producer.flush()
        runner.run_once()
        assert len(dispatches) == 1
        assert len(dispatches[0]) == 2
        assert all(r.value["keep"] for r in dispatches[0])
        runner.stop()

    def test_batch_accumulates_across_polls(self, bus_with_topic):
        """Batch accumulates records across multiple run_once calls."""
        bus = bus_with_topic
        producer = bus.producer()
        dispatches = []

        runner = ConsumerRunner(bus, [
            ConsumerConfig(
                topic="test",
                group="g1",
                batch=BatchConfig(window_count=3),
                action=actions.call_function(lambda rs: dispatches.append(list(rs))),
            ),
        ])

        producer.send("test", value={"n": 1})
        producer.flush()
        runner.run_once()
        assert len(dispatches) == 0

        producer.send("test", value={"n": 2})
        producer.flush()
        runner.run_once()
        assert len(dispatches) == 0

        producer.send("test", value={"n": 3})
        producer.flush()
        runner.run_once()
        assert len(dispatches) == 1
        assert len(dispatches[0]) == 3
        runner.stop()

    def test_batch_stop_flushes_pending(self, bus_with_topic):
        """Stopping the runner flushes any pending batch."""
        bus = bus_with_topic
        producer = bus.producer()
        dispatches = []

        runner = ConsumerRunner(bus, [
            ConsumerConfig(
                topic="test",
                group="g1",
                batch=BatchConfig(window_count=100),
                action=actions.call_function(lambda rs: dispatches.append(list(rs))),
            ),
        ])

        producer.send("test", value={"n": 1})
        producer.send("test", value={"n": 2})
        producer.flush()
        runner.run_once()
        assert len(dispatches) == 0  # not enough for batch

        runner.stop()
        assert len(dispatches) == 1  # flushed on stop
        assert len(dispatches[0]) == 2


class TestConsumerRunnerRetries:

    def test_action_failure_no_retry(self, bus_with_topic):
        """With max_retries=0, failure is immediate."""
        bus = bus_with_topic
        producer = bus.producer()
        producer.send("test", value={"n": 1})
        producer.flush()

        call_count = 0
        def fail(records):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("fail")

        runner = ConsumerRunner(bus, [
            ConsumerConfig(
                topic="test",
                group="g1",
                action=actions.call_function(fail),
                max_retries=0,
            ),
        ])
        runner.run_once()
        assert call_count == 1
        runner.stop()

    def test_action_failure_with_retries(self, bus_with_topic):
        """Action is retried max_retries times."""
        bus = bus_with_topic
        producer = bus.producer()
        producer.send("test", value={"n": 1})
        producer.flush()

        call_count = 0
        def fail(records):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("fail")

        runner = ConsumerRunner(bus, [
            ConsumerConfig(
                topic="test",
                group="g1",
                action=actions.call_function(fail),
                max_retries=3,
            ),
        ])
        runner.run_once()
        assert call_count == 4  # 1 initial + 3 retries
        runner.stop()

    def test_action_succeeds_on_retry(self, bus_with_topic):
        """Action that fails then succeeds should work."""
        bus = bus_with_topic
        producer = bus.producer()
        producer.send("test", value={"n": 1})
        producer.flush()

        call_count = 0
        received = []
        def flaky(records):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("transient")
            received.extend(records)

        runner = ConsumerRunner(bus, [
            ConsumerConfig(
                topic="test",
                group="g1",
                action=actions.call_function(flaky),
                max_retries=3,
            ),
        ])
        runner.run_once()
        assert call_count == 3
        assert len(received) == 1
        runner.stop()

    def test_error_action_called_on_exhausted_retries(self, bus_with_topic):
        """Error action fires after all retries are exhausted."""
        bus = bus_with_topic
        producer = bus.producer()
        producer.send("test", value={"n": 1})
        producer.flush()

        error_records = []

        runner = ConsumerRunner(bus, [
            ConsumerConfig(
                topic="test",
                group="g1",
                action=actions.call_function(lambda rs: (_ for _ in ()).throw(RuntimeError("fail"))),
                max_retries=1,
                error_action=actions.call_function(lambda rs: error_records.extend(rs)),
            ),
        ])
        runner.run_once()
        assert len(error_records) == 1
        runner.stop()

    def test_error_action_with_dead_letter(self, bus_with_topic):
        """Dead letter action captures failed records."""
        bus = bus_with_topic
        producer = bus.producer()
        producer.send("test", value={"n": 1}, key="bad-key")
        producer.flush()

        def always_fail(records):
            raise RuntimeError("permanent failure")

        runner = ConsumerRunner(bus, [
            ConsumerConfig(
                topic="test",
                group="g1",
                action=actions.call_function(always_fail),
                max_retries=0,
                error_action=actions.dead_letter(bus, topic="dlq"),
            ),
        ])
        runner.run_once()

        # Check DLQ
        consumer = bus.consumer(group_id="dlq-reader", topics=["dlq"])
        dlq = consumer.poll(timeout_ms=50)
        assert len(dlq) == 1
        assert dlq[0].payload["original_key"] == "bad-key"
        assert dlq[0].payload["original_payload"] == {"n": 1}
        consumer.close()
        runner.stop()

    def test_error_action_failure_is_logged_not_raised(self, bus_with_topic):
        """If error_action also fails, it should be logged but not crash."""
        bus = bus_with_topic
        producer = bus.producer()
        producer.send("test", value={"n": 1})
        producer.flush()

        def always_fail(records):
            raise RuntimeError("action fail")

        def error_also_fails(records):
            raise RuntimeError("error action fail")

        runner = ConsumerRunner(bus, [
            ConsumerConfig(
                topic="test",
                group="g1",
                action=actions.call_function(always_fail),
                error_action=actions.call_function(error_also_fails),
            ),
        ])
        # Should not raise
        runner.run_once()
        runner.stop()


class TestConsumerRunnerMultiConsumer:

    def test_multiple_consumers_different_topics(self, bus):
        bus.create_topic("topic-a", partitions=1)
        bus.create_topic("topic-b", partitions=1)
        producer = bus.producer()
        producer.send("topic-a", value={"src": "a"})
        producer.send("topic-b", value={"src": "b"})
        producer.flush()

        received_a = []
        received_b = []

        runner = ConsumerRunner(bus, [
            ConsumerConfig(
                topic="topic-a",
                group="ga",
                action=actions.call_function(lambda rs: received_a.extend(rs)),
            ),
            ConsumerConfig(
                topic="topic-b",
                group="gb",
                action=actions.call_function(lambda rs: received_b.extend(rs)),
            ),
        ])
        runner.run_once()
        assert len(received_a) == 1
        assert received_a[0].value == {"src": "a"}
        assert len(received_b) == 1
        assert received_b[0].value == {"src": "b"}
        runner.stop()

    def test_multiple_consumers_same_topic_different_groups(self, bus_with_topic):
        bus = bus_with_topic
        producer = bus.producer()
        producer.send("test", value={"n": 1})
        producer.flush()

        received_1 = []
        received_2 = []

        runner = ConsumerRunner(bus, [
            ConsumerConfig(
                topic="test",
                group="g1",
                action=actions.call_function(lambda rs: received_1.extend(rs)),
            ),
            ConsumerConfig(
                topic="test",
                group="g2",
                action=actions.call_function(lambda rs: received_2.extend(rs)),
            ),
        ])
        runner.run_once()
        assert len(received_1) == 1
        assert len(received_2) == 1
        runner.stop()

    def test_run_once_returns_per_group_counts(self, bus):
        bus.create_topic("t1", partitions=1)
        bus.create_topic("t2", partitions=1)
        producer = bus.producer()
        producer.send("t1", value={"n": 1})
        producer.send("t1", value={"n": 2})
        producer.send("t2", value={"n": 3})
        producer.flush()

        runner = ConsumerRunner(bus, [
            ConsumerConfig(topic="t1", group="g1", action=actions.noop()),
            ConsumerConfig(topic="t2", group="g2", action=actions.noop()),
        ])
        results = runner.run_once()
        assert results == {"g1": 2, "g2": 1}
        runner.stop()


class TestConsumerRunnerRunForever:

    def test_run_forever_processes_and_stops(self, bus_with_topic):
        """run_forever processes records and stops on KeyboardInterrupt."""
        bus = bus_with_topic
        producer = bus.producer()
        producer.send("test", value={"n": 1})
        producer.flush()

        received = []
        call_count = 0

        original_run_once = ConsumerRunner.run_once

        def counting_run_once(self_runner):
            nonlocal call_count
            result = original_run_once(self_runner)
            call_count += 1
            if call_count >= 2:
                self_runner._running = False
            return result

        runner = ConsumerRunner(bus, [
            ConsumerConfig(
                topic="test",
                group="g1",
                action=actions.call_function(lambda rs: received.extend(rs)),
            ),
        ])

        with patch.object(ConsumerRunner, 'run_once', counting_run_once):
            runner.run_forever(poll_interval_ms=10)

        assert call_count >= 2
        # Runner should be stopped
        assert not runner._running


class TestConsumerRunnerProduceAction:
    """Test the produce action within the consumer runner (topic chaining)."""

    def test_consume_and_produce_chain(self, bus):
        """Records from topic A are enriched and sent to topic B."""
        bus.create_topic("raw", partitions=1)
        bus.create_topic("enriched", partitions=1)

        producer = bus.producer()
        producer.send("raw", value={"name": "prop1", "price": 100}, key="p1")
        producer.flush()

        runner = ConsumerRunner(bus, [
            ConsumerConfig(
                topic="raw",
                group="enricher",
                action=actions.produce(
                    bus, "enriched",
                    lambda r: {**r.value, "enriched": True, "price_per_sqft": r.value["price"] / 10},
                ),
            ),
        ])
        runner.run_once()

        consumer = bus.consumer(group_id="reader", topics=["enriched"])
        out = consumer.poll(timeout_ms=50)
        assert len(out) == 1
        assert out[0].value["enriched"] is True
        assert out[0].value["price_per_sqft"] == 10.0
        assert out[0].key == "p1"
        consumer.close()
        runner.stop()

    def test_three_stage_pipeline(self, bus):
        """raw -> filtered -> enriched (multi-stage pipeline)."""
        bus.create_topic("stage1", partitions=1)
        bus.create_topic("stage2", partitions=1)
        bus.create_topic("stage3", partitions=1)

        producer = bus.producer()
        producer.send("stage1", value={"n": 10})
        producer.send("stage1", value={"n": 3})
        producer.send("stage1", value={"n": 20})
        producer.flush()

        # Stage 1->2: filter n > 5
        runner1 = ConsumerRunner(bus, [
            ConsumerConfig(
                topic="stage1",
                group="filter",
                filter=lambda r: r.value["n"] > 5,
                action=actions.produce(bus, "stage2", lambda r: r.value),
            ),
        ])
        runner1.run_once()

        # Stage 2->3: enrich
        runner2 = ConsumerRunner(bus, [
            ConsumerConfig(
                topic="stage2",
                group="enrich",
                action=actions.produce(bus, "stage3", lambda r: {**r.value, "big": True}),
            ),
        ])
        runner2.run_once()

        consumer = bus.consumer(group_id="final", topics=["stage3"])
        out = consumer.poll(timeout_ms=50)
        assert len(out) == 2
        assert all(r.value["big"] for r in out)
        values = sorted([r.value["n"] for r in out])
        assert values == [10, 20]
        consumer.close()
        runner1.stop()
        runner2.stop()


class TestConsumerRunnerEdgeCases:

    def test_nonexistent_topic(self, bus):
        """Consumer on nonexistent topic should not crash."""
        runner = ConsumerRunner(bus, [
            ConsumerConfig(
                topic="does-not-exist",
                group="g1",
                action=actions.noop(),
            ),
        ])
        results = runner.run_once()
        assert results == {"g1": 0}
        runner.stop()

    def test_empty_configs_list(self, bus):
        """Runner with no configs should work."""
        runner = ConsumerRunner(bus, [])
        results = runner.run_once()
        assert results == {}
        runner.stop()

    def test_consumer_runner_preserves_record_metadata(self, bus_with_topic):
        """Action receives records with full metadata (key, headers, etc)."""
        bus = bus_with_topic
        producer = bus.producer()
        producer.send("test", value={"msg": "hi"}, key="k1", headers={"source": "test"})
        producer.flush()

        received = []
        runner = ConsumerRunner(bus, [
            ConsumerConfig(
                topic="test",
                group="g1",
                action=actions.call_function(lambda rs: received.extend(rs)),
            ),
        ])
        runner.run_once()
        assert len(received) == 1
        r = received[0]
        assert r.key == "k1"
        assert r.value == {"msg": "hi"}
        assert r.headers == {"source": "test"}
        assert r.topic == "test"
        assert r.partition == 0
        assert r.offset == 0
        assert r.timestamp > 0
        runner.stop()

    def test_large_batch_of_records(self, bus_with_topic):
        """Handle a large number of records without issues."""
        bus = bus_with_topic
        producer = bus.producer()
        for i in range(200):
            producer.send("test", value={"n": i})
        producer.flush()

        received = []
        runner = ConsumerRunner(bus, [
            ConsumerConfig(
                topic="test",
                group="g1",
                action=actions.call_function(lambda rs: received.extend(rs)),
            ),
        ])
        runner.run_once()
        assert len(received) == 200
        runner.stop()

    def test_filter_with_key_based_routing(self, bus_with_topic):
        """Filter can route based on record key."""
        bus = bus_with_topic
        producer = bus.producer()
        producer.send("test", value={"msg": "a"}, key="user-1")
        producer.send("test", value={"msg": "b"}, key="user-2")
        producer.send("test", value={"msg": "c"}, key="user-1")
        producer.flush()

        received = []
        runner = ConsumerRunner(bus, [
            ConsumerConfig(
                topic="test",
                group="g1",
                filter=lambda r: r.key == "user-1",
                action=actions.call_function(lambda rs: received.extend(rs)),
            ),
        ])
        runner.run_once()
        assert len(received) == 2
        assert all(r.key == "user-1" for r in received)
        runner.stop()

    def test_batch_window_resets_after_flush(self, bus_with_topic):
        """After a batch flushes, the window resets for the next batch."""
        bus = bus_with_topic
        producer = bus.producer()
        dispatches = []

        runner = ConsumerRunner(bus, [
            ConsumerConfig(
                topic="test",
                group="g1",
                batch=BatchConfig(window_count=2),
                action=actions.call_function(lambda rs: dispatches.append(list(rs))),
            ),
        ])

        # First batch
        producer.send("test", value={"batch": 1, "n": 1})
        producer.send("test", value={"batch": 1, "n": 2})
        producer.flush()
        runner.run_once()
        assert len(dispatches) == 1

        # Second batch
        producer.send("test", value={"batch": 2, "n": 1})
        producer.send("test", value={"batch": 2, "n": 2})
        producer.flush()
        runner.run_once()
        assert len(dispatches) == 2
        assert len(dispatches[1]) == 2
        runner.stop()

    def test_multi_action_with_produce_and_log(self, bus, caplog):
        """Multi action combining produce and log."""
        bus.create_topic("input", partitions=1)
        bus.create_topic("output", partitions=1)
        producer = bus.producer()
        producer.send("input", value={"n": 42}, key="test-key")
        producer.flush()

        runner = ConsumerRunner(bus, [
            ConsumerConfig(
                topic="input",
                group="g1",
                action=actions.multi(
                    actions.log(template=lambda r: f"Processing {r.key}"),
                    actions.produce(bus, "output", lambda r: {**r.value, "processed": True}),
                ),
            ),
        ])

        with caplog.at_level(logging.INFO, logger="bus.consumers"):
            runner.run_once()

        assert "Processing test-key" in caplog.text

        consumer = bus.consumer(group_id="verify", topics=["output"])
        out = consumer.poll(timeout_ms=50)
        assert len(out) == 1
        assert out[0].value == {"n": 42, "processed": True}
        consumer.close()
        runner.stop()

    def test_produce_preserves_none_key(self, bus_with_topic):
        """Produce action preserves None key on records."""
        bus = bus_with_topic
        bus.create_topic("output", partitions=1)
        action = actions.produce(bus, "output", lambda r: r.value)
        action([make_record(key=None, value={"x": 1})])

        consumer = bus.consumer(group_id="verify", topics=["output"])
        out = consumer.poll(timeout_ms=50)
        assert len(out) == 1
        assert out[0].key is None
        consumer.close()

    def test_double_stop(self, bus_with_topic):
        """Calling stop() twice should not crash."""
        bus = bus_with_topic
        runner = ConsumerRunner(bus, [
            ConsumerConfig(topic="test", group="g1", action=actions.noop()),
        ])
        runner.stop()
        runner.stop()  # should not raise

    def test_stop_clears_internal_state(self, bus_with_topic):
        """After stop(), consumers and batch_states are cleared."""
        bus = bus_with_topic
        runner = ConsumerRunner(bus, [
            ConsumerConfig(
                topic="test", group="g1", action=actions.noop(),
                batch=BatchConfig(window_count=10),
            ),
        ])
        assert len(runner._consumers) == 1
        assert len(runner._batch_states) == 1
        runner.stop()
        assert len(runner._consumers) == 0
        assert len(runner._batch_states) == 0

    def test_stop_without_batch_configs(self, bus_with_topic):
        """Stop with no batch configs closes consumers cleanly."""
        bus = bus_with_topic
        producer = bus.producer()
        producer.send("test", value={"n": 1})
        producer.flush()

        received = []
        runner = ConsumerRunner(bus, [
            ConsumerConfig(
                topic="test", group="g1",
                action=actions.call_function(lambda rs: received.extend(rs)),
            ),
        ])
        runner.run_once()
        assert len(received) == 1
        runner.stop()  # should not raise

    def test_stop_commits_offsets_for_flushed_batch(self, bus_with_topic):
        """After stop flushes a batch, offsets are committed so new consumer doesn't re-read."""
        bus = bus_with_topic
        producer = bus.producer()
        producer.send("test", value={"n": 1})
        producer.flush()

        dispatches = []
        runner = ConsumerRunner(bus, [
            ConsumerConfig(
                topic="test", group="g1",
                batch=BatchConfig(window_count=100),
                action=actions.call_function(lambda rs: dispatches.append(list(rs))),
            ),
        ])
        runner.run_once()
        runner.stop()
        assert len(dispatches) == 1  # flushed

        # New consumer in same group should NOT see those records
        consumer = bus.consumer(group_id="g1", topics=["test"])
        out = consumer.poll(timeout_ms=50)
        assert len(out) == 0
        consumer.close()

    def test_process_consumer_missing_consumer(self, bus_with_topic):
        """_process_consumer returns 0 if consumer is not in _consumers dict."""
        bus = bus_with_topic
        runner = ConsumerRunner(bus, [
            ConsumerConfig(topic="test", group="g1", action=actions.noop()),
        ])
        # Remove the consumer to simulate missing state
        runner._consumers.pop("g1")
        config = runner.configs[0]
        assert runner._process_consumer(config) == 0
        runner.stop()


class TestActionsAdvanced:
    """Additional action tests from review gaps."""

    def test_log_warning_level(self, caplog):
        """Log action with warning level uses logger.warning."""
        action = actions.log(level="warning")
        with caplog.at_level(logging.WARNING, logger="bus.consumers"):
            action([make_record(key="warnkey", value={"warn": True})])
        assert "warnkey" in caplog.text

    def test_log_invalid_level_falls_back(self, caplog):
        """Invalid log level falls back to logger.info."""
        action = actions.log(level="nonexistent_level")
        with caplog.at_level(logging.INFO, logger="bus.consumers"):
            action([make_record(key="fallback")])
        assert "fallback" in caplog.text

    def test_log_multiple_records(self, caplog):
        """Log action logs each record separately."""
        action = actions.log(template=lambda r: f"R:{r.offset}")
        records = [make_record(offset=i) for i in range(3)]
        with caplog.at_level(logging.INFO, logger="bus.consumers"):
            action(records)
        assert "R:0" in caplog.text
        assert "R:1" in caplog.text
        assert "R:2" in caplog.text

    def test_multi_empty_actions(self):
        """Multi with no actions is a no-op."""
        action = actions.multi()
        action([make_record()])  # should not raise

    def test_produce_batch_empty_transform(self, bus_with_topic):
        """produce_batch with transform returning empty list."""
        bus = bus_with_topic
        bus.create_topic("out", partitions=1)
        action = actions.produce_batch(bus, "out", lambda rs: [])
        action([make_record()])  # should not crash

        consumer = bus.consumer(group_id="verify", topics=["out"])
        out = consumer.poll(timeout_ms=50)
        assert len(out) == 0
        consumer.close()

    def test_dead_letter_preserves_all_metadata(self, bus_with_topic):
        """Dead letter envelope has original_partition and original_offset."""
        bus = bus_with_topic
        action = actions.dead_letter(bus, topic="dlq2")
        record = make_record(partition=2, offset=7, key="k", payload={"v": 1})
        action([record])

        consumer = bus.consumer(group_id="verify", topics=["dlq2"])
        out = consumer.poll(timeout_ms=50)
        assert len(out) == 1
        assert out[0].payload["original_partition"] == 2
        assert out[0].payload["original_offset"] == 7
        assert out[0].payload["original_topic"] == "test"
        assert out[0].payload["original_key"] == "k"
        assert out[0].payload["original_payload"] == {"v": 1}
        assert isinstance(out[0].payload["error_time"], int)
        consumer.close()

    def test_run_forever_keyboard_interrupt(self, bus_with_topic):
        """KeyboardInterrupt in run_forever triggers stop()."""
        bus = bus_with_topic

        call_count = 0
        original_run_once = ConsumerRunner.run_once

        def interrupt_run_once(self_runner):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise KeyboardInterrupt()
            return original_run_once(self_runner)

        runner = ConsumerRunner(bus, [
            ConsumerConfig(topic="test", group="g1", action=actions.noop()),
        ])

        with patch.object(ConsumerRunner, 'run_once', interrupt_run_once):
            runner.run_forever(poll_interval_ms=10)

        assert not runner._running
        assert call_count == 2

    def test_batch_init_sets_window_start(self, bus_with_topic):
        """After init, batch state has window_start set (not 0.0)."""
        bus = bus_with_topic
        runner = ConsumerRunner(bus, [
            ConsumerConfig(
                topic="test", group="g1",
                batch=BatchConfig(window_count=10),
                action=actions.noop(),
            ),
        ])
        state = runner._batch_states["g1"]
        assert state.window_start > 0
        runner.stop()
