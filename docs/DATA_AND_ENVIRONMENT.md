# Data, shared entries and environment

This document owns causal information, cohort timing, accounting and reward semantics. The contract is implemented and exercised by the test suite; results and limitations are recorded in RESULTS.

## Public data and integrity

Download BTCUSDT 1h spot bars from the Binance public monthly archive. Record source URLs, retrieval time, local and published SHA-256, symbol/interval, schema, rows and UTC range. Normalize documented timestamp units: archive spot timestamps change to microseconds from January 2025. Public REST routes have their own documented units. Do not guess units independently for individual rows.

Reject duplicate/missing hourly opens, invalid OHLC relationships, nonpositive prices, negative volume and unfinished candles. Never forward-fill an executable price. Keep raw downloads outside Git and publish only permitted small artifacts or reproducible download instructions.

A cohort needs 169 completed pre-entry hourly closes for the 168-return volatility feature, the entire 24h path and its endpoint open. Missing or invalid required data excludes that cohort for **all** methods. Report exclusions. Warm-up may use earlier partitions; trade outcomes must remain inside the scored partition.

## Frozen daily entry generator

Let day D's window be `[D 00:00, D+1 00:00]` UTC. Evaluate the gate from bars completed strictly before D 00:00: the last completed close divided by the completed close 24 hours earlier must exceed 1. No entry when equal or negative. Gate and eligibility are precomputed independently of exit policies.

For an eligible positive-gate day, every method enters at the same reference open `P0 = O[D,00]` with the same starting capital. A non-entry day is cash for all methods. Boundary/invalid-data days are excluded observations, not invented cash days.

This historical open assumes zero extra latency after the preceding candle closes. It is an approximation. The paper runner uses a quote actually observed after computing the gate and records that difference.

## Exact exit schedule

| Time relative to entry | Behavior |
|---|---|
| Hour 0 | Mandatory shared entry; no RL action |
| Hours 1–23 | Observe only completed bars through that boundary; choose hold/exit and simulate at that boundary's next-bar open |
| Hour 24 | Force liquidation of any remaining BTC at the endpoint open; no extra policy action |
| After early exit | Remain in cash through hour 24 for calendar scoring; no additional entry |

Example: the 00:00–01:00 bar is complete at 01:00. The first action may use its close and fills at the 01:00 bar open under the replay approximation. It cannot trade at an intrabar high. Fixed-6h and fixed-24h methods exit at their respective scheduled opens.

The 2% trailing rule compares the latest completed close with 98% of the highest observed completed close since entry, seeding that peak at the actual entry reference price. On a trigger, exit at the next open. Use no bar high/low or assumed exact stop fill; price gaps are borne by the strategy.

The endpoint price must belong to the same partition. Drop a boundary-crossing day rather than using the next partition's outcome. If consecutive daily cohorts meet at midnight, liquidate the old cohort before the next entry and charge both required operations; this finite-cohort convention may add churn versus an uninterrupted strategy.

## Ledger and costs

Normalize each episode to starting equity `E0 = 10,000`, cash only. With all-in one-way friction `k`, entry reference `P0`:

- BTC quantity is `q = E0 / (P0 × (1 + k))`; cash is zero within declared numerical tolerance.
- Pre-exit equity at reference price `P` is `q × P`.
- Selling produces cash `q × P × (1 − k)` and BTC becomes zero.
- Net episode return is `final cash / E0 − 1`.

Base `k = 0.0015` (15 bps, 0.15% per side); stress `k = 0.0030`. These are scenario assumptions, not verified tariffs. Reference prices receive no second adverse adjustment for the same modeled spread/slippage. All methods pay entry and exit costs, including forced exits. Since all take one round trip, cost stress does not mean RL saves trades.

Use float64 ledger arithmetic with invariant tolerance `1e−8 × max(1, equity)`. Reject nonfinite/invalid prices, negative holdings or nonpositive equity; do not mask material errors with clipping. For intuition: at constant prices, round-trip return is `(1−k)/(1+k) − 1`, approximately −0.30% at base cost.

## Observation contract

Eight float32 values, in this order:

1. Completed close log returns over 1h, 6h and 24h: three values.
2. Standard deviation of the last 168 hourly close returns.
3. Log of completed volume divided by its trailing 24-bar mean; floor each volume term at `1e−12` BTC.
4. Net liquidation return if sold at the latest completed close, including already paid entry cost and hypothetical exit cost.
5. Drawdown from the observed completed-close peak, seeded at entry price.
6. Elapsed scheduled hours divided by 24.

Fit market-feature means/scales on training data only. A zero-variance feature uses scale 1. Trade-state fractions/clock use their declared units directly. No absolute date, future maximum, future exit outcome or unobserved high/low is an input. Freeze feature order/scaler/schema hashes with the model. Action IDs: 0 = hold; 1 = exit. No actions are accepted after termination.

## Reward and episode completion

Use `100 × log(new equity / previous reward-anchor equity)` with `gamma=1`. The reward sum must equal `100 × log(final cash / E0)` exactly within tolerance.

Reset performs the mandatory entry and advances to the first decision at hour 1. Keep `E0` as the initial reward anchor so the entry cost and initial holding return are not lost. For the first action, book that common accrued prefix in the first transition's reward. It is already incurred before the learned decision.

On an exit at hour h, sell at its open, return the remaining anchored reward and terminate. On hold, advance to the next open and mark equity for the reward/next decision; the first such transition also contains the initial prefix. A hold at hour 23 advances to hour 24, sells, includes terminal cost and terminates. This bookkeeping telescopes despite different action counts; no discount rewards early termination.

Early exit terminates the learning episode but the reporting ledger pads the rest of its common window with real simulated cash. Do not train on meaningless idle actions after exit. Tool interruption is truncation, not successful liquidation. Preserve diagnostics and restart from a clear episode boundary rather than fabricating a completed trade.
