#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""
bus - CLI for the local Kafka-on-SQLite message bus.

Usage:
    bus create-topic <name> [--partitions N] [--retention-days N]
    bus delete-topic <name>
    bus topics
    bus info <topic>
    bus produce <topic> <payload-json> [--key KEY] [--type TYPE] [--source SOURCE] [--headers JSON]
    bus consume <topic> --group GROUP [--follow] [--from-beginning] [--max N]
    bus offsets [--group GROUP] [--topic TOPIC]
    bus groups
    bus seek --group GROUP --topic TOPIC [--to-beginning] [--to-end] [--to-offset N] [--to-timestamp MS]
    bus replay <topic> [--from-offset N] [--from-timestamp MS] [--limit N] [--partition N]
    bus tail <topic> --group GROUP
    bus prune
    bus stats [--topic TOPIC]
"""

import argparse
import json
import sys
import time
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from bus.bus import Bus


def _normalize_timestamp_ms(ts: int) -> int:
    """Auto-detect seconds vs ms timestamps.

    All bus.db timestamps are in Unix milliseconds. But users naturally think
    in seconds. If the value is less than 2e12 (year ~2033 in ms, but year
    ~65000 in seconds), it's likely seconds and should be multiplied by 1000.
    """
    if ts < 2_000_000_000_000:
        return ts * 1000
    return ts


def cmd_create_topic(args):
    with Bus(args.db) as bus:
        retention_ms = args.retention_days * 24 * 60 * 60 * 1000
        created = bus.create_topic(args.name, partitions=args.partitions, retention_ms=retention_ms)
        if created:
            print(f"Created topic '{args.name}' with {args.partitions} partition(s), retention {args.retention_days}d")
        else:
            print(f"Topic '{args.name}' already exists")


def cmd_delete_topic(args):
    with Bus(args.db) as bus:
        deleted = bus.delete_topic(args.name)
        if deleted:
            print(f"Deleted topic '{args.name}' and all its records")
        else:
            print(f"Topic '{args.name}' not found")


def cmd_topics(args):
    with Bus(args.db) as bus:
        topics = bus.list_topics()
        if not topics:
            print("No topics")
            return
        print(f"{'TOPIC':<30} {'PARTITIONS':>10} {'RETENTION':>12}")
        print("-" * 54)
        for t in topics:
            retention_days = t["retention_ms"] / (24 * 60 * 60 * 1000)
            print(f"{t['name']:<30} {t['partitions']:>10} {retention_days:>10.0f}d")


def cmd_info(args):
    with Bus(args.db) as bus:
        info = bus.topic_info(args.topic)
        if not info:
            print(f"Topic '{args.topic}' not found")
            sys.exit(1)

        retention_days = info["retention_ms"] / (24 * 60 * 60 * 1000)
        print(f"Topic: {info['name']}")
        print(f"Partitions: {info['partitions']}")
        print(f"Retention: {retention_days:.0f} days")
        print(f"Total records: {info['total_records']}")
        print()
        print(f"{'PARTITION':>10} {'LATEST OFFSET':>15}")
        print("-" * 27)
        for p, offset in sorted(info["partition_offsets"].items()):
            print(f"{p:>10} {offset:>15}")


def cmd_produce(args):
    with Bus(args.db) as bus:
        try:
            payload = json.loads(args.payload)
        except json.JSONDecodeError as e:
            print(f"Invalid JSON payload: {e}", file=sys.stderr)
            sys.exit(1)

        headers = None
        if args.headers:
            try:
                headers = json.loads(args.headers)
            except json.JSONDecodeError as e:
                print(f"Invalid JSON headers: {e}", file=sys.stderr)
                sys.exit(1)

        producer = bus.producer()
        record = producer.send(
            args.topic,
            payload=payload,
            key=args.key,
            type=args.type,
            source=args.source,
            headers=headers,
        )
        print(f"Produced to {record.topic}[{record.partition}] @ offset {record.offset}")


def cmd_consume(args):
    with Bus(args.db) as bus:
        consumer = bus.consumer(
            group_id=args.group,
            topics=[args.topic],
            auto_offset_reset="earliest" if args.from_beginning else "latest",
        )

        if args.from_beginning:
            consumer.seek_to_beginning()

        try:
            while True:
                records = consumer.poll(
                    timeout_ms=100 if args.follow else 0,
                    max_records=args.max,
                )
                for r in records:
                    _print_record(r)
                consumer.commit()

                if not args.follow:
                    break
        except KeyboardInterrupt:
            pass
        finally:
            consumer.close()


def cmd_offsets(args):
    with Bus(args.db) as bus:
        # Get all consumer groups or filter
        cursor = bus._conn.execute(
            "SELECT DISTINCT group_id FROM consumer_offsets ORDER BY group_id"
        )
        groups = [row[0] for row in cursor.fetchall()]

        if args.group:
            groups = [g for g in groups if g == args.group]

        if not groups:
            print("No consumer group offsets found")
            return

        print(f"{'GROUP':<25} {'TOPIC':<25} {'PARTITION':>10} {'OFFSET':>10} {'LAG':>10}")
        print("-" * 82)

        for group_id in groups:
            query = (
                "SELECT co.topic, co.partition, co.committed_offset "
                "FROM consumer_offsets co WHERE co.group_id = ?"
            )
            params: list = [group_id]
            if args.topic:
                query += " AND co.topic = ?"
                params.append(args.topic)
            query += " ORDER BY co.topic, co.partition"

            cursor = bus._conn.execute(query, params)
            for topic, partition, committed in cursor.fetchall():
                cursor2 = bus._conn.execute(
                    "SELECT COALESCE(MAX(offset), -1) FROM records WHERE topic = ? AND partition = ?",
                    (topic, partition),
                )
                latest = cursor2.fetchone()[0]
                lag = max(0, latest - committed)
                print(f"{group_id:<25} {topic:<25} {partition:>10} {committed:>10} {lag:>10}")


def cmd_groups(args):
    """Show consumer groups with members, generations, and partition assignments."""
    with Bus(args.db) as bus:
        groups = bus.list_consumer_groups()
        if not groups:
            print("No consumer groups")
            return

        for g in groups:
            print(f"Group: {g['group_id']}  (generation {g['generation']})")
            if not g["members"]:
                print("  No active members")
            else:
                for m in g["members"]:
                    status = "alive" if m["alive"] else "DEAD"
                    heartbeat_ago = (_now_ms() - m["last_heartbeat"]) / 1000
                    partitions = ", ".join(
                        f"{p['topic']}:{p['partition']}" for p in m["assigned_partitions"]
                    ) or "(none)"
                    print(
                        f"  {m['consumer_id']}  gen={m['generation']}  "
                        f"status={status}  heartbeat={heartbeat_ago:.1f}s ago  "
                        f"partitions=[{partitions}]"
                    )
            print()


def cmd_seek(args):
    """Seek consumer group offsets without creating a full consumer."""
    with Bus(args.db) as bus:
        if args.to_beginning:
            # Set all partitions for topic to -1
            cursor = bus._conn.execute(
                "SELECT partitions FROM topics WHERE name = ?", (args.topic,)
            )
            row = cursor.fetchone()
            if not row:
                print(f"Topic '{args.topic}' not found", file=sys.stderr)
                sys.exit(1)
            for p in range(row[0]):
                bus.update_offset(args.group, args.topic, p, -1)
            print(f"Seeked group '{args.group}' to beginning of '{args.topic}'")

        elif args.to_end:
            cursor = bus._conn.execute(
                "SELECT partitions FROM topics WHERE name = ?", (args.topic,)
            )
            row = cursor.fetchone()
            if not row:
                print(f"Topic '{args.topic}' not found", file=sys.stderr)
                sys.exit(1)
            for p in range(row[0]):
                cursor2 = bus._conn.execute(
                    "SELECT COALESCE(MAX(offset), -1) FROM records WHERE topic = ? AND partition = ?",
                    (args.topic, p),
                )
                max_offset = cursor2.fetchone()[0]
                bus.update_offset(args.group, args.topic, p, max_offset)
            print(f"Seeked group '{args.group}' to end of '{args.topic}'")

        elif args.to_offset is not None:
            partition = args.partition or 0
            bus.update_offset(args.group, args.topic, partition, args.to_offset - 1)
            print(f"Seeked group '{args.group}' to offset {args.to_offset} of '{args.topic}[{partition}]'")

        elif args.to_timestamp is not None:
            cursor = bus._conn.execute(
                "SELECT partitions FROM topics WHERE name = ?", (args.topic,)
            )
            row = cursor.fetchone()
            if not row:
                print(f"Topic '{args.topic}' not found", file=sys.stderr)
                sys.exit(1)
            for p in range(row[0]):
                cursor2 = bus._conn.execute(
                    "SELECT MIN(offset) - 1 FROM records "
                    "WHERE topic = ? AND partition = ? AND timestamp >= ?",
                    (args.topic, p, _normalize_timestamp_ms(args.to_timestamp)),
                )
                result = cursor2.fetchone()
                if result and result[0] is not None:
                    bus.update_offset(args.group, args.topic, p, result[0])
            print(f"Seeked group '{args.group}' to timestamp {args.to_timestamp} in '{args.topic}'")

        else:
            print("Must specify --to-beginning, --to-end, --to-offset, or --to-timestamp", file=sys.stderr)
            sys.exit(1)


def cmd_replay(args):
    """Read records directly without a consumer group (for debugging/inspection)."""
    with Bus(args.db) as bus:
        query = "SELECT topic, partition, offset, timestamp, key, type, source, payload, headers FROM records WHERE topic = ?"
        params: list = [args.topic]

        if args.partition is not None:
            query += " AND partition = ?"
            params.append(args.partition)

        if args.from_offset is not None:
            query += " AND offset >= ?"
            params.append(args.from_offset)

        if args.from_timestamp is not None:
            query += " AND timestamp >= ?"
            params.append(_normalize_timestamp_ms(args.from_timestamp))

        if hasattr(args, 'type') and args.type:
            query += " AND type = ?"
            params.append(args.type)

        if hasattr(args, 'source') and args.source:
            query += " AND source = ?"
            params.append(args.source)

        query += " ORDER BY partition, offset ASC"

        if args.limit:
            query += " LIMIT ?"
            params.append(args.limit)

        cursor = bus._conn.execute(query, params)
        count = 0
        for topic, partition, offset, ts, key, rec_type, rec_source, payload_json, headers_json in cursor.fetchall():
            ts_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts / 1000))
            key_str = key or "(null)"
            type_str = f" type={rec_type}" if rec_type else ""
            source_str = f" source={rec_source}" if rec_source else ""
            header_str = f" headers={headers_json}" if headers_json else ""
            print(f"[{topic}:{partition}@{offset}] {ts_str} key={key_str}{type_str}{source_str} {payload_json}{header_str}")
            count += 1

        print(f"\n--- {count} record(s) ---")


def cmd_tail(args):
    """Follow a topic from the end (like tail -f). Alias for consume --follow --from-end."""
    with Bus(args.db) as bus:
        consumer = bus.consumer(
            group_id=args.group,
            topics=[args.topic],
            auto_offset_reset="latest",
        )
        consumer.seek_to_end()
        consumer.commit()

        try:
            while True:
                records = consumer.poll(timeout_ms=500)
                for r in records:
                    _print_record(r)
                consumer.commit()
        except KeyboardInterrupt:
            pass
        finally:
            consumer.close()


def cmd_prune(args):
    with Bus(args.db) as bus:
        deleted = bus.prune()
        print(f"Pruned {deleted} record(s) past retention")


def cmd_stats(args):
    with Bus(args.db) as bus:
        if args.topic:
            topics = [args.topic]
        else:
            topics = [t["name"] for t in bus.list_topics()]

        if not topics:
            print("No topics")
            return

        print(f"{'TOPIC':<25} {'RECORDS':>10} {'FIRST':>22} {'LATEST':>22}")
        print("-" * 81)

        for topic in topics:
            cursor = bus._conn.execute(
                "SELECT COUNT(*), MIN(timestamp), MAX(timestamp) FROM records WHERE topic = ?",
                (topic,),
            )
            count, min_ts, max_ts = cursor.fetchone()
            first = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(min_ts / 1000)) if min_ts else "—"
            latest = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(max_ts / 1000)) if max_ts else "—"
            print(f"{topic:<25} {count:>10} {first:>22} {latest:>22}")

        # Consumer groups summary
        groups = bus.list_consumer_groups()
        if groups:
            print()
            print(f"{'CONSUMER GROUP':<30} {'GENERATION':>10} {'MEMBERS':>10}")
            print("-" * 52)
            for g in groups:
                alive = sum(1 for m in g["members"] if m["alive"])
                print(f"{g['group_id']:<30} {g['generation']:>10} {alive:>10}")


def _print_record(r):
    """Print a record in a consistent format."""
    ts_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r.timestamp / 1000))
    key_str = r.key or "(null)"
    type_str = f" type={r.type}" if r.type else ""
    source_str = f" source={r.source}" if r.source else ""
    payload_str = json.dumps(r.payload)
    header_str = ""
    if r.headers:
        header_str = f" headers={json.dumps(r.headers)}"
    print(f"[{r.topic}:{r.partition}@{r.offset}] {ts_str} key={key_str}{type_str}{source_str} {payload_str}{header_str}")


def _now_ms() -> int:
    return int(time.time() * 1000)


def main():
    parser = argparse.ArgumentParser(
        prog="bus",
        description="Local Kafka-on-SQLite message bus",
    )
    parser.add_argument(
        "--db",
        default=str(Path.home() / "dispatch" / "state" / "bus.db"),
        help="Path to bus database (default: ~/dispatch/state/bus.db)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # create-topic
    p = subparsers.add_parser("create-topic", help="Create a new topic")
    p.add_argument("name", help="Topic name")
    p.add_argument("--partitions", type=int, default=1, help="Number of partitions (default: 1)")
    p.add_argument("--retention-days", type=int, default=7, help="Retention in days (default: 7)")

    # delete-topic
    p = subparsers.add_parser("delete-topic", help="Delete a topic and all its records")
    p.add_argument("name", help="Topic name")

    # topics
    subparsers.add_parser("topics", help="List all topics")

    # info
    p = subparsers.add_parser("info", help="Show topic details")
    p.add_argument("topic", help="Topic name")

    # produce
    p = subparsers.add_parser("produce", help="Produce a record to a topic")
    p.add_argument("topic", help="Topic name")
    p.add_argument("payload", help="JSON payload")
    p.add_argument("--key", help="Record key (determines partition)")
    p.add_argument("--type", help="Event type (e.g. message.in, session.restart)")
    p.add_argument("--source", help="Origin system (e.g. imessage, signal, daemon)")
    p.add_argument("--headers", help="JSON headers")

    # consume
    p = subparsers.add_parser("consume", help="Consume records from a topic")
    p.add_argument("topic", help="Topic name")
    p.add_argument("--group", required=True, help="Consumer group ID")
    p.add_argument("--follow", "-f", action="store_true", help="Follow mode (like tail -f)")
    p.add_argument("--from-beginning", action="store_true", help="Start from beginning")
    p.add_argument("--max", type=int, default=500, help="Max records per poll (default: 500)")

    # offsets
    p = subparsers.add_parser("offsets", help="Show consumer group offsets and lag")
    p.add_argument("--group", help="Filter by consumer group")
    p.add_argument("--topic", help="Filter by topic")

    # groups
    subparsers.add_parser("groups", help="Show consumer groups with members and assignments")

    # seek
    p = subparsers.add_parser("seek", help="Seek consumer group offsets")
    p.add_argument("--group", required=True, help="Consumer group ID")
    p.add_argument("--topic", required=True, help="Topic name")
    p.add_argument("--partition", type=int, help="Partition (default: all)")
    p.add_argument("--to-beginning", action="store_true")
    p.add_argument("--to-end", action="store_true")
    p.add_argument("--to-offset", type=int)
    p.add_argument("--to-timestamp", type=int, help="Unix timestamp in ms")

    # replay
    p = subparsers.add_parser("replay", help="Replay records (no consumer group, direct read)")
    p.add_argument("topic", help="Topic name")
    p.add_argument("--partition", type=int, help="Filter by partition")
    p.add_argument("--from-offset", type=int, help="Start from offset (per-partition)")
    p.add_argument("--from-timestamp", type=int, help="Start from timestamp (unix ms)")
    p.add_argument("--type", help="Filter by event type")
    p.add_argument("--source", help="Filter by source system")
    p.add_argument("--limit", type=int, help="Max records to show")

    # tail
    p = subparsers.add_parser("tail", help="Follow topic from end (like tail -f)")
    p.add_argument("topic", help="Topic name")
    p.add_argument("--group", default="tail-debug", help="Consumer group (default: tail-debug)")

    # prune
    subparsers.add_parser("prune", help="Delete records past retention period")

    # stats
    p = subparsers.add_parser("stats", help="Show bus statistics")
    p.add_argument("--topic", help="Filter by topic")

    args = parser.parse_args()

    commands = {
        "create-topic": cmd_create_topic,
        "delete-topic": cmd_delete_topic,
        "topics": cmd_topics,
        "info": cmd_info,
        "produce": cmd_produce,
        "consume": cmd_consume,
        "offsets": cmd_offsets,
        "groups": cmd_groups,
        "seek": cmd_seek,
        "replay": cmd_replay,
        "tail": cmd_tail,
        "prune": cmd_prune,
        "stats": cmd_stats,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
