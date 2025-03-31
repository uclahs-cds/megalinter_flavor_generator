"""
Modify a Megalinter submodule to add a custom flavor.

Modified from the original at
https://github.com/Heyzi/megalinter_flavor_generator/blob/ec51579b500636334fb591b4c4343383b36f3615/flavor_generator.py
"""

import argparse
import logging
import os
import string
import subprocess
import sys
import textwrap
from pathlib import Path

from ruamel.yaml import YAML

# Default values
DEFAULT_NEW_FLAVOR = "bioinformatics"
DEFAULT_NEW_FLAVOR_DESCRIPTION = "Optimized for bioinformatics pipelines workflows"
DEFAULT_COMPONENTS = [
    "actionlint",
    "bashexec",
    "shellcheck",
    "shfmt",
    "npm-groovy-lint",
    "es",
    "standard",
    "prettier",
    "jsonlint",
    "v8r",
    "prettier",
    "npm-package-json-lint",
    "perlcritic",
    "pylint",
    "black",
    "flake8",
    "isort",
    "bandit",
    "mypy",
    "pyright",
    "ruff",
    "lintr",
    "prettier",
    "yamllint",
    "v8r",
    "readme_text",
    "required_files",
]


INJECT_TEMPLATE = string.Template("""\
RUN <<EOWRAP

readonly scriptpath='/usr/local/bin/${script_name}'

# Confirm that the script does not already exist
[ ! -f "$$scriptpath" ]

cat > "$$scriptpath" << 'EOPYTHON'
${script_contents}
EOPYTHON
chmod +x "$$scriptpath"
EOWRAP
""")

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Update MegaLinter flavor and components."
    )
    parser.add_argument(
        "--flavor-name", default=DEFAULT_NEW_FLAVOR, help="Name of the new flavor"
    )
    parser.add_argument(
        "--flavor-description",
        default=DEFAULT_NEW_FLAVOR_DESCRIPTION,
        help="Description of the new flavor",
    )
    parser.add_argument(
        "--components",
        default=DEFAULT_COMPONENTS,
        nargs="+",
        help="Components to include",
    )
    parser.add_argument(
        "--add-descriptor",
        action="append",
        dest="descriptors",
        type=Path,
        help="New custom descriptor files to inject",
    )
    return parser.parse_args()


def update_flavor_factory(
    megalinter_repo_dir: Path, flavor_name: str, flavor_description: str
) -> None:
    """Update the flavor factory file with the new flavor if it doesn't already exist."""
    flavor_factory = megalinter_repo_dir / "megalinter" / "flavor_factory.py"
    logger.info("Updating flavor factory file: %s", flavor_factory)

    content = flavor_factory.read_text(encoding="utf-8")

    # Hijack and re-define the function
    content += textwrap.dedent(f"""\
        list_megalinter_flavors_ = list_megalinter_flavors

        def list_megalinter_flavors():
            flavors = list_megalinter_flavors_()
            flavors.setdefault(
                {repr(flavor_name)},
                dict(label={repr(flavor_description)})
            )
            return flavors
        """)

    flavor_factory.write_text(content, encoding="utf-8")
    logger.info("Added '%s' flavor in flavor_factory.py", flavor_name)


def inject_yaml_descriptors(
    megalinter_repo_dir: Path, descriptor_files: list[Path]
) -> None:
    """Inject a new custom descriptor into MegaLinter."""
    descriptor_dir = megalinter_repo_dir / "megalinter" / "descriptors"

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)

    for descriptor_file in descriptor_files:
        logger.info("Injecting descriptor: %s", descriptor_file)

        # Read in the descriptor to see if there are any python scripts to be
        # embedded
        with descriptor_file.open(mode="rb") as file:
            descriptor_data = yaml.load(file)

        for linter_data in descriptor_data["linters"]:
            install_data = linter_data.get("install", {})
            if inject_script := install_data.pop("dockerinject", None):
                logger.info("Injecting python script: %s", inject_script)
                script_path = descriptor_file.parent.joinpath(inject_script)
                script_contents = script_path.read_text(encoding="utf-8")

                assert "EOPYTHON" not in script_contents
                assert "EOWRAP" not in script_contents

                install_data.setdefault("dockerfile", []).append(
                    INJECT_TEMPLATE.substitute(
                        script_name=script_path.name, script_contents=script_contents
                    )
                )

        with (descriptor_dir / descriptor_file.name).open(
            mode="w", encoding="utf-8"
        ) as outfile:
            yaml.dump(descriptor_data, outfile)


