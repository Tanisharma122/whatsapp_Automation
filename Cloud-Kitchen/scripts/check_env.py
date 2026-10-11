"""
check_env.py — Startup environment diagnostic script.

Run this anytime to see which configuration variables are missing
WITHOUT revealing their actual values.

Usage:
    python scripts/check_env.py
"""
import sys
from pathlib import Path

# Make `src/` importable when running from the project root
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app.config import settings  # noqa: E402


def main() -> None:
    print(f"\n{'='*55}")
    print(f"  {settings.app_name} v{settings.app_version}")
    print(f"  Environment : {settings.app_env.value}")
    print(f"  Log level   : {settings.log_level.value}")
    print(f"{'='*55}\n")

    groups = {
        "Module 2 — WhatsApp Cloud API": settings.missing_module2_vars(),
        "Module 3 — Google Sheets":      settings.missing_module3_vars(),
        "Module 4 — LLM Provider":       settings.missing_module4_vars(),
    }

    all_ok = True
    for group_name, missing in groups.items():
        if missing:
            all_ok = False
            print(f"  [MISSING] {group_name}")
            for var in missing:
                print(f"            Missing: {var}")
        else:
            print(f"  [OK]      {group_name} -- fully configured")
        print()

    if all_ok:
        print("  [ALL OK] All configuration groups are ready.\n")
    else:
        print(
            "  [INFO] Missing variables are normal during early modules.\n"
            "         Copy .env.example -> .env and fill in the values\n"
            "         for each module as you need them.\n"
        )


if __name__ == "__main__":
    main()
