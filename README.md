# KAIROS

KAIROS studies whether a PPO policy can improve the exit timing of a fixed Bitcoin entry rule. It uses shared entries, chronological partitions, modeled transaction costs and paired simple baselines. The viewer displays saved historical research; paper simulation does not place exchange orders.

## Result

In a frozen historical evaluation of 147 eligible trades, the median of three PPO seeds improved by 3.90 basis points per trade over the validation-selected 2% trailing exit, below the predeclared 5 bps threshold. Median net return was −0.248% per trade at 15 bps per side; the continuation screen failed. These are historical simulations, not verified fills or proof of an edge. See [results](docs/RESULTS.md), [research protocol](docs/RESEARCH_PROTOCOL.md), and [environment and accounting](docs/DATA_AND_ENVIRONMENT.md).

## Reproduction

Python 3.11+ and `uv` are required. Raw market data, models and run artifacts are not included. The data command downloads public BTCUSDT hourly archives and verifies published checksums. Training runs three CPU seeds and can take substantial time.

```bash
uv sync --frozen --extra test
uv run pytest -q
uv run kairos data --directory data/archive
uv run kairos train --data data/archive --run runs/reproduce
uv run kairos seal --run runs/reproduce
uv run kairos evaluate --data data/archive --run runs/reproduce
KAIROS_RUN=runs/reproduce uv run kairos ui
```

Evaluation is once-only per run and must follow sealing. Results may vary across platforms. Historical reference-open fills assume zero latency and do not represent actual executions.
