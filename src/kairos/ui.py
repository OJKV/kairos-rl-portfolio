"""Read-only historical research viewer. Start with ``streamlit run src/kairos/ui.py``."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


class ArtifactError(ValueError):
    """An artifact is unavailable or incompatible with this viewer."""


def load_artifacts(run: Path, split: str) -> dict:
    """Gate evaluation before opening any evaluation file or caching its contents."""
    run = Path(run)
    if split not in ("validation", "evaluation"):
        raise ArtifactError("Unknown split.")
    if split == "evaluation":
        freeze = run / "bundle" / "freeze.json"
        if not freeze.is_file():
            raise ArtifactError("Evaluation is locked: frozen bundle is missing.")
        try:
            freeze_bytes = freeze.read_bytes()
            manifest = json.loads(freeze_bytes)
        except (OSError, ValueError) as exc:
            raise ArtifactError("Evaluation is locked: invalid freeze manifest.") from exc
        if not isinstance(manifest, dict) or manifest.get("frozen") is not True:
            raise ArtifactError("Evaluation is locked: bundle is not frozen.")
    folder = run / split
    try:
        if split == "evaluation":
            checks = json.loads((folder / "artifact_checksums.json").read_text())
            freeze_id = hashlib.sha256(freeze_bytes).hexdigest()
            if checks.get("freeze_id") != freeze_id or checks.get("source_freeze_sha256") != freeze_id:
                raise ArtifactError("Evaluation is locked: freeze identity mismatch.")
            names = ("summary.json", "trades.csv", "equity.csv", "steps.csv", "report.md")
            files = {name: (folder / name).read_bytes() for name in names}
            digests = checks.get("files", {})
            if not isinstance(digests, dict) or any(hashlib.sha256(files[name]).hexdigest() != digests.get(name) for name in names):
                raise ArtifactError("Evaluation is locked: artifact checksum mismatch.")
            summary = json.loads(files["summary.json"])
            if summary.get("freeze_id") != freeze_id:
                raise ArtifactError("Evaluation is locked: summary freeze identity mismatch.")
        else:
            summary = json.loads((folder / "summary.json").read_text())
        if not isinstance(summary, dict) or summary.get("phase") != split:
            raise ArtifactError("Summary does not match the selected split.")
        if split == "evaluation" and summary.get("frozen") is not True:
            raise ArtifactError("Evaluation is locked: summary is not frozen.")
        data = {name: pd.read_csv(io.BytesIO(files[f"{name}.csv"]) if split == "evaluation" else folder / f"{name}.csv") for name in ("trades", "equity", "steps")}
    except (OSError, ValueError, TypeError, AttributeError, pd.errors.ParserError) as exc:
        if isinstance(exc, ArtifactError):
            raise
        prefix = "Evaluation is locked: cannot read checksums or artifacts" if split == "evaluation" else f"Cannot read {split} artifacts"
        raise ArtifactError(f"{prefix}: {exc}") from exc
    required = {
        "trades": {"day", "method", "seed", "entry_time", "exit_time", "entry_price", "exit_price", "holding_hours", "net_return"},
        "equity": {"day", "method", "seed", "equity"},
        "steps": {"day", "method", "seed", "hour", "timestamp", "price", "action", "equity"},
    }
    for name, columns in required.items():
        missing = columns - set(data[name].columns)
        if missing:
            raise ArtifactError(f"Incompatible {name}.csv; missing: {', '.join(sorted(missing))}.")
    return {"summary": summary, **data}


def replay_prefix(steps: pd.DataFrame, trades: pd.DataFrame, cutoff: pd.Timestamp) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Only completed observations and exits at or before the replay boundary."""
    cutoff = pd.to_datetime(cutoff, utc=True)
    times = pd.to_datetime(steps["timestamp"], utc=True, errors="coerce")
    visible = steps.loc[times <= cutoff].copy()
    if "bar_end" in visible:
        ends = pd.to_datetime(visible["bar_end"], utc=True, errors="coerce")
        visible = visible.loc[ends <= cutoff].copy()
    exits = pd.to_datetime(trades["exit_time"], utc=True, errors="coerce")
    return visible, trades.loc[exits <= cutoff].copy()


def cost_slice(frame: pd.DataFrame, cost: object) -> pd.DataFrame:
    return frame.loc[frame["cost_bps"] == cost].copy() if "cost_bps" in frame else frame.copy()


