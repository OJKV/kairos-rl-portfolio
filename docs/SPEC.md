# Research specification

Version 0.1 — 13 November 2026. Implemented prototype; RESULTS records behavior and limits.

## The question

**Given the same BTC entries, can an RL agent choose better exit times than fixed holding periods and a trailing-exit rule, after costs?**

The agent does not choose the entry or increase the position. It learns a finite **optimal-stopping** problem: continue an existing opportunity or end it. The null result is no demonstrated benefit over simple exits.

## Why an entry rule is needed

An exit must belong to a particular entry. Buying during upward momentum and buying after a sharp decline produce different future trade paths. An exit method that helps one entry style may not help the other.

Use one small entry generator, not a separate strategy-development project: at each **00:00 UTC** boundary, buy only if the just-completed 24-hour BTC close return is positive. Otherwise remain in cash for that entire day. All methods receive the same daily gate and hypothetical entry. This rule is a frozen sampling condition, not a claimed profitable signal.

Early exits cannot unlock extra entries. Remain in cash until the common next-midnight endpoint. A later extension may repeat the study with an unconditional daily entry or another independently frozen gate; do not change the primary gate after seeing results.

## First-version boundaries

| Item | Definition |
|---|---|
| Market | BTCUSDT spot, one public venue, 1h candles |
| Cohort | One shared daily opportunity, positive previous-24h-return gate |
| Position | Fully funded long BTC; 10,000 simulated quote units per normalized episode |
| Actions | Hold or exit; no adding, reversing or new entry |
| Timing | Earliest learned exit at hour 1; maximum scheduled exit at hour 24 |
| Learner | Small Stable-Baselines3 PPO MLP on CPU |
| Comparisons | Fixed 6h, fixed 24h, completed-close trailing exit at 2% |
| Friction | Explicit one-way all-in costs, base and stress scenarios |
| UI | Primary historical-replay showcase; secondary read-only paper-status screen |
| Operation | Build both: historical replay is the primary demo; current-data paper simulation is the secondary/backup demo |

The exact contracts live in DATA_AND_ENVIRONMENT and RESEARCH_PROTOCOL. The design assumes fractional BTC, no leverage, no funding, and a constant USDT quote unit. It does not estimate real fills, market impact, order-book queues or stablecoin risk.

## What counts as complete

- Validated data/split and shared-entry manifests with eligible and excluded counts.
- Checked entry/exit accounting, causal features and finite-horizon environment.
- Three recorded PPO seeds and all frozen simple-exit baselines.
- Frozen historical comparison, cost stress, per-trade traces and a concise conclusion.
- Local UI showing real run artifacts with clear empty/error states.
- Restart-safe paper simulator, or an explicitly incomplete operational milestone if a genuine blocker remains.

Positive, negative and inconclusive results are valid research outcomes. Do not assume profitability or unprofitability in advance; the goal is a fair answer to the question. A usable policy, profitable result or long forward record cannot be guaranteed within two days.

The primary demo uses saved historical episodes and results, so it does not depend on a current entry or network connection once artifacts are available. The paper simulator remains in the first build scope as the secondary/backup demo; its live-data availability and daily entry schedule must be shown honestly.

## Claims and limits

Results apply to this entry cohort, asset, horizon and execution approximation. The main question is exit quality conditional on entry; the entry signal's independent alpha is not established. Public prices are sufficient to construct the experiment but do not establish its statistical power or execution realism.

The initial design-only baseline has been implemented; see RESULTS for evidence and limitations. Real exchange orders, online learning, extra entry searches, deep models and a custom web stack are outside the first build.
