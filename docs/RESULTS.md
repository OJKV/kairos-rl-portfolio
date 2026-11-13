# Frozen research results

13 November 2026. Run: `runs/main`. This report summarizes the original saved evaluation; it does not rerun or replace it.

## Design and sample

Daily positive previous-24h-return BTC entry, same starting notional and entries for every exit method. Earliest learned exit hour 1, forced exit hour 24. Three PPO seeds trained 100,352 steps each; 536 training trades, 183 validation trades and 147 historical-evaluation trades. Training data are recycled, not independent new observations. Previously viewed history is labeled historical evaluation, not untouched evidence.

Validation selected the frozen completed-close trailing-2% exit. Prices use the declared next-open approximation with one-way all-in friction of 15 bps; stress doubles it. All methods take one round trip. Clock/trade-state features and scalers are frozen for evaluation.

| PPO seed | Mean net trade return, 15 bps/side | Paired improvement vs trailing exit |
|---|---:|---:|
| 0, predetermined paper model | −0.2482% | +3.90 bps |
| 1 | −0.3589% | −7.17 bps |
| 2 | −0.1997% | +8.76 bps |
| Median | **−0.2482%** | **+3.90 bps** |

Median net trade return under 30 bps/side: **−0.5470%**. At base costs, fixed 6h mean return was −0.3396%, fixed 24h −0.2598%, and trailing 2% −0.2872%.

## Conclusion

Two seeds improved on the validation-selected exit, but the median improvement missed the predeclared +5 bps threshold and median net returns were negative. The numeric continuation screen fails. This study demonstrates no advantage sufficient to promote RL under that screen. It does not prove that every RL exit policy or every entry rule is unprofitable.

Seed variation is material. The result is conditional on one asset/venue, entry gate, horizon and assumed costs; it is not a significance claim, real-fill result or forward return record. Keep the failed result rather than tune this evaluation period.

## Evidence and review

The ignored run includes per-method/seed/cost trade and equity traces, paired comparisons, lower-tail and log-growth metrics, freeze linkage, output checksums, and exact training/evaluation source snapshots. Freeze ID: `ddd62ea5513b24aad748bd5c01d7072a7497582d5d916de6036fcc5d133017db`.

Independent review verified linked hashes, actual artifact loading and trained-bundle paper CLI behavior. Original summary deliberately retains its pre-review pending audit field; this dated review/report supplies subsequent evidence without mutating sealed results. The software later received provenance and operational fixes; saved evaluation-source snapshots remain authoritative for the original figures.

Reproduce software behavior with the test suite. No independent second full retraining or long prospective paper record is claimed.
