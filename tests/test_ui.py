import json
import importlib.util
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

spec = importlib.util.spec_from_file_location("kairos_viewer", Path(__file__).parents[1] / "src/kairos/ui.py")
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)
ArtifactError, load_artifacts, replay_prefix, trade_chart = ui.ArtifactError, ui.load_artifacts, ui.replay_prefix, ui.trade_chart


def make_run(tmp_path):
    folder = tmp_path / "validation"
    folder.mkdir()
    (folder / "summary.json").write_text(json.dumps({"phase": "validation", "frozen": False, "metrics": []}))
    trades = pd.DataFrame([
        {"day": "2025-01-01", "method": m, "seed": 0 if m == "rl" else None, "cost_bps": 15, "entry_time": "2025-01-01T00:00:00Z", "exit_time": f"2025-01-01T0{h}:00:00Z", "entry_price": 100, "exit_price": p, "holding_hours": h, "net_return": ret}
        for m, h, p, ret in [("rl", 1, 90, -0.1), ("6h", 2, 110, 0.1)]
    ])
    steps = pd.DataFrame([
        {"day": "2025-01-01", "method": "rl", "seed": 0, "cost_bps": 15, "hour": h, "timestamp": f"2025-01-01T0{h}:00:00Z", "bar_end": f"2025-01-01T0{h}:00:00Z", "open": 100, "high": high, "low": 90, "close": 100, "price": 100, "action": "hold", "equity": 10000}
        for h, high in [(1, 101), (2, 999)]
    ])
    equity = pd.DataFrame([{"day": "2025-01-01", "method": "rl", "seed": 0, "cost_bps": 15, "equity": 9000}])
    for name, frame in [("trades", trades), ("steps", steps), ("equity", equity)]:
        frame.to_csv(folder / f"{name}.csv", index=False)
    return trades, steps


def test_replay_never_exposes_future_candles_or_exits(tmp_path):
    trades, steps = make_run(tmp_path)
    visible, exits = replay_prefix(steps, trades, pd.Timestamp("2025-01-01T01:00:00Z"))
    assert visible["high"].tolist() == [101]
    assert exits["method"].tolist() == ["rl"]
    fig = trade_chart(visible, exits, trades.iloc[0])
    assert list(fig.data[0].high) == [101]
    assert all("6h" not in trace.name for trace in fig.data)
    visible, exits = replay_prefix(steps, trades, pd.Timestamp("2025-01-01T00:00:00Z"))
    assert visible.empty and exits.empty


def test_forming_bar_is_not_visible(tmp_path):
    trades, steps = make_run(tmp_path)
    steps.loc[0, "bar_end"] = "2025-01-01T02:00:00Z"
    visible, _ = replay_prefix(steps, trades, pd.Timestamp("2025-01-01T01:00:00Z"))
    assert visible.empty


