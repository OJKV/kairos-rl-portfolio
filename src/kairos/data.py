"""Validated public candles and shared daily cohorts."""
from pathlib import Path
import hashlib
import json
import zipfile
from datetime import datetime, timezone

import numpy as np
import pandas as pd

PARTITIONS = {"train": ("2022-01-01", "2025-01-01"), "validation": ("2025-01-01", "2026-01-01"), "evaluation": ("2026-01-01", "2026-11-01")}
COLUMNS = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "trades", "taker_base", "taker_quote", "unused"]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_archives(directory):
    paths = sorted(Path(directory).glob("BTCUSDT-1h-*.zip"))
    if not paths:
        raise ValueError("No BTCUSDT hourly archives found")
    frames, inventory = [], []
    for path in paths:
        checksum_path = Path(str(path) + ".CHECKSUM")
        if not checksum_path.exists():
            raise ValueError(f"Missing checksum: {checksum_path}")
        expected = checksum_path.read_text().split()[0].lower()
        actual = sha256(path)
        if actual != expected:
            raise ValueError(f"Checksum mismatch: {path}")
        with zipfile.ZipFile(path) as z:
            members = [n for n in z.namelist() if n.endswith('.csv')]
            if len(members) != 1:
                raise ValueError(f"Expected one CSV in {path}")
            with z.open(members[0]) as f:
                df = pd.read_csv(f, header=None, names=COLUMNS)
        df = df[pd.to_numeric(df.open_time, errors="coerce").notna()].copy()
        # Binance spot archives switched to microseconds from January 2025.
        unit = 'us' if path.stem[-7:] >= '2025-01' else 'ms'
        df['time'] = pd.to_datetime(pd.to_numeric(df.open_time), unit=unit, utc=True)
        for c in ['open', 'high', 'low', 'close', 'volume']:
            df[c] = pd.to_numeric(df[c], errors='raise')
        frames.append(df[['time', 'open', 'high', 'low', 'close', 'volume']])
        url = 'https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1h/' + path.name
        inventory.append({'file': path.name, 'sha256': actual, 'published_sha256': expected, 'url': url, 'checksum_url': url + '.CHECKSUM', 'retrieved_at': None, 'audited_at': datetime.now(timezone.utc).isoformat()})
    bars = pd.concat(frames, ignore_index=True).sort_values('time').reset_index(drop=True)
    validate_bars(bars)
    return bars, inventory


def validate_bars(bars):
    if bars.empty or bars.time.duplicated().any() or not bars.time.is_monotonic_increasing:
        raise ValueError('Empty, duplicate or unsorted candles')
    v = bars[['open', 'high', 'low', 'close', 'volume']].to_numpy(dtype=float)
    if not np.isfinite(v).all() or (v[:, :4] <= 0).any() or (v[:, 4] < 0).any():
        raise ValueError('Invalid prices or volume')
    if ((bars.high < bars[['open', 'close', 'low']].max(axis=1)) | (bars.low > bars[['open', 'close', 'high']].min(axis=1))).any():
        raise ValueError('Invalid OHLC ordering')
    if (bars.time != bars.time.dt.floor('h')).any():
        raise ValueError('Candle timestamps must align to UTC hours')
    delta = bars.time.diff().dropna().dt.total_seconds()
    if (delta % 3600 != 0).any():
        raise ValueError('Non-hourly candle timestamps')


def cohorts(bars, start, end):
    """Return all valid calendar days and shared entered boundary positions."""
    start, end = pd.Timestamp(start, tz='UTC'), pd.Timestamp(end, tz='UTC')
    index = pd.DatetimeIndex(bars.time)
    by_time = {t: i for i, t in enumerate(index)}
    result = []
    for day in pd.date_range(start, end, freq='D', inclusive='left'):
        pos = by_time.get(day)
        endpoint = day + pd.Timedelta(hours=24)
        valid = pos is not None and endpoint < end and pos >= 169 and pos + 24 < len(bars)
        if valid:
            times = index[pos - 169:pos + 25]
            valid = len(times) == 194 and (np.diff(times.to_numpy()) == np.timedelta64(1, "h")).all()
        gate = bool(bars.close.iloc[pos - 1] > bars.close.iloc[pos - 25]) if valid else False
        result.append({'day': day, 'index': pos if valid else None, 'valid': bool(valid), 'gate': gate})
    return pd.DataFrame(result)


def save_manifest(path, bars, inventory, partitions):
    data = {'sources': inventory, 'rows': len(bars), 'start': bars.time.iloc[0].isoformat(), 'end': bars.time.iloc[-1].isoformat(), 'partitions': {k: {'days': len(v), 'valid': int(v.valid.sum()), 'entered': int(v.gate.sum())} for k, v in partitions.items()}}
    Path(path).write_text(json.dumps(data, indent=2) + '\n')
