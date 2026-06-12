"""
Re-insert the Nexus Open WebUI functions into a FRESH webui.db.

On a brand-new pod, Open WebUI's database is empty — so the "Auto (Smart
Routing)" and "Blueprint Analyzer" pipe functions (which appear as models) are
gone. Run this AFTER you've created your admin account in the browser:

    DATA_DIR=/workspace/open-webui python3 /workspace/nexus/bootstrap_functions.py

It reads the function .py files, finds your admin user, and inserts the
functions so they show up as models again. Schema-agnostic (reads the live
table columns), and also sets the default model + privacy/UI config.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time

DATA_DIR = os.environ.get("DATA_DIR", "/workspace/open-webui")
DB = os.path.join(DATA_DIR, "webui.db")
NEXUS = os.path.dirname(os.path.abspath(__file__))

FUNCTIONS = [
    ("auto_smart_routing", "Auto (Smart Routing)",
     "openwebui_autorouter_function.py"),
    ("blueprint_analyzer", "Blueprint Analyzer",
     "openwebui_blueprint_function.py"),
]


def main() -> int:
    if not os.path.exists(DB):
        print(f"No DB at {DB} — start Open WebUI once first.")
        return 1
    c = sqlite3.connect(DB)

    # admin user (first user created)
    row = c.execute("SELECT id FROM user ORDER BY created_at ASC LIMIT 1").fetchone()
    if not row:
        print("No user yet — create your account in the browser first, then "
              "re-run this.")
        return 1
    user_id = row[0]

    fn_cols = [r[1] for r in c.execute("PRAGMA table_info(function)")]
    now = int(time.time())

    for fid, name, fname in FUNCTIONS:
        path = os.path.join(NEXUS, fname)
        if not os.path.exists(path):
            print(f"  ! missing {fname}, skipping")
            continue
        content = open(path).read()
        values = {
            "id": fid, "user_id": user_id, "name": name, "type": "pipe",
            "content": content, "meta": json.dumps({"description": name}),
            "valves": "{}", "is_active": 1, "is_global": 1,
            "created_at": now, "updated_at": now,
        }
        cols = [col for col in fn_cols if col in values]
        placeholders = ",".join("?" for _ in cols)
        c.execute(
            f"INSERT OR REPLACE INTO function ({','.join(cols)}) "
            f"VALUES ({placeholders})",
            [values[col] for col in cols],
        )
        print(f"  ✓ inserted function: {name}")

    # default model + privacy/UI config
    crow = c.execute("SELECT id, data FROM config ORDER BY id DESC LIMIT 1").fetchone()
    if crow:
        cfg = json.loads(crow[1])
        cfg.setdefault("ui", {})["default_models"] = "auto_smart_routing.auto-router"
        c.execute("UPDATE config SET data=? WHERE id=?",
                  (json.dumps(cfg), crow[0]))
        print("  ✓ default model set to Auto (Smart Routing)")

    c.commit()
    print("\nDone. Restart Open WebUI (tmux kill-session -t webui; re-run boot.sh "
          "webui step) so it loads the functions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