def update_yaml_descriptors(
    megalinter_repo_dir: Path, components: set[str], new_flavor: str
) -> None:
    """Update YAML descriptor files with minimal changes."""
    descriptor_dir = megalinter_repo_dir / "megalinter" / "descriptors"
    logger.info("Updating YAML descriptors in %s", descriptor_dir)

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)

    install_descriptors = {new_flavor, "all_flavors"}

    for file_path in descriptor_dir.glob("*.y*ml"):
        logger.debug("Processing file: %s", file_path)

        with file_path.open("r") as file:
            descriptor_data = yaml.load(file)

        modified = False
        any_components_present = False

        if not isinstance(descriptor_data, dict):
            logger.error("Malformed descriptor file: %s", file_path.name)
            continue

        for linter in descriptor_data.get("linters", []):
            if not isinstance(linter, dict):
                logger.error("Malformed linter in %s: %s", file_path.name, linter)
                continue

            if (linter_name := linter.get("linter_name", "")) in components:
                any_components_present = True

                if new_flavor not in linter.setdefault("descriptor_flavors", []):
                    linter["descriptor_flavors"].append(new_flavor)
                    modified = True
                    logger.info(
                        "Added %s to %s in %s", new_flavor, linter_name, file_path
                    )

                    # Check if we need to update root descriptor_flavors
                    if (
                        "install" in descriptor_data
                        and new_flavor
                        not in descriptor_data.setdefault("descriptor_flavors", [])
                    ):
                        descriptor_data["descriptor_flavors"].append(new_flavor)
                        logger.info(
                            "Added %s to root descriptor_flavors in %s",
                            new_flavor,
                            file_path,
                        )
                continue

            # We need to make sure this linter is _not_ installed
            existing_descriptors = set(linter.get("descriptor_flavors", []))

            if install_descriptors & existing_descriptors:
                linter["descriptor_flavors"] = sorted(
                    existing_descriptors - install_descriptors
                )
                modified = True
                logger.info(
                    "Removed %s from %s in %s",
                    install_descriptors & existing_descriptors,
                    linter_name,
                    file_path,
                )

        # Check the root descriptor_flavors
        existing_descriptors = set(descriptor_data.get("descriptor_flavors", []))
        descriptors_present = install_descriptors & existing_descriptors

        if any_components_present and not descriptors_present:
            # Inject the root-level descriptor
            modified = True
            descriptor_data["descriptor_flavors"] = sorted(
                existing_descriptors | install_descriptors
            )
            logger.info(
                "Added %s to root-level in %s",
                install_descriptors - existing_descriptors,
                file_path,
            )
        elif not any_components_present and descriptors_present:
            # Remove the root-level descriptors
            modified = True
            descriptor_data["descriptor_flavors"] = sorted(
                existing_descriptors - install_descriptors
            )
            logger.info(
                "Removed %s from root-level in %s",
                install_descriptors & existing_descriptors,
                file_path,
            )

        if modified:
            with file_path.open("w") as file:
                yaml.dump(descriptor_data, file)
            logger.info("Updated %s", file_path)
        else:
            logger.debug("No changes needed for %s", file_path)


def run_build_script(megalinter_repo_dir: Path) -> None:
    """Run the build script with the correct Python path."""
    logger.info("Running build.py with PYTHONPATH set to '.'")

    proc_env = os.environ.copy()
    proc_env.update({"PYTHONPATH": "."})

    script_path = megalinter_repo_dir / ".automation" / "build.py"

    try:
        subprocess.run(
            [sys.executable, script_path],
            cwd=megalinter_repo_dir,
            env=proc_env,
            check=True,
        )

    except subprocess.CalledProcessError as err:
        logger.exception("Error in build.py: %s", err)
        raise RuntimeError(
            f"Build script failed with return code {err.returncode}"
        ) from err
    except FileNotFoundError:
        logger.exception("Build script not found: %s", script_path)
        raise FileNotFoundError(
            f"The build script {script_path} was not found."
        ) from None


def update_flavor() -> None:
    """Main function to orchestrate the update process and run the build script."""
    args = parse_arguments()

    flavor_name = args.flavor_name
    flavor_description = args.flavor_description

    components = {component.strip() for component in args.components}

    logger.info("New flavor name: %s", flavor_name)
    logger.info("New flavor description: %s", flavor_description)
    logger.info("Components: %s", components)

    megalinter_repo_dir = Path(__file__).resolve().parent / "megalinter"

    update_flavor_factory(megalinter_repo_dir, flavor_name, flavor_description)

    inject_yaml_descriptors(megalinter_repo_dir, args.descriptors)

    update_yaml_descriptors(megalinter_repo_dir, components, flavor_name)
    logger.info("MegaLinter flavor update process completed successfully")

    logger.info("Starting build script execution")
    run_build_script(megalinter_repo_dir)
    logger.info("Build script execution completed successfully")


if __name__ == "__main__":
    update_flavor()
