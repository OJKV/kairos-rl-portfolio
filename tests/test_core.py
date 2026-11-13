import numpy as np
import pandas as pd
import pytest
from kairos.data import cohorts, validate_bars
from kairos.environment import ExitEnv, FeatureScaler, entry_gate, observation


def bars():
    n = 500
    price = 100.0 * np.exp(np.arange(n) * 0.0002)
    return pd.DataFrame({'time': pd.date_range('2024-01-01', periods=n, freq='h', tz='UTC'), 'open': price, 'high': price * 1.01, 'low': price * .99, 'close': price, 'volume': np.ones(n)})


def test_telescoping_exit_and_deadline():
    b = bars(); idx = 200; cost = 0.0015
    scaler = FeatureScaler([0]*5, [1]*5)
    for exit_hour in (1, 6, 24):
        env = ExitEnv(b, [idx], scaler, cost)
        obs, _ = env.reset(seed=4)
        rewards = []
        for hour in range(1, 24):
            obs, r, done, truncated, info = env.step(1 if hour == exit_hour else 0)
            rewards.append(r)
            if done: break
        expected = b.open.iloc[idx + exit_hour] / b.open.iloc[idx] * (1-cost)/(1+cost)
        assert not truncated
        assert info['hour'] == exit_hour
        assert info['equity'] == pytest.approx(10000 * expected)
        assert sum(rewards) == pytest.approx(100 * np.log(expected))
        with pytest.raises(ValueError): env.step(0)


def test_causal_features_and_gate():
    b = bars(); i = 220
    before = observation(b, i, b.open.iloc[i - 3], .0015, 3)
    altered = b.copy(); altered.loc[i:, ['open','high','low','close']] *= 10
    after = observation(altered, i, b.open.iloc[i - 3], .0015, 3)
    np.testing.assert_array_equal(before, after)
    assert entry_gate(b, i) == entry_gate(altered, i)
    assert len(observation(b, len(b), b.open.iloc[-3], .0015, 3)) == 8


def test_missing_hour_excludes_cohort_and_boundary():
    b = bars(); b = b.drop(index=220).reset_index(drop=True)
    validate_bars(b)
    c = cohorts(b, '2024-01-08', '2024-01-18')
    assert not c.loc[c.day == pd.Timestamp('2024-01-10', tz='UTC'), 'valid'].iloc[0]
    assert not c.iloc[-1].valid


def test_invalid_data_rejected():
    b = bars(); b.loc[100, 'high'] = 1
    with pytest.raises(ValueError): validate_bars(b)


def test_baseline_comparisons_share_ledger():
    from kairos.research import simulate
    b = bars(); scaler = FeatureScaler([0]*5, [1]*5)
    for method, hour in [('fixed_6h', 6), ('fixed_24h', 24), ('trailing_2pct', 24)]:
        trade, trace = simulate(b, 200, method, None, scaler, .0015, None)
        expected = b.open.iloc[200 + hour] / b.open.iloc[200] * (1-.0015)/(1+.0015) - 1
        assert trade['holding_hours'] == hour
        assert trade['net_return'] == pytest.approx(expected)
        assert len(trace) == 24
        assert trace[hour-1]['action'] == 'exit'
        assert all(t['action'] == 'cash' for t in trace[hour:])


def test_complete_hourly_cohort_is_valid():
    b = bars()
    c = cohorts(b, '2024-01-09', '2024-01-11')
    assert c.iloc[0].valid
    assert c.iloc[0].gate
    assert not c.iloc[-1].valid


def test_evaluation_outputs_same_days_and_models(tmp_path):
    from kairos.research import outputs
    b = bars(); c = cohorts(b, '2024-01-09', '2024-01-11')
    scaler = FeatureScaler([0]*5, [1]*5)
    class Policy:
        def predict(self, obs, deterministic):
            assert deterministic
            return np.array(1), None
    summary = outputs(tmp_path, b, c, {0: Policy()}, scaler)
    trades = pd.read_csv(tmp_path / 'trades.csv')
    steps = pd.read_csv(tmp_path / 'steps.csv')
    assert summary['selected_baseline'] in {'fixed_6h', 'fixed_24h', 'trailing_2pct'}
    assert len(trades) == 8
    assert len(steps) == 8*24
    assert set(trades['cost_bps']) == {15, 30}
    assert len(trades.day.unique()) == 1
    assert (trades.loc[trades.method == 'ppo', 'holding_hours'] == 1).all()
    assert {'open','high','low','close','bar_end'} <= set(steps.columns)


