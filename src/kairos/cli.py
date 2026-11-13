"""Command-line entry points."""
import argparse
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(prog='kairos')
    subs = parser.add_subparsers(dest='command', required=True)
    data = subs.add_parser('data', help='Download public archives and published checksums')
    data.add_argument('--directory', required=True)
    train = subs.add_parser('train', help='Train on training data and freeze after validation')
    train.add_argument('--data', required=True); train.add_argument('--run', required=True); train.add_argument('--steps', type=int, default=100000)
    seal = subs.add_parser('seal', help='Record final frozen source and protocol identity before evaluation')
    seal.add_argument('--run', required=True); seal.add_argument('--training-source-hashes')
    evaluation = subs.add_parser('evaluate', help='Once-only frozen historical evaluation')
    evaluation.add_argument('--data', required=True); evaluation.add_argument('--run', required=True)
    subs.add_parser('paper', help='Start paper simulator')
    subs.add_parser('ui', help='Start local viewer')
    args, remainder = parser.parse_known_args()
    if args.command == 'data':
        directory = Path(args.directory); directory.mkdir(parents=True, exist_ok=True)
        for year in range(2022, 2027):
            for month in range(1, 13):
                if year == 2026 and month > 10: break
                name = f'BTCUSDT-1h-{year}-{month:02d}.zip'
                base = 'https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1h/' + name
                for suffix in ('', '.CHECKSUM'):
                    target = directory / (name + suffix)
                    if not target.exists():
                        temporary = target.with_suffix(target.suffix + '.part')
                        try:
                            subprocess.run(['curl', '--fail', '--silent', '--show-error', '--location', '--output', str(temporary), base + suffix], check=True)
                            temporary.replace(target)
                        finally:
                            temporary.unlink(missing_ok=True)
        from .data import read_archives
        bars, inventory = read_archives(directory)
        print(f'Validated {len(bars)} rows in {len(inventory)} monthly archives')
    elif args.command == 'train':
        from .research import train_and_freeze
        train_and_freeze(args.data, args.run, args.steps)
    elif args.command == 'seal':
        from .research import seal_freeze
        seal_freeze(args.run, args.training_source_hashes)
    elif args.command == 'evaluate':
        from .research import evaluate
        evaluate(args.data, args.run)
    elif args.command == 'paper':
        from .paper import main as paper_main
        paper_main(remainder)
    elif args.command == 'ui':
        import sys
        subprocess.run([sys.executable, '-m', 'streamlit', 'run', str(Path(__file__).with_name('ui.py')),
                        '--server.address', '127.0.0.1', '--server.headless', 'true',
                        '--browser.gatherUsageStats', 'false', '--', *remainder], check=True)

if __name__ == '__main__':
    main()
