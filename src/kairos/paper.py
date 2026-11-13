"""Public-data-only, observed-quote paper simulation. Never sends exchange orders."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

HOUR = 3_600_000
DAY = 24 * HOUR
DELAY = 2_000
MAX_LATE = 90_000
BASE = 'https://data-api.binance.vision'


def _json(value):
    return json.dumps(value, sort_keys=True, allow_nan=False)


def _connect(path):
    db = sqlite3.connect(path, timeout=10, isolation_level=None)
    db.execute('PRAGMA busy_timeout=10000')
    return db


def initialize(path, session_id, bundle_hash, now_ms, capital=10000., cost=.0015):
    if not session_id or not bundle_hash or not math.isfinite(capital) or capital <= 0 or not 0 <= cost < 1:
        raise ValueError('invalid session configuration')
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    state = dict(status='waiting', cash=float(capital), btc=0., cohort_day=None,
                 endpoint_ms=None, last_boundary_ms=None, entry_price=None, last_action=None,
                 updated_ms=now_ms, error=None, bundle_hash=bundle_hash, cost=cost,
                 start_day_ms=(now_ms // DAY + 1) * DAY, degraded=False, observed_peak=None)
    with _connect(path) as db:
        db.executescript('''CREATE TABLE IF NOT EXISTS sessions
            (session_id TEXT PRIMARY KEY, bundle_hash TEXT NOT NULL, state_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events
            (id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, cohort_day INTEGER NOT NULL,
             boundary_ms INTEGER NOT NULL, kind TEXT NOT NULL, payload_json TEXT NOT NULL,
             UNIQUE(session_id, cohort_day, boundary_ms, kind));''')
        db.execute('INSERT INTO sessions VALUES (?, ?, ?)', (session_id, bundle_hash, _json(state)))


def snapshot(path, session_id=None):
    """Read an atomic snapshot without ever creating or modifying the database."""
    uri = Path(path).resolve().as_uri() + '?mode=ro'
    with sqlite3.connect(uri, uri=True) as db:
        db.execute('BEGIN')
        if session_id is None:
            rows = db.execute('SELECT session_id, state_json FROM sessions ORDER BY session_id').fetchall()
            if len(rows) != 1:
                raise ValueError('specify session ID when database has zero or multiple sessions')
            session_id, state_json = rows[0]
        else:
            row = db.execute('SELECT state_json FROM sessions WHERE session_id=?', (session_id,)).fetchone()
            if row is None:
                raise ValueError('unknown session')
            state_json = row[0]
        events = [dict(cohort_day=r[0], boundary_ms=r[1], kind=r[2], payload=json.loads(r[3]))
                  for r in db.execute('SELECT cohort_day,boundary_ms,kind,payload_json FROM events WHERE session_id=? ORDER BY id', (session_id,))]
        return {'session_id': session_id, 'state': json.loads(state_json), 'events': events}


def _state(db, session_id, bundle_hash):
    row = db.execute('SELECT bundle_hash,state_json FROM sessions WHERE session_id=?', (session_id,)).fetchone()
    if not row or row[0] != bundle_hash:
        raise ValueError('unknown session or incompatible bundle')
    state = json.loads(row[1])
    cash, btc, cost = float(state['cash']), float(state['btc']), float(state['cost'])
    if not all(map(math.isfinite, (cash, btc, cost))) or cash < 0 or btc < 0 or cash + btc <= 0 or not 0 <= cost < 1:
        raise ValueError('invalid persisted paper ledger')
    return state


def _event(db, session_id, state, boundary, kind, payload):
    db.execute('INSERT INTO events(session_id,cohort_day,boundary_ms,kind,payload_json) VALUES(?,?,?,?,?)',
               (session_id, state['cohort_day'], boundary, kind, _json(payload)))


def _save(db, session_id, state, now):
    state['updated_ms'] = now
    db.execute('UPDATE sessions SET state_json=? WHERE session_id=?', (_json(state), session_id))


def _quote(market, boundary=None):
    q = market.quote()
    bid, ask = float(q['bid']), float(q['ask'])
    if not all(map(math.isfinite, (bid, ask, float(q['duration'])))) or bid <= 0 or ask <= 0 or bid > ask or not 0 <= q['duration'] <= 2:
        raise ValueError('invalid, crossed or slow observed quote')
    if boundary is not None and market.server_time() - boundary > MAX_LATE:
        raise ValueError('decision or quote exceeded the allowed boundary delay')
    q['mid'] = (bid + ask) / 2
    return q


def _bars(market, boundary):
    bars = market.bars(boundary)
    if len(bars) < 169:
        raise ValueError('insufficient completed candle history')
    timestamps = list(bars['open_time'])
    if timestamps[-1] != boundary - HOUR or any(b - a != HOUR for a, b in zip(timestamps, timestamps[1:])):
        raise ValueError('missing, duplicate or noncontiguous candles')
    for row in bars.itertuples(index=False):
        prices = (float(row.open), float(row.high), float(row.low), float(row.close))
        if not all(math.isfinite(p) and p > 0 for p in prices) or row.high < max(row.open, row.close, row.low) or row.low > min(row.open, row.close, row.high) or not math.isfinite(float(row.volume)) or row.volume < 0:
            raise ValueError('invalid candle')
    return bars


def _sell(db, sid, state, market, now, kind):
    q = _quote(market, now // HOUR * HOUR if kind == 'exit' else None)
    proceeds = state['btc'] * q['mid'] * (1 - state['cost'])
    if not math.isfinite(proceeds) or proceeds <= 0:
        raise ValueError('invalid liquidation proceeds')
    payload = dict(quote=q, quantity=state['btc'], cost=state['btc'] * q['mid'] * state['cost'], cash=proceeds, observed_ms=now)
    _event(db, sid, state, state['endpoint_ms'] if kind == 'deadline' else now // HOUR * HOUR, kind, payload)
    state.update(cash=proceeds, btc=0., status='exited', last_action=kind, error=None)
    if kind == 'deadline' and now > state['endpoint_ms'] + MAX_LATE:
        state['degraded'] = True
    return payload


def cycle(path, session_id, bundle_hash, market, policy):
    """Process at most one fresh boundary; all state and event writes are atomic."""
    try:
        now = int(market.server_time())
    except (OSError, ValueError, KeyError) as exc:
        with _connect(path) as db:
            db.execute('BEGIN IMMEDIATE')
            state = _state(db, session_id, bundle_hash)
            state['error'] = 'server time unavailable: ' + str(exc)
            if state['btc']:
                state.update(status='paused', degraded=True)
            _save(db, session_id, state, int(time.time() * 1000))
            db.commit()
            return state
    with _connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        state = _state(db, session_id, bundle_hash)
        if state['btc'] and now >= state['endpoint_ms']:
            try:
                _sell(db, session_id, state, market, now, 'deadline')
            except (ValueError, OSError, KeyError) as exc:
                state.update(status='liquidation_pending', error=str(exc), degraded=True)
                _save(db, session_id, state, now)
                db.commit()
                return state
            _save(db, session_id, state, now)
            db.commit()
            return state
        if state['status'] in ('paused', 'liquidation_pending'):
            return state
        boundary = now // HOUR * HOUR
        if now - boundary < DELAY or now < state['start_day_ms']:
            return state
        day = boundary // DAY * DAY
        if state['btc']:
            expected = state['last_boundary_ms'] + HOUR
            if boundary < expected:
                return state
            if boundary > expected or now - boundary > MAX_LATE:
                state.update(status='paused', error='missed or late hourly decision', degraded=True)
                _save(db, session_id, state, now)
                db.commit()
                return state
            try:
                bars = _bars(market, boundary)
                if market.server_time() - boundary > MAX_LATE:
                    raise ValueError('decision exceeded the allowed boundary delay')
                action = int(policy.decide(bars, state['entry_price'], state['cost'], (boundary - state['cohort_day']) // HOUR))
                if market.server_time() - boundary > MAX_LATE:
                    raise ValueError('inference exceeded the allowed boundary delay')
                if action not in (0, 1):
                    raise ValueError('invalid action')
                elapsed = (boundary - state['cohort_day']) // HOUR
                state['observed_peak'] = max(state['entry_price'], float(bars['close'].iloc[-elapsed:].max()))
                obs = getattr(policy, 'last_observation', None)
                if action == 1:
                    detail = _sell(db, session_id, state, market, now, 'exit')
                    detail.update(action=action, observation=obs, observed_peak=state['observed_peak'])
                    db.execute('UPDATE events SET payload_json=? WHERE id=last_insert_rowid()', (_json(detail),))
                else:
                    _event(db, session_id, state, boundary, 'hold', {'action': action, 'observation': obs, 'observed_peak': state['observed_peak']})
                state.update(last_boundary_ms=boundary, last_action='exit' if action else 'hold', error=None)
            except (ValueError, OSError, KeyError) as exc:
                state.update(status='paused', error=str(exc), degraded=True)
        else:
            if day < state['start_day_ms'] or (state['cohort_day'] is not None and day <= state['cohort_day']):
                return state
            state.update(cohort_day=day, endpoint_ms=day + DAY, last_boundary_ms=day, entry_price=None, degraded=False)
            if boundary != day or now - day > MAX_LATE:
                state.update(status='missed', last_action='missed', error='entry window passed')
                _event(db, session_id, state, day, 'missed', {'observed_ms': now})
            else:
                try:
                    bars = _bars(market, day)
                except (ValueError, OSError, KeyError) as exc:
                    state.update(status='paused', error=str(exc), degraded=True)
                else:
                    gate = bool(policy.gate(bars))
                    if not gate:
                        state.update(status='no_entry', last_action='no_entry', error=None)
                        _event(db, session_id, state, day, 'no_entry', {'gate': False, 'observed_ms': now})
                    else:
                        try:
                            q = _quote(market, day)
                        except (ValueError, OSError, KeyError) as exc:
                            state.update(status='paused', error=str(exc), degraded=True)
                        else:
                            quantity = state['cash'] / (q['mid'] * (1 + state['cost']))
                            _event(db, session_id, state, day, 'entry', {'gate': True, 'quote': q, 'quantity': quantity, 'cost': quantity * q['mid'] * state['cost'], 'observed_ms': now})
                            state.update(status='held', btc=quantity, cash=0., entry_price=q['mid'], observed_peak=q['mid'], last_action='entry', error=None)
        _save(db, session_id, state, now)
        db.commit()
        return state


def recover(path, session_id, bundle_hash, market):
    now = int(market.server_time())
    with _connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        state = _state(db, session_id, bundle_hash)
        if state['status'] != 'paused':
            raise ValueError('only paused sessions can be recovered')
        if state['btc'] and now >= state['endpoint_ms']:
            raise ValueError('deadline passed; use cycle for current-quote liquidation')
        boundary = now // HOUR * HOUR
        bars = _bars(market, boundary)
        old = state['last_boundary_ms']
        if state['btc']:
            if boundary > old:
                _event(db, session_id, state, boundary, 'recovery', {'skipped_after_ms': old, 'through_ms': boundary, 'observed_ms': now})
                state['last_boundary_ms'] = boundary
            elapsed = (boundary - state['cohort_day']) // HOUR
            state['observed_peak'] = max(state['entry_price'], float(bars['close'].iloc[-elapsed:].max()))
            state.update(status='held', error=None)
        else:
            _event(db, session_id, state, boundary, 'recovery', {'missed_entry': True, 'observed_ms': now})
            state.update(status='missed', error=None)
        _save(db, session_id, state, now)
        db.commit()
        return state


def close(path, session_id, bundle_hash, market):
    now = int(market.server_time())
    with _connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        state = _state(db, session_id, bundle_hash)
        if not state['btc']:
            raise ValueError('no position to close')
        _sell(db, session_id, state, market, now, 'manual_close')
        _save(db, session_id, state, now)
        db.commit()
        return state


class BinanceMarket:
    def _get(self, path, params=None):
        url = BASE + path + ('?' + urlencode(params) if params else '')
        with urlopen(url, timeout=2) as response:
            return json.load(response)

    def server_time(self):
        return int(self._get('/api/v3/time')['serverTime'])

    def bars(self, boundary):
        import pandas as pd
        rows = self._get('/api/v3/klines', {'symbol': 'BTCUSDT', 'interval': '1h', 'endTime': boundary - 1, 'limit': 200})
        return pd.DataFrame([[int(r[0]), *map(float, r[1:6])] for r in rows], columns=['open_time', 'open', 'high', 'low', 'close', 'volume'])

    def quote(self):
        start = int(time.time() * 1000)
        monotonic = time.monotonic()
        data = self._get('/api/v3/ticker/bookTicker', {'symbol': 'BTCUSDT'})
        return dict(bid=float(data['bidPrice']), ask=float(data['askPrice']), request_ms=start,
                    received_ms=int(time.time() * 1000), duration=time.monotonic() - monotonic,
                    update_id=data.get('lastUpdateId'))


class FrozenPolicy:
    def __init__(self, bundle):
        validate_freeze(bundle)
        from kairos.research import load_bundle
        self.model, self.scaler, self.config = load_bundle(bundle)
        if self.config['seed'] != 0 or self.config['gate'] != 'positive_24h_return' or self.config['symbol'] != 'BTCUSDT' or self.config['interval'] != '1h':
            raise ValueError('paper requires matching seed-0 BTCUSDT hourly bundle')

    def gate(self, bars):
        from kairos.environment import entry_gate
        return entry_gate(bars, len(bars))

    def decide(self, bars, entry, cost, elapsed):
        from kairos.environment import observation
        obs = observation(bars, len(bars), entry, cost, elapsed)
        self.last_observation = obs.tolist()
        action, _ = self.model.predict(self.scaler.transform(obs), deterministic=True)
        return int(action)


def validate_freeze(bundle):
    """Require a sealed run tied to this exact seed-0 config and policy."""
    path = Path(bundle)
    try:
        config_bytes = (path / 'config.json').read_bytes()
        freeze_bytes = (path / 'freeze.json').read_bytes()
        config = json.loads(config_bytes)
        freeze = json.loads(freeze_bytes)
        valid = (freeze.get('frozen') is True and freeze.get('sealed') is True
                 and freeze.get('config_sha256') == hashlib.sha256(config_bytes).hexdigest()
                 and freeze.get('bundle_config') == config and config.get('seed') == 0
                 and freeze.get('policy_hashes', {}).get('0') == config.get('policy_sha256')
                 and bool(config.get('policy_sha256')))
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        raise ValueError('missing or invalid sealed freeze') from exc
    if not valid:
        raise ValueError('missing, unsealed or incompatible frozen bundle')
    return hashlib.sha256(freeze_bytes).hexdigest()


def bundle_hash(bundle):
    return validate_freeze(bundle)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['init', 'status', 'once', 'run', 'recover', 'close'])
    parser.add_argument('--db', required=True)
    parser.add_argument('--session', required=True)
    parser.add_argument('--bundle', help='frozen seed-0 bundle directory (required except status)')
    args = parser.parse_args(argv)
    if args.command == 'status':
        print(_json(snapshot(args.db, args.session)))
        return
    if not args.bundle:
        parser.error('--bundle is required')
    policy = FrozenPolicy(args.bundle)
    identity = bundle_hash(args.bundle)
    market = BinanceMarket()
    if args.command == 'init':
        initialize(args.db, args.session, identity, market.server_time(), cost=float(policy.config['cost']))
        print(_json(snapshot(args.db, args.session)))
    elif args.command == 'recover':
        print(_json(recover(args.db, args.session, identity, market)))
    elif args.command == 'close':
        print(_json(close(args.db, args.session, identity, market)))
    else:
        while True:
            print(_json(cycle(args.db, args.session, identity, market, policy)), flush=True)
            if args.command == 'once': break
            time.sleep(5)


if __name__ == '__main__':
    main()