def test_training_learns_toy_stopping_and_bundle_integrity(tmp_path):
    import gymnasium as gym
    import torch
    from stable_baselines3 import PPO
    from kairos.research import save_bundle, load_bundle
    class StopTask(gym.Env):
        observation_space = gym.spaces.Box(-1, 1, (8,), dtype=np.float32)
        action_space = gym.spaces.Discrete(2)
        def reset(self, *, seed=None, options=None):
            super().reset(seed=seed)
            return np.zeros(8, np.float32), {}
        def step(self, action):
            return np.zeros(8, np.float32), float(action == 1), True, False, {}
    torch.set_num_threads(1)
    model = PPO('MlpPolicy', StopTask(), n_steps=64, batch_size=32, n_epochs=3, learning_rate=.003, seed=1, verbose=0)
    model.learn(total_timesteps=512)
    assert int(model.predict(np.zeros(8, np.float32), deterministic=True)[0]) == 1
    scaler = FeatureScaler([0]*5, [1]*5)
    save_bundle(tmp_path, model, scaler, 0)
    loaded, fitted, config = load_bundle(tmp_path)
    assert int(loaded.predict(fitted.transform(np.zeros(8)), deterministic=True)[0]) == 1
    (tmp_path / 'scaler.json').write_text('{}')
    with pytest.raises(ValueError, match='hash mismatch'):
        load_bundle(tmp_path)


def test_off_hour_timestamps_rejected():
    b = bars(); b['time'] = b.time + pd.Timedelta(minutes=1)
    with pytest.raises(ValueError, match='align'):
        validate_bars(b)


def test_real_exit_environment_api():
    from gymnasium.utils.env_checker import check_env
    env = ExitEnv(bars(), [200, 220], FeatureScaler([0]*5, [1]*5))
    check_env(env, skip_render_check=True)


def test_evaluation_artifact_hashes(tmp_path):
    import json
    from kairos.research import outputs
    from kairos.data import sha256
    b = bars(); c = cohorts(b, '2024-01-09', '2024-01-11')
    scaler = FeatureScaler([0]*5, [1]*5)
    class Policy:
        def predict(self, obs, deterministic): return np.array(1), None
    summary = outputs(tmp_path, b, c, {0: Policy()}, scaler, 'fixed_6h', 'evaluation', 'test-freeze')
    manifest = json.loads((tmp_path / 'artifact_checksums.json').read_text())
    assert summary['freeze_id'] == manifest['freeze_id'] == 'test-freeze'
    for name, digest in manifest['files'].items():
        assert sha256(tmp_path / name) == digest
    assert len(summary['comparisons']) == 6
    assert not summary['continuation_screen']['checks']['all_three_seeds']


def test_training_source_snapshot_survives_source_change(tmp_path):
    import json
    from kairos.research import TRAINING_SOURCE_NAMES, snapshot_training_source, verify_training_source
    root = tmp_path / 'project'; run = tmp_path / 'run'; run.mkdir()
    for name in TRAINING_SOURCE_NAMES:
        p = root / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_text('original ' + name)
    hashes = snapshot_training_source(root, run)
    snapshot = run / 'provenance' / 'training-source'
    (root / TRAINING_SOURCE_NAMES[0]).write_text('changed after training start')
    verify_training_source(run, hashes)
    assert (snapshot / TRAINING_SOURCE_NAMES[0]).read_text().startswith('original ')
    assert json.loads((run / 'training_source.json').read_text()) == hashes
    assert len((snapshot.parent / 'training-source.sha256').read_text().splitlines()) == len(hashes)
    (snapshot / TRAINING_SOURCE_NAMES[0]).write_text('tampered')
    with pytest.raises(ValueError, match='hash mismatch'):
        verify_training_source(run, hashes)


def test_archive_manifest_distinguishes_audit_and_unknown_retrieval(tmp_path):
    import hashlib, zipfile
    from kairos.data import read_archives
    path = tmp_path / 'BTCUSDT-1h-2022-01.zip'
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('candles.csv', '1640995200000,100,101,99,100,5,0,0,0,0,0,0\n')
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / (path.name + '.CHECKSUM')).write_text(checksum + '  ' + path.name)
    b, records = read_archives(tmp_path)
    assert len(b) == 1
    assert records[0]['retrieved_at'] is None
    assert records[0]['audited_at']
    assert records[0]['url'].endswith(path.name)
    assert records[0]['published_sha256'] == records[0]['sha256'] == checksum
