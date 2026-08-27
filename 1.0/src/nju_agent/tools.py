from pathlib import Path


def list_files(root: str) -> list[str]:
    base = Path(root)
    return sorted(p.name for p in base.iterdir())
