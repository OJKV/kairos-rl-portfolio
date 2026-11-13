"""One common daily entry and causal finite-horizon hold/exit control."""
import numpy as np
import gymnasium as gym
from gymnasium import spaces

SCHEMA = ['return_1h', 'return_6h', 'return_24h', 'volatility_168h', 'volume_relative_24h', 'net_liquidation_return', 'drawdown_from_peak', 'elapsed_fraction']


def entry_gate(bars, boundary_index):
    if boundary_index < 25 or boundary_index > len(bars):
        raise ValueError('Insufficient gate history')
    return bool(bars.close.iloc[boundary_index - 1] > bars.close.iloc[boundary_index - 25])


def observation(bars, boundary_index, entry_price, entry_cost_fraction, elapsed_hours):
    i = int(boundary_index)
    if i < 169 or i > len(bars) or not 1 <= elapsed_hours <= 23 or entry_price <= 0 or not 0 <= entry_cost_fraction < 1:
        raise ValueError('Invalid observation boundary or parameters')
    closes = bars.close.to_numpy(dtype=float)
    volumes = bars.volume.to_numpy(dtype=float)
    c = closes[i - 1]
    if not np.isfinite(c) or c <= 0:
        raise ValueError('Invalid close')
    returns = np.log(closes[i - 168:i] / closes[i - 169:i - 1])
    peak = max(entry_price, float(np.max(closes[i - elapsed_hours:i])))
    obs = np.array([np.log(c / closes[i - 2]), np.log(c / closes[i - 7]), np.log(c / closes[i - 25]), np.std(returns, ddof=1), np.log(max(volumes[i - 1], 1e-12) / max(np.mean(volumes[i - 24:i]), 1e-12)), c / entry_price * (1 - entry_cost_fraction) / (1 + entry_cost_fraction) - 1, c / peak - 1, elapsed_hours / 24], dtype=np.float32)
    if not np.isfinite(obs).all():
        raise ValueError('Nonfinite feature')
    return obs


class FeatureScaler:
    def __init__(self, means, scales):
        self.means, self.scales = np.asarray(means, dtype=float), np.asarray(scales, dtype=float)
        if self.means.shape != (5,) or self.scales.shape != (5,) or not np.isfinite(self.means).all() or not np.isfinite(self.scales).all() or (self.scales <= 0).any():
            raise ValueError('Invalid scaler')

    @classmethod
    def fit(cls, observations):
        x = np.asarray(observations, dtype=float)[:, :5]
        scale = x.std(axis=0)
        return cls(x.mean(axis=0), np.where(scale > 0, scale, 1.0))

    def transform(self, obs):
        x = np.asarray(obs, dtype=np.float32).copy()
        if x.shape != (8,):
            raise ValueError('Expected eight features')
        x[:5] = (x[:5] - self.means) / self.scales
        return x

    def as_dict(self):
        return {'means': self.means.tolist(), 'scales': self.scales.tolist()}


class ExitEnv(gym.Env):
    metadata = {}
    def __init__(self, bars, entry_indices, scaler, cost=0.0015):
        super().__init__()
        self.bars, self.indices, self.scaler, self.cost = bars, list(entry_indices), scaler, cost
        if not self.indices or not 0 <= cost < 1:
            raise ValueError('No eligible entries or invalid cost')
        self.sampled_entries = set()
        self.episode_count = 0
        self.action_space = spaces.Discrete(2)
        self.observation_space = spaces.Box(-np.inf, np.inf, shape=(8,), dtype=np.float32)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self.entry = int(options['entry']) if options and 'entry' in options else int(self.np_random.choice(self.indices))
        if self.entry not in self.indices:
            raise ValueError('Entry not in cohort')
        self.sampled_entries.add(self.entry)
        self.episode_count += 1
        self.hour = 1
        self.p0 = float(self.bars.open.iloc[self.entry])
        self.qty = 10000 / (self.p0 * (1 + self.cost))
        self.anchor = 10000.0
        self.done = False
        return self._obs(), {'entry': self.entry}

    def _obs(self):
        return self.scaler.transform(observation(self.bars, self.entry + self.hour, self.p0, self.cost, self.hour))

    def step(self, action):
        if self.done or not self.action_space.contains(action):
            raise ValueError('Invalid action or completed episode')
        if int(action) == 1:
            price = float(self.bars.open.iloc[self.entry + self.hour])
            equity = self.qty * price * (1 - self.cost)
            self.done = True
            reason = 'exit'
        else:
            self.hour += 1
            price = float(self.bars.open.iloc[self.entry + self.hour])
            self.done = self.hour == 24
            equity = self.qty * price * (1 - self.cost if self.done else 1)
            reason = 'deadline' if self.done else 'hold'
        reward = 100 * np.log(equity / self.anchor)
        self.anchor = equity
        obs = np.zeros(8, dtype=np.float32) if self.done else self._obs()
        return obs, float(reward), self.done, False, {'equity': equity, 'hour': self.hour, 'price': price, 'reason': reason}
