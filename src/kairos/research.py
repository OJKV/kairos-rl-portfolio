"""Training, frozen bundle identity and matched evaluation artifacts."""
from pathlib import Path
import hashlib
import json
import platform
import sys
import subprocess
from importlib import metadata

import numpy as np
import pandas as pd
import torch
from stable_baselines3 import PPO

from .data import PARTITIONS, cohorts, read_archives, save_manifest, sha256
from .environment import ExitEnv, FeatureScaler, SCHEMA, observation


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def schema_hash():
    return hashlib.sha256(json.dumps(SCHEMA, separators=(',', ':')).encode()).hexdigest()


def save_bundle(path, model, scaler, seed, cost=0.0015):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    model.save(str(path / 'policy_seed_0.zip'))
    write_json(path / 'scaler.json', scaler.as_dict())
    config = {'version': 1, 'seed': seed, 'cost': cost, 'feature_schema': SCHEMA, 'schema_sha256': schema_hash(), 'policy_sha256': sha256(path / 'policy_seed_0.zip'), 'scaler_sha256': sha256(path / 'scaler.json'), 'gate': 'positive_24h_return', 'symbol': 'BTCUSDT', 'interval': '1h'}
    write_json(path / 'config.json', config)
    return config


def load_bundle(path):
    path = Path(path)
    config = json.loads((path / 'config.json').read_text())
    if config['version'] != 1 or config['seed'] != 0 or config['feature_schema'] != SCHEMA or config['schema_sha256'] != schema_hash() or config['gate'] != 'positive_24h_return' or config['symbol'] != 'BTCUSDT' or config['interval'] != '1h' or not 0 <= config['cost'] < 1:
        raise ValueError('Incompatible bundle')
    for name, key in [('policy_seed_0.zip', 'policy_sha256'), ('scaler.json', 'scaler_sha256')]:
        if sha256(path / name) != config[key]:
            raise ValueError(f'Bundle hash mismatch: {name}')
    scaler = FeatureScaler(**json.loads((path / 'scaler.json').read_text()))
    return PPO.load(str(path / 'policy_seed_0.zip'), device='cpu'), scaler, config


def fit_scaler(bars, entries):
    # All causal training-state features, independent of learned exit timing.
    rows = [observation(bars, idx + h, float(bars.open.iloc[idx]), 0.0015, h) for idx in entries for h in range(1, 24)]
    return FeatureScaler.fit(rows)


def simulate(bars, index, method, model, scaler, cost, seed):
    p0 = float(bars.open.iloc[index]); q = 10000 / (p0 * (1 + cost))
    chosen, reason, steps = None, None, []
    for hour in range(1, 25):
        price = float(bars.open.iloc[index + hour])
        if chosen is None:
            if hour == 24:
                exit_now, reason = True, 'deadline'
            elif method == 'fixed_6h':
                exit_now = hour == 6
                if exit_now: reason = 'fixed_6h'
            elif method == 'fixed_24h':
                exit_now = False
            elif method == 'trailing_2pct':
                x = observation(bars, index + hour, p0, cost, hour)
                exit_now = bool(x[6] <= -0.02)
                if exit_now: reason = 'trailing_2pct'
            else:
                x = observation(bars, index + hour, p0, cost, hour)
                action, _ = model.predict(scaler.transform(x), deterministic=True)
                exit_now = int(action) == 1
                if exit_now: reason = 'policy'
            if exit_now:
                chosen = hour
                final_cash = q * price * (1 - cost)
                exit_price = price
        bar = bars.iloc[index + hour - 1]
        x = observation(bars, index + min(hour, 23), p0, cost, min(hour, 23))
        action_name = 'exit' if chosen == hour else ('cash' if chosen is not None else 'hold')
        equity = final_cash if chosen is not None else q * price
        row = {'hour': hour, 'timestamp': bars.time.iloc[index + hour].isoformat(), 'bar_end': bars.time.iloc[index + hour].isoformat(), 'open': float(bar['open']), 'high': float(bar['high']), 'low': float(bar['low']), 'close': float(bar['close']), 'price': price, 'action': action_name, 'equity': equity}
        row.update({f'feature_{j}': float(v) for j, v in enumerate(x)})
        steps.append(row)
    trade = {'entry_time': bars.time.iloc[index].isoformat(), 'exit_time': bars.time.iloc[index + chosen].isoformat(), 'entry_price': p0, 'exit_price': exit_price, 'holding_hours': chosen, 'net_return': final_cash / 10000 - 1, 'exit_reason': reason, 'entry_cost': 10000 * cost / (1 + cost), 'exit_cost': q * exit_price * cost}
    return trade, steps


