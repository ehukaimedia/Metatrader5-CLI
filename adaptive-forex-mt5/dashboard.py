"""Trade journal dashboard.

Local web view of agent trades, reasoning, and outcomes. Reads journal.py
and state.db. Binds 127.0.0.1; expose to tailnet via:
    tailscale serve https / http://localhost:8765
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import journal
import state_db

ROOT = Path(__file__).parent
STATE_DB = ROOT / "state.db"


def load_config() -> dict:
    cfg_path = ROOT / "config.json"
    if not cfg_path.exists():
        raise SystemExit("missing config.json")
    return json.loads(cfg_path.read_text(encoding="utf-8"))


def _state_payload() -> dict:
    """Read the manager's mutable state for the dashboard."""
    if not STATE_DB.exists():
        return {"managed": [], "heartbeat": [], "unmanaged_warnings": []}
    managed = state_db.list_managed_positions(STATE_DB, only_active=True)
    hb = state_db.heartbeat_all(STATE_DB)
    # Unmanaged-warning rows live in their own table so positions that never
    # bootstrapped (no journal match, fail-closed) still surface a banner —
    # the previous implementation read from managed_position which by
    # definition does not exist for fail-closed cases.
    unmanaged = state_db.unmanaged_warning_recent(STATE_DB, since_seconds=60)
    return {"managed": managed, "heartbeat": hb, "unmanaged_warnings": unmanaged}


