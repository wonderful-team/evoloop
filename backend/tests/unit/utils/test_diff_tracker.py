"""Unit tests for ``DiffTracker`` 并发安全（模块级全局可变状态的锁保护）。

覆盖：并发 capture/drop/get 不丢数据、不抛异常；快照键按 thread 隔离。
"""

import threading

from app.utils.diff import DiffTracker


class TestDiffTrackerConcurrency:
    def test_concurrent_capture_and_drop(self, tmp_path):
        """并发 capture / get / drop：操作不竞争、结果一致。"""
        tracker = DiffTracker()
        p = tmp_path / "f.txt"
        p.write_text("hello\n", encoding="utf-8")

        errors: list[BaseException] = []

        def _worker(idx: int):
            try:
                for _ in range(50):
                    tracker.capture_snapshot(str(p), f"t-{idx}")
                    assert tracker.get_snapshot(str(p), f"t-{idx}") == "hello\n"
                    tracker.drop_snapshot(str(p), f"t-{idx}")
            except BaseException as e:  # noqa: BLE001 - 汇聚到主线程断言
                errors.append(e)

        threads = [threading.Thread(target=_worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert tracker.get_snapshot_count() == 0

    def test_concurrent_capture_same_key_no_loss(self, tmp_path):
        """同 key 并发写入：最终只保留一个快照，不产生 dict 损坏。"""
        tracker = DiffTracker()
        p = tmp_path / "f.txt"
        p.write_text("x\n", encoding="utf-8")

        def _worker():
            for _ in range(100):
                tracker.capture_snapshot(str(p), "t-shared")

        threads = [threading.Thread(target=_worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert tracker.get_snapshot_count("t-shared") == 1
        assert tracker.get_snapshot(str(p), "t-shared") == "x\n"
