import json
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated

import cappa
import tomlkit
from cruft import diff as cruft_diff
from falco.utils import default_falco_config
from falco.utils import FalcoConfig
from falco.utils import get_project_name
from falco.utils import RICH_INFO_MARKER
from falco.utils import RICH_SUCCESS_MARKER
from rich import print as rich_print

from . import checks


@contextmanager
def cruft_file(cruft_state: dict):
    file_path = Path(".cruft.json")
    try:
        file_path.write_text(json.dumps(cruft_state))
        yield
    finally:
        file_path.unlink()


def cruft_state_from(config: FalcoConfig, project_name: str, author_name: str, author_email: str) -> dict:
    return {
        "template": config["blueprint"],
        "commit": config["revision"],
        "skip": config["skip"],
        "checkout": None,
        "context": {
            "cookiecutter": {
                "project_name": project_name,
                "author_name": author_name,
                "author_email": author_email,
                "_template": config["blueprint"],
            }
        },
        "directory": None,
    }


@cappa.command(help="Update your project with changes from falco.")
class Update:
    init: Annotated[
        bool,
        cappa.Arg(default=False, short="-i", long="--init", help="Initialize falco config."),
    ]
    diff: Annotated[
        bool,
        cappa.Arg(default=False, short="-d", long="--diff", help="Show diff of changes."),
    ]

    def __call__(self, project_name: Annotated[str, cappa.Dep(get_project_name)]) -> None:
        # if is_new_falco_cli_available(fail_on_error=True):
        #     raise cappa.Exit(
        #         "You need have the latest version of falco-cli to update.", code=1
        #     )

        checks.clean_git_repo()

        pyproject_path = Path("pyproject.toml")
        try:
            pyproject = tomlkit.parse(pyproject_path.read_text())
        except FileNotFoundError as e:
            raise cappa.Exit("Could not find a pyproject.toml file in the current directory.", code=1) from e

        if self.init:
            existing_config = pyproject["tool"].get("falco", {})
            existing_config.update(default_falco_config())
            pyproject["tool"]["falco"] = existing_config
            pyproject_path.write_text(tomlkit.dumps(pyproject))
            rich_print(f"{RICH_SUCCESS_MARKER} Initialized falco config.")
            raise cappa.Exit(code=0)

        cruft_state = cruft_state_from(
            config=pyproject["tool"]["falco"],
            project_name=project_name,
            author_name=pyproject["project"]["authors"][0]["name"],
            author_email=pyproject["project"]["authors"][0]["email"],
        )

        if self.diff:
            with cruft_file(cruft_state):
                cruft_diff()
            raise cappa.Exit(code=0)

        last_commit = self.update(cruft_state=cruft_state)
        if last_commit is None:
            rich_print(f"{RICH_INFO_MARKER} Nothing to do, project is already up to date!")
            raise cappa.Exit(code=0)
        pyproject["tool"]["falco"]["revision"] = last_commit
        pyproject_path.write_text(tomlkit.dumps(pyproject))
        rich_print(f"{RICH_SUCCESS_MARKER} Great! Your project has been updated to the latest version!")

    def update(self, cruft_state: dict) -> str | None:
        """The update function from cruft"""
        from cruft._commands.utils.iohelper import AltTemporaryDirectory
        from cruft._commands import utils
        from cruft._commands.update import _apply_project_updates

        project_dir = Path()

        directory = "repo"
        skip_apply_ask = True
        skip_update = False
        allow_untracked_files = True
        strict = False

        with AltTemporaryDirectory(directory) as tmpdir_:
            # Initial setup
            tmpdir = Path(tmpdir_)
            repo_dir = tmpdir / "repo"
            current_template_dir = tmpdir / "current_template"
            new_template_dir = tmpdir / "new_template"
            deleted_paths: set[Path] = set()
            # Clone the template
            with utils.cookiecutter.get_cookiecutter_repo(cruft_state["template"], repo_dir) as repo:
                last_commit = repo.head.object.hexsha

                if utils.cruft.is_project_updated(repo, cruft_state["commit"], last_commit, strict=strict):
                    return None

                utils.generate.cookiecutter_template(
                    output_dir=current_template_dir,
                    repo=repo,
                    cruft_state=cruft_state,
                    project_dir=project_dir,
                    checkout=cruft_state["commit"],
                    deleted_paths=deleted_paths,
                    update_deleted_paths=True,
                )

            if _apply_project_updates(
                current_template_dir,
                new_template_dir,
                project_dir,
                skip_update,
                skip_apply_ask,
                allow_untracked_files,
            ):
                return last_commit

        return None
