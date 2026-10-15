"""Tests for utils.concurrency (no network, no real sleeping)."""

import threading
import unittest

from utils.concurrency import parallel_map, retry_call


def _no_sleep(_seconds: float) -> None:
    """Stand-in for ``time.sleep`` so backoff does not slow the tests."""
    return None


class TestRetryCall(unittest.TestCase):
    def test_returns_value_without_retrying(self):
        calls = []

        def func():
            calls.append(1)
            return "ok"

        self.assertEqual(retry_call(func, sleep=_no_sleep), "ok")
        self.assertEqual(len(calls), 1)

    def test_retries_until_success(self):
        attempts = []

        def flaky():
            attempts.append(1)
            if len(attempts) < 3:
                raise RuntimeError("transient")
            return "recovered"

        self.assertEqual(retry_call(flaky, attempts=3, sleep=_no_sleep), "recovered")
        self.assertEqual(len(attempts), 3)

    def test_reraises_after_exhausting_attempts(self):
        calls = []

        def always_fails():
            calls.append(1)
            raise ValueError("nope")

        with self.assertRaises(ValueError):
            retry_call(always_fails, attempts=2, sleep=_no_sleep)
        self.assertEqual(len(calls), 2)

    def test_backs_off_exponentially(self):
        delays = []

        def always_fails():
            raise RuntimeError("nope")

        with self.assertRaises(RuntimeError):
            retry_call(
                always_fails, attempts=3, backoff=0.5, sleep=delays.append
            )
        self.assertEqual(delays, [0.5, 1.0])


class TestParallelMap(unittest.TestCase):
    def test_empty_items(self):
        self.assertEqual(parallel_map(lambda x: x, []), [])

    def test_preserves_input_order(self):
        results = parallel_map(lambda x: x * 2, [5, 3, 1, 4, 2], max_workers=4)
        self.assertEqual([item for item, _, _ in results], [5, 3, 1, 4, 2])
        self.assertEqual([value for _, value, _ in results], [10, 6, 2, 8, 4])

    def test_single_item_runs_inline(self):
        results = parallel_map(lambda x: x + 1, [41])
        self.assertEqual(results, [(41, 42, None)])

    def test_failures_do_not_abort_the_batch(self):
        def maybe_fail(value):
            if value == 2:
                raise RuntimeError("boom")
            return value

        results = parallel_map(maybe_fail, [1, 2, 3], max_workers=3)
        self.assertEqual([value for _, value, _ in results], [1, None, 3])
        errors = [error for _, _, error in results]
        self.assertIsNone(errors[0])
        self.assertIsInstance(errors[1], RuntimeError)
        self.assertIsNone(errors[2])

    def test_retries_each_item(self):
        attempts = {}

        def flaky(value):
            attempts[value] = attempts.get(value, 0) + 1
            if attempts[value] < 2:
                raise RuntimeError("transient")
            return value

        results = parallel_map(flaky, [1, 2], max_workers=2, attempts=3)
        self.assertEqual([value for _, value, _ in results], [1, 2])
        self.assertEqual(attempts, {1: 2, 2: 2})

    def test_runs_workers_concurrently(self):
        barrier = threading.Barrier(3, timeout=5)

        def wait_for_peers(value):
            barrier.wait()  # deadlocks if the three items do not overlap
            return value

        results = parallel_map(wait_for_peers, [1, 2, 3], max_workers=3)
        self.assertEqual([value for _, value, _ in results], [1, 2, 3])

    def test_max_workers_one_is_sequential(self):
        results = parallel_map(lambda x: x, [1, 2, 3], max_workers=1)
        self.assertEqual([value for _, value, _ in results], [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
