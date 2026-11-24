"""Start the API from any directory, reloading Python changes during local development."""
import sys
from pathlib import Path

import uvicorn

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


if __name__ == "__main__":
    # Reload local code; use AUTH_STATE_BACKEND=sqlite to keep sessions across reloads.
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True,
                reload_dirs=[str(BACKEND / "app")])
