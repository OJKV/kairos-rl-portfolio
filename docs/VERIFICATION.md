# Verification requirements

The integrated suite has 39 passing tests; see CODE_REVIEW for executed evidence. The requirements below remain acceptance criteria. Document validation alone does not verify an RL system.

## Data and shared cohort

- Parse millisecond/microsecond archive fixtures correctly; reject duplicate/missing hours, bad OHLC and incomplete candles.
- Gate uses completed pre-entry returns only; future-price changes cannot change past eligibility or features.
- Every method receives exactly the same entered/excluded day IDs, entry reference and starting notional.
- No episode crosses a partition boundary; warm-up and endpoint rules are explicit.
- Missing days are not labeled cash; report actual eligible/gated counts and repeated training exposure.

## Economics, rewards and timing

- On flat prices, every exit loses exactly `(1−k)/(1+k) − 1`; cash/non-entry days stay flat.
- Fully funded entry spends cash including cost; all exits, including hour 24, pay closing cost once.
- Earliest action is hour 1; fixed exits occur at hours 6/24; no extra action exists at hour 24 or after exit.
- A gap before exit belongs to existing inventory; no method captures a price move before its mandatory entry.
- Trailing peak uses observed closes plus entry reference, never an intrabar high or future price.
- Hand-check paths where RL exits at hour 1, holds to hour 24 and exits in between. Sum of rewards must equal scaled terminal net log return, including the initial prefix and final cost.
- Changing exit time cannot unlock an extra entry. Calendar scoring remains through the shared day end.
- Nonfinite/negative ledger states fail the run; tooling truncation is not invented liquidation.

## Models and frozen evaluation

- Gymnasium/SB3 checker accepts observation/action/reset/termination contracts.
- A tiny known stopping task provides evidence the pipeline can learn; calling an API alone is insufficient.
- Training-only scaling, seeded sampling, every attempted run and actual interaction counts are recorded.
- `predict(..., deterministic=True)` is used for every evaluation/reload/paper decision. Saved/reloaded artifacts reproduce a fixed fixture within declared tolerances.
- All simple exits and seeds share data/cost conventions; stress keeps models/rules frozen.
- Baseline selection is validation-only. Undefined metrics remain undefined, not infinity or fake zeros.
- Validate paired-return tables and complete calendar aggregation independently from plots.

## Paper operation

- Duplicate polling and crashes before/after commit cannot duplicate a committed entry or exit.
- New entry must be timely at the daily gate; a missed midnight is skipped, never backfilled as a trade.
- A post-decision quote and bounded request duration are recorded without inventing exchange quote age.
- Recover missed hours with skipped decisions, original holdings/endpoint and causal peak reconstruction.
- An overdue active trade enters pending liquidation and is visibly degraded; a new cohort cannot overlap it.
- Restart preserves model identity, entry reference, cash/BTC and clock. Manual stop is not automatic liquidation.

## Viewer

- Compare displayed figures with saved artifacts, including negative returns and undefined metrics.
- Check empty, locked, corrupt/mismatched, paused/stale and no-entry states.
- Replay removes future candles, extrema/axis scaling, markers, hover values and final outcomes until revealed.
- Locked evaluation artifacts are not read or cached by any tab before freeze permits access.
- Paper refresh uses read-only database access and cannot mutate state or trigger learning/trading.
- Inspect desktop layout and readable labels/units; method identity is not conveyed by color alone.

## Review and handoff

Before completing the first build, obtain independent review of timing, entry equality, reward telescoping, selection and recovery. Reproduce substantive findings and retain regressions. Record actual commands/results and limitations; confirmed failures belong to FAILURE_LOG.

For this documentation baseline, verify relative links, balanced fences, factual status, portable paths, content boundaries and staged documentation-only scope. No claim about trained performance or running software follows from that check.