def test_locked_evaluation_never_reads_csv(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("locked evaluation file was read")
    monkeypatch.setattr(pd, "read_csv", forbidden)
    with pytest.raises(ArtifactError, match="locked"):
        load_artifacts(tmp_path, "evaluation")
    (tmp_path / "bundle").mkdir()
    (tmp_path / "bundle" / "freeze.json").write_text('{"frozen": false}')
    with pytest.raises(ArtifactError, match="locked"):
        load_artifacts(tmp_path, "evaluation")


def test_app_overview_and_replay(tmp_path, monkeypatch):
    make_run(tmp_path)
    monkeypatch.setenv("KAIROS_RUN", str(tmp_path))
    app = AppTest.from_file(str(Path(__file__).parents[1] / "src/kairos/ui.py")).run()
    assert not app.exception
    assert any("research question" in sub.value.lower() for sub in app.subheader)
    app.sidebar.radio[0].set_value("Trade inspector").run()
    assert not app.exception
    assert any("No exits" in info.value for info in app.info)
    app.slider[0].set_value(1).run()
    assert not app.exception
    assert app.dataframe[0].value["method"].tolist() == ["rl"]
    app.radio[0].set_value("Posthoc comparison").run()
    assert not app.exception
    assert set(app.dataframe[0].value["method"]) == {"rl", "6h"}


def test_app_empty_state(tmp_path, monkeypatch):
    monkeypatch.setenv("KAIROS_RUN", str(tmp_path))
    app = AppTest.from_file(str(Path(__file__).parents[1] / "src/kairos/ui.py")).run()
    assert not app.exception
    assert any("Cannot read" in warning.value for warning in app.warning)


def test_evaluation_requires_frozen_summary_before_csv(tmp_path, monkeypatch):
    (tmp_path / "bundle").mkdir()
    (tmp_path / "bundle" / "freeze.json").write_text('{"frozen": true}')
    (tmp_path / "evaluation").mkdir()
    (tmp_path / "evaluation" / "summary.json").write_text('{"phase": "evaluation", "frozen": false}')
    monkeypatch.setattr(pd, "read_csv", lambda *args, **kwargs: pytest.fail("evaluation CSV was read"))
    with pytest.raises(ArtifactError, match="locked"):
        load_artifacts(tmp_path, "evaluation")


def test_paper_missing_database_shows_waiting(tmp_path, monkeypatch):
    monkeypatch.setenv("KAIROS_PAPER_DB", str(tmp_path / "missing.sqlite"))
    app = AppTest.from_file(str(Path(__file__).parents[1] / "src/kairos/ui.py")).run()
    app.sidebar.radio[0].set_value("Paper status").run()
    assert not app.exception
    assert any("Waiting" in info.value for info in app.info)
    assert not (tmp_path / "missing.sqlite").exists()


def test_evaluation_rejects_tampered_files_before_parsing(tmp_path, monkeypatch):
    import hashlib
    import shutil
    make_run(tmp_path)
    (tmp_path / 'bundle').mkdir()
    freeze = b'{"frozen": true}'
    (tmp_path / 'bundle' / 'freeze.json').write_bytes(freeze)
    freeze_id = hashlib.sha256(freeze).hexdigest()
    folder = tmp_path / 'evaluation'
    shutil.copytree(tmp_path / 'validation', folder)
    (folder / 'summary.json').write_text(json.dumps({'phase': 'evaluation', 'frozen': True, 'freeze_id': freeze_id}))
    names = ['summary.json', 'trades.csv', 'equity.csv', 'steps.csv', 'report.md']
    (folder / 'report.md').write_text('report')
    files = {name: hashlib.sha256((folder / name).read_bytes()).hexdigest() for name in names}
    (folder / 'artifact_checksums.json').write_text(json.dumps({'freeze_id': freeze_id, 'source_freeze_sha256': freeze_id, 'files': files}))
    load_artifacts(tmp_path, 'evaluation')
    (folder / 'trades.csv').write_text('tampered')
    monkeypatch.setattr(pd, 'read_csv', lambda *args, **kwargs: pytest.fail('tampered CSV parsed'))
    with pytest.raises(ArtifactError, match='checksum'):
        load_artifacts(tmp_path, 'evaluation')


def test_candle_is_anchored_at_start_not_decision_time(tmp_path):
    trades, steps = make_run(tmp_path)
    steps['bar_start'] = ['2025-01-01T00:00:00Z', '2025-01-01T01:00:00Z']
    visible, exits = replay_prefix(steps, trades, pd.Timestamp('2025-01-01T01:00:00Z'))
    fig = trade_chart(visible, exits, trades.iloc[0])
    assert list(fig.data[0].x) == ['2025-01-01T00:00:00Z']


def test_candle_start_is_derived_for_existing_runs(tmp_path):
    trades, steps = make_run(tmp_path)
    visible, exits = replay_prefix(steps, trades, pd.Timestamp('2025-01-01T01:00:00Z'))
    fig = trade_chart(visible, exits, trades.iloc[0])
    assert pd.Timestamp(fig.data[0].x[0]) == pd.Timestamp('2025-01-01T00:00:00Z')


def test_evaluation_rejects_mismatched_freeze_identity(tmp_path):
    (tmp_path / 'bundle').mkdir()
    (tmp_path / 'bundle' / 'freeze.json').write_text('{"frozen": true}')
    (tmp_path / 'evaluation').mkdir()
    (tmp_path / 'evaluation' / 'artifact_checksums.json').write_text('{"freeze_id": "wrong", "source_freeze_sha256": "wrong", "files": {}}')
    with pytest.raises(ArtifactError, match='freeze identity'):
        load_artifacts(tmp_path, 'evaluation')
