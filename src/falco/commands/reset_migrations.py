import subprocess
from pathlib import Path
from typing import Annotated

import cappa
from falco.utils import get_current_dir_as_project_name
from falco.utils import run_in_shell
from falco.utils import simple_progress
from rich import print as rich_print

from .rm_migrations import RmMigrations

reset_migrations_table_code = """
from django.db import connection

with connection.cursor() as cursor:
    cursor.execute("DELETE FROM django_migrations")
"""


@cappa.command(help="Delete and recreate all migrations.", name="reset-migrations")
class ResetMigrations:
    apps_dir: Annotated[
        Path | None,
        cappa.Arg(default=None, help="The path to your django apps directory."),
    ]
    skip_git_check: Annotated[
        bool,
        cappa.Arg(
            default=False,
            long="--skip-git-check",
            help="Do not check if your git repo is clean.",
        ),
    ]

    def __call__(self, project_name: Annotated[str, cappa.Dep(get_current_dir_as_project_name)]):
        with simple_progress("Running django check..."):
            result = subprocess.run(
                ["python", "manage.py", "check"],
                check=False,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                print(result.stderr)
                raise cappa.Exit(code=1)

        RmMigrations(skip_git_check=self.skip_git_check, apps_dir=self.apps_dir)(project_name)
        with simple_progress("Resetting migrations..."):
            run_in_shell(reset_migrations_table_code, eval_result=False)
            subprocess.run(
                ["python", "manage.py", "makemigrations"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            subprocess.run(
                ["python", "manage.py", "migrate", "--fake"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        rich_print("Done!")
