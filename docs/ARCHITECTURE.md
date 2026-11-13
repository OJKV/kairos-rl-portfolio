# Architecture

Implemented as one small Python research package, a separate paper process and a read-only local viewer. See README for reproduction commands.

```mermaid
flowchart LR
    A[Public BTC archive] --> B[Validate and manifest]
    B --> C[Shared daily entry cohort]
    C --> D[Causal features and ledger]
    D --> E[Gymnasium hold or exit environment]
    E --> F[SB3 PPO training]
    C --> G[Three fixed exit baselines]
    F --> H[Frozen paired evaluation]
    G --> H
    H --> I[Report and trade artifacts]
    I --> J[Read-only Streamlit viewer]
    K[Public candles and observed quotes] --> L[Paper runner]
    F --> M[Frozen seed-0 bundle]
    M --> L
    D --> L
    L --> N[SQLite ledger and events]
    N --> J
```

## Responsibilities

| Component | Owns | Boundary |
|---|---|---|
| Data/cohorts | Downloads, checksums, UTC quality, entry eligibility and exclusions | Cannot select entries using exit outcomes |
| Features | Ordered causal observations and frozen scaler | No fitting on validation/test |
| Ledger/environment | Fully funded entry, exit cost, timing, reward and termination | No exchange order endpoints |
| Baselines | Frozen shared-entry exit rules | No per-trade hindsight selection |
| Training | PPO seeds/budget and artifact identities | No UI-triggered fitting or test selection |
| Evaluation/report | Paired outcomes, calendar metrics and complete trial history | No updated model/scaler |
| Paper runner | Daily scheduling, post-decision observed reference, simulated holdings and recovery | No learning or historical fill substitution |
| Viewer | Display verified artifacts and read-only paper snapshots | Cannot train, place trades or mutate state |

The shared ledger prevents inconsistent economics. Independent hand-calculated fixtures challenge mistakes shared by all methods. Historical-open and observed-quote adapters stay separate and labeled.

## Planned interfaces and storage

Proposed CLI entry points: `kairos data`, `kairos train`, `kairos evaluate`, `kairos report`, `kairos paper`, `kairos ui`. They are design names, not working commands. Use standard-library argument parsing and TOML where practical; create only necessary modules under a future `src/kairos/` package.

| Artifact | Minimum content |
|---|---|
| Dataset manifest | URLs, retrieval/checksums, range/schema/quality |
| Cohort/split manifest | Gate version, entry/endpoint times, valid/excluded/gated counts, prior-use classification |
| Experiment ledger | Git/config/package/data hashes, every trial/seed/baseline, budget and freeze identity |
| Frozen bundle | Policy, scaler, feature schema, entry and cost contracts |
| Episode outputs | Shared entry ID, timestamps, observed inputs/actions, prices/costs, exit reason, per-method return and hourly equity |
| Paper state | Session/cohort/bundle identity, holdings, cursor, endpoint and atomic event history |
| UI/report bundle | Immutable manifest and small reviewed tables/plots; explicit fixture/development/evaluation/paper mode |

Large data, models, raw runs and local state remain ignored. Commit only reviewed portable reports and permitted small samples later.

## Tools and dependency budget

Initial target Python 3.12, subject to stable package compatibility checks. Core: Gymnasium, SB3/PyTorch, NumPy/pandas and a basic plotting library. Viewer: Streamlit; add Plotly only for the candlestick/exit inspector, with native charts for simple plots. SQLite, hashing, logging and config parsing use the standard library.

No frontend build toolchain, web API, tracking server, broker service or authentication system is needed for a localhost demo. Archive download must preserve TLS verification; system curl is a valid initial transport if Python's local CA setup is unresolved. Pin a tested environment during implementation, not an invented lock now.

Backtesting.py is an optional independent development cross-check. Freqtrade is a possible later candle-based paper adapter; NautilusTrader offers a later execution integration. Neither is required to learn/test this exit policy, and reconciling a second engine is deferred.

UI state cannot be the source of trading truth. Streamlit reruns must only read data; SQLite single-writer paper state and manifest checks own durable identity.
