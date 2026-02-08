from __future__ import annotations

import typer

from budgeting_cli.commands.import_cmd import import_app
from budgeting_cli.commands.report_cmd import report_app
from budgeting_cli.commands.reset_cmd import reset_app
from budgeting_cli.commands.sort_unsorted_cmd import sort_unsorted_app
from budgeting_cli.menu import run_menu


app = typer.Typer(add_completion=False, no_args_is_help=False)


@app.callback(invoke_without_command=True)
def _root_callback(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        run_menu()

app.add_typer(import_app, name="import")
app.add_typer(sort_unsorted_app, name="sort-unsorted")
app.add_typer(report_app, name="report")
app.add_typer(reset_app, name="reset")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
