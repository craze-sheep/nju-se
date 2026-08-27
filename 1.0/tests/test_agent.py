import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def test_package_can_be_imported() -> None:
    import nju_agent

    assert nju_agent.__version__ == "1.0.0"


def test_cli_prints_received_task() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC)

    result = subprocess.run(
        [sys.executable, "-m", "nju_agent", "hello"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "用户任务：hello" in result.stdout
