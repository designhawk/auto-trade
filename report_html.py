# report_html.py
"""
Self-contained HTML daily report.

Reads trading.db only (no broker connection). Renders an overview (KPIs,
equity curve, per-trade result bars) followed by drill-down sections
(round trips with every fill, all signals, costs, sector attribution).

Usage:
    from report_html import build_html_report
    html = build_html_report("2026-09-18")
"""

from collections import Counter, defaultdict
from datetime import datetime
from html import escape as _esc

from config import config
from db import get_all_sessions, get_signals_for_date, get_trades_for_date
from sectors import sector_of

CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body { margin: 0; padding: 24px; font: 14px/1.5 -apple-system, "Segoe UI", Roboto,
       Helvetica, Arial, sans-serif; color: #0f172a; background: #f8fafc; }
.wrap { max-width: 1080px; margin: 0 auto; }
h1 { font-size: 22px; margin: 0; }
h2 { font-size: 16px; margin: 28px 0 10px; padding-bottom: 6px;
     border-bottom: 1px solid #e2e8f0; }
.sub { color: #64748b; font-size: 12px; margin-top: 2px; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
         gap: 10px; margin-top: 16px; }
.card { background: #fff; border: 1px solid #e2e8f0; border-radius: 10px;
        padding: 10px 12px; }
.card .k { font-size: 11px; text-transform: uppercase; letter-spacing: .04em;
           color: #64748b; }
.card .v { font-size: 18px; font-weight: 650; margin-top: 2px; }
.card .s { font-size: 11px; color: #64748b; margin-top: 2px; }
.pos { color: #15803d; } .neg { color: #b91c1c; } .mut { color: #64748b; }
.charts { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 14px; }
.chart { background: #fff; border: 1px solid #e2e8f0; border-radius: 10px;
         padding: 10px 12px 4px; }
.chart h3 { font-size: 12px; margin: 0 0 6px; color: #475569; font-weight: 600; }
svg { width: 100%; height: auto; display: block; }
details.trip { background: #fff; border: 1px solid #e2e8f0; border-radius: 8px;
               margin-bottom: 6px; }
details.trip > summary { display: grid; align-items: center; gap: 8px; cursor: pointer;
  grid-template-columns: 100px 110px 110px 60px 70px 90px 1fr 90px;
  padding: 8px 12px; list-style: none; font-size: 13px; }
details.trip > summary::-webkit-details-marker { display: none; }
.px { color: #64748b; font-size: 11px; }
.tag { display: inline-block; font-size: 10.5px; padding: 1px 7px; border-radius: 999px;
       border: 1px solid #cbd5e1; color: #475569; margin-right: 4px; white-space: nowrap; }
.tag.ok { border-color: #bbf7d0; background: #f0fdf4; color: #15803d; }
.tag.bad { border-color: #fecaca; background: #fef2f2; color: #b91c1c; }
.tag.warn { border-color: #fde68a; background: #fffbeb; color: #92400e; }
table { width: 100%; border-collapse: collapse; background: #fff; }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid #eef2f7;
         font-size: 13px; }
th { font-size: 11px; text-transform: uppercase; letter-spacing: .04em;
     color: #64748b; background: #fff; position: sticky; top: 0; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
.tbl { border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden; }
.fills { padding: 4px 12px 12px 28px; }
.fills table { border: 1px solid #eef2f7; border-radius: 6px; }
.chips { margin: 8px 0; }
.bar { height: 8px; border-radius: 4px; background: #e2e8f0; position: relative;
       overflow: hidden; }
.bar > i { position: absolute; top: 0; bottom: 0; left: 50%; display: block; }
.bar > i.p { background: #16a34a; } .bar > i.n { background: #dc2626; }
footer { margin-top: 32px; color: #94a3b8; font-size: 11.5px; }
code { background: #f1f5f9; padding: 1px 5px; border-radius: 4px; font-size: 12px; }
@media (max-width: 760px) { .charts { grid-template-columns: 1fr; }
  details.trip > summary { grid-template-columns: 90px 1fr 80px; }
  details.trip > summary .hide-sm { display: none; } }
"""


def _rs(x) -> str:
    return f"Rs.{x:,.2f}"


def _sign_cls(x) -> str:
    return "pos" if x > 0 else ("neg" if x < 0 else "mut")


def _short_ts(ts: str) -> str:
    return (ts or "")[11:19]


def _hold_str(entry_ts: str, exit_ts: str) -> str:
    if not entry_ts or not exit_ts:
        return "-"
    try:
        a = datetime.fromisoformat(entry_ts)
        b = datetime.fromisoformat(exit_ts)
    except ValueError:
        return "-"
    mins = max(0, int((b - a).total_seconds() // 60))
    if mins < 60:
        return f"{mins}m"
    return f"{mins // 60}h {mins % 60:02d}m"


def _round_trips(trades: list) -> list:
    """Group fills into per-symbol round trips (all same-day fills merged)."""
    by_symbol = defaultdict(list)
    for t in sorted(trades, key=lambda r: r.get("timestamp") or ""):
        by_symbol[t.get("symbol") or "?"].append(t)

    trips = []
    for sym, fills in by_symbol.items():
        trip = {
            "symbol": sym, "fills": fills, "entry_ts": None, "exit_ts": None,
            "buy_qty": 0, "sell_qty": 0, "buy_value": 0.0, "sell_value": 0.0,
            "costs": 0.0, "pnl": 0.0, "mfe": None, "mae": None,
            "exit_reasons": [],
        }
        for f in fills:
            trip["costs"] += sum(
                f.get(c) or 0
                for c in ("brokerage", "stt", "other_costs", "slippage_cost")
            )
            if f.get("side") == "BUY":
                trip["buy_qty"] += f.get("qty") or 0
                trip["buy_value"] += f.get("value") or 0
                if trip["entry_ts"] is None:
                    trip["entry_ts"] = f.get("timestamp")
            else:
                trip["sell_qty"] += f.get("qty") or 0
                trip["sell_value"] += f.get("value") or 0
                trip["pnl"] += f.get("pnl") or 0
                trip["exit_ts"] = f.get("timestamp")
                if f.get("exit_reason"):
                    trip["exit_reasons"].append(f["exit_reason"])
                if f.get("mfe") is not None:
                    trip["mfe"] = max(trip["mfe"], f["mfe"]) if trip["mfe"] is not None else f["mfe"]
                if f.get("mae") is not None:
                    trip["mae"] = min(trip["mae"], f["mae"]) if trip["mae"] is not None else f["mae"]
        trip["avg_entry"] = trip["buy_value"] / trip["buy_qty"] if trip["buy_qty"] else None
        trip["avg_exit"] = trip["sell_value"] / trip["sell_qty"] if trip["sell_qty"] else None
        trip["hold"] = _hold_str(trip["entry_ts"], trip["exit_ts"])
        trip["is_open"] = trip["sell_qty"] < trip["buy_qty"]
        trips.append(trip)

    trips.sort(key=lambda t: t["entry_ts"] or "")
    return trips


def _svg_equity(sells: list) -> str:
    pts = [t.get("pnl") or 0 for t in sells]
    if len(pts) < 2:
        return _chart_placeholder("Equity curve", "needs 2+ exits")
    cum, run = [], 0.0
    for p in pts:
        run += p
        cum.append(run)
    return _line_svg(cum, [t.get("timestamp") for t in sells],
                     "Realized equity curve (cumulative Rs.)")


def _line_svg(vals: list, stamps: list, title: str) -> str:
    w, h, pad_l, pad_r, pad_t, pad_b = 560, 150, 56, 10, 12, 24
    lo, hi = min(vals + [0.0]), max(vals + [0.0])
    if hi - lo < 1e-9:
        hi, lo = lo + 1.0, lo - 1.0
    rng = hi - lo

    def x(i):
        return pad_l + i * (w - pad_l - pad_r) / max(1, len(vals) - 1)

    def y(v):
        return pad_t + (hi - v) * (h - pad_t - pad_b) / rng

    poly = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(vals))
    zero = y(0.0)
    last_color = "#16a34a" if vals[-1] >= 0 else "#dc2626"
    return (
        f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{_esc(title)}">'
        f'<line x1="{pad_l}" y1="{zero:.1f}" x2="{w - pad_r}" y2="{zero:.1f}" '
        'stroke="#cbd5e1" stroke-dasharray="4 4"/>'
        f'<polyline points="{poly}" fill="none" stroke="#2563eb" stroke-width="2"/>'
        f'<circle cx="{x(len(vals) - 1):.1f}" cy="{y(vals[-1]):.1f}" r="3" fill="{last_color}"/>'
        f'<text x="6" y="{pad_t + 8}" font-size="10" fill="#94a3b8">{hi:,.0f}</text>'
        f'<text x="6" y="{h - pad_b}" font-size="10" fill="#94a3b8">{lo:,.0f}</text>'
        f'<text x="{pad_l}" y="{h - 6}" font-size="10" fill="#94a3b8">{_short_ts(stamps[0])}</text>'
        f'<text x="{w - pad_r}" y="{h - 6}" font-size="10" fill="#94a3b8" '
        f'text-anchor="end">{_short_ts(stamps[-1])}</text>'
        "</svg>"
    )


def _svg_trip_bars(trips: list) -> str:
    closed = [t for t in trips if not t["is_open"]]
    if not closed:
        return _chart_placeholder("Trade results", "no closed trades")
    w, h, pad_l, pad_r, pad_t, pad_b = 560, 150, 56, 10, 12, 24
    vals = [t["pnl"] for t in closed]
    mx = max(max(vals), abs(min(vals)), 1.0)
    y0 = pad_t + (h - pad_t - pad_b) / 2
    scale = (h - pad_t - pad_b) / 2 / mx
    bw = max(6.0, (w - pad_l - pad_r) / max(1, len(vals)) - 6)
    parts = [
        f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Per-trade net P&L">',
        f'<line x1="{pad_l}" y1="{y0:.1f}" x2="{w - pad_r}" y2="{y0:.1f}" '
        'stroke="#cbd5e1"/>',
    ]
    for i, v in enumerate(vals):
        cx = pad_l + (i + 0.5) * (w - pad_l - pad_r) / len(vals)
        bh = abs(v) * scale
        by = y0 - bh if v >= 0 else y0
        color = "#16a34a" if v > 0 else "#dc2626"
        sym = _esc(closed[i]["symbol"])
        parts.append(
            f'<rect x="{cx - bw / 2:.1f}" y="{by:.1f}" width="{bw:.1f}" '
            f'height="{max(1.0, bh):.1f}" fill="{color}" rx="2">'
            f"<title>{sym}: {_rs(v)}</title></rect>"
        )
    parts.append(
        f'<text x="6" y="{pad_t + 8}" font-size="10" fill="#94a3b8">+{mx:,.0f}</text>'
        f'<text x="6" y="{h - pad_b}" font-size="10" fill="#94a3b8">-{mx:,.0f}</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


def _chart_placeholder(title: str, msg: str) -> str:
    return (
        '<svg viewBox="0 0 560 150" role="img">'
        f'<text x="280" y="70" font-size="12" fill="#94a3b8" text-anchor="middle">'
        f"{_esc(title)} - {_esc(msg)}</text></svg>"
    )


def _kpi_cards(trades: list, trips: list, session: dict | None) -> str:
    sells = [t for t in trades if t.get("side") == "SELL"]
    buys = [t for t in trades if t.get("side") == "BUY"]
    closed = [t for t in trips if not t["is_open"]]
    wins = [t for t in closed if t["pnl"] > 0]
    losses = [t for t in closed if t["pnl"] <= 0]
    costs = sum(
        (t.get(c) or 0) for t in trades
        for c in ("brokerage", "stt", "other_costs", "slippage_cost")
    )
    realized = sum(t.get("pnl") or 0 for t in sells)
    gross_w = sum(t["pnl"] for t in wins)
    gross_l = abs(sum(t["pnl"] for t in losses))
    pf = (gross_w / gross_l) if gross_l > 0 else None
    best = max(closed, key=lambda t: t["pnl"], default=None)
    worst = min(closed, key=lambda t: t["pnl"], default=None)

    if session:
        # Session rows are written per process run: start_capital is the
        # capital at the last restart, so derive portfolio P&L vs the
        # configured starting capital instead (restart-proof day number).
        init = config.INITIAL_CAPITAL or 0.0
        pnl = (session.get("end_capital") or 0.0) - init
        pnl_pct = (pnl / init * 100) if init else 0.0
        cash_note = f"{pnl_pct:+.2f}% vs {_rs(init)} start"
    else:
        pnl, cash_note = realized, "realized-only (no session row)"

    cards = [
        ("Portfolio P&L (cash)", _rs(pnl), cash_note,
         _sign_cls(pnl) if session else "mut"),
        ("Realized P&L", _rs(realized), f"{len(sells)} exit fills",
         _sign_cls(realized)),
        ("Trades", f"{len(buys)} / {len(sells)}",
         "buys / sells", "mut"),
        ("Win rate", f"{(len(wins) / len(closed) * 100 if closed else 0):.0f}%",
         f"{len(wins)}W / {len(losses)}L closed", "mut"),
        ("Profit factor", f"{pf:.2f}" if pf is not None else "-",
         "gross win / gross loss", _sign_cls((pf or 0) - 1)),
        ("Total costs", _rs(costs), "all-in incl. slippage", "mut"),
        ("Best trade", _rs(best["pnl"]) + f" {best['symbol']}" if best else "-",
         best["exit_reasons"][0] if best and best["exit_reasons"] else "", "pos"),
        ("Worst trade", _rs(worst["pnl"]) + f" {worst['symbol']}" if worst else "-",
         worst["exit_reasons"][0] if worst and worst["exit_reasons"] else "", "neg"),
    ]
    out = ['<div class="cards">']
    for k, v, s, cls in cards:
        out.append(
            f'<div class="card"><div class="k">{_esc(k)}</div>'
            f'<div class="v {cls}">{_esc(v)}</div>'
            f'<div class="s">{_esc(s)}</div></div>'
        )
    out.append("</div>")
    return "".join(out)


def _trips_html(trips: list) -> str:
    if not trips:
        return '<p class="mut">No trades this day.</p>'
    out = []
    for t in trips:
        status = "OPEN" if t["is_open"] else "/".join(dict.fromkeys(t["exit_reasons"])) or "CLOSED"
        tag_cls = "warn" if t["is_open"] else ("ok" if t["pnl"] > 0 else "bad")
        mfe = f"{t['mfe']:.2f}R" if t["mfe"] is not None else "-"
        mae = f"{t['mae']:.2f}R" if t["mae"] is not None else "-"
        entry = f"{t['avg_entry']:,.2f}" if t["avg_entry"] else "-"
        exit_ = f"{t['avg_exit']:,.2f}" if t["avg_exit"] else "-"
        out.append('<details class="trip"><summary>')
        out.append(f"<b>{_esc(t['symbol'])}</b>")
        out.append(f'<span>{_esc(_short_ts(t["entry_ts"]))} <span class="px">entry</span> '
                   f'{_esc(entry)}</span>')
        out.append(f'<span>{_esc(_short_ts(t["exit_ts"]))} <span class="px">exit</span> '
                   f'{_esc(exit_)}</span>')
        out.append(f'<span class="hide-sm">{t["buy_qty"]}/{t["sell_qty"]} qty</span>')
        out.append(f'<span class="hide-sm">{_esc(t["hold"])}</span>')
        out.append(f'<span class="hide-sm mut">cost {_rs(t["costs"])}</span>')
        out.append(f'<span class="tag {tag_cls}">{_esc(status)}</span>')
        out.append(f'<span class="num {_sign_cls(t["pnl"])}"><b>{_rs(t["pnl"])}</b> '
                   f'<span class="px">MFE {mfe} / MAE {mae}</span></span>')
        out.append("</summary>")
        out.append('<div class="fills"><table><thead><tr>'
                   '<th>Time</th><th>Side</th><th class="num">Qty</th>'
                   '<th class="num">Price</th><th class="num">Value</th>'
                   '<th class="num">Costs</th><th class="num">P&L</th>'
                   '<th>Exit</th></tr></thead><tbody>')
        for f in t["fills"]:
            costs = sum(f.get(c) or 0 for c in
                        ("brokerage", "stt", "other_costs", "slippage_cost"))
            pnl = f.get("pnl")
            cls = _sign_cls(pnl) if pnl else "mut"
            out.append(
                f'<tr><td>{_esc(_short_ts(f.get("timestamp")))}</td>'
                f'<td>{_esc(f.get("side") or "")}</td>'
                f'<td class="num">{f.get("qty") or 0}</td>'
                f'<td class="num">{(f.get("price") or 0):,.2f}</td>'
                f'<td class="num">{(f.get("value") or 0):,.2f}</td>'
                f'<td class="num">{costs:,.2f}</td>'
                f'<td class="num {cls}">{_rs(pnl) if pnl is not None else "-"}</td>'
                f'<td>{_esc(f.get("exit_reason") or "")}</td></tr>'
            )
        out.append("</tbody></table></div></details>")
    return "".join(out)


def _signals_html(signals: list) -> str:
    if not signals:
        return '<p class="mut">No signals this day.</p>'
    approved = [s for s in signals if s.get("approved")]
    rejected = [s for s in signals if not s.get("approved")]
    chips = [f'<span class="tag ok">{len(approved)} approved</span>',
             f'<span class="tag bad">{len(rejected)} rejected</span>']
    for reason, n in Counter(
        s.get("rejection_reason") or "?" for s in rejected
    ).most_common(6):
        chips.append(f'<span class="tag warn">{_esc(reason)}: {n}</span>')
    out = [f'<div class="chips">{"".join(chips)}</div>',
           '<div class="tbl"><table><thead><tr><th>Time</th><th>Symbol</th>'
           '<th class="num">Conf</th><th class="num">Entry</th><th class="num">SL</th>'
           '<th class="num">TP</th><th>Status</th><th>Reason</th></tr></thead><tbody>']
    for s in signals:
        ok = s.get("approved")
        status = ('<span class="tag ok">APPROVED</span>' if ok
                  else '<span class="tag bad">REJECTED</span>')
        reason = (s.get("rejection_reason") or "") if not ok else ""
        out.append(
            f'<tr><td>{_esc(_short_ts(s.get("timestamp")))}</td>'
            f'<td><b>{_esc(s.get("symbol") or "")}</b></td>'
            f'<td class="num">{(s.get("confidence") or 0):.2f}</td>'
            f'<td class="num">{(s.get("entry_price") or 0):,.2f}</td>'
            f'<td class="num">{(s.get("stop_loss") or 0):,.2f}</td>'
            f'<td class="num">{(s.get("take_profit") or 0):,.2f}</td>'
            f"<td>{status}</td><td>{_esc(reason)}</td></tr>"
        )
    out.append("</tbody></table></div>")
    return "".join(out)


def _costs_html(trades: list) -> str:
    items = [
        ("Brokerage", "brokerage"), ("STT (sell)", "stt"),
        ("Stamp/exchange/SEBI/GST", "other_costs"), ("Slippage", "slippage_cost"),
    ]
    total = sum((t.get(c) or 0) for t in trades for _, c in items)
    rows = "".join(
        f"<tr><td>{_esc(name)}</td><td class=\"num\">{_rs(sum((t.get(c) or 0) for t in trades))}</td></tr>"
        for name, c in items
    )
    return ('<div class="tbl"><table><thead><tr><th>Item</th>'
            '<th class="num">Total</th></tr></thead><tbody>' + rows +
            f'<tr><td><b>All-in</b></td><td class="num"><b>{_rs(total)}</b></td></tr>'
            "</tbody></table></div>")


def _sectors_html(trades: list) -> str:
    pnl = defaultdict(float)
    for t in trades:
        if t.get("side") == "SELL":
            pnl[sector_of(t.get("symbol") or "")] += t.get("pnl") or 0
    if not pnl:
        return '<p class="mut">No closed P&L this day.</p>'
    mx = max(abs(v) for v in pnl.values()) or 1.0
    rows = []
    for sec, v in sorted(pnl.items(), key=lambda kv: -kv[1]):
        pct = abs(v) / mx * 50
        side = f'<i class="p" style="width:{pct:.1f}%"></i>' if v >= 0 else \
               f'<i class="n" style="right:50%;width:{pct:.1f}%"></i>'
        rows.append(
            f'<tr><td>{_esc(sec)}</td><td class="num {_sign_cls(v)}">{_rs(v)}</td>'
            f'<td style="width:45%"><div class="bar">{side}</div></td></tr>'
        )
    return ('<div class="tbl"><table><thead><tr><th>Sector</th>'
            '<th class="num">P&L</th><th></th></tr></thead><tbody>'
            + "".join(rows) + "</tbody></table></div>")


def build_html_report(day: str) -> str:
    trades = get_trades_for_date(day)
    signals = get_signals_for_date(day)
    trips = _round_trips(trades)
    sells = [t for t in trades if t.get("side") == "SELL"]

    session = None
    try:
        session = next((s for s in get_all_sessions() if s.get("date") == day), None)
    except Exception:
        session = None

    notes = (session or {}).get("notes") or ""
    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    head = (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>Trading Report - {_esc(day)}</title><style>{CSS}</style></head><body>"
        "<div class=\"wrap\">"
        f"<h1>Trading Report - {_esc(day)}</h1>"
        f"<div class=\"sub\">{_esc(notes) or 'PAPER'} &middot; "
        f"generated {_esc(generated)}</div>"
    )

    body = (
        _kpi_cards(trades, trips, session)
        + '<div class="charts">'
        + f'<div class="chart"><h3>Equity curve</h3>{_svg_equity(sells)}</div>'
        + f'<div class="chart"><h3>Per-trade net P&L</h3>{_svg_trip_bars(trips)}</div>'
        + "</div>"
        + f"<h2>Round trips ({len(trips)})</h2>"
        + _trips_html(trips)
        + f"<h2>Signals ({len(signals)})</h2>"
        + _signals_html(signals)
        + "<h2>Costs</h2>" + _costs_html(trades)
        + "<h2>Sector attribution</h2>" + _sectors_html(trades)
    )

    footer = (
        "<footer>Paper simulation. Cost schedule: Groww intraday brokerage "
        "(0.1% per order, cap Rs.20, floor Rs.5) + STT 0.025% sell + stamp 0.003% buy "
        "+ NSE exchange/SEBI + 18% GST + sampled slippage (0-0.04%). "
        "Exit P&L includes the position&rsquo;s allocated buy-side costs; rows recorded "
        "before 2026-09-18 used the older schedule (0.03% brokerage, buy costs not "
        "allocated), so older days read slightly optimistic. "
        "MFE/MAE are in R multiples of the initial risk.</footer>"
    )

    return head + body + footer + "</div></body></html>"