def score(bars, cohort, models, scaler, cost):
    trades, steps, equity = [], [], []
    methods = [('fixed_6h', None, None), ('fixed_24h', None, None), ('trailing_2pct', None, None)] + [('ppo', seed, model) for seed, model in models.items()]
    for method, seed, model in methods:
        balance, prior = 10000.0, None
        for row in cohort.itertuples(index=False):
            day = row.day.isoformat()
            if not row.valid:
                prior = None
                continue
            if prior is None or row.day - prior != pd.Timedelta(days=1):
                balance = 10000.0
                segment = day
            prior = row.day
            net = 0.0
            common = {'day': day, 'method': method, 'seed': seed, 'cost_bps': int(round(cost * 10000))}
            if row.gate:
                trade, trace = simulate(bars, int(row.index), method, model, scaler, cost, seed)
                net = trade['net_return']
                trades.append({**common, **trade})
                steps.extend([{**common, **s} for s in trace])
            balance *= 1 + net
            equity.append({**common, 'daily_return': net, 'equity': balance, 'segment': segment})
    return pd.DataFrame(trades), pd.DataFrame(equity), pd.DataFrame(steps)


def summarize(trades, baseline, equity):
    metrics = []
    for cost in sorted(trades.cost_bps.unique()):
        subset = trades[trades.cost_bps == cost]
        reference = subset[subset.method == baseline].set_index('day').net_return
        for (method, seed), group in subset.groupby(['method', 'seed'], dropna=False):
            paired = group.set_index('day').net_return - reference
            eq = equity[(equity.cost_bps == cost) & (equity.method == method)]
            eq = eq[eq.seed.isna()] if pd.isna(seed) else eq[eq.seed == seed]
            drawdowns = []
            for _, segment in eq.groupby('segment'):
                values = np.r_[10000.0, segment.equity.to_numpy()]
                drawdowns.append(float(np.min(values / np.maximum.accumulate(values) - 1)))
            metrics.append({'method': method, 'seed': None if pd.isna(seed) else int(seed), 'cost_bps': int(cost), 'trades': len(group), 'mean_net_return': float(group.net_return.mean()), 'mean_paired_bps': float(paired.mean() * 10000), 'median_paired_bps': float(paired.median() * 10000), 'win_fraction': float((paired > 0).mean()), 'mean_holding_hours': float(group.holding_hours.mean()), 'max_drawdown': min(drawdowns), 'total_friction': float((group.entry_cost + group.exit_cost).sum()), 'mean_log_growth': float(np.log1p(group.net_return).mean()), 'fifth_percentile_return': float(group.net_return.quantile(.05))})
    return metrics


def comparisons_and_screen(trades, metrics, selected):
    comparisons = []
    for cost in sorted(trades.cost_bps.unique()):
        subset = trades[trades.cost_bps == cost]
        for seed, group in subset[subset.method == 'ppo'].groupby('seed'):
            for baseline in ('fixed_6h', 'fixed_24h', 'trailing_2pct'):
                ref = subset[subset.method == baseline].set_index('day').net_return
                diffs = group.set_index('day').net_return - ref
                if diffs.isna().any():
                    raise ValueError('Unmatched evaluation cohorts')
                comparisons.append({'cost_bps': int(cost), 'seed': int(seed), 'baseline': baseline, 'mean_paired_bps': float(diffs.mean() * 10000), 'median_paired_bps': float(diffs.median() * 10000), 'win_fraction': float((diffs > 0).mean())})
    medians = []
    for cost in sorted(trades.cost_bps.unique()):
        ppo_metrics = [m for m in metrics if m['method'] == 'ppo' and m['cost_bps'] == cost]
        for baseline in ('fixed_6h', 'fixed_24h', 'trailing_2pct'):
            cm = [m for m in comparisons if m['cost_bps'] == cost and m['baseline'] == baseline]
            medians.append({'cost_bps': int(cost), 'baseline': baseline, 'median_seed_mean_paired_bps': float(np.median([m['mean_paired_bps'] for m in cm])), 'positive_seed_count': sum(m['mean_paired_bps'] > 0 for m in cm), 'median_seed_net_return': float(np.median([m['mean_net_return'] for m in ppo_metrics])), 'median_seed_max_drawdown': float(np.median([m['max_drawdown'] for m in ppo_metrics]))})
    base = next(m for m in medians if m['cost_bps'] == 15 and m['baseline'] == selected)
    stress = next(m for m in medians if m['cost_bps'] == 30 and m['baseline'] == selected)
    baseline_dd = next(m['max_drawdown'] for m in metrics if m['method'] == selected and m['cost_bps'] == 15)
    checks = {'all_three_seeds': len([m for m in metrics if m['method'] == 'ppo' and m['cost_bps'] == 15]) == 3, 'median_improvement_at_least_5bps': base['median_seed_mean_paired_bps'] >= 5, 'at_least_two_seeds_improve': base['positive_seed_count'] >= 2, 'median_net_return_positive': base['median_seed_net_return'] > 0, 'drawdown_not_more_than_2pp_worse': base['median_seed_max_drawdown'] >= baseline_dd - .02, 'stress_median_net_return_positive': stress['median_seed_net_return'] > 0}
    return comparisons, medians, {'checks': checks, 'statistical_significance': False, 'numeric_screen_passed': all(checks.values()), 'full_screen_status': 'pending independent verification and trial audit'}


