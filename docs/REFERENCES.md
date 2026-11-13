# Sources and naming

Checked during design research, 13 November 2026. Resolve actual stable package versions during implementation. None of these sources establishes trading profitability.

## Name

**KAIROS** evokes the opportune moment, fitting the decision to hold or exit. It is a project theme, not an affiliation with similarly named organizations or assets. See [Kairos: The Right Moment or Occasion, Institute for Advanced Study](https://www.ias.edu/ideas/baert-kairos), including its discussion of the Greek personification and ancient sculpture.

## Public data

- [Binance public archive](https://github.com/binance/binance-public-data): hourly candles, fields, timestamp-unit change, checksums and corrections.
- [Market-data-only endpoints](https://github.com/binance/binance-spot-api-docs/blob/master/faqs/market_data_only.md): no-key candles, server time and bookTicker.
- [Market REST responses](https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints): verify actual quote fields and rate limits; do not invent an exchange event timestamp.

## RL and evaluation

- [Gymnasium custom environment](https://gymnasium.farama.org/introduction/create_custom_env/): observation/action/reset/step contracts.
- [SB3 PPO](https://stable-baselines3.readthedocs.io/en/master/modules/ppo.html): discrete actions and CPU policy implementation.
- [SB3 installation](https://stable-baselines3.readthedocs.io/en/master/guide/install.html): current Python/PyTorch compatibility.
- [SB3 practical evaluation advice](https://stable-baselines3.readthedocs.io/en/master/guide/rl_tips.html): multiple runs, separate evaluation and environment checks.
- [Deep RL at the Edge of the Statistical Precipice](https://papers.neurips.cc/paper/2021/hash/f514cec81cb148559cf475e7426eed5e-Abstract.html): uncertainty when comparing few training runs.

## Viewer and operations

- [Streamlit installation](https://docs.streamlit.io/get-started/installation) and [local run command](https://docs.streamlit.io/develop/api-reference/cli/run).
- [Streamlit tabs](https://docs.streamlit.io/develop/api-reference/layout/st.tabs): tabs are navigation, not an artifact-access control.
- [Streamlit Plotly charts](https://docs.streamlit.io/develop/api-reference/charts/st.plotly_chart) and [Plotly candlesticks](https://plotly.com/python/candlestick-charts/).
- [Python sqlite3](https://docs.python.org/3/library/sqlite3.html): verify actual transaction settings and read-only connections with recovery tests.

## Optional later trading frameworks

- [backtesting.py](https://kernc.github.io/backtesting.py/doc/backtesting/backtesting.html): lightweight historical cross-check, not a live broker.
- [FreqAI RL](https://www.freqtrade.io/en/stable/freqai-reinforcement-learning/): training/live differences must be reconciled before integration.
- [NautilusTrader backtesting](https://nautilustrader.io/docs/latest/concepts/backtesting/): shared engine components do not establish a particular fill model's realism.
