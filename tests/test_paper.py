import json
import io
from contextlib import redirect_stdout
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from kairos import paper

H = 3_600_000
DAY = 24 * H


class Market:
    def __init__(self, now):
        self.now = now
        self.quote_calls = 0
        self.broken = False

    def server_time(self):
        return self.now

    def bars(self, boundary):
        import pandas as pd
        rows = []
        for t in range(boundary - 200 * H, boundary, H):
            p = 100 + (t - (boundary - 200 * H)) / 100
            rows.append([t, p, p, p, p, 1.0])
        if self.broken:
            rows.pop(-3)
        return pd.DataFrame(rows, columns=['open_time', 'open', 'high', 'low', 'close', 'volume'])

    def quote(self):
        self.quote_calls += 1
        return {'bid': 99.0, 'ask': 101.0, 'request_ms': self.now,
                'received_ms': self.now + 1, 'duration': 0.001}


class Policy:
    def __init__(self, action=0): self.action = action
    def gate(self, bars): return True
    def decide(self, bars, entry, cost, elapsed): return self.action


class PaperTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'paper.db'
        self.t = 30 * DAY
        self.m = Market(self.t - 5000)
        self.p = Policy()
        paper.initialize(self.db, 's', 'hash', self.m.now, 10000, 0.0015)

    def test_initialize_creates_missing_state_directory(self):
        nested = Path(self.tmp.name) / 'state' / 'paper.sqlite'
        paper.initialize(nested, 'new', 'hash', self.m.now)
        self.assertEqual(paper.snapshot(nested, 'new')['state']['cash'], 10000.)

    def tearDown(self): self.tmp.cleanup()

    def step(self, ms):
        self.m.now = ms
        return paper.cycle(self.db, 's', 'hash', self.m, self.p)

    def test_entry_duplicate_exit_and_snapshot(self):
        self.step(self.t + 2000)
        s = paper.snapshot(self.db, 's')
        self.assertEqual(s['state']['status'], 'held')
        self.assertAlmostEqual(s['state']['btc'], 10000 / 100 / 1.0015)
        self.step(self.t + 3000)
        self.assertEqual(self.m.quote_calls, 1)
        self.p.action = 1
        self.step(self.t + H + 2000)
        s = paper.snapshot(self.db, 's')
        self.assertEqual(s['state']['status'], 'exited')
        self.assertAlmostEqual(s['state']['cash'], 10000 * (1 - .0015) / (1 + .0015))
        self.assertEqual(len([e for e in s['events'] if e['kind'] == 'exit']), 1)

    def test_late_entry_and_no_retroactive_trade(self):
        self.step(self.t + 91000)
        self.assertEqual(paper.snapshot(self.db, 's')['state']['status'], 'missed')
        self.assertEqual(self.m.quote_calls, 0)
        self.step(self.t + H + 2000)
        self.assertEqual(self.m.quote_calls, 0)

    def test_gap_pause_recover_then_future_action(self):
        self.step(self.t + 2000)
        self.step(self.t + 2 * H + 2000)
        self.assertEqual(paper.snapshot(self.db, 's')['state']['status'], 'paused')
        paper.recover(self.db, 's', 'hash', self.m)
        self.assertEqual(paper.snapshot(self.db, 's')['state']['status'], 'held')
        self.step(self.t + 3 * H + 2000)
        self.assertEqual(paper.snapshot(self.db, 's')['state']['last_boundary_ms'], self.t + 3 * H)

    def test_deadline_after_outage_and_bundle_mismatch(self):
        self.step(self.t + 2000)
        self.m.now = self.t + DAY + 4 * H
        with self.assertRaises(ValueError):
            paper.cycle(self.db, 's', 'wrong', self.m, self.p)
        paper.cycle(self.db, 's', 'hash', self.m, self.p)
        s = paper.snapshot(self.db, 's')['state']
        self.assertEqual(s['status'], 'exited')
        self.assertEqual(s['btc'], 0)
        self.assertTrue(s['degraded'])

    def test_bad_quote_and_crash_leave_no_trade(self):
        self.m.quote = lambda: {'bid': 101., 'ask': 100., 'request_ms': self.m.now,
                                'received_ms': self.m.now, 'duration': 0.0}
        self.step(self.t + 2000)
        self.assertEqual(paper.snapshot(self.db, 's')['state']['status'], 'paused')
        self.assertEqual(paper.snapshot(self.db, 's')['events'], [])

    def test_transaction_rolls_back_if_crash_before_commit(self):
        self.m.now = self.t + 2000
        with patch.object(paper, '_save', side_effect=RuntimeError('crash')):
            with self.assertRaises(RuntimeError):
                paper.cycle(self.db, 's', 'hash', self.m, self.p)
        snap = paper.snapshot(self.db, 's')
        self.assertEqual(snap['state']['status'], 'waiting')
        self.assertEqual(snap['events'], [])
        paper.cycle(self.db, 's', 'hash', self.m, self.p)
        self.assertEqual(len(paper.snapshot(self.db, 's')['events']), 1)

    def test_slow_or_late_quote_cannot_enter(self):
        self.m.now = self.t + 2000
        def late():
            self.m.now = self.t + 91000
            return {'bid': 99., 'ask': 101., 'request_ms': self.t + 2000,
                    'received_ms': self.t + 91000, 'duration': .1}
        self.m.quote = late
        paper.cycle(self.db, 's', 'hash', self.m, self.p)
        self.assertEqual(paper.snapshot(self.db, 's')['state']['btc'], 0)
        self.assertEqual(paper.snapshot(self.db, 's')['state']['status'], 'paused')
        paper.recover(self.db, 's', 'hash', self.m)
        self.assertEqual(paper.snapshot(self.db, 's')['state']['status'], 'missed')

    def test_network_loss_preserves_position_and_pauses(self):
        self.step(self.t + 2000)
        self.m.server_time = lambda: (_ for _ in ()).throw(OSError('offline'))
        state = paper.cycle(self.db, 's', 'hash', self.m, self.p)
        self.assertEqual(state['status'], 'paused')
        self.assertGreater(state['btc'], 0)
        self.assertIn('offline', state['error'])

    def test_bundle_requires_matching_sealed_freeze(self):
        import hashlib
        bundle = Path(self.tmp.name) / 'bundle'
        bundle.mkdir()
        config = {'seed': 0, 'policy_sha256': 'policy'}
        raw = json.dumps(config).encode()
        (bundle / 'config.json').write_bytes(raw)
        with self.assertRaises(ValueError):
            paper.validate_freeze(bundle)
        freeze = {'frozen': True, 'sealed': True, 'config_sha256': hashlib.sha256(raw).hexdigest(),
                  'bundle_config': config, 'policy_hashes': {'0': 'policy'}}
        (bundle / 'freeze.json').write_text(json.dumps(freeze))
        identity = paper.validate_freeze(bundle)
        self.assertEqual(len(identity), 64)
        freeze['policy_hashes']['0'] = 'tampered'
        (bundle / 'freeze.json').write_text(json.dumps(freeze))
        with self.assertRaises(ValueError):
            paper.validate_freeze(bundle)
        freeze['policy_hashes']['0'] = 'policy'
        freeze['sealed'] = False
        (bundle / 'freeze.json').write_text(json.dumps(freeze))
        with self.assertRaises(ValueError):
            paper.validate_freeze(bundle)
        freeze['sealed'] = True
        (bundle / 'freeze.json').write_text(json.dumps(freeze))
        (bundle / 'config.json').write_text(json.dumps({'seed': 1}))
        with self.assertRaises(ValueError):
            paper.validate_freeze(bundle)

    def test_cli_accepts_delegated_arguments_and_reads_status(self):
        output = io.StringIO()
        with redirect_stdout(output):
            paper.main(['status', '--db', str(self.db), '--session', 's'])
        self.assertEqual(json.loads(output.getvalue())['state']['status'], 'waiting')

    def test_invalid_ledger_is_rejected_without_trade(self):
        import sqlite3
        with sqlite3.connect(self.db) as db:
            state = json.loads(db.execute('SELECT state_json FROM sessions').fetchone()[0])
            state['cash'] = -1
            db.execute('UPDATE sessions SET state_json=?', (json.dumps(state),))
        with self.assertRaises(ValueError):
            self.step(self.t + 2000)
        self.assertEqual(self.m.quote_calls, 0)

    def test_data_gap_pauses_and_read_only_snapshot(self):
        self.m.broken = True
        self.step(self.t + 2000)
        self.assertEqual(paper.snapshot(self.db, 's')['state']['status'], 'paused')
        with self.assertRaises(Exception):
            import sqlite3
            con = sqlite3.connect(f'file:{self.db}?mode=ro', uri=True)
            try: con.execute('DELETE FROM sessions')
            finally: con.close()

if __name__ == '__main__': unittest.main()
