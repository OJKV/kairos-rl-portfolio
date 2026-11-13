# Decision record

Design baseline: 13 November 2026. Change choices deliberately and record which trial/protocol they affect.

| ID | Decision | Reason and consequence |
|---|---|---|
| D001 | Name KAIROS, repository kairos-rl | The opportune moment is a useful theme for exit timing; no affiliation with similarly named products. |
| D002 | Daily 00:00 UTC positive-24h-return entry gate | Simple causal shared cohort; avoids developing a second strategy and prevents exit-dependent re-entry. Conclusions remain conditional on this gate. |
| D003 | Hold/exit at hours 1–23; forced close at 24 | Small finite stopping problem with explicit timing and limits. |
| D004 | Fully funded spot entry and one all-in cost per side | Transparent cash/BTC accounting without leverage, lot-size or funding complexity. |
| D005 | Net log-growth reward with gamma 1 | No artificial discount preference for an earlier episode end. Primary simple-return comparison is reported separately. |
| D006 | SB3 PPO, small CPU network, three fixed seeds | Use maintained learning code and expose instability; repeated trades are not new market samples. |
| D007 | Fixed 6h/24h and close-only 2% trailing exits | Recognizable comparisons; no hindsight or intrabar stop-price assumptions. |
| D008 | Chronological partitions and explicit prior-use audit | Previously viewed history is not untouched evidence. |
| D009 | Seed 0 for initial paper, deterministic frozen inference | Avoid best-seed selection and restart randomness. |
| D010 | Public observed quotes for paper, next-open approximation for replay | Honest price-timing distinction, without private trading credentials. |
| D011 | SQLite one-writer paper state; read-only UI | Atomic events and simple local recovery without a database service. |
| D012 | Streamlit native UI plus one Plotly inspector | A local showcase within the time budget; no custom frontend or training controls. |
| D013 | Private documentation-only bootstrap | Review design before application implementation; first commit/push explicitly requested. |
| D014 | Historical replay is the primary demo; current-data paper simulation is secondary/backup | Saved episodes provide a repeatable main showcase without waiting for a daily entry. Keep both modes and their verification in the first build scope. Plan update only; implementation has not been requested. |

## Resolved during design review

- Independent research review found no substantive blocker in cohort equality, hourly timing, reward telescoping, costs or partition boundaries. The continuation screen now names maximum drawdown as the explicit risk gate and reports lower-tail losses separately.
- Independent UI/operations review found no material blocker in read-only state, replay causality, test-artifact gating or recovery. Quote references are labeled post-decision observed, without claiming measured exchange age.

These are design checks, not observed application behavior.

## Remaining build checks

- Resolve and lock compatible stable Python/SB3/PyTorch/Streamlit versions on the actual machine.
- Reproduce the data/cohort audit from the run manifest before training; preserve exclusions and prior-use labels.
- Freeze serialization schema, library defaults and CLI commands only after they work.
- Choose a distribution license before broader release; no license is invented in this private design baseline.

None requires owner input for the documentation task. Expanding the entry search, live execution or UI scope needs a new recorded decision.
