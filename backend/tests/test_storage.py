"""Coverage for the SQLite-backed storage layer itself (app/db.py,
app/storage.py, app/parameters/storage.py) — round-trips through real
SQLite (not mocked), plus the one behavior change that mattered most:
a version collision for the same project now fails loudly and retryably
instead of one BOM silently overwriting another.
"""

import threading
import uuid

import pytest

from app.parameters.schema import BOM, COC
from app.parameters.storage import (
    create_bom_version,
    get_active_bom,
    get_next_bom_version,
    list_boms,
    list_cocs_for_bom,
    load_bom,
    load_coc,
    save_bom,
    save_coc,
)
from app.storage import list_parsed, load_parsed, save_parsed
from tests.factories import make_bom_item, make_parsed_document


def _bom(project_id: str, version: int, status: str = "active", **kwargs) -> BOM:
    return BOM(
        bom_id=str(uuid.uuid4()),
        project_id=project_id,
        parsed_document_id=str(uuid.uuid4()),
        filename="bom.xlsx",
        version=version,
        status=status,
        items=[make_bom_item(part_id="ABC-123", quantity=10)],
        **kwargs,
    )


def test_save_and_load_bom_round_trips():
    bom = _bom("proj-a", 1)
    save_bom(bom)

    loaded = load_bom(bom.bom_id)

    assert loaded is not None
    assert loaded.bom_id == bom.bom_id
    assert loaded.items[0].part_id == "ABC-123"


def test_load_bom_missing_returns_none():
    assert load_bom("does-not-exist") is None


def test_list_boms_orders_newest_first():
    older = _bom("proj-b", 1)
    save_bom(older)
    newer = _bom("proj-b", 2)
    save_bom(newer)

    boms = list_boms()

    assert boms[0].bom_id == newer.bom_id


def test_get_active_bom_and_next_version_track_supersession():
    v1 = _bom("proj-c", 1, status="active")
    save_bom(v1)

    assert get_active_bom("proj-c").bom_id == v1.bom_id
    assert get_next_bom_version("proj-c") == (2, v1)

    v1.status = "superseded"
    save_bom(v1)  # re-save (UPDATE path via ON CONFLICT(bom_id))
    v2 = _bom("proj-c", 2, status="active")
    save_bom(v2)

    assert get_active_bom("proj-c").bom_id == v2.bom_id
    assert get_next_bom_version("proj-c") == (3, v2)


def test_get_active_bom_no_project_returns_none():
    assert get_active_bom("no-such-project") is None


def test_save_bom_version_collision_raises_value_error_not_silent_overwrite():
    # Simulates the race: two BOMs for the same project computed the same
    # "next version" before either was saved. The second save must fail
    # loudly (and distinctly, as a bom_id — not overwrite the first).
    first = _bom("proj-d", 1)
    save_bom(first)

    colliding = _bom("proj-d", 1)  # same project + version, different bom_id
    with pytest.raises(ValueError, match="version conflict"):
        save_bom(colliding)

    # The first BOM must still be intact, not overwritten.
    assert load_bom(first.bom_id) is not None
    assert load_bom(colliding.bom_id) is None


def test_concurrent_uploads_for_same_project_do_not_silently_corrupt():
    # save_bom's UNIQUE(project_id, version) safety net in isolation — if
    # something upstream ever races into a genuine version collision, this
    # fails loudly and retryably rather than one BOM silently overwriting
    # another. bom_service.ingest_bom itself no longer goes through this
    # two-call read-then-write shape (see the create_bom_version test
    # below, which closes the race outright rather than just failing safe).
    project_id = "proj-concurrent"
    save_bom(_bom(project_id, 1, status="active"))

    barrier = threading.Barrier(2)
    succeeded: list[BOM] = []
    failed: list[ValueError] = []

    def upload():
        version, prior = get_next_bom_version(project_id)
        barrier.wait()  # hold both threads here until both have read the same prior state
        try:
            if prior is not None:
                prior.status = "superseded"
                save_bom(prior)
            new_bom = _bom(project_id, version, status="active")
            save_bom(new_bom)
            succeeded.append(new_bom)
        except ValueError as exc:
            failed.append(exc)

    threads = [threading.Thread(target=upload) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Exactly one upload wins with version 2; the other fails loudly
    # (retryable) instead of silently overwriting the winner's BOM.
    assert len(succeeded) == 1
    assert len(failed) == 1
    assert succeeded[0].version == 2
    assert load_bom(succeeded[0].bom_id) is not None


def test_create_bom_version_fully_closes_the_race():
    # The real write path (bom_service.ingest_bom -> create_bom_version):
    # two concurrent calls for the same project, released together via the
    # barrier at the point where each has committed to *starting* its
    # transaction. Unlike the save_bom-level test above, BOTH must succeed
    # here — with sequential versions — because BEGIN IMMEDIATE serializes
    # them instead of letting them both read the same "next version".
    project_id = "proj-atomic"
    create_bom_version(project_id, lambda v: _bom(project_id, v))

    barrier = threading.Barrier(2)
    results: list[BOM] = []
    errors: list[Exception] = []

    def upload():
        barrier.wait()
        try:
            results.append(create_bom_version(project_id, lambda v: _bom(project_id, v)))
        except Exception as exc:  # noqa: BLE001 - want to see anything unexpected too
            errors.append(exc)

    threads = [threading.Thread(target=upload) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert len(results) == 2
    assert sorted(r.version for r in results) == [2, 3]
    # Both actually persisted, not just returned.
    for r in results:
        assert load_bom(r.bom_id) is not None
    # Exactly one is active (the later version); the other got superseded.
    active = get_active_bom(project_id)
    assert active.version == 3


def test_updating_an_existing_bom_does_not_trip_the_version_constraint():
    # Re-saving the SAME bom_id (e.g. flipping status to superseded) must
    # not be treated as a new conflicting row.
    bom = _bom("proj-e", 1)
    save_bom(bom)

    bom.status = "superseded"
    save_bom(bom)  # should not raise

    assert load_bom(bom.bom_id).status == "superseded"


def test_save_and_load_coc_round_trips_and_filters_by_bom():
    bom = _bom("proj-f", 1)
    save_bom(bom)

    coc = COC(
        coc_id=str(uuid.uuid4()),
        bom_id=bom.bom_id,
        parsed_document_id=str(uuid.uuid4()),
        filename="coc.pdf",
        matched_item_id=bom.items[0].item_id,
        fields=[],
        validations=[],
    )
    save_coc(coc)

    assert load_coc(coc.coc_id).coc_id == coc.coc_id
    assert [c.coc_id for c in list_cocs_for_bom(bom.bom_id)] == [coc.coc_id]
    assert list_cocs_for_bom("some-other-bom-id") == []


def test_save_and_load_parsed_document_round_trips():
    doc = make_parsed_document(table_rows=[["Part No."], ["ABC-123"]], filename="doc.pdf")
    save_parsed(doc)

    loaded = load_parsed(doc.document_id)
    assert loaded is not None
    assert loaded.filename == "doc.pdf"

    summaries = list_parsed()
    assert any(s.document_id == doc.document_id for s in summaries)


def test_load_parsed_missing_returns_none():
    assert load_parsed("does-not-exist") is None