def outputs(path, bars, cohort, models, scaler, selected=None, phase='validation', freeze_id=None):
    path = Path(path); path.mkdir(parents=True, exist_ok=True)
    all_trades, all_equity, all_steps = [], [], []
    for cost in (0.0015, 0.003):
        t, e, s = score(bars, cohort, models, scaler, cost)
        all_trades.append(t); all_equity.append(e); all_steps.append(s)
    trades, equity, steps = map(lambda x: pd.concat(x, ignore_index=True), (all_trades, all_equity, all_steps))
    if selected is None:
        base = trades[(trades.cost_bps == 15) & (trades.method != 'ppo')]
        order = {'fixed_6h': 0, 'fixed_24h': 1, 'trailing_2pct': 2}
        ranking = []
        for method, group in base.groupby('method'):
            downside = float(np.sqrt(np.mean(np.minimum(group.net_return.to_numpy(), 0) ** 2)))
            ranking.append((-float(group.net_return.mean()), downside, order[method], method))
        selected = min(ranking)[3]
    trades.to_csv(path / 'trades.csv', index=False)
    equity.to_csv(path / 'equity.csv', index=False)
    steps.to_csv(path / 'steps.csv', index=False)
    metrics = summarize(trades, selected, equity)
    comparisons, medians, screen = comparisons_and_screen(trades, metrics, selected)
    summary = {'status': 'complete', 'phase': phase, 'frozen': phase == 'evaluation', 'selected_baseline': selected, 'metrics': metrics, 'comparisons': comparisons, 'seed_medians': medians, 'continuation_screen': screen, 'freeze_id': freeze_id}
    write_json(path / 'summary.json', summary)
    if phase == 'evaluation':
        lines = ['# Frozen historical evaluation', '', f"Selected validation baseline: {selected}.", '', 'The following values describe paired episode returns, not a live trading result.', '', '| Cost (bps) | Baseline | Median PPO improvement (bps) | Positive seeds | Median net return |', '|---:|---|---:|---:|---:|']
        for m in medians:
            lines.append(f"| {m['cost_bps']} | {m['baseline']} | {m['median_seed_mean_paired_bps']:.2f} | {m['positive_seed_count']} | {m['median_seed_net_return']:.4%} |")
        lines += ['', f"Numeric continuation checks passed: {screen['numeric_screen_passed']}. Full continuation screen requires recorded independent verification and trial audit.", 'The screen is heuristic, not statistical significance. Three seeds share one historical market path.', 'Costs are modeled assumptions; hourly reference opens are not verified fills. This is conditional on the frozen entry cohort.', '']
        (path / 'report.md').write_text('\n'.join(lines))
        files = {name: sha256(path / name) for name in ('summary.json', 'trades.csv', 'equity.csv', 'steps.csv', 'report.md')}
        write_json(path / 'artifact_checksums.json', {'freeze_id': freeze_id, 'source_freeze_sha256': freeze_id, 'files': files})
    return summary


