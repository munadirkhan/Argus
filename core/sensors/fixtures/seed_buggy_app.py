"""Copy the crash fixture into a disposable workspace; rerun to reset the bug."""
from pathlib import Path
import argparse
import shutil


def seed(target: Path):
    source = Path(__file__).parent / "buggy-app"
    target = target.expanduser().resolve()
    if target == source.resolve() or source.resolve() in target.parents:
        raise ValueError("Choose a separate demo workspace")
    target.mkdir(parents=True, exist_ok=True)
    for path in source.iterdir():
        if path.is_file():
            shutil.copy2(path, target / path.name)
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", type=Path,
                        default=Path(__file__).resolve().parents[4] / "desk-dashboard")
    print(seed(parser.parse_args().target))