def trade_chart(steps: pd.DataFrame, exits: pd.DataFrame, entry: pd.Series) -> go.Figure:
    fig = go.Figure()
    # Each method sees the same price path. Keep only one observation per timestamp.
    bars = steps.sort_values("timestamp").drop_duplicates("timestamp")
    if {"open", "high", "low", "close", "bar_end"}.issubset(bars.columns):
        starts = bars["bar_start"] if "bar_start" in bars else (pd.to_datetime(bars["bar_end"], utc=True) - pd.Timedelta(hours=1)).map(lambda value: value.isoformat())
        fig.add_trace(go.Candlestick(x=starts, open=bars["open"], high=bars["high"], low=bars["low"], close=bars["close"], name="Completed candles"))
    elif not bars.empty:
        fig.add_trace(go.Scatter(x=bars["timestamp"], y=bars["price"], name="Observed boundary price", mode="lines"))
    fig.add_trace(go.Scatter(x=[entry["entry_time"]], y=[entry["entry_price"]], mode="markers", name="Shared entry", marker=dict(color="#E8EDF5", size=11, symbol="circle")))
    colors = {"ppo": ("#38BDF8", "triangle-down"), "rl": ("#38BDF8", "triangle-down"), "6h": ("#A78BFA", "square"), "24h": ("#FBBF24", "diamond"), "trailing": ("#FB923C", "x")}
    for _, row in exits.iterrows():
        method = str(row["method"])
        color, symbol = next((v for k, v in colors.items() if k in method.lower()), ("#A8B3CF", "circle"))
        fig.add_trace(go.Scatter(x=[row["exit_time"]], y=[row["exit_price"]], mode="markers", name=f"{method} exit", marker=dict(color=color, size=12, symbol=symbol)))
    fig.update_layout(template="plotly_dark", height=420, xaxis_title="Time (UTC)", yaxis_title="BTC price (USDT)", paper_bgcolor="#141B2D", plot_bgcolor="#141B2D", xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=25, b=10))
    return fig


def overview(data: dict) -> None:
    summary, trades, equity = data["summary"], data["trades"], data["equity"]
    st.subheader("The research question")
    st.write("Given the same BTC entries, can learned exits improve on simple exits after costs?")
    st.caption("Daily positive 24-hour momentum gate · maximum hold 24 hours · simulated fills and assumed costs")
    a, b, c = st.columns(3)
    a.metric("Shared entry days", trades["day"].nunique() if not trades.empty else "—")
    b.metric("Exit records", len(trades))
    c.metric("Validation-selected baseline", summary.get("selected_baseline") or "—")
    st.subheader("All methods and seeds")
    if trades.empty:
        st.info("No eligible trades in this artifact.")
    else:
        table = trades.groupby(["method", "seed"], dropna=False).agg(trades=("net_return", "count"), mean_net_return=("net_return", "mean"), median_net_return=("net_return", "median"), mean_holding_hours=("holding_hours", "mean")).reset_index()
        st.dataframe(table, hide_index=True, width="stretch")
    if summary.get("metrics"):
        st.caption("Saved comparison metrics")
        st.dataframe(pd.DataFrame(summary["metrics"]), hide_index=True, width="stretch")
    st.subheader("Matched equity")
    if equity.empty:
        st.info("Equity history is unavailable.")
    else:
        labels = equity["method"].astype(str) + " · seed " + equity["seed"].astype(str)
        plotted = equity.assign(series=labels).pivot_table(index="day", columns="series", values="equity", aggfunc="last")
        st.line_chart(plotted)
        st.subheader("Drawdown from recorded peak")
        st.line_chart(plotted.div(plotted.cummax()).sub(1))
        st.caption("Recorded equity; gaps and calendar coverage depend on the saved run.")
    st.info("Historical simulation is not evidence of future profitability. Costs are assumptions; inspect the saved run for data quality and coverage.")
    with st.expander("Provenance and saved summary"):
        st.json(summary)