TRAINING_SOURCE_NAMES = ['src/kairos/__init__.py', 'src/kairos/data.py', 'src/kairos/environment.py', 'src/kairos/research.py', 'src/kairos/cli.py', 'pyproject.toml', 'docs/SPEC.md', 'docs/DATA_AND_ENVIRONMENT.md', 'docs/RESEARCH_PROTOCOL.md']


def snapshot_training_source(root, run):
    root, run = Path(root), Path(run)
    dest = run / 'provenance' / 'training-source'
    if dest.exists() or (run / 'training_source.json').exists():
        raise ValueError('Training source snapshot already exists; use a new run')
    hashes = {}
    for name in TRAINING_SOURCE_NAMES:
        content = (root / name).read_bytes()
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        hashes[name] = hashlib.sha256(content).hexdigest()
    write_json(run / 'training_source.json', hashes)
    (dest.parent / 'training-source.sha256').write_text(''.join(f'{digest}  {name}\n' for name, digest in hashes.items()))
    return hashes


def verify_training_source(run, hashes):
    dest = Path(run) / 'provenance' / 'training-source'
    if not hashes or any(sha256(dest / name) != digest for name, digest in hashes.items()):
        raise ValueError('Training source snapshot hash mismatch')


def train_and_freeze(archive_dir, run_dir, steps=100000):
    run = Path(run_dir); run.mkdir(parents=True, exist_ok=True)
    if (run / 'bundle' / 'freeze.json').exists() or (run / 'evaluation').exists():
        raise ValueError('Run already frozen or evaluated; use a new directory')
    snapshot_training_source(Path(__file__).resolve().parents[2], run)
    bars, inventory = read_archives(archive_dir)
    splits = {name: cohorts(bars, *bounds) for name, bounds in PARTITIONS.items()}
    for name, minimum in [('train', 100), ('validation', 30), ('evaluation', 30)]:
        if int(splits[name].gate.sum()) < minimum:
            raise ValueError(f'Insufficient {name} cohort')
        splits[name].to_csv(run / f'{name}_cohort.csv', index=False)
    save_manifest(run / 'data_manifest.json', bars, inventory, splits)
    entries = splits['train'].loc[splits['train'].gate, 'index'].astype(int).tolist()
    scaler = fit_scaler(bars, entries)
    torch.set_num_threads(1)
    models, ledger = {}, []
    for seed in (0, 1, 2):
        env = ExitEnv(bars, entries, scaler)
        model = PPO('MlpPolicy', env, seed=seed, learning_rate=0.0003, n_steps=1024, batch_size=64, n_epochs=10, gamma=1.0, gae_lambda=0.95, clip_range=0.2, ent_coef=0.0, policy_kwargs={'net_arch': dict(pi=[32, 32], vf=[32, 32])}, device='cpu', verbose=0)
        model.learn(total_timesteps=steps)
        model.save(str(run / f'policy_seed_{seed}.zip'))
        models[seed] = model
        ledger.append({'seed': seed, 'requested_steps': steps, 'actual_steps': model.num_timesteps, 'episodes': env.episode_count, 'unique_training_days': len(env.sampled_entries), 'policy_sha256': sha256(run / f'policy_seed_{seed}.zip')})
        print(f'trained seed {seed}: {model.num_timesteps} steps', flush=True)
    validation = outputs(run / 'validation', bars, splits['validation'], models, scaler)
    bundle = run / 'bundle'
    config = save_bundle(bundle, models[0], scaler, 0)
    freeze = {'version': 1, 'frozen': True, 'selected_baseline': validation['selected_baseline'], 'manifest_sha256': sha256(run / 'data_manifest.json'), 'config_sha256': sha256(bundle / 'config.json'), 'policy_hashes': {str(v['seed']): v['policy_sha256'] for v in ledger}, 'python': sys.version, 'platform': platform.platform(), 'ledger': ledger}
    write_json(bundle / 'freeze.json', freeze)
    print('Frozen bundle and validation baseline:', freeze['selected_baseline'], flush=True)
    return freeze


