"""
Concurrency tests for WorkerManager thread-start guards.

Covers Mimir s-39 finding S-2: every thread-start site was a check-then-act
pair —

    if workers.scan_thread and workers.scan_thread.is_alive():
        return "already running"
    workers.scan_thread = threading.Thread(...); workers.scan_thread.start()

— with no lock. The HTTP routes and the pywebview bridge share one
WorkerManager instance, so two callers could both pass the check and both
launch a worker against the same files.

`WorkerManager.start_worker` closes that window: check and start happen
under one lock.
"""

import os
import sys
import threading
import unittest

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from web.workers import WorkerManager


class _ParkedLivenessCheck:
    """A not-alive thread stand-in whose first `is_alive()` parks.

    This holds the check-then-act window open deterministically so a second
    caller can be released into it. Without a lock, both callers observe
    "not running" and both start. With a lock, the second caller cannot
    enter until the first has already installed a live thread.
    """

    def __init__(self, entered, proceed):
        self._entered = entered
        self._proceed = proceed
        self._calls = 0

    def is_alive(self):
        self._calls += 1
        if self._calls == 1:
            self._entered.set()
            self._proceed.wait(timeout=5)
        return False


class TestStartWorkerBasics(unittest.TestCase):

    def setUp(self):
        self.wm = WorkerManager()
        self.release = threading.Event()
        self.ran = threading.Event()

    def tearDown(self):
        self.release.set()
        thread = getattr(self.wm, "scan_thread", None)
        if thread is not None and hasattr(thread, "join"):
            thread.join(timeout=5)

    def _worker(self):
        self.ran.set()
        self.release.wait(timeout=5)

    def test_starts_when_idle(self):
        started = self.wm.start_worker("scan_thread", self._worker)

        self.assertTrue(started)
        self.assertTrue(self.ran.wait(timeout=5))
        self.assertIsNotNone(self.wm.scan_thread)

    def test_refuses_while_worker_is_alive(self):
        self.assertTrue(self.wm.start_worker("scan_thread", self._worker))
        self.assertTrue(self.ran.wait(timeout=5))
        first = self.wm.scan_thread

        second = self.wm.start_worker("scan_thread", self._worker)

        self.assertFalse(second)
        self.assertIs(self.wm.scan_thread, first)

    def test_starts_again_once_previous_worker_finished(self):
        self.assertTrue(self.wm.start_worker("scan_thread", self._worker))
        self.assertTrue(self.ran.wait(timeout=5))
        self.release.set()
        self.wm.scan_thread.join(timeout=5)

        self.release.clear()
        self.ran.clear()

        self.assertTrue(self.wm.start_worker("scan_thread", self._worker))
        self.assertTrue(self.ran.wait(timeout=5))

    def test_passes_args_to_target(self):
        seen = []

        def target(a, b):
            seen.append((a, b))
            self.release.wait(timeout=5)

        self.assertTrue(
            self.wm.start_worker("scan_thread", target, ("x", 2)))
        self.release.set()
        self.wm.scan_thread.join(timeout=5)

        self.assertEqual(seen, [("x", 2)])

    def test_worker_thread_is_daemon(self):
        self.wm.start_worker("scan_thread", self._worker)
        self.assertTrue(self.wm.scan_thread.daemon)


class TestStartWorkerCancelEvent(unittest.TestCase):

    def setUp(self):
        self.wm = WorkerManager()
        self.release = threading.Event()
        self.ran = threading.Event()

    def tearDown(self):
        self.release.set()
        thread = getattr(self.wm, "scan_thread", None)
        if thread is not None and hasattr(thread, "join"):
            thread.join(timeout=5)

    def _worker(self):
        self.ran.set()
        self.release.wait(timeout=5)

    def test_fresh_cancel_event_on_successful_start(self):
        stale = self.wm.scan_cancel
        stale.set()

        self.wm.start_worker(
            "scan_thread", self._worker, cancel_attr="scan_cancel")

        self.assertIsNot(self.wm.scan_cancel, stale)
        self.assertFalse(self.wm.scan_cancel.is_set())

    def test_running_workers_cancel_event_is_not_clobbered_on_refusal(self):
        """A refused start must not hand the running worker a new event.

        If it did, a subsequent cancel would set an event nobody is watching
        and the running worker would never stop.
        """
        self.wm.start_worker(
            "scan_thread", self._worker, cancel_attr="scan_cancel")
        self.assertTrue(self.ran.wait(timeout=5))
        live_event = self.wm.scan_cancel

        refused = self.wm.start_worker(
            "scan_thread", self._worker, cancel_attr="scan_cancel")

        self.assertFalse(refused)
        self.assertIs(self.wm.scan_cancel, live_event)