def inspector(data: dict, seed: object) -> None:
    trades, steps = data["trades"], data["steps"]
    # Baselines can be stored per seed; select the same seed for all methods.
    trades = trades.loc[trades["seed"].isna() | (trades["seed"] == seed)]
    steps = steps.loc[steps["seed"].isna() | (steps["seed"] == seed)]
    if trades.empty:
        st.info("No eligible trades for this seed and cost scenario.")
        return
    days = sorted(trades["day"].astype(str).unique())
    day = st.selectbox("Shared entry day (UTC)", days)
    selected = trades.loc[trades["day"].astype(str) == day].copy()
    observations = steps.loc[steps["day"].astype(str) == day].copy()
    if observations.empty:
        st.warning("No saved observation trace for this entry.")
        return
    entry = selected.iloc[0]
    if selected["entry_time"].nunique() != 1 or selected["entry_price"].nunique() != 1:
        st.error("Incompatible artifact: methods do not share an entry.")
        return
    mode = st.radio("View", ["Replay", "Posthoc comparison"], horizontal=True)
    if mode == "Replay":
        hour = st.slider("Completed hour since entry", 0, 24, 0)
        cutoff = pd.to_datetime(entry["entry_time"], utc=True) + pd.Timedelta(hours=hour)
        visible, exits = replay_prefix(observations, selected, cutoff)
        st.caption(f"Replay through {cutoff:%Y-%m-%d %H:%M UTC}. Future bars and exits are hidden.")
    else:
        visible, exits = observations, selected
        st.warning("Posthoc comparison: the full historical episode and outcomes are visible.")
    st.plotly_chart(trade_chart(visible, exits, entry), width="stretch")
    st.caption("Exit markers are simulated comparisons, not exchange fills. Price data is shown only when saved in the artifact.")
    st.subheader("Revealed exits" if mode == "Replay" else "Simulated exits")
    if exits.empty:
        st.info("No exits have been revealed yet.")
    else:
        columns = [c for c in ("method", "exit_time", "exit_price", "holding_hours", "net_return", "exit_reason") if c in exits]
        st.dataframe(exits[columns], hide_index=True, width="stretch")
    st.subheader("Saved observations and actions")
    if visible.empty:
        st.info("No completed observations at this boundary.")
    else:
        st.dataframe(visible.sort_values("timestamp"), hide_index=True, width="stretch")


def paper_status() -> None:
    st.subheader("Paper simulation · read-only")
    path = st.text_input("SQLite database path", value=os.environ.get("KAIROS_PAPER_DB", "state/paper.sqlite"))
    if not Path(path).is_file():
        st.info("Waiting for a paper session. No database exists at this path.")
        return
    try:
        from kairos.paper import snapshot
        result = snapshot(Path(path))
    except Exception as exc:
        st.error(f"Paper snapshot unavailable: {exc}")
        return
    if not result or not result.get("state"):
        st.info("Waiting for a paper session; no observed state is available.")
        return
    st.caption(f"Session: {result.get('session_id', '—')} · all timestamps are UTC when displayed as such")
    st.json(result["state"])
    st.subheader("Recent events")
    if result.get("events"):
        st.dataframe(pd.DataFrame(result["events"]), hide_index=True, width="stretch")
    else:
        st.info("No events recorded.")


def main() -> None:
    st.set_page_config(page_title="KAIROS · Research viewer", layout="wide")
    st.markdown("<style>.stApp{background:#0B1020;color:#E8EDF5} [data-testid='stMetric']{background:#141B2D;padding:16px;border:1px solid #25324A;border-radius:8px}</style>", unsafe_allow_html=True)
    st.title("KAIROS")
    st.caption("Learn when to exit · local research viewer · UTC")
    view = st.sidebar.radio("View", ["Overview", "Trade inspector", "Paper status"])
    if view == "Paper status":
        paper_status()
        return
    run = Path(st.sidebar.text_input("Run directory", value=os.environ.get("KAIROS_RUN", "runs/latest"))).expanduser()
    mode = st.sidebar.selectbox("Data mode", ["Research artifacts", "Fixture (development only)"])
    split = st.sidebar.selectbox("Split", ["validation", "evaluation"])
    try:
        data = load_artifacts(run, split)
    except ArtifactError as exc:
        st.warning(str(exc))
        st.caption("Choose a saved run directory. Evaluation requires a frozen bundle and frozen evaluation summary.")
        return
    costs = sorted(data["trades"]["cost_bps"].dropna().unique()) if "cost_bps" in data["trades"] else []
    cost = st.sidebar.selectbox("Cost (bps per side)", costs) if costs else None
    if cost is not None:
        for name in ("trades", "equity", "steps"):
            data[name] = cost_slice(data[name], cost)
        if data["summary"].get("metrics"):
            metrics = pd.DataFrame(data["summary"]["metrics"])
            data["summary"] = {**data["summary"], "metrics": cost_slice(metrics, cost).to_dict("records")}
    seeds = sorted(data["trades"]["seed"].dropna().unique(), key=str)
    seed = st.sidebar.selectbox("Inspector seed", seeds) if seeds else None
    st.caption(f"{mode} · {split} · run {run.name} · seed {seed if seed is not None else '—'} · cost {str(cost) + ' bps/side' if cost is not None else 'not recorded'}")
    if mode.startswith("Fixture"):
        st.warning("Fixture mode: development data only; exclude from research claims.")
    if view == "Overview":
        overview(data)
    elif seed is None:
        st.info("No eligible trades in this artifact.")
    else:
        inspector(data, seed)


if __name__ == "__main__":
    main()
