# api.py
"""
FastAPI REST Server for Trading System

Provides endpoints to query:
- Current trading status
- Signals and trades
- Portfolio value
- Session summaries

Usage:
    python api.py  # Start server on port 8000
    
Endpoints:
    GET /health - Health check
    GET /status - Current trading status
    GET /signals - Recent signals
    GET /trades - Recent trades
    GET /portfolio - Portfolio summary
    GET /sessions - Session history
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse
from datetime import datetime, date
from typing import List, Optional
import sqlite3
from contextlib import contextmanager
import json
import re

from db import get_db, get_trades_for_date, get_signals_for_date, get_all_sessions, get_cash_flow
import db as _dbmod
from config import config

# Broker for live prices
_broker = None

def get_broker():
    global _broker
    if _broker is None:
        from groww_broker import GrowwBroker
        _broker = GrowwBroker()
        _broker.connect()
    return _broker


def _live_prices(symbols: list[str]) -> tuple[dict[str, float], bool]:
    """
    Best-effort live LTP lookup.

    Returns (prices, live_flag). Falls back to ({}, False) when the broker
    is unreachable (no creds, market closed, trader not running) so endpoints
    stay usable with entry-price valuations. Callers MUST surface live_flag
    as "live_prices" so clients know which they're seeing.
    """
    if not symbols:
        return {}, False
    try:
        prices = get_broker().get_ltp(symbols)
        # Live only if we got a price for EVERY requested symbol;
        # otherwise callers fall back to entry prices per row.
        live = bool(prices) and all(s in prices for s in symbols)
        return (prices if live else {}), live
    except Exception:
        return {}, False

app = FastAPI(
    title="Auto Trading API",
    description="REST API for auto trading system observability",
    version="1.0.0"
)

# Enable CORS for dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }


@app.get("/status")
def get_status():
    """Get current trading system status."""
    try:
        # Live reference: honors test/region re-pointing
        db_connected = _dbmod.DB_PATH.exists()

        sessions, latest_session = [], None
        signals_today, trades_today = 0, 0
        if db_connected:
            try:
                # Get latest session info
                sessions = get_all_sessions()
                latest_session = sessions[0] if sessions else None

                # Count today's signals and trades
                today = date.today().isoformat()
                signals_today = len(get_signals_for_date(today))
                trades_today = len(get_trades_for_date(today))
            except Exception:
                # File exists but schema is missing/unreadable
                db_connected = False

        return {
            "status": "running" if db_connected else "error",
            "timestamp": datetime.now().isoformat(),
            "database_connected": db_connected,
            "latest_session": latest_session,
            "today_signals": signals_today,
            "today_trades": trades_today,
            "total_sessions": len(sessions)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/signals")
def get_signals(
    limit: int = 50,
    approved_only: bool = False,
    date: Optional[str] = None
):
    """Get trading signals."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            query = "SELECT * FROM signals"
            params = []
            
            # Filter by date
            if date:
                query += " WHERE DATE(timestamp) = ?"
                params.append(date)
            
            # Filter by approval status
            if approved_only:
                if date:
                    query += " AND approved = 1"
                else:
                    query += " WHERE approved = 1"
            
            # Order and limit
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            signals = [dict(row) for row in rows]
            return {
                "count": len(signals),
                "signals": signals
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/trades")
def get_trades(
    limit: int = 50,
    date: Optional[str] = None,
    symbol: Optional[str] = None
):
    """Get executed trades."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            query = "SELECT * FROM trades"
            conditions = []
            params = []
            
            if date:
                conditions.append("DATE(timestamp) = ?")
                params.append(date)
            
            if symbol:
                conditions.append("symbol = ?")
                params.append(symbol)
            
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            trades = [dict(row) for row in rows]
            
            # Calculate summary stats
            if trades:
                total_pnl = sum(t.get('pnl', 0) or 0 for t in trades)
                winning_trades = len([t for t in trades if (t.get('pnl') or 0) > 0])
            else:
                total_pnl = 0
                winning_trades = 0
            
            return {
                "count": len(trades),
                "total_pnl": total_pnl,
                "winning_trades": winning_trades,
                "trades": trades
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/positions")
def get_positions():
    """Get current open positions (today's trades netted; live prices when available)."""
    try:
        today = date.today().isoformat()

        with get_db() as conn:
            cursor = conn.cursor()

            # Net today's BUYs against SELLs per symbol (partial sells OK)
            cursor.execute("""
                SELECT symbol,
                    SUM(CASE WHEN side = 'BUY' THEN qty ELSE -qty END) as net_qty,
                    SUM(CASE WHEN side = 'BUY' THEN qty * price ELSE 0 END)
                        / NULLIF(SUM(CASE WHEN side = 'BUY' THEN qty ELSE 0 END), 0) as avg_price,
                    MAX(CASE WHEN side = 'BUY' THEN timestamp END) as last_buy_time
                FROM trades
                WHERE DATE(timestamp) = ?
                GROUP BY symbol
                HAVING net_qty > 0
                ORDER BY last_buy_time DESC
            """, (today,))

            rows = cursor.fetchall()

            symbols = [str(row[0]) for row in rows]
            live_prices, live = _live_prices(symbols)

            positions = []

            for row in rows:
                symbol = str(row[0])
                qty = int(row[1])
                entry_price = float(row[2])
                current_price = live_prices.get(symbol, entry_price)

                # Best-effort plan levels from the latest approved signal
                # (signals table only; in-memory trailing/breakeven moves
                # are not persisted, so R is an estimate vs the plan)
                stop_loss = take_profit = r_multiple = None
                sig = cursor.execute("""
                    SELECT entry_price, stop_loss, take_profit FROM signals
                    WHERE symbol = ? AND approved = 1 AND action = 'BUY'
                    ORDER BY timestamp DESC LIMIT 1
                """, (symbol,)).fetchone()
                if sig and sig[1] is not None and sig[0] is not None:
                    stop_loss = float(sig[1])
                    take_profit = float(sig[2]) if sig[2] is not None else None
                    risk = float(sig[0]) - stop_loss
                    if risk > 0:
                        r_multiple = round((current_price - float(sig[0])) / risk, 2)

                positions.append({
                    "symbol": symbol,
                    "side": "BUY",
                    "entry_price": entry_price,
                    "current_price": current_price,
                    "qty": qty,
                    "value": current_price * qty,
                    "entry_time": str(row[3]),
                    "stop_loss": stop_loss,
                    "take_profit": take_profit,
                    "r_multiple": r_multiple,
                })

            return {
                "count": len(positions),
                "live_prices": live,
                "positions": positions
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/portfolio")
def get_portfolio_summary():
    """Get current portfolio summary with real-time values."""
    try:
        # Get latest session
        sessions = get_all_sessions()
        
        if not sessions:
            return {
                "status": "no_sessions",
                "message": "No trading sessions found"
            }
        
        latest = sessions[0]
        # Cash baseline must be the account's starting capital: get_cash_flow
        # is all-time, while a session row's start_capital is the capital at
        # the last restart - mixing them double-counts pre-restart trades
        # (2026-09-18 showed Rs.99,955 instead of the true Rs.1,00,029).
        start_capital = config.INITIAL_CAPITAL
        
        # Get today's approved signals as open positions
        today = date.today().isoformat()
        
        with get_db() as conn:
            cursor = conn.cursor()
            # Net all BUYs against SELLs (partial sells reduce, not erase)
            cursor.execute("""
                SELECT symbol,
                    SUM(CASE WHEN side = 'BUY' THEN qty ELSE -qty END) as net_qty,
                    SUM(CASE WHEN side = 'BUY' THEN qty * price ELSE 0 END)
                        / NULLIF(SUM(CASE WHEN side = 'BUY' THEN qty ELSE 0 END), 0) as avg_price
                FROM trades
                GROUP BY symbol
                HAVING net_qty > 0
            """)
            rows = cursor.fetchall()
            open_positions = [
                (str(r[0]), int(r[1]), float(r[2])) for r in rows
            ]

            # Calculate cash from gross flows + cost columns (exact)
            buy_out, sell_in = get_cash_flow()
            cash = start_capital - buy_out + sell_in

        # Value positions at live prices when available, entry prices otherwise
        live_prices, live = _live_prices([s for s, _, _ in open_positions])
        position_value = sum(
            qty * live_prices.get(symbol, avg_price)
            for symbol, qty, avg_price in open_positions
        ) if open_positions else 0
        num_positions = len(open_positions)
        
        current_value = cash + position_value
        
        # Get today's trades for P&L
        today_trades = get_trades_for_date(today)
        today_pnl = sum(t.get('pnl', 0) or 0 for t in today_trades)
        
        return {
            "status": "active",
            "latest_session_date": latest.get('date'),
            "start_capital": start_capital,
            "current_value": current_value,
            "cash": cash,
            "position_value": position_value,
            "live_prices": live,
            "num_positions": num_positions,
            "total_return_pct": (today_pnl / start_capital * 100) if start_capital else 0,
            "total_trades": len(today_trades),
            "win_rate": 0,
            "today_pnl": today_pnl,
            "today_trades": len(today_trades),
            "max_drawdown_pct": 0,
            "sharpe_ratio": 0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sessions")
def get_sessions(limit: int = 30):
    """Get trading session history."""
    try:
        sessions = get_all_sessions()
        
        # Calculate cumulative stats
        if sessions:
            total_pnl = sum(s.get('total_pnl', 0) or 0 for s in sessions)
            total_trades = sum(s.get('total_trades', 0) or 0 for s in sessions)
        else:
            total_pnl = 0
            total_trades = 0
        
        return {
            "count": len(sessions),
            "total_pnl_all_sessions": total_pnl,
            "total_trades_all_sessions": total_trades,
            "sessions": sessions[:limit]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/today")
def get_today_summary():
    """Get today's trading summary."""
    try:
        today = date.today().isoformat()
        
        # Get today's signals
        signals = get_signals_for_date(today)
        approved_signals = [s for s in signals if s.get('approved')]
        rejected_signals = [s for s in signals if not s.get('approved')]
        
        # Get today's trades
        trades = get_trades_for_date(today)
        buy_trades = [t for t in trades if t.get('side') == 'BUY']
        sell_trades = [t for t in trades if t.get('side') == 'SELL']
        
        # Calculate P&L
        total_pnl = sum(t.get('pnl', 0) or 0 for t in trades)
        
        return {
            "date": today,
            "signals_total": len(signals),
            "signals_approved": len(approved_signals),
            "signals_rejected": len(rejected_signals),
            "trades_total": len(trades),
            "trades_buy": len(buy_trades),
            "trades_sell": len(sell_trades),
            "total_pnl": total_pnl,
            "signals": signals[-10:],  # last 10 signals (list is ASC by time)
            "trades": trades[-10:]     # last 10 trades (list is ASC by time)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


_REPORT_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+\.(html|md)$")

MOBILE_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Auto Trade Live</title>
<style>
:root{color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:#0b1220;color:#e2e8f0;
 font:15px/1.45 -apple-system,"Segoe UI",Roboto,sans-serif;padding:14px 14px 40px}
h1{font-size:17px;margin:0}
.sub{color:#8aa0b8;font-size:12px;margin-top:2px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px}
.card{background:#141f33;border:1px solid #22314b;border-radius:12px;padding:10px 12px}
.k{font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;color:#8aa0b8}
.v{font-size:19px;font-weight:650;margin-top:2px}
.s{font-size:11px;color:#8aa0b8;margin-top:2px}
.pos{color:#4ade80}.neg{color:#f87171}.mut{color:#8aa0b8}
h2{font-size:12.5px;text-transform:uppercase;letter-spacing:.05em;color:#8aa0b8;margin:20px 0 8px}
.row{display:flex;justify-content:space-between;align-items:center;gap:8px;
 background:#141f33;border:1px solid #22314b;border-radius:10px;padding:8px 10px;margin-bottom:6px}
.sym{font-weight:650}
.small{font-size:11.5px;color:#8aa0b8}
.tag{font-size:10.5px;padding:1px 7px;border-radius:999px;border:1px solid #2c3d5c;color:#8aa0b8;white-space:nowrap}
.tag.ok{border-color:#14532d;background:#052e16;color:#4ade80}
.tag.no{border-color:#7f1d1d;background:#2a0a0a;color:#f87171}
a{color:#7cb8ff;text-decoration:none}
button{background:#1d2b45;border:1px solid #2c3d5c;color:#e2e8f0;border-radius:8px;
 padding:6px 12px;font-size:13px}
.foot{margin-top:22px;color:#5c718c;font-size:11px}
.sysline{display:flex;flex-wrap:wrap;gap:6px 12px;margin-top:10px;font-size:12px}
.seg .k{color:#8aa0b8;text-transform:uppercase;font-size:10px;letter-spacing:.04em;margin-right:3px}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{background:#141f33;border:1px solid #22314b;border-radius:8px;padding:4px 8px;font-size:12px}
.chip .small{font-size:10px}
details summary{cursor:pointer}
pre{background:#141f33;border:1px solid #22314b;border-radius:10px;padding:10px;
 margin:0;max-height:320px;overflow:auto;font-size:11px;line-height:1.5;white-space:pre-wrap}
.lerr{color:#f87171}.lwarn{color:#fbbf24}.lsig{color:#22d3ee}
</style></head><body>
<h1>Auto Trade &middot; Live</h1>
<div class="sub" id="when">loading&hellip;</div>
<div class="sysline" id="sys"><span class="seg mut">waiting&hellip;</span></div>
<h2>Portfolio</h2><div class="grid" id="summary"></div>
<h2>Regime</h2><div class="grid" id="regime"></div>
<h2>Positions</h2><div id="positions" class="small">&ndash;</div>
<h2>Watchlist</h2><div id="watch" class="small">&ndash;</div>
<h2 id="sigH">Latest signals</h2><div id="signals" class="small">&ndash;</div>
<h2 id="trdH">Latest trades</h2><div id="trades" class="small">&ndash;</div>
<h2>Live log</h2><div id="log" class="small">&ndash;</div>
<h2>Reports</h2><div id="reports" class="small">&ndash;</div>
<div class="foot"><button onclick="refresh()">Refresh now</button>
 &nbsp;auto-refresh: 30s</div>
<script>
var esc = function(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){
  return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});};
var rs = function(v){return 'Rs.'+Number(v||0).toLocaleString('en-IN',{maximumFractionDigits:0});};
var el = function(id){return document.getElementById(id);};
var signCls = function(v){return v>0?'pos':(v<0?'neg':'mut');};
function card(k,v,s,cls){return '<div class="card"><div class="k">'+esc(k)+
  '</div><div class="v '+esc(cls||'')+'">'+esc(v)+'</div>'+
  '<div class="s">'+esc(s||'')+'</div></div>';}
function row(l,r){return '<div class="row">'+l+'<span>'+r+'</span></div>';}
function seg(k,v,cls){return '<span class="seg"><span class="k">'+esc(k)+'</span>'+
  '<span class="'+esc(cls||'')+'">'+esc(v)+'</span></span>';}
async function j(u){var r=await fetch(u,{cache:'no-store'});
  if(!r.ok) throw new Error(u+' '+r.status); return r.json();}
function hhmm(ts){return ts?String(ts).substr(11,5):'';}
function ageTxt(a){
  if(a==null) return 'not running';
  if(a<150) return a+'s ago';
  if(a<3600) return Math.round(a/60)+'m ago';
  var h=Math.round(a/3600);
  return (h<48 ? h+'h' : Math.round(h/24)+'d')+' ago';
}
function ageCls(a){return a==null?'mut':(a<150?'pos':(a<300?'':'neg'));}
async function refresh(){
  try{
    var d = await Promise.all([j('/portfolio'),j('/positions'),j('/today'),j('/reports_list'),j('/tui')]);
    var pf=d[0], po=d[1], td=d[2], rp=d[3], tu=d[4];
    var wl=tu.watchlist||{}, rg=tu.regime||{};
    var tickAge=(tu.trader||{}).last_tick_age_s;
    var tickTxt=ageTxt(tickAge);
    var tickCls=ageCls(tickAge);
    el('sys').innerHTML = seg('Trader',tickTxt,tickCls)+seg('Feed',tu.feed||'?','')+
      seg('DB',tu.db?'ok':'MISSING',tu.db?'pos':'neg')+
      seg('Watchlist',(wl.count||0)+' names'+(wl.stale?' (stale)':''),'')+
      seg('API','up','pos');
    el('regime').innerHTML =
      card('Entries',rg.entries||'?','',String(rg.entries||'').indexOf('OPEN')===0?'pos':'mut')+
      card('India VIX',(rg.vix==null?'-':Number(rg.vix).toFixed(2)),(rg.vix_note||'fail-open'),'')+
      card('Trade cap',(rg.buys_today||0)+' / '+(rg.trade_cap==null?'?':rg.trade_cap),'buys today','')+
      card('Market',rg.market||'?',rg.market_time||'','');
    var wrows=(wl.symbols||[]).map(function(s){return '<span class="chip">'+esc(s.symbol)+
      ' <span class="small">'+esc(s.sector)+'</span></span>';}).join('');
    el('watch').innerHTML = wrows?('<details><summary>'+esc(wl.count||0)+' names'+
      (wl.updated?(' &middot; updated '+esc(String(wl.updated).substr(11,5))):'')+
      '</summary><div class="chips" style="margin-top:8px">'+wrows+'</div></details>')
      :'<div class="row mut"><span>not published yet</span></div>';
    var llines=(tu.log_lines||[]).map(function(l){
      var cls=l.indexOf('[ERROR]')>=0?'lerr':(l.indexOf('[WARNING]')>=0?'lwarn':
        (l.indexOf('SIGNAL')>=0?'lsig':''));
      return '<span class="'+cls+'">'+esc(l)+'</span>';}).join(String.fromCharCode(10));
    el('log').innerHTML='<pre>'+llines+'</pre>';
    var sigDate=null, todayStr=new Date().toLocaleDateString('en-CA');
    if(((td.signals||[]).length===0) && ((td.trades||[]).length===0) &&
       pf.latest_session_date && pf.latest_session_date!==todayStr){
      var extra = await Promise.all([
        j('/signals?limit=10&date='+encodeURIComponent(pf.latest_session_date)),
        j('/trades?limit=10&date='+encodeURIComponent(pf.latest_session_date))]);
      td = {signals: extra[0].signals||[], trades: extra[1].trades||[]};
      sigDate = pf.latest_session_date;
    }
    var pnl=(pf.current_value||0)-(pf.start_capital||0);
    el('summary').innerHTML =
      card('Value',rs(pf.current_value),(pf.live_prices?'live prices':''),'')+
      card('P&L',rs(pnl),'vs start capital',signCls(pnl))+
      card('Cash',rs(pf.cash),'', '')+
      card('Positions',pf.num_positions,'today: '+(pf.today_trades||0)+' trades','');
    var rows=(po.positions||[]).map(function(p){
      var now=p.current_price||p.entry_price||0;
      var pv=(now-(p.entry_price||0))*(p.qty||0);
      var extra=[];
      if(p.r_multiple!=null) extra.push('R '+(p.r_multiple>0?'+':'')+Number(p.r_multiple).toFixed(1));
      if(p.stop_loss) extra.push('SL '+Number(p.stop_loss).toFixed(2));
      if(p.take_profit) extra.push('TP '+Number(p.take_profit).toFixed(2));
      return row('<span><span class="sym">'+esc(p.symbol)+'</span> '+
        '<span class="small">x'+esc(p.qty)+' @ '+esc((p.entry_price||0).toFixed(2))+
        ' &rarr; '+esc(now.toFixed(2))+'</span>'+
        (extra.length?'<br><span class="small">'+esc(extra.join('  '))+'</span>':'')+'</span>',
        '<span class="'+signCls(pv)+'">'+esc(rs(pv))+'</span>');
    }).join('');
    el('positions').innerHTML = rows || '<div class="row mut"><span>flat</span></div>';
    var sigs=(td.signals||[]).slice(-5).reverse().map(function(s){
      var tag=s.approved?'<span class="tag ok">OK</span>':'<span class="tag no">'+esc(s.rejection_reason||'rejected')+'</span>';
      return row('<span><span class="sym">'+esc(s.symbol)+'</span> <span class="small">'+
        esc(hhmm(s.timestamp))+' @ '+esc((s.entry_price||0).toFixed(2))+'</span></span>',tag);
    }).join('');
    el('signals').innerHTML = sigs || '<div class="row mut"><span>none</span></div>';
    el('sigH').textContent = 'Latest signals'+(sigDate?(' \u2014 '+sigDate):'');
    var trs=(td.trades||[]).slice(-5).reverse().map(function(t){
      var pnl=t.pnl||0;
      return row('<span><span class="sym">'+esc(t.side)+' '+esc(t.symbol)+'</span> '+
        '<span class="small">x'+esc(t.qty)+' @ '+esc((t.price||0).toFixed(2))+
        ' '+(t.exit_reason?esc(t.exit_reason):'')+'</span></span>',
        '<span class="'+signCls(pnl)+'">'+(t.side==='SELL'?esc(rs(pnl)):'')+'</span>');
    }).join('');
    el('trades').innerHTML = trs || '<div class="row mut"><span>none</span></div>';
    el('trdH').textContent = 'Latest trades'+(sigDate?(' \u2014 '+sigDate):'');
    var files=(rp.files||[]).slice(0,6).map(function(f){
      return '<div class="row"><a href="/reports/'+encodeURIComponent(f)+'">'+esc(f)+'</a></div>';
    }).join('');
    el('reports').innerHTML = files || '<div class="row mut"><span>none yet</span></div>';
    el('when').textContent = 'updated '+new Date().toLocaleTimeString()+
      (pf.latest_session_date?('  - last session '+pf.latest_session_date):'');
  }catch(e){
    el('when').textContent = 'trader/API unreachable - '+e.message;
  }
}
refresh(); setInterval(refresh, 30000);
</script></body></html>"""


@app.get("/tui")
def tui_panels():
    """Everything the monitor TUI shows (system, regime, watchlist, log)."""
    from monitor import (IST, _clean_log_lines, _feed_status, _last_tick_time,
                         _tail_lines, market_status)

    lines = _clean_log_lines(_tail_lines(1200))
    # Legacy test-run pollution (pre test-shield) wrote pytest temp paths
    # into the real log; never real trading lines, safe to drop.
    lines = [l for l in lines if "pytest-of-" not in l]
    tick = _last_tick_time(lines)
    age = int((datetime.now() - tick).total_seconds()) if tick else None

    vix = vix_note = None
    vix_re = re.compile(r"India VIX: ([\d.]+) \(([^)]+)\)")
    for line in reversed(lines):
        m = vix_re.search(line)
        if m:
            try:
                vix, vix_note = float(m.group(1)), m.group(2)
            except ValueError:
                pass
            break

    wl = {}
    try:
        from paths import LOG_DIR

        wl = json.loads((LOG_DIR / "watchlist.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        wl = {}
    from sectors import sector_of

    updated = str(wl.get("updated") or "")
    stale = bool(updated) and updated[:10] != date.today().isoformat()
    symbols = [{"symbol": str(s), "sector": sector_of(str(s))}
               for s in (wl.get("symbols") or [])]

    buys = sum(1 for t in get_trades_for_date(date.today().isoformat())
               if t.get("side") == "BUY")

    now_ist = datetime.now(IST)
    hm = (now_ist.hour, now_ist.minute)
    if hm < (config.ENTRY_START_HOUR, config.ENTRY_START_MINUTE):
        entries = f"opens {config.ENTRY_START_HOUR}:{config.ENTRY_START_MINUTE:02d}"
    elif hm >= (config.ENTRY_CUTOFF_HOUR, config.ENTRY_CUTOFF_MINUTE):
        entries = (f"closed ({config.ENTRY_CUTOFF_HOUR}:"
                   f"{config.ENTRY_CUTOFF_MINUTE:02d} cutoff)")
    elif ((0, 0) < config.ENTRY_PAUSE_START < config.ENTRY_PAUSE_END
          and config.ENTRY_PAUSE_START <= hm < config.ENTRY_PAUSE_END):
        entries = "PAUSED (lunch lull)"
    else:
        entries = "OPEN"

    db_ok = True
    try:
        with get_db() as conn:
            conn.execute("SELECT 1").fetchone()
    except Exception:
        db_ok = False

    mkt, _ = market_status(now_ist)
    return {
        "trader": {"last_tick_age_s": age},
        "feed": _feed_status(),
        "db": db_ok,
        "watchlist": {
            "count": wl.get("count", len(symbols)),
            "updated": updated,
            "stale": stale,
            "strategy": wl.get("strategy"),
            "symbols": symbols,
        },
        "regime": {
            "entries": entries,
            "vix": vix,
            "vix_note": vix_note,
            "buys_today": buys,
            "trade_cap": config.MAX_TRADES_PER_DAY or "unlimited",
            "market": mkt,
            "market_time": now_ist.strftime("%H:%M:%S"),
        },
        "log_lines": lines[-30:],
    }


@app.get("/reports_list")
def list_reports():
    """List generated daily report files (newest first)."""
    from paths import REPORT_DIR

    try:
        files = sorted(
            (p.name for p in REPORT_DIR.glob("*") if _REPORT_NAME_RE.match(p.name)),
            reverse=True,
        )
    except OSError:
        files = []
    return {"files": files}


@app.get("/reports/{name}")
def serve_report(name: str):
    """Serve a daily report file (visual HTML report or Markdown card)."""
    from paths import REPORT_DIR

    if not _REPORT_NAME_RE.match(name):
        raise HTTPException(status_code=404, detail="Report not found")
    path = REPORT_DIR / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Report not found")
    text = path.read_text(encoding="utf-8")
    if name.endswith(".html"):
        return HTMLResponse(text)
    return PlainTextResponse(text)


@app.get("/mobile", response_class=HTMLResponse)
def mobile_page():
    """Phone-friendly live view (no CDNs; polls the local API every 30s)."""
    return HTMLResponse(MOBILE_PAGE)


if __name__ == "__main__":
    import uvicorn
    print(f"Starting API server on http://localhost:{config.API_PORT}")
    print(f"Documentation: http://localhost:{config.API_PORT}/docs")
    uvicorn.run(app, host="0.0.0.0", port=config.API_PORT)
