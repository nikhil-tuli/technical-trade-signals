"""Smoke test: Algo Signals page runs end to end with a stubbed fetch."""
import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_algo_scanner import build  # noqa: E402

PAGE = str(Path(__file__).resolve().parent.parent / "pages" / "2_Algo_Signals.py")


@pytest.fixture
def stub_fetch(monkeypatch):
    import data_fetch
    data = {"AAA": build(n=80, spike_at=60), "BBB": build(n=80), "CCC": build(n=10)}

    def fake(symbols, period="18mo", progress_callback=None):
        out = {s: data[s] for s in symbols if s in data}
        fails = {s: "empty response" for s in symbols if s not in data}
        if progress_callback:
            for i, s in enumerate(symbols, 1):
                progress_callback(i, len(symbols), s)
        return out, fails
    monkeypatch.setattr(data_fetch, "fetch_universe", fake)


def test_page_scan_custom(stub_fetch, monkeypatch):
    import algo_scanner
    import datetime as dt
    monkeypatch.setattr(algo_scanner, "now_ist",
                        lambda: dt.datetime(2026, 10, 10, 18, 0, tzinfo=algo_scanner.IST))
    at = AppTest.from_file(PAGE, default_timeout=30).run()
    assert not at.exception
    assert any("Run scan" in i.value for i in at.info)
    at.selectbox(key="algo_universe").select("Custom").run()
    at.text_input(key="algo_custom").input("AAA, BBB, CCC, ZZZ").run()
    at.button(key="algo_run").click().run()
    assert not at.exception, at.exception
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Triggered breakouts"] == "1"
    assert metrics["Stocks scanned"] == "3"
    assert at.dataframe  # table + failures
    assert not at.error
