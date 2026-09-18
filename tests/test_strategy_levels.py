"""Rounded entry/SL/TP must still satisfy the advertised R:R.

Regression: TP was rounded from unrounded levels, so the rounded trio could
read 1.998 (displayed as "Risk-reward 2.00 < 2.0") and get rejected -
STAR live 2026-09-18 and the NEOGEN/ALKEM/SHILPAMED morning cases.
"""
from intraday_strategy import _rounded_levels


def _ratio(entry_r, stop_r, tp_r):
    return (tp_r - entry_r) / (entry_r - stop_r)


def test_rounding_shortfall_cases_now_pass():
    cases = [
        (1005.307, 999.932),
        (221.097, 205.381),
        (415.216, 407.742),
    ]
    for entry, stop in cases:
        entry_r, stop_r, tp_r = _rounded_levels(entry, stop, 2.0)
        assert _ratio(entry_r, stop_r, tp_r) >= 2.0 - 1e-9, (entry, stop)


def test_exact_case_is_untouched():
    entry_r, stop_r, tp_r = _rounded_levels(100.0, 98.0, 2.0)
    assert (entry_r, stop_r, tp_r) == (100.0, 98.0, 104.0)