def seal_freeze(run_dir, training_source_hashes=None):
    """Record the full pre-evaluation identity; callable only before opening evaluation."""
    run = Path(run_dir); bundle = run / 'bundle'
    if (run / 'evaluation').exists():
        raise ValueError('Cannot reseal after evaluation opened')
    freeze_path = bundle / 'freeze.json'
    freeze = json.loads(freeze_path.read_text())
    if freeze.get('sealed'):
        raise ValueError('Freeze is already sealed')
    root = Path(__file__).resolve().parents[2]
    source_names = ['src/kairos/__init__.py', 'src/kairos/data.py', 'src/kairos/environment.py', 'src/kairos/research.py', 'src/kairos/cli.py', 'pyproject.toml', 'docs/SPEC.md', 'docs/DATA_AND_ENVIRONMENT.md', 'docs/RESEARCH_PROTOCOL.md']
    source = {name: sha256(root / name) for name in source_names}
    if training_source_hashes:
        training_source = {}
        for line in Path(training_source_hashes).read_text().splitlines():
            digest, filename = line.split(maxsplit=1)
            training_source[filename.lstrip('*')] = digest
    else:
        snapshot = run / 'training_source.json'
        if not snapshot.exists():
            raise ValueError('Missing training-time source snapshot; provide audited hashes')
        training_source = json.loads(snapshot.read_text())
        verify_training_source(run, training_source)
    def git(*args):
        return subprocess.run(['git', *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
    versions = {name: metadata.version(name) for name in ['numpy', 'pandas', 'gymnasium', 'stable-baselines3', 'torch', 'scikit-learn']}
    freeze['training_policy_hashes'] = dict(freeze['policy_hashes'])
    freeze['policy_hashes']['0'] = sha256(bundle / 'policy_seed_0.zip')
    freeze.update({'sealed': True, 'training_source_sha256': training_source, 'evaluation_source_sha256': source, 'git_revision': git('rev-parse', 'HEAD'), 'git_dirty': bool(git('status', '--porcelain')), 'dependencies': versions, 'cohort_sha256': {name: sha256(run / f'{name}_cohort.csv') for name in PARTITIONS}, 'validation_summary_sha256': sha256(run / 'validation' / 'summary.json'), 'model_config': {'algorithm': 'PPO', 'seeds': [0, 1, 2], 'requested_steps': freeze['ledger'][0]['requested_steps'], 'gamma': 1.0, 'gae_lambda': .95, 'learning_rate': .0003, 'n_steps': 1024, 'batch_size': 64, 'n_epochs': 10, 'clip_range': .2, 'entropy_coefficient': 0, 'hidden_layers_actor_critic': [32, 32], 'costs_bps': [15, 30]}, 'bundle_config': json.loads((bundle / 'config.json').read_text())})
    write_json(freeze_path, freeze)
    return freeze


def evaluate(archive_dir, run_dir):
    run = Path(run_dir); bundle = run / 'bundle'; target = run / 'evaluation'
    if target.exists():
        raise ValueError('Evaluation already opened; use a new run')
    freeze = json.loads((bundle / 'freeze.json').read_text())
    if not freeze.get('sealed'):
        raise ValueError('Freeze is not sealed')
    root = Path(__file__).resolve().parents[2]
    for name, digest in freeze['evaluation_source_sha256'].items():
        if sha256(root / name) != digest:
            raise ValueError(f'Frozen source or protocol mismatch: {name}')
    for name, digest in freeze['cohort_sha256'].items():
        if sha256(run / f'{name}_cohort.csv') != digest:
            raise ValueError(f'Frozen cohort mismatch: {name}')
    if sha256(run / 'validation' / 'summary.json') != freeze['validation_summary_sha256']:
        raise ValueError('Frozen validation identity mismatch')
    if sha256(bundle / 'config.json') != freeze['config_sha256'] or sha256(run / 'data_manifest.json') != freeze['manifest_sha256']:
        raise ValueError('Freeze identity mismatch')
    model0, scaler, _ = load_bundle(bundle)
    models = {0: model0}
    for seed in (1, 2):
        path = run / f'policy_seed_{seed}.zip'
        if sha256(path) != freeze['policy_hashes'][str(seed)]:
            raise ValueError('Policy identity mismatch')
        models[seed] = PPO.load(str(path), device='cpu')
    bars, inventory = read_archives(archive_dir)
    original = json.loads((run / 'data_manifest.json').read_text())
    identity = lambda records: [(item['file'], item['sha256']) for item in records]
    if identity(inventory) != identity(original['sources']):
        raise ValueError('Data identity mismatch')
    cohort = cohorts(bars, *PARTITIONS['evaluation'])
    return outputs(target, bars, cohort, models, scaler, freeze['selected_baseline'], phase='evaluation', freeze_id=sha256(bundle / 'freeze.json'))
