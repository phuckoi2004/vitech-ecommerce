"""Run the same Gemini adapter used by the shop, without loading the database."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.cli.check_gemini import main


if __name__ == "__main__":
    raise SystemExit(main())