class TestStartWorkerBeforeStartHook(unittest.TestCase):
    """Callers that prime progress dicts must do so under the same lock.

    Several bridge methods set progress to "running" between the guard and
    the thread start. Left outside the lock, a refused start would still
    advertise a run that never began.
    """

    def setUp(self):
        self.wm = WorkerManager()
        self.release = threading.Event()
        self.ran = threading.Event()

    def tearDown(self):
        self.release.set()
        thread = getattr(self.wm, "scan_thread", None)
        if thread is not None and hasattr(thread, "join"):
            thread.join(timeout=5)

    def _worker(self):
        self.ran.set()
        self.release.wait(timeout=5)

    def test_before_start_runs_on_successful_start(self):
        calls = []
        self.wm.start_worker(
            "scan_thread", self._worker,
            before_start=lambda: calls.append("primed"))

        self.assertEqual(calls, ["primed"])

    def test_before_start_runs_before_the_worker_does(self):
        order = []

        def prime():
            order.append("prime")

        def worker():
            order.append("worker")
            self.release.wait(timeout=5)

        self.wm.start_worker("scan_thread", worker, before_start=prime)
        self.release.set()
        self.wm.scan_thread.join(timeout=5)

        self.assertEqual(order, ["prime", "worker"])

    def test_before_start_is_skipped_when_start_is_refused(self):
        calls = []
        self.assertTrue(self.wm.start_worker("scan_thread", self._worker))
        self.assertTrue(self.ran.wait(timeout=5))

        refused = self.wm.start_worker(
            "scan_thread", self._worker,
            before_start=lambda: calls.append("primed"))

        self.assertFalse(refused)
        self.assertEqual(calls, [])


class TestStartWorkerRace(unittest.TestCase):
    """The finding itself: two callers must not both win the guard."""

    def setUp(self):
        self.wm = WorkerManager()
        self.release = threading.Event()
        self.started_count = 0
        self.count_lock = threading.Lock()

    def tearDown(self):
        self.release.set()

    def _worker(self):
        with self.count_lock:
            self.started_count += 1
        self.release.wait(timeout=5)

    def test_only_one_caller_wins_a_contended_start(self):
        entered = threading.Event()
        proceed = threading.Event()
        self.wm.scan_thread = _ParkedLivenessCheck(entered, proceed)

        results = {}

        def caller(name):
            results[name] = self.wm.start_worker("scan_thread", self._worker)

        first = threading.Thread(target=caller, args=("a",), daemon=True)
        first.start()

        # Wait until caller "a" is parked inside the check-then-act window.
        self.assertTrue(entered.wait(timeout=5))

        second = threading.Thread(target=caller, args=("b",), daemon=True)
        second.start()
        second.join(timeout=0.5)

        proceed.set()
        first.join(timeout=5)
        second.join(timeout=5)

        self.assertEqual(
            sorted(results.values()), [False, True],
            "exactly one caller should have started a worker, got: "
            + repr(results),
        )

        self.release.set()
        self.assertEqual(
            self.started_count, 1,
            "exactly one worker thread should have run",
        )

    def test_many_concurrent_callers_start_exactly_one_worker(self):
        contenders = 24
        ready = threading.Barrier(contenders)
        wins = []
        wins_lock = threading.Lock()

        def caller():
            ready.wait(timeout=5)
            won = self.wm.start_worker("scan_thread", self._worker)
            with wins_lock:
                wins.append(won)

        threads = [threading.Thread(target=caller, daemon=True)
                   for _ in range(contenders)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        self.assertEqual(wins.count(True), 1)
        self.assertEqual(wins.count(False), contenders - 1)


class TestThreadLockExists(unittest.TestCase):

    def test_manager_exposes_a_reentrant_thread_lock(self):
        wm = WorkerManager()
        self.assertTrue(hasattr(wm, "_thread_lock"))
        # RLock so a lock-holding caller can nest without deadlocking.
        self.assertTrue(wm._thread_lock.acquire(blocking=False))
        self.assertTrue(wm._thread_lock.acquire(blocking=False))
        wm._thread_lock.release()
        wm._thread_lock.release()


if __name__ == "__main__":
    unittest.main()
