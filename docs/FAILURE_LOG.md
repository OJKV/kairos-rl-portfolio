# Failure log

Application/runtime verification now exists. Preserve setup/research failures separately from product defects and record affected conclusions.

## SETUP-001 — Python downloader certificate trust

- **Observed:** 13 November 2026, during the public-data feasibility audit.
- **Trigger/actual:** Python urllib downloads failed with `CERTIFICATE_VERIFY_FAILED` because its local trust configuration could not validate the certificate chain.
- **Impact:** the first audit retrieved no usable archives; its zero cohort counts were a transport failure, not evidence of absent public data.
- **Resolution:** changed the audit transport to the working system curl with normal TLS verification and verified each published archive checksum. No certificate verification was disabled.
- **Prevention:** the build must verify download transport/CA setup on one archive before a bulk job and stop early on repeated transport failures. Record real download errors separately from dataset gaps.
- **Research consequence:** no model or trading result existed or was affected.

## Future entry template

Record ID/time; exact trigger; expected/actual behavior; run/config/Git/data identities; reproduced cause or unresolved status; minimal resolution; regression check/output; and whether prior evaluations or conclusions were affected. Never delete failed runs to improve the reported history.

## BUILD-001 — Integration/startup corrections

Paper CLI argument delegation, sealed-bundle enforcement, invalid ledger rejection, viewer artifact identity, and candle alignment were corrected with regression checks during integration. A real public initialization exposed a missing state-directory parent: a failing regression reproduced it, initialization now creates the parent, and the same real command succeeded. UI launch is explicitly localhost-bound, with a regression test. Full suite: 39 passed. None changed the preserved original historical policy predictions or return table; presentation/source-provenance fixes are documented separately from the sealed evaluation.
