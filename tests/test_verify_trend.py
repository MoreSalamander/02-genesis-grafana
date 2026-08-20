"""The trend bar of verification.

A fix that worked shows up as the queue CRESTING — a peak, then a strict
drain — long before the backlog is gone. These are hermetic unit tests of
the judgment itself: no sleeps, no network, no farm.
"""
from app.agents.executive.executive import OperationalExecutive


def _h(*queues: float, gpu: float = 90.0) -> list[dict[str, float]]:
    return [{"render_queue_depth": q, "gpu_utilization_pct": gpu} for q in queues]


BEFORE = {"render_queue_depth": 256.0, "gpu_utilization_pct": 94.2, "render_latency_s": 6.4}


def test_crest_passes_when_queue_peaks_then_drains():
    note = OperationalExecutive._crested(_h(261, 270, 279, 283, 281, 276, 271, 265), BEFORE)
    assert "crested at 283" in note
    assert "draining" in note and "trend reversal" in note


def test_still_climbing_never_crests():
    assert OperationalExecutive._crested(_h(261, 270, 279, 284, 290, 295, 301, 308), BEFORE) == ""


def test_flat_wobble_is_not_a_drain():
    assert OperationalExecutive._crested(_h(279, 280, 281, 280, 281, 280, 279, 280), BEFORE) == ""


def test_gpu_worse_blocks_the_crest_even_if_queue_drains():
    hist = _h(261, 270, 279, 283, 276, 268, 260, 252, gpu=99.0)
    assert OperationalExecutive._crested(hist, BEFORE) == ""


def test_short_history_never_crests():
    assert OperationalExecutive._crested(_h(283, 270, 258), BEFORE) == ""


def test_trajectory_names_the_failure_mode():
    climbing = OperationalExecutive._trajectory(_h(261, 270, 279, 290))
    assert "still climbing" in climbing and "261" in climbing and "290" in climbing
    cresting = OperationalExecutive._trajectory(_h(261, 279, 275, 274))
    assert "drain not yet confirmed" in cresting
