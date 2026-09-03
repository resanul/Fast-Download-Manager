from fastdm.queue import DownloadQueue, Priority


def test_priority_and_fifo_order():
    queue = DownloadQueue(max_concurrent=1)
    queue.enqueue("low", Priority.LOW)
    queue.enqueue("normal", Priority.NORMAL)
    queue.enqueue("high", Priority.HIGH)
    assert queue.next_ready().task_id == "high"
    queue.mark_started("high")
    queue.mark_finished("high")
    assert queue.next_ready().task_id == "normal"


def test_concurrency_limit():
    queue = DownloadQueue(max_concurrent=2)
    queue.enqueue("a")
    queue.enqueue("b")
    queue.enqueue("c")
    assert queue.mark_started("a")
    assert queue.mark_started("b")
    assert not queue.mark_started("c")
    assert queue.active_count == 2
    queue.mark_finished("a")
    assert queue.next_ready().task_id == "c"
