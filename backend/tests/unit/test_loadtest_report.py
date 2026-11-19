"""Load-test report parsing (the numbers in loadtest/results come from here)."""

from pathlib import Path

from loadtest.run import read_stats, render

LOCUST_CSV = (
    "Type,Name,Request Count,Failure Count,Median Response Time,"
    "Average Response Time,Min Response Time,Max Response Time,"
    "Average Content Size,Requests/s,Failures/s,50%,66%,75%,80%,90%,95%,98%,"
    "99%,99.9%,99.99%,100%\n"
    "POST,/api/v1/analyze,152,0,6200,6150.5,4100,7600,900,2.59,0,6200,6500,"
    "6700,6800,7000,7200,7300,7400,7600,7600,7600\n"
)


def test_locust_csv_is_read_into_seconds_friendly_stats(tmp_path: Path) -> None:
    (tmp_path / "run_stats.csv").write_text(LOCUST_CSV, encoding="utf-8")

    stats = read_stats(tmp_path / "run")

    assert stats["/api/v1/analyze"] == {
        "requests": 152,
        "failures": 0,
        "p50_ms": 6200.0,
        "p95_ms": 7200.0,
        "p99_ms": 7400.0,
        "mean_ms": 6150.5,
        "rps": 2.59,
    }


def test_markdown_states_the_simulation_settings(tmp_path: Path) -> None:
    (tmp_path / "run_stats.csv").write_text(LOCUST_CSV, encoding="utf-8")
    record = {
        "started_at": "2026-11-19T08:42:11+00:00",
        "git_commit": "abc1234",
        "settings": {"users": 20, "duration": 60, "latency": 1.5, "jitter": 0.5},
        "note": "simulated",
        "stats": read_stats(tmp_path / "run"),
    }

    text = render(record)

    assert "20 users for 60 s; simulated model latency 1.5 ± 0.5 s" in text
    assert (
        "| /api/v1/analyze | 152 | 0 | 6.20 s | 7.20 s | 7.40 s | 2.59 req/s |" in text
    )
