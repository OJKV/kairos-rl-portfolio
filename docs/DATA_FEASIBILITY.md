# Public-data feasibility audit

Observed **13 November 2026**. This is a data-access/cohort check, not a trained-model result or a performance backtest.

## What was checked

- Downloaded all **58 monthly BTCUSDT 1h spot archives**, January 2022 through October 2026, using the public Binance archive.
- Matched every downloaded ZIP against its published SHA-256 checksum.
- Parsed **42,359 hourly rows**, normalized the documented timestamp-unit change, and checked duplicates, positive prices, OHLC ordering and nonnegative volume. No invalid OHLC/volume rows were found.
- Found **one absent hourly open: 24 March 2023, 13:00 UTC**. The surrounding opens are 12:00 and 14:00. Do not forward-fill it; exclude cohorts whose path or warm-up depends on that missing observation.
- Counted complete daily windows and positive previous-24h-return entries under the already proposed gate, including warm-up and inside-partition endpoint requirements.

| Candidate partition | Complete daily windows | Positive-gate trades | Excluded boundary/coverage days |
|---|---:|---:|---:|
| Train: 2022-01-01 to 2025-01-01 | 1,079 | **536** | 17 |
| Validation: 2025-01-01 to 2026-01-01 | 364 | **183** | 1 |
| Historical evaluation: 2026-01-01 to 2026-11-01 | 303 | **147** | 1 |

Intervals are half-open UTC ranges. Gate-negative complete days remain cash for all methods. The exclusions include initial warm-up, the endpoint rule and the one gap's effect on several days of trailing history. Raw hourly count is not the number of independent trade experiments.

## Dataset identity

Archive-inventory SHA-256:

`60803d149ce93efdd95e0fe54c9cdd0b184f170389055a074aecd965aa6d3290`

Computed from sorted lines `ZIP filename + space + ZIP SHA-256`, each ending with a newline. This identifies the downloaded archive inventory; it is not a substitute for per-file hashes in an actual run manifest. Archives may later be corrected, so reproduce counts against recorded data identities before training.

Source route: [Binance public data and checksums](https://github.com/binance/binance-public-data). Filename pattern is `BTCUSDT-1h-YYYY-MM.zip` under the spot/monthly/klines/BTCUSDT/1h archive directory.

## What the check establishes

There is enough accessible data to build the proposed small experiment, compare matched exit rules and show historical replay. Current public BTC/ETH candle routes were also successfully exercised in source-access checks; the documented [no-key market-data API](https://github.com/binance/binance-spot-api-docs/blob/master/faqs/market_data_only.md) supports the planned paper inputs.

The public BTCUSDT bookTicker route was also tested directly: it returned valid bid/ask values and the fields symbol, bidPrice, bidQty, askPrice and askQty. No exchange event timestamp was present in that response. This supports the observed-quote design without establishing quote age.

It does not establish that PPO will learn a useful exit, that the samples provide strong statistical power, or that historical reference prices are real executable fills. The cohort is modest and conditional on one gate. No learned exit, baseline performance or trading return was evaluated during this audit.

The local Python certificate issue encountered before the successful audit is recorded in FAILURE_LOG. It was resolved through a certificate-verifying transport, not by disabling TLS checks. Raw downloads and scratch audit files remain outside this repository.
