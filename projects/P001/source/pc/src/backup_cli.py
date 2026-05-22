from __future__ import annotations

import sys
from pathlib import Path

from .storage_manager import StorageManager


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or sys.argv[1:])
    command = argv[0] if argv else "help"
    storage = StorageManager(root_dir=Path(__file__).resolve().parent.parent)
    storage.ensure_structure()

    if command == "backup":
        storage.sync_latest_backup(include_files=True, include_settings=True, reason="manual-cli")
        history_path = storage.create_history_backup(reason="manual-cli", include_files=True, include_settings=True)
        print(f"Backup created: {history_path}")
        return 0

    if command == "restore-latest":
        storage.restore_from_backup(storage.backup_latest_zip_path)
        print(f"Restored latest backup from: {storage.backup_latest_zip_path}")
        return 0

    print("Usage:")
    print("  python -m src.backup_cli backup")
    print("  python -m src.backup_cli restore-latest")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
