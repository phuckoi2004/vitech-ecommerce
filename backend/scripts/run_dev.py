"""Start the API from any directory, reloading Python changes during local development."""
import sys
from pathlib import Path

import uvicorn

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


if __name__ == "__main__":
    # Keep one worker: the development auth state store lives in memory.
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True,
                reload_dirs=[str(BACKEND / "app")])
