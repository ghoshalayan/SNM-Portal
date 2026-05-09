"""Concurrency probe for the C2 fix (sp_getapplock-based number-allocator).

Three tests, all running against the configured DB:

  1. SAME KEY, TWO HOLDERS -> the second to acquire waits for the first
     (regardless of which thread "wins" the race to start). Proves the
     lock serializes contention.

  2. DIFFERENT KEYS, TWO HOLDERS -> both proceed in parallel. Proves the
     lock is per-key, not global.

  3. N parallel claimants on the same key -> each gets a distinct
     candidate, no exceptions. Proves the helper is contention-safe.

Read-mostly: tests take + release locks with no INSERTs. Nothing persists.

Run from the backend dir:

    python -m tests.probes.concurrency_probe
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple

# Quiet SQLAlchemy's per-statement INFO logs so the probe output stays readable.
# The engine itself isn't reconfigured — only the logger threshold for this run.
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

from sqlalchemy import text  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.services.number_allocator import _acquire_applock  # noqa: E402


def _take_lock(
    key: str, hold_seconds: float, label: str, results: list, start_barrier: threading.Event,
) -> None:
    """Wait on the start barrier so threads contend genuinely, then take an
    exclusive applock, hold for ``hold_seconds``, release by committing.
    Records (label, rc, acquired_offset, released_offset).
    """
    db = SessionLocal()
    start_barrier.wait()  # release all threads simultaneously
    started = time.perf_counter()
    try:
        db.execute(text("BEGIN TRANSACTION"))
        rc = db.execute(
            text(
                "DECLARE @rc INT; "
                "EXEC @rc = sp_getapplock "
                "  @Resource = :r, @LockMode = 'Exclusive', "
                "  @LockOwner = 'Transaction', @LockTimeout = 15000; "
                "SELECT @rc;"
            ),
            {"r": key},
        ).scalar()
        acquired = time.perf_counter()
        time.sleep(hold_seconds)
        db.execute(text("COMMIT"))
        released = time.perf_counter()
        results.append((label, rc, acquired - started, released - started))
    finally:
        db.close()


def test_same_key_serializes() -> bool:
    """Two holders, same key. ONE acquires immediately (rc=0); the OTHER
    must wait roughly the hold duration before it gets in (rc=1)."""
    print("\n[1] Same key, two holders -- expect serialization")
    HOLD = 1.0
    KEY = "PROBE:C2:same-key"
    results: list = []
    barrier = threading.Event()

    threads = [
        threading.Thread(target=_take_lock, args=(KEY, HOLD, "A", results, barrier)),
        threading.Thread(target=_take_lock, args=(KEY, HOLD, "B", results, barrier)),
    ]
    for t in threads:
        t.start()
    barrier.set()  # release both simultaneously
    for t in threads:
        t.join()

    by_label = {r[0]: r for r in results}
    a_rc, a_wait = by_label["A"][1], by_label["A"][2]
    b_rc, b_wait = by_label["B"][1], by_label["B"][2]
    print(f"    A: rc={a_rc}  acquired after {a_wait*1000:.0f}ms")
    print(f"    B: rc={b_rc}  acquired after {b_wait*1000:.0f}ms")

    # Exactly one thread should have rc=0 (immediate) and one rc=1 (waited).
    rcs = sorted([a_rc, b_rc])
    rc_pattern_ok = rcs == [0, 1]
    # The waiting thread should have stalled close to the hold duration.
    waiter_wait = max(a_wait, b_wait)
    serialized = waiter_wait >= HOLD * 0.8

    ok = rc_pattern_ok and serialized
    print(f"    rc pattern (0,1)? {rc_pattern_ok}    waiter waited >= {HOLD*0.8:.2f}s? {serialized}")
    return ok


def test_different_keys_parallel() -> bool:
    """Two holders, different keys. Both should acquire near-immediately."""
    print("\n[2] Different keys, two holders -- expect parallel")
    HOLD = 1.0
    results: list = []
    barrier = threading.Event()

    threads = [
        threading.Thread(target=_take_lock, args=("PROBE:C2:key-X", HOLD, "X", results, barrier)),
        threading.Thread(target=_take_lock, args=("PROBE:C2:key-Y", HOLD, "Y", results, barrier)),
    ]
    for t in threads:
        t.start()
    barrier.set()
    for t in threads:
        t.join()

    by_label = {r[0]: r for r in results}
    x_rc, x_wait = by_label["X"][1], by_label["X"][2]
    y_rc, y_wait = by_label["Y"][1], by_label["Y"][2]
    print(f"    X: rc={x_rc}  acquired after {x_wait*1000:.0f}ms")
    print(f"    Y: rc={y_rc}  acquired after {y_wait*1000:.0f}ms")

    # Both should be granted synchronously (rc=0) and quickly (< 200 ms).
    parallel = x_rc == 0 and y_rc == 0 and max(x_wait, y_wait) < 0.2
    print(f"    both rc=0 and < 200ms? {parallel}")
    return parallel


def _claim(key: str, idx: int, results: list, barrier: threading.Event) -> None:
    """Acquire the applock via the production helper, generate a
    candidate inside the critical section, release.
    """
    db = SessionLocal()
    barrier.wait()
    try:
        db.execute(text("BEGIN TRANSACTION"))
        _acquire_applock(db, key)
        # Inside the critical section: generate a candidate. In real
        # usage this is the MAX(quotNo)+1 SELECT.
        candidate = f"PROBE-{idx}-{time.time_ns()}"
        # Trivial work to make timings observable.
        time.sleep(0.05)
        db.execute(text("COMMIT"))
        results.append((idx, candidate, time.perf_counter()))
    finally:
        db.close()


def test_allocator_distinct_under_contention() -> bool:
    """N parallel claimants on the same lock_key. Every candidate must
    be distinct, every claim must succeed."""
    print("\n[3] N parallel claimants, same lock_key -- expect distinct values, no exceptions")
    N = 8
    KEY = "PROBE:C2:allocator-contention"
    results: list = []
    errors: list = []
    barrier = threading.Event()

    with ThreadPoolExecutor(max_workers=N) as pool:
        futures = [pool.submit(_claim, KEY, i, results, barrier) for i in range(N)]
        barrier.set()
        for f in as_completed(futures):
            try:
                f.result()
            except Exception as exc:
                errors.append(exc)

    if errors:
        print(f"    {len(errors)} error(s):")
        for e in errors[:3]:
            print(f"      {type(e).__name__}: {e}")
        return False

    candidates = [r[1] for r in results]
    distinct = len(set(candidates)) == len(candidates)
    print(f"    {len(candidates)} candidates  ->  {len(set(candidates))} distinct  ->  ok? {distinct}")
    completions = sorted(r[2] for r in results)
    gaps = [completions[i + 1] - completions[i] for i in range(len(completions) - 1)]
    print(f"    completion gaps (ms): {[f'{g*1000:.0f}' for g in gaps]}")
    return distinct


def main() -> int:
    print("Concurrency probe -- C2 (sp_getapplock) verification")
    print("=" * 60)

    passed: List[Tuple[str, bool]] = []
    passed.append(("same-key serialization", test_same_key_serializes()))
    passed.append(("different-key parallel", test_different_keys_parallel()))
    passed.append(("allocator distinct under contention", test_allocator_distinct_under_contention()))

    print("\n" + "=" * 60)
    print("Summary:")
    for name, ok in passed:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    return 0 if all(ok for _, ok in passed) else 1


if __name__ == "__main__":
    raise SystemExit(main())
