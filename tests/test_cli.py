import json
import sys
from unittest.mock import patch

from kairos.cli import main
from kairos.paper import initialize


def test_ui_binds_to_localhost(monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['kairos', 'ui'])
    with patch('kairos.cli.subprocess.run') as run:
        main()
    command = run.call_args.args[0]
    assert command[command.index('--server.address') + 1] == '127.0.0.1'


def test_paper_dispatcher_reads_real_state(tmp_path, monkeypatch, capsys):
    db = tmp_path / 'paper.sqlite'
    initialize(db, 's', 'hash', 0)
    monkeypatch.setattr(sys, 'argv', ['kairos', 'paper', 'status', '--db', str(db), '--session', 's'])
    main()
    assert json.loads(capsys.readouterr().out)['state']['status'] == 'waiting'
