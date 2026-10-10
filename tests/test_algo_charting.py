import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import algo_scanner as A
from algo_charting import build_algo_chart
from test_algo_scanner import build, AFTER_CLOSE


def _walk(node, found):
    if isinstance(node, dict):
        enc = node.get("encoding")
        if enc and "x" in enc:
            found.append(enc["x"])
        for v in node.values():
            _walk(v, found)
    elif isinstance(node, list):
        for v in node:
            _walk(v, found)


def test_every_x_encoding_uses_the_fixed_domain():
    """Regression: layers with a default quantitative x scale pulled the axis
    down to 0, squeezing all candles into a sliver on the right."""
    r = A.scan_symbol("X", build(n=140, spike_at=127), now=AFTER_CLOSE)
    found = []
    _walk(build_algo_chart(r).to_dict(), found)
    assert found
    for x in found:
        assert x.get("scale", {}).get("domain"), x
        assert x["scale"].get("zero") is False
