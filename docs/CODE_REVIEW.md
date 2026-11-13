# Independent review

Scope: integrated research, historical evaluation, paper simulator and read-only viewer against SPEC, DATA_AND_ENVIRONMENT, RESEARCH_PROTOCOL. This is a research prototype review, not authorization for real-money trading.

## Outcome

No remaining confirmed blocker was found in the reviewed integrated paths. The accounting, causal feature boundary, common daily gate, non-overlapping trade horizon, hour 1–23 decisions, forced hour-24 exit, un-discounted telescoping reward, training-only feature scaling, validation baseline selection, three-seed scoring, and same-cohort cost stress are consistent with the stated design on code inspection and existing focused tests. SQLite transactions and unique event identities protect ordinary duplicate polling; pause/recovery and deadline liquidation are covered by paper tests. The viewer gates historical evaluation on linked freeze/artifact hashes and hides unrevealed steps and exits in replay.

## Findings and resolutions

- **Resolved — CLI integration:** the original paper CLI invocation passed an argument to a zero-argument `paper.main`, preventing paper commands. Integrated `paper.main(argv=None)` accepts and parses it; a persistent dispatcher regression test reads actual saved state.
- **Resolved — paper initialization:** initialization now creates a missing parent directory for the SQLite state file; a regression test exercises the missing-directory case.
- **Resolved — viewer startup:** the CLI explicitly binds Streamlit to 127.0.0.1 and disables usage statistics. A regression test checks the bind address.
- **Resolved — paper freeze check:** paper initially accepted a bundle with no sealed freeze. Integrated `validate_freeze` verifies the sealed freeze, config and seed-0 identity, and `load_bundle` checks policy/scaler hashes.
- **Resolved — evaluation visibility and chart time:** viewer now validates evaluation checksum linkage to the freeze; candles are positioned at their start while visibility remains gated by completed-bar end.
- **Resolved for this run — training provenance:** the five training-time source files are preserved at `runs/main/provenance/training-source` and all match the recorded training hashes. They differ where expected from later evaluation/reporting code, whose hashes match the integrated source.
- **Resolved — future training-source portability:** `snapshot_training_source` now saves source and protocol bytes and hashes before training, and the standard seal path verifies the snapshot. The current run retains its independently recovered training snapshot.
- **Operational limitation:** `runs/` and `data/` are Git-ignored. Preserve and transfer the run bundle, source provenance and necessary archives separately; a source-only checkout does not carry the demonstrated results. A paper run is simulated and actual live availability, a future opportunity and long-term uptime were not verified by this review.

## Evidence

- The integrated full suite passed 39 tests, as reported by the integration run. An independent focused run of the final CLI and paper tests passed 15 tests; the integrated core suite independently passed 13 tests.
- On the actual integrated `runs/main`, the freeze identity, every recorded evaluation output checksum, seed 1/2 policy hashes, all five recorded training-source hashes and all nine frozen evaluation-source hashes matched their preserved snapshots. The current `data.py` and `research.py` have since changed, so the frozen evaluation snapshot is the authoritative code for that historical result. The freeze records all three seeds at 100,352 steps, rounded from 100,000 requested.
- UI loaded the actual historical evaluation: 1,764 trade rows and 42,336 trace rows; at entry time replay showed zero future trace rows and zero future exits.
- The integration run also initialized the actual frozen bundle against public data and executed one cycle: the session remained waiting with 10,000 cash, no events and no error. No prospective entry has been observed.
- Using the actual frozen seed-0 bundle with a deterministic fake market, `kairos paper init`, then two `once` cycles, produced one entry and one policy exit; cash ended at 9,970.0449 for a constant 100 midpoint and 15 bps per side. This checks the trained-bundle CLI path without claiming current market connectivity.
- The validation-selected baseline was trailing 2%. Evaluation records median PPO improvement of 3.903 bps versus it at 15 bps per side, median net episode return −0.2482%, and stress median net return −0.5470% at 30 bps. The numerical continuation screen failed; results do not demonstrate an advantage under the stated screen. The report correctly leaves independent verification/trial-audit status pending rather than asserting a full screen pass.

## Limits

This review did not independently retrain all seeds, repeat the once-only historical evaluation, establish untouched historical data, prove statistical significance, observe a full prospective paper cohort, or independently verify public quote freshness. It inspected stored hashes and targeted behavior, not a full market-execution audit. Keep the once-only historical artifacts and their linked source untouched; any post-evaluation behavioral correction is exploratory under the protocol.
