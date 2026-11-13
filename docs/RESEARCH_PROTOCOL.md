# Research protocol

Freeze the resolved data, cohort, configuration and Git identities before full training. This document owns model selection and reporting.

## Primary comparison

For every eligible entered day, compute RL net episode return minus the matched baseline's net episode return. Primary metric is the **mean paired difference in basis points** against the strongest simple exit selected on validation. Report all individual baselines too. One basis point is 0.01%; 5 bps on a normalized 10,000 account is 5 quote units.

PPO trains on net log growth; the primary comparison uses simple percentage returns for readability. These objectives are related but not mathematically identical. Report both, plus downside risk, holding time, costs and calendar outcomes. Winning versus a weak exit or one favorable seed is insufficient.

## Candidate partitions and prior use

| Partition | Half-open UTC range | Use |
|---|---|---|
| Train | 2022-01-01 to 2025-01-01 | Fit scaler and train policy |
| Validation | 2025-01-01 to 2026-01-01 | Development checks and declared baseline selection |
| Historical evaluation | 2026-01-01 to 2026-11-01 | Once-only frozen comparison |

Resolve coverage before training. Require complete warm-up, path and endpoint, with trade outcomes entirely inside one partition. Earlier data may provide causal warm-up. Purge crossing days; do not split hours of the same trade across partitions. Record candidate days, complete windows, positive-gate entries and every exclusion.

Previously viewed history is not untouched evidence. Audit known prior use and uncertainty; default label is **historical evaluation**. Any independent prospective evidence begins after the final bundle is frozen and requires actual elapsed observations.

At most 365/366 daily windows exist per year; the entry gate reduces this further. Require at least 100 eligible training trades and 30 each in validation/evaluation as a minimal prototype feasibility check, not a power calculation. If counts are lower, report insufficient sample or amend dates before fitting; do not optimize the gate to manufacture better results.

## Frozen baseline rules

- **Fixed 6h:** sell at hour 6's reference open.
- **Fixed 24h:** sell at the forced endpoint open.
- **Trailing 2%:** evaluate completed-close drawdown as defined in DATA_AND_ENVIRONMENT, exit at the next open, with mandatory hour-24 close if no trigger.

All use identical entries, starting notional, eligible dates, price adapter and costs. Early exit stays cash through the common day end. Cash/non-entry days are calendar context, not a competing method allowed to avoid the shared trade.

Choose the strongest simple exit by highest mean eligible-trade net return on validation at base costs; ties choose lower downside deviation, then the fixed order 6h, 24h, trailing. Freeze its identity before final evaluation. No entry-rule, holding-time or trailing-threshold search in version 1.

## PPO configuration and budget

| Parameter | Initial choice |
|---|---|
| Algorithm | SB3 PPO, MlpPolicy, CPU |
| Network | Actor/critic with two 32-unit hidden layers; pin activation and defaults in the resolved configuration |
| Action / observation | Discrete hold/exit; eight features per DATA_AND_ENVIRONMENT |
| Seeds | 0, 1, 2 |
| Interaction budget | 100,000 requested steps per seed; record rollout rounding |
| Learning rate | 0.0003 |
| Rollout / batch / update epochs | 1,024 / 64 / 10 |
| Discount / GAE | 1.0 / 0.95 |
| Clip / entropy coefficient | 0.2 / 0.0 |
| Reward | 100 × net log equity change, including entry/exit costs |
| Episode sampling | Uniform eligible training day with replacement, seeded; chronology within each day is preserved |
| Checkpoint | Final budget checkpoint; no best-test or best-seed selection |
| Inference | `predict(..., deterministic=True)` for validation, evaluation, reload checks and paper |

Fit only market-feature scaling on training. Do not adapt scalers/rewards during evaluation. Record unique sampled days, episode/action counts and repeated exposure, not just nominal step counts. Early-exit episodes are short, so a fixed interaction budget may replay the same days many times.

Run a tiny training-only API/runtime check first. If budget must shrink, freeze the same reduction for all seeds before examining evaluation outcomes. No alternate reward, learner or architecture search in the two-day core. Record every attempted configuration and preserve failures.

## Freeze sequence

1. Validate data/cohort definitions and independent ledger traces on development fixtures.
2. Fit training scaler; run declared baselines and three PPO seeds.
3. Inspect validation; select only the declared baseline identity. Do not choose a paper seed by performance: **seed 0** is fixed in advance.
4. Save policy/scaler/schema, data/cohort hashes, all-trial ledger and frozen protocol/config revision. Mark the artifact bundle frozen.
5. Evaluate every seed and baseline once on historical evaluation at 15 and 30 bps. Keep policies, cohort and rules frozen under stress.
6. Publish a complete report and start separate prospective paper observations.

A post-evaluation bug fix consumes that period for further development. Preserve the original artifacts, explain affected conclusions and label corrected reruns exploratory; do not silently produce a new final result.

## Reporting and uncertainty

Show mean/median paired improvement, win fraction versus each exit, downside losses, average holding time, entry/exit counts and total friction. Net arithmetic return per episode is `cash_end / cash_start − 1`. Report PPO reward/log growth separately.

For calendar results, compound normalized daily return factors on matched dates and include real gate-negative cash days. Invalid/missing days are gaps, not assumed zero returns; only calculate uninterrupted equity/Sharpe on explicitly identified complete calendar segments. State the initial/final-cost convention. Daily Sharpe uses zero risk-free rate and sqrt(365) annualization, with serial-dependence limitations; zero variance is undefined.

Report all seeds plus their median. Seeds measure learning instability, not independent market samples. An optional paired 7-calendar-day block bootstrap can describe uncertainty, retaining all methods and gate-negative days together; disclose sample and block-choice limitations. No confidence claim follows automatically from three seeds or a positive average.

## Continuation screen

Consider a longer paper study if median seed improvement versus the validation-selected baseline is at least **5 bps per eligible trade**, at least two seeds improve, median net episode return is positive, and median maximum drawdown is no more than **2 percentage points worse** on the matched complete calendar segment. Report lower-tail losses separately rather than implying an undeclared cutoff for that metric.

Also require positive median net return under 30 bps, complete accounting/causality checks and no hidden trial selection. These are research heuristics, not significance levels or permission for real trading. Same round-trip counts mean higher fixed costs mainly test net profitability; they do not establish a turnover advantage.

If evidence is mixed, undefined or insufficient, conclude **no demonstrated advantage in this study**. Paper observation and the UI can still demonstrate the verified pipeline with that result clearly labeled.
