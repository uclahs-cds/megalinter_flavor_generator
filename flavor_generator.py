"""
Modify a Megalinter submodule to add a custom flavor.

Modified from the original at
https://github.com/Heyzi/megalinter_flavor_generator/blob/ec51579b500636334fb591b4c4343383b36f3615/flavor_generator.py
"""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import List

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
]

# Paths
BASE_DIR = Path(__file__).resolve().parent / "megalinter"
MEGALINTER_DIR = BASE_DIR / "megalinter"
PATHS = {
    "descriptors": MEGALINTER_DIR / "descriptors",
    "schema": MEGALINTER_DIR
    / "descriptors"
    / "schemas"
    / "megalinter-descriptor.jsonschema.json",
    "flavor_factory": MEGALINTER_DIR / "flavor_factory.py",
    "build_script": BASE_DIR / ".automation" / "build.py",
}

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
        "--new-flavor", default=DEFAULT_NEW_FLAVOR, help="Name of the new flavor"
    )
    parser.add_argument(
        "--new-flavor-description",
        default=DEFAULT_NEW_FLAVOR_DESCRIPTION,
        help="Description of the new flavor",
    )
    parser.add_argument(
        "--components",
        default=",".join(DEFAULT_COMPONENTS),
        help="Comma-separated list of components to include",
    )
    return parser.parse_args()


def update_schema_file(file_path: Path, new_flavor: str) -> None:
    """Update the schema file with the new flavor if it doesn't already exist."""
    logger.info("Updating schema file: %s", file_path)
    try:
        with file_path.open("r") as file:
            schema = json.load(file)

        enum_flavors = schema["definitions"]["enum_flavors"]["enum"]
        if new_flavor not in enum_flavors:
            enum_flavors.append(new_flavor)
            enum_flavors.sort()

            with file_path.open("w") as file:
                json.dump(schema, file, indent=2)
            logger.info("Added '%s' to enum_flavors in the schema file.", new_flavor)
        else:
            logger.info(
                "'%s' already exists in enum_flavors. No changes made to the schema file.",
                new_flavor,
            )
    except Exception as err:
        logger.error("Error updating schema file: %s", err, exc_info=True)
        raise


def update_flavor_factory(
    file_path: Path, new_flavor: str, new_flavor_description: str
) -> None:
    """Update the flavor factory file with the new flavor if it doesn't already exist."""
    logger.info("Updating flavor factory file: %s", file_path)
    try:
        with file_path.open("r") as file:
            content = file.read()

        # Find the flavors dictionary in the content
        start = content.index("def list_megalinter_flavors():")
        end = content.index("return flavors", start)
        flavors_dict_str = content[start:end]

        # Check if the new flavor already exists
        if f'"{new_flavor}":' not in flavors_dict_str:
            # Find the last entry in the dictionary
            last_entry = re.findall(
                r'\s+".+?": {.+?},?\n', flavors_dict_str, re.DOTALL
            )[-1]
            last_entry_pos = flavors_dict_str.rfind(last_entry)

            # Prepare the new flavor entry
            match = re.match(r"\s+", last_entry)
            indent = match.group() if match else ""
            new_flavor_entry = f'{indent}"{new_flavor}": {{"strict": True, "label": "{new_flavor_description}"}},\n'

            # Insert the new flavor entry
            updated_flavors_str = (
                flavors_dict_str[:last_entry_pos]
                + last_entry.rstrip(",\n")
                + ",\n"
                + new_flavor_entry
                + flavors_dict_str[last_entry_pos + len(last_entry) :].rstrip()
                + "\n"
                + indent[:-4]
            )

            # Update the file content
            updated_content = (
                content[:start]
                + updated_flavors_str
                + "return flavors\n"
                + content[end + len("return flavors") :]
            )

            with file_path.open("w") as file:
                file.write(updated_content)
            logger.info("Added '%s' flavor in flavor_factory.py", new_flavor)
        else:
            logger.info("'%s' flavor already exists. No changes made.", new_flavor)
    except Exception as err:
        logger.error("Error updating flavor factory file: %s", err, exc_info=True)
        raise


def update_yaml_descriptors(
    directory: Path, components: List[str], new_flavor: str
) -> None:
    """Update YAML descriptor files with minimal changes."""
    logger.info("Updating YAML descriptors in %s", directory)

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml_files = list(directory.glob("*.y*ml"))

    for file_path in yaml_files:
        logger.debug("Processing file: %s", file_path)
        try:
            with file_path.open("r") as file:
                data = yaml.load(file)

            modified = False
            root_flavor_added = False

            if isinstance(data, dict) and "linters" in data:
                for linter in data["linters"]:
                    if isinstance(linter, dict) and "linter_name" in linter:
                        linter_name = linter["linter_name"]

                        if "descriptor_flavors" not in linter:
                            linter["descriptor_flavors"] = []

                        if linter_name in components:
                            if new_flavor not in linter["descriptor_flavors"]:
                                linter["descriptor_flavors"].append(new_flavor)
                                modified = True
                                logger.info(
                                    "Added %s to %s in %s",
                                    new_flavor,
                                    linter_name,
                                    file_path,
                                )

                                # Check if we need to update root descriptor_flavors
                                if "install" in data and not root_flavor_added:
                                    if "descriptor_flavors" not in data:
                                        data["descriptor_flavors"] = []
                                    if new_flavor not in data["descriptor_flavors"]:
                                        data["descriptor_flavors"].append(new_flavor)
                                        root_flavor_added = True
                                        logger.info(
                                            "Added %s to root descriptor_flavors in %s",
                                            new_flavor,
                                            file_path,
                                        )
                        else:
                            if new_flavor in linter["descriptor_flavors"]:
                                linter["descriptor_flavors"].remove(new_flavor)
                                modified = True
                                logger.info(
                                    "Removed %s from %s in %s",
                                    new_flavor,
                                    linter_name,
                                    file_path,
                                )

            if modified:
                with file_path.open("w") as file:
                    yaml.dump(data, file)
                logger.info("Updated %s", file_path)
            else:
                logger.debug("No changes needed for %s", file_path)
        except Exception as err:
            logger.error("Error processing file %s: %s", file_path, err)
            raise


def run_build_script() -> None:
    """Run the build script with the correct Python path."""
    logger.info("Running build.py with PYTHONPATH set to '.'")

    os.environ["PYTHONPATH"] = "."
    script_path = str(PATHS["build_script"])

    try:
        subprocess.run([sys.executable, script_path], cwd=BASE_DIR, check=True)

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


def main() -> None:
    """Main function to orchestrate the update process and run the build script."""
    try:
        args = parse_arguments()
        new_flavor = args.new_flavor
        new_flavor_description = args.new_flavor_description
        components = [comp.strip() for comp in args.components.split(",")]

        logger.info(
            "Starting MegaLinter flavor update process with new flavor: %s", new_flavor
        )
        logger.info("New flavor description: %s", new_flavor_description)
        logger.info("Components: %s", components)

        update_schema_file(PATHS["schema"], new_flavor)
        update_flavor_factory(
            PATHS["flavor_factory"], new_flavor, new_flavor_description
        )
        update_yaml_descriptors(PATHS["descriptors"], components, new_flavor)
        logger.info("MegaLinter flavor update process completed successfully")

        logger.info("Starting build script execution")
        run_build_script()
        logger.info("Build script execution completed successfully")

    except Exception as err:
        logger.error("MegaLinter update and build process failed: %s", err)
        raise


if __name__ == "__main__":
    main()
