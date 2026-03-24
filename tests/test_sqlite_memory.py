from __future__ import annotations

from agent_memory_os.models import BlockKind, BlockPlane, EventRecord, MemoryBlock, MessageRole

from nanocli.sqlite_memory import SQLiteEventStore, SQLiteHybridRetriever


def test_sqlite_memory_store_round_trip_and_retrieval(tmp_path):
    store = SQLiteEventStore(tmp_path / "state.db")
    namespace = "project:test"
    event = EventRecord(namespace=namespace, role=MessageRole.USER, content="Implement a cache safe planner")
    block = MemoryBlock(
        namespace=namespace,
        plane=BlockPlane.DERIVED,
        kind=BlockKind.SUMMARY,
        text="Cache-safe planner implementation details and retrieval notes",
        tags=["planner", "cache", "implementation"],
    )

    store.append_event(event)
    store.upsert_block(block)

    events = store.list_events(namespace)
    blocks = store.list_blocks(namespace)
    hits = SQLiteHybridRetriever(store).retrieve(namespace=namespace, query="planner cache", top_k=3)

    assert len(events) == 1
    assert events[0].role == MessageRole.USER
    assert len(blocks) == 1
    assert hits
    assert hits[0].block.block_id == block.block_id
