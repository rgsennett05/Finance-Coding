"""Checks the dashboard's math and log reading (no internet needed)."""
import json
from datetime import date

import pandas as pd

from dashboard.data import latest_run, performance_vs_benchmark, run_logs


def test_performance_starts_both_lines_at_zero_on_funding_day():
    days = [date(2026, 11, d) for d in (1, 2, 3, 4)]
    fund = pd.Series([0, 100_000, 101_000, 99_000], index=days)       # funded on day 2
    voo = pd.Series([600, 610, 616.1, 610], index=days)
    df = performance_vs_benchmark(fund, voo)
    f = df[df.series == "Trading City"].set_index("date")["pct"]
    v = df[df.series == "VOO"].set_index("date")["pct"]
    assert days[0] not in f.index                                       # unfunded day dropped
    assert f[days[1]] == 0 and v[days[1]] == 0
    assert round(f[days[2]], 4) == 0.01 and round(v[days[2]], 4) == 0.01


def test_performance_with_no_money_is_empty():
    assert performance_vs_benchmark(pd.Series([0.0, 0.0]), pd.Series([1.0, 2.0])).empty


def test_run_logs_newest_first_and_skips_broken_files(tmp_path):
    (tmp_path / "run_2026-11-01_100000.json").write_text(json.dumps({"mode": "paper"}))
    (tmp_path / "run_2026-11-02_100000.json").write_text(json.dumps({"mode": "dry-run"}))
    (tmp_path / "run_2026-11-03_100000.json").write_text("{not json")
    runs = run_logs(tmp_path)
    assert [r["mode"] for r in runs] == ["dry-run", "paper"]
    assert latest_run(tmp_path, include_dry_runs=False)["mode"] == "paper"


def test_benchmark_is_based_on_its_close_before_a_weekend_start():
    fund = pd.Series([100_000, 101_000], index=[date(2026, 10, 31), date(2026, 11, 2)])   # Sat, Mon
    voo = pd.Series([600, 606], index=[date(2026, 10, 30), date(2026, 11, 2)])             # Fri, Mon
    df = performance_vs_benchmark(fund, voo)
    v = df[df.series == "VOO"].set_index("date")["pct"]
    assert v[date(2026, 10, 31)] == 0 and round(v[date(2026, 11, 2)], 4) == 0.01