INDEX_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>adaptive-forex-mt5 journal</title>
<style>
  body { font-family: -apple-system, system-ui, sans-serif; background: #0f1419; color: #e6e6e6; margin: 0; padding: 16px; }
  h1, h2 { font-size: 14px; color: #94a3b8; font-weight: 500; margin: 0 0 10px; text-transform: uppercase; letter-spacing: 0.5px; }
  .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 8px; margin-bottom: 20px; }
  .stat { background: #1a2332; border-radius: 6px; padding: 10px; }
  .stat .v { font-size: 22px; font-weight: 600; color: #f1f5f9; font-variant-numeric: tabular-nums; }
  .stat .l { font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; }
  .stat.win .v { color: #5eead4; }
  .stat.loss .v { color: #f87171; }
  .trade { background: #1a2332; border-radius: 6px; padding: 12px; margin-bottom: 8px; border-left: 3px solid #475569; }
  .trade.open { border-left-color: #fbbf24; }
  .trade.win { border-left-color: #5eead4; }
  .trade.loss { border-left-color: #f87171; }
  .trade .top { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; flex-wrap: wrap; }
  .sym { font-weight: 600; font-size: 16px; }
  .dir { display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: 11px; font-weight: 600; text-transform: uppercase; }
  .dir.buy { background: #134e4a; color: #5eead4; }
  .dir.sell { background: #422006; color: #fbbf24; }
  .meta { color: #64748b; font-size: 12px; font-variant-numeric: tabular-nums; }
  .row { display: flex; gap: 16px; flex-wrap: wrap; margin-top: 6px; font-size: 13px; color: #cbd5e1; }
  .row span b { color: #94a3b8; font-weight: 500; }
  .reason { margin-top: 8px; font-size: 12px; color: #94a3b8; line-height: 1.5; }
  .gates { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
  .gate { background: #134e4a; color: #5eead4; padding: 1px 6px; border-radius: 3px; font-size: 10px; }
  .pl { font-variant-numeric: tabular-nums; font-weight: 600; }
  .pl.pos { color: #5eead4; }
  .pl.neg { color: #f87171; }
  .by-pair { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 8px; margin-bottom: 16px; }
  .pair-card { background: #1a2332; border-radius: 6px; padding: 8px 10px; font-size: 12px; }
  .pair-card .p { font-weight: 600; color: #f1f5f9; }
  .empty { color: #64748b; font-style: italic; padding: 24px 0; text-align: center; }
</style></head>
<body>
<div id="banner"></div>
<h1>adaptive-forex-mt5 journal <span class="meta" id="ts">-</span></h1>
<div class="stats" id="stats"></div>
<h2>Process heartbeat</h2>
<div class="by-pair" id="hb"></div>
<h2>Managed positions</h2>
<div id="managed"></div>
<h2>By pair</h2>
<div class="by-pair" id="bypair"></div>
<h2>Trades</h2>
<div id="trades"></div>
<script>
function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
}
function fmt(n, d) { return Number(n).toFixed(d); }
function digitsFor(s) { return s && s.endsWith && s.endsWith('JPY') ? 3 : 5; }

async function refreshState() {
  try {
    const s = await (await fetch('/state.json')).json();
    const banner = document.getElementById('banner');
    banner.replaceChildren();
    if ((s.unmanaged_warnings || []).length > 0) {
      const items = s.unmanaged_warnings.map(u => u.symbol + '#' + u.ticket).join('; ');
      const b = el('div', null, '⚠ Unmanaged poc-magic positions: ' + items);
      b.style.cssText = 'background:#7f1d1d;color:white;padding:10px;border-radius:6px;margin-bottom:12px;font-weight:600;';
      banner.appendChild(b);
    }

    const hb = document.getElementById('hb');
    hb.replaceChildren();
    const now = Date.now();
    for (const h of s.heartbeat || []) {
      const t = new Date(h.last_seen).getTime();
      const ageS = (now - t) / 1000;
      const floor = h.process === 'manager' ? 10 : 120;
      const ok = ageS <= floor;
      const card = el('div', 'pair-card');
      card.appendChild(el('div', 'p', h.process));
      card.appendChild(el('div', 'meta', 'pid ' + (h.pid || '?') + ' · ' + ageS.toFixed(1) + 's ago'));
      const status = el('div', 'pl ' + (ok ? 'pos' : 'neg'), ok ? 'OK' : 'STALE');
      card.appendChild(status);
      hb.appendChild(card);
    }
    if ((s.heartbeat || []).length === 0) {
      hb.appendChild(el('div', 'empty', 'no heartbeats yet'));
    }

    const m = document.getElementById('managed');
    m.replaceChildren();
    if ((s.managed || []).length === 0) {
      m.appendChild(el('div', 'empty', 'no managed positions'));
    }
    for (const r of s.managed || []) {
      const cur_sl = r.last_sl_set != null ? r.last_sl_set : r.initial_sl;
      const card = el('div', 'trade');
      const top = el('div', 'top');
      const left = el('span');
      left.appendChild(el('span', 'sym', r.symbol));
      const dirCls = r.direction === 'buy' ? 'dir buy' : 'dir sell';
      left.appendChild(el('span', dirCls, r.direction.toUpperCase()));
      left.appendChild(el('span', 'meta', ' · #' + r.ticket + ' · ' + r.stage + (r.pending_action ? ' (pending: ' + r.pending_action + ')' : '')));
      top.appendChild(left);
      card.appendChild(top);
      const row = el('div', 'row');
      function field(label, val) {
        const s = el('span'); s.appendChild(el('b', null, label + ' '));
        s.appendChild(document.createTextNode(val)); return s;
      }
      row.appendChild(field('entry', fmt(r.entry_price, r.digits)));
      row.appendChild(field('init sl', fmt(r.initial_sl, r.digits)));
      row.appendChild(field('cur sl', fmt(cur_sl, r.digits)));
      if (r.favorable_extreme_price != null) row.appendChild(field('hwm', fmt(r.favorable_extreme_price, r.digits)));
      card.appendChild(row);
      m.appendChild(card);
    }
  } catch (e) {
    // state.db may not exist yet — silently ignore
  }
}

async function refresh() {
  await refreshState();
  try {
    const j = await (await fetch('/journal.json')).json();
    document.getElementById('ts').textContent = 'updated ' + new Date().toLocaleTimeString();
    const st = j.stats;
    const stats = document.getElementById('stats');
    stats.replaceChildren();
    function addStat(label, value, cls) {
      const s = el('div', 'stat' + (cls ? ' ' + cls : ''));
      s.appendChild(el('div', 'v', value));
      s.appendChild(el('div', 'l', label));
      stats.appendChild(s);
    }
    addStat('total', st.total);
    addStat('open', st.open);
    addStat('wins', st.wins, 'win');
    addStat('losses', st.losses, 'loss');
    addStat('win rate', (st.win_rate * 100).toFixed(0) + '%');
    const netVal = st.total_net !== undefined ? st.total_net : (st.total_profit || 0);
    addStat('net P/L', (netVal >= 0 ? '+' : '') + fmt(netVal, 2), netVal >= 0 ? 'win' : 'loss');
    if (st.total_realized_r !== undefined) {
      addStat('total R', (st.total_realized_r >= 0 ? '+' : '') + fmt(st.total_realized_r, 2), st.total_realized_r >= 0 ? 'win' : 'loss');
      addStat('avg R', (st.avg_realized_r >= 0 ? '+' : '') + fmt(st.avg_realized_r, 2));
    }

    const bp = document.getElementById('bypair');
    bp.replaceChildren();
    const pairs = Object.entries(st.by_pair || {});
    if (pairs.length === 0) {
      bp.appendChild(el('div', 'empty', 'no closed trades yet'));
    }
    for (const [pair, b] of pairs) {
      const card = el('div', 'pair-card');
      card.appendChild(el('div', 'p', pair));
      card.appendChild(el('div', 'meta', b.wins + 'W / ' + b.losses + 'L · ' + b.total + ' total'));
      const n = b.net !== undefined ? b.net : (b.profit || 0);
      const pl = el('div', 'pl ' + (n >= 0 ? 'pos' : 'neg'), (n >= 0 ? '+' : '') + fmt(n, 2));
      card.appendChild(pl);
      if (b.realized_r_sum !== undefined && b.total > 0) {
        const rr = b.realized_r_sum;
        card.appendChild(el('div', 'meta', 'R: ' + (rr >= 0 ? '+' : '') + fmt(rr, 2)));
      }
      bp.appendChild(card);
    }

    const tr = document.getElementById('trades');
    tr.replaceChildren();
    if ((j.trades || []).length === 0) {
      tr.appendChild(el('div', 'empty', 'no trades yet'));
    }
    for (const t of j.trades || []) {
      const oc = t.outcome;
      const open = !oc;
      const win = oc && (oc.result === 'tp' || (oc.profit || 0) > 0);
      const loss = oc && (oc.result === 'sl' || (oc.profit || 0) < 0);
      const cls = 'trade' + (open ? ' open' : win ? ' win' : loss ? ' loss' : '');
      const card = el('div', cls);

      const top = el('div', 'top');
      const left = el('div');
      left.appendChild(el('span', 'sym', t.pair || '?'));
      left.appendChild(document.createTextNode(' '));
      left.appendChild(el('span', 'dir ' + (t.direction || ''), t.direction || '-'));
      left.appendChild(document.createTextNode(' '));
      left.appendChild(el('span', 'meta', '#' + (t.ticket || '?') + ' · ' + new Date(t.ts).toLocaleString()));
      top.appendChild(left);

      const right = el('div');
      if (oc) {
        const profit = oc.profit || 0;
        right.appendChild(el('span', 'pl ' + (profit >= 0 ? 'pos' : 'neg'), (profit >= 0 ? '+' : '') + fmt(profit, 2)));
      } else {
        right.appendChild(el('span', 'meta', 'OPEN'));
      }
      top.appendChild(right);
      card.appendChild(top);

      const digits = digitsFor(t.pair);
      const row = el('div', 'row');
      function field(label, val) {
        const s = el('span');
        const b = el('b', null, label + ' ');
        s.appendChild(b);
        s.appendChild(document.createTextNode(val));
        return s;
      }
      if (t.entry !== undefined) row.appendChild(field('entry', fmt(t.entry, digits)));
      if (t.sl !== undefined) row.appendChild(field('sl', fmt(t.sl, digits)));
      if (t.tp !== undefined) row.appendChild(field('tp', fmt(t.tp, digits)));
      if (t.rr !== undefined) row.appendChild(field('rr', fmt(t.rr, 2)));
      if (t.reasoning && t.reasoning.quality_score !== undefined) row.appendChild(field('q', fmt(t.reasoning.quality_score, 2)));
      card.appendChild(row);

      const r = t.reasoning || {};
      if (r.explain && r.explain.length) {
        const why = el('div', 'reason', r.explain.join(' · '));
        card.appendChild(why);
      }
      if (r.gates_passed && r.gates_passed.length) {
        const g = el('div', 'gates');
        for (const name of r.gates_passed) g.appendChild(el('span', 'gate', name));
        card.appendChild(g);
      }
      tr.appendChild(card);
    }
  } catch (e) {
    document.getElementById('ts').textContent = 'fetch error: ' + String(e);
  }
}
refresh();
setInterval(refresh, REFRESH_MS);
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args, **kwargs):
        pass

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            html = INDEX_HTML.replace("REFRESH_MS", str(self.server.refresh_ms))
            self._send(200, "text/html; charset=utf-8", html)
            return
        if self.path == "/journal.json":
            payload = {
                "trades": journal.folded_trades(),
                "stats": journal.stats(),
            }
            self._send(200, "application/json", json.dumps(payload, default=str))
            return
        if self.path == "/state.json":
            self._send(200, "application/json", json.dumps(_state_payload(), default=str))
            return
        self._send(404, "text/plain", "not found")

    def _send(self, code: int, ctype: str, body: str) -> None:
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)


def run() -> None:
    cfg = load_config()
    host = cfg["dashboard"]["bind_host"]
    port = int(cfg["dashboard"]["bind_port"])
    refresh_ms = int(cfg["dashboard"]["refresh_seconds"]) * 1000
    server = ThreadingHTTPServer((host, port), Handler)
    server.refresh_ms = refresh_ms
    print(f"[dashboard] http://{host}:{port}/  (refresh {refresh_ms}ms)")
    print("[dashboard] expose to tailnet:  tailscale serve https / http://localhost:" + str(port))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[dashboard] stopped")


if __name__ == "__main__":
    run()
