"""Trial run of Lumo's real look, on this Mac (no Cloud Run): real Gemini + the saved login.

    gcloud auth application-default login            # once
    GOOGLE_CLOUD_PROJECT=<id> .venv/bin/python scripts/try_patrol.py   # default: instagram

Prints the report and saves every screenshot Lumo used to ~/.lumo/patrol-shots/ (private SNS content:
kept outside the repo).
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "avatar_api"))
os.environ.setdefault("SNS_SESSION_FILE", str(Path.home() / ".lumo" / "sns-session.json"))
os.environ.setdefault("PATROL_DEBUG_DIR", str(Path.home() / ".lumo" / "patrol-shots"))

from gemini import AvatarGenerator  # noqa: E402  (needs the path above)

print(AvatarGenerator().patrol(sys.argv[1:] or ["instagram"]).model_dump_json(indent=2))
print("screenshots:", os.environ["PATROL_DEBUG_DIR"])
