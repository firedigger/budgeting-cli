from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil

import questionary
import typer

from budgeting_cli.db import DB_FILENAME
from budgeting_cli.ui import console


reset_app = typer.Typer(add_completion=False, no_args_is_help=True)


def run_reset(*, yes: bool, db_path: Path | None, backup: bool) -> None:
    path = Path.cwd() / DB_FILENAME if db_path is None else db_path

    if not path.exists():
        console.print(f"No database found at: {path}")
        return

    backup_path: Path | None = None
    if backup:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = path.with_name(f"{path.name}.bak-{stamp}")

    if not yes:
        console.print("This will delete ALL stored data (transactions + vendor rules).")
        if backup_path is not None:
            console.print(f"A backup will be created at: {backup_path}")

        confirm = questionary.confirm("Proceed?", default=False).ask()
        if not confirm:
            console.print("Cancelled.")
            return

        typed = questionary.text("Type RESET to confirm", default="").ask()
        if (typed or "").strip() != "RESET":
            console.print("Cancelled.")
            return

    if backup_path is not None:
        try:
            shutil.copy2(path, backup_path)
        except OSError as e:
            raise typer.BadParameter(f"Failed to create backup at {backup_path}: {e}")

    try:
        path.unlink()
    except PermissionError as e:
        raise typer.BadParameter(
            f"Failed to delete database (is it open somewhere?): {path}\n{e}"
        )

    if backup_path is not None:
        console.print(f"Backup:  {backup_path}")
    console.print(f"Deleted: {path}")


@reset_app.callback(invoke_without_command=True)
def reset(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
    no_backup: bool = typer.Option(False, "--no-backup", help="Do not create a backup file"),
    db_path: Path | None = typer.Option(
        None, "--db", help="Path to budgeting.sqlite (defaults to ./budgeting.sqlite)"
    ),
) -> None:
    """Hard reset: wipe ALL stored data (transactions + vendor rules) by deleting the SQLite file."""
    run_reset(yes=yes, db_path=db_path, backup=(not no_backup))
