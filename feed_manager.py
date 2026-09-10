# feed_manager.py
"""
Streaming LTP layer over GrowwFeed (sync-poll mode).

We deliberately never call feed.consume() (it blocks forever). Instead we
subscribe once and poll feed.get_ltp(), which returns the last tick per
instrument. The broker serves get_ltp() from this cache while fresh and
falls back to REST otherwise, so a dead socket degrades gracefully instead
of halting trading.
"""

import time


class FeedManager:
    """Subscribe/diff/cache wrapper around a GrowwFeed instance."""

    def __init__(self, feed, now=None):
        """
        Args:
            feed: GrowwFeed instance (already constructed with auth client).
            now: Clock function returning epoch seconds (injectable for tests).
        """
        self._feed = feed
        self._now = now or time.time
        self._subscribed: set = set()
        self._tokens: dict = {}
        self.last_ok: float = 0.0
        self.active: bool = False

    @staticmethod
    def _instrument(symbol: str, token: str) -> dict:
        return {"exchange": "NSE", "segment": "CASH", "exchange_token": str(token)}

    def resubscribe(self, symbols: list, tokens: dict) -> bool:
        """
        Converge subscriptions to exactly `symbols` (intersected with
        resolved tokens). Returns True when the feed is usable afterwards.
        Never raises.
        """
        want = {s for s in symbols if s in tokens}
        try:
            drop = self._subscribed - want
            add = want - self._subscribed
            if drop:
                # NOTE: dropped symbols may be absent from the new token map -
                # resolve instruments from the currently subscribed tokens
                self._feed.unsubscribe_ltp(
                    [self._instrument(s, self._tokens[s]) for s in sorted(drop)
                     if s in self._tokens]
                )
                self._subscribed -= drop
            if add:
                self._feed.subscribe_ltp(
                    [self._instrument(s, tokens[s]) for s in sorted(add)]
                )
                self._subscribed |= add
            self._tokens = {s: tokens[s] for s in want}
            self.active = True
            return True
        except Exception:
            self.active = False
            return False

    def get_cached(self, symbols: list) -> tuple:
        """
        Returns ({symbol: price}, parsed_any) from the streaming store.
        Raises on transport/parse failure so callers fall back to REST.
        """
        raw = self._feed.get_ltp() or {}
        node = ((raw.get("ltp") or {}).get("NSE") or {}).get("CASH") or {}
        prices: dict = {}
        latest = 0.0
        for s in symbols:
            tok = self._tokens.get(s)
            if tok is None:
                continue
            entry = node.get(str(tok)) or node.get(tok)
            if not entry:
                continue
            try:
                prices[s] = float(entry["ltp"])
                ts = float(entry.get("tsInMillis", 0) or 0)
                if ts > latest:
                    latest = ts
            except (TypeError, ValueError, KeyError):
                continue
        if latest > 0:
            self.last_ok = latest / 1000.0
        return prices, bool(prices)

    def is_fresh(self, max_age_s: float) -> bool:
        """True when ticks arrived recently enough to trust for decisions."""
        return self.active and (self._now() - self.last_ok) <= max_age_s

    def stop(self) -> None:
        """Unsubscribe everything. Never raises."""
        try:
            if self._subscribed:
                self._feed.unsubscribe_ltp(
                    [self._instrument(s, self._tokens[s]) for s in sorted(self._subscribed)]
                )
        except Exception:
            pass
        finally:
            self._subscribed = set()
            self._tokens = {}
            self.active = False
