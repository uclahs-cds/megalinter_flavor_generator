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
DEFAULT_NEW_FLAVOR = "devops_light"
DEFAULT_NEW_FLAVOR_DESCRIPTION = "Optimized for DevOps pipelines workflows"
DEFAULT_COMPONENTS = [
    "prettier", "npm-groovy-lint", "helm", "yamllint", "sqlfluff",
    "gitleaks", "secretlint", "trivy", "pylint", "black",
    "flake8", "isort", "bandit", "mypy", "pyright",
    "ruff", "hadolint", "ansible", "bash-exec", "shellcheck",
    "shfmt", "jscpd"
]

# Paths
BASE_DIR = Path(__file__).resolve().parent
MEGALINTER_DIR = BASE_DIR / "megalinter"
PATHS = {
    "descriptors": MEGALINTER_DIR / "descriptors",
    "schema": MEGALINTER_DIR / "descriptors" / "schemas" / "megalinter-descriptor.jsonschema.json",
    "flavor_factory": MEGALINTER_DIR / "flavor_factory.py",
    "build_script": BASE_DIR / ".automation" / "build.py"
}

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize YAML parser
yaml = YAML()
yaml.preserve_quotes = True
yaml.indent(mapping=2, sequence=4, offset=2)


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Update MegaLinter flavor and components.")
    parser.add_argument("--new-flavor", default=DEFAULT_NEW_FLAVOR, help="Name of the new flavor")
    parser.add_argument("--new-flavor-description", default=DEFAULT_NEW_FLAVOR_DESCRIPTION, help="Description of the new flavor")
    parser.add_argument("--components", default=','.join(DEFAULT_COMPONENTS), help="Comma-separated list of components to include")
    return parser.parse_args()


def update_schema_file(file_path: Path, new_flavor: str) -> None:
    """Update the schema file with the new flavor if it doesn't already exist."""
    logger.info(f"Updating schema file: {file_path}")
    try:
        with file_path.open('r') as file:
            schema = json.load(file)

        enum_flavors = schema['definitions']['enum_flavors']['enum']
        if new_flavor not in enum_flavors:
            enum_flavors.append(new_flavor)
            enum_flavors.sort()

            with file_path.open('w') as file:
                json.dump(schema, file, indent=2)
            logger.info(f"Added '{new_flavor}' to enum_flavors in the schema file.")
        else:
            logger.info(f"'{new_flavor}' already exists in enum_flavors. No changes made to the schema file.")
    except Exception as e:
        logger.error(f"Error updating schema file: {e}", exc_info=True)
        raise


def update_flavor_factory(file_path: Path, new_flavor: str, new_flavor_description: str) -> None:
    """Update the flavor factory file with the new flavor if it doesn't already exist."""
    logger.info(f"Updating flavor factory file: {file_path}")
    try:
        with file_path.open('r') as file:
            content = file.read()

        # Find the flavors dictionary in the content
        start = content.index("def list_megalinter_flavors():")
        end = content.index("return flavors", start)
        flavors_dict_str = content[start:end]

        # Check if the new flavor already exists
        if f'"{new_flavor}":' not in flavors_dict_str:
            # Find the last entry in the dictionary
            last_entry = re.findall(r'\s+".+?": {.+?},?\n', flavors_dict_str, re.DOTALL)[-1]
            last_entry_pos = flavors_dict_str.rfind(last_entry)

            # Prepare the new flavor entry
            match = re.match(r'\s+', last_entry)
            indent = match.group() if match else ''
            new_flavor_entry = f'{indent}"{new_flavor}": {{"label": "{new_flavor_description}"}},\n'

            # Insert the new flavor entry
            updated_flavors_str = (
                flavors_dict_str[:last_entry_pos] +
                last_entry.rstrip(',\n') + ',\n' +
                new_flavor_entry +
                flavors_dict_str[last_entry_pos + len(last_entry):].rstrip() +
                '\n' + indent[:-4]
            )

            # Update the file content
            updated_content = (
                content[:start] +
                updated_flavors_str +
                "return flavors\n" +
                content[end + len("return flavors"):]
            )

            with file_path.open('w') as file:
                file.write(updated_content)
            logger.info(f"Added '{new_flavor}' flavor in flavor_factory.py")
        else:
            logger.info(f"'{new_flavor}' flavor already exists. No changes made.")
    except Exception as e:
        logger.error(f"Error updating flavor factory file: {e}", exc_info=True)
        raise


def update_yaml_descriptors(directory: Path, components: List[str], new_flavor: str) -> None:
    """Update YAML descriptor files with minimal changes."""
    logger.info(f"Updating YAML descriptors in {directory}")
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml_files = list(directory.glob('*.y*ml'))

    for file_path in yaml_files:
        logger.debug(f"Processing file: {file_path}")
        try:
            with file_path.open('r') as file:
                data = yaml.load(file)

            modified = False
            if isinstance(data, dict) and 'linters' in data:
                for linter in data['linters']:
                    if isinstance(linter, dict) and 'linter_name' in linter:
                        if 'descriptor_flavors' not in linter:
                            linter['descriptor_flavors'] = []

                        if linter['linter_name'] in components:
                            if new_flavor not in linter['descriptor_flavors']:
                                linter['descriptor_flavors'].append(new_flavor)
                                modified = True
                                logger.info(f"Added {new_flavor} to {linter['linter_name']} in {file_path}")
                        else:
                            if new_flavor in linter['descriptor_flavors']:
                                linter['descriptor_flavors'].remove(new_flavor)
                                modified = True
                                logger.info(f"Removed {new_flavor} from {linter['linter_name']} in {file_path}")

            if modified:
                with file_path.open('w') as file:
                    yaml.dump(data, file)
                logger.info(f"Updated {file_path}")
            else:
                logger.debug(f"No changes needed for {file_path}")
        except Exception as e:
            logger.error(f"Error processing file {file_path}: {e}", exc_info=True)
            raise


def run_build_script() -> None:
    """Run the build script with the correct Python path."""
    logger.info("Running build.py with PYTHONPATH set to '.'")

    os.environ['PYTHONPATH'] = '.'
    script_path = str(PATHS["build_script"])

    try:
        process = subprocess.Popen(
            [sys.executable, script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True
        )

        # Real-time output processing
        if process.stdout:
            for line in process.stdout:
                logger.info(line.strip())
        else:
            logger.warning("No stdout from the process")

        # Ensure the process completes and capture any remaining output
        stdout, stderr = process.communicate()

        if stderr:
            logger.error(f"Errors from build script: {stderr}")

        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, script_path)

    except subprocess.CalledProcessError as e:
        logger.exception(f"Error in build.py: {e}")
        raise RuntimeError(f"Build script failed with return code {e.returncode}") from e
    except FileNotFoundError:
        logger.exception(f"Build script not found: {script_path}")
        raise FileNotFoundError(f"The build script {script_path} was not found.") from None


def build_docker_image(new_flavor: str) -> None:
    """
    Build the Docker image for the new flavor using Docker CLI directly.
    """
    dockerfile_path = f'flavors/{new_flavor}/Dockerfile'
    context_path = '.'
    image_name = f'megalinter-{new_flavor}:latest'

    logger.info(f"Building Docker image for {new_flavor} flavor...")

    try:
        # Check if Dockerfile exists
        if not os.path.exists(dockerfile_path):
            raise FileNotFoundError(f"Dockerfile not found at {dockerfile_path}")

        # Prepare the Docker build command
        build_command = [
            "docker", "build",
            "--build-arg", "BUILDKIT_INLINE_CACHE=1",
            "-f", dockerfile_path,
            "-t", image_name,
            context_path
        ]

        # Set environment variable to enable BuildKit
        env = os.environ.copy()
        env["DOCKER_BUILDKIT"] = "1"

        # Execute the Docker build command
        process = subprocess.Popen(
            build_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env
        )

        # Log the build process in real-time
        if process.stdout:
            for line in iter(process.stdout.readline, ''):
                logger.info(line.strip())
        else:
            logger.warning("No stdout from the process")

        # Wait for the process to complete
        return_code = process.wait()

        if return_code != 0:
            raise subprocess.CalledProcessError(return_code, " ".join(build_command))

        logger.info(f"Successfully built Docker image: {image_name}")

    except subprocess.CalledProcessError as e:
        logger.error(f"Error building Docker image: {e}")
        raise RuntimeError(f"Docker build failed: {e}") from e
    except FileNotFoundError as e:
        logger.error(str(e))
        raise
    except Exception as e:
        logger.error(f"Unexpected error during Docker build: {e}")
        raise RuntimeError(f"Unexpected error during Docker build: {e}") from e


def main() -> None:
    """Main function to orchestrate the update process and run the build script."""
    try:
        args = parse_arguments()
        new_flavor = args.new_flavor
        new_flavor_description = args.new_flavor_description
        components = [comp.strip() for comp in args.components.split(',')]

        logger.info(f"Starting MegaLinter flavor update process with new flavor: {new_flavor}")
        logger.info(f"New flavor description: {new_flavor_description}")
        logger.info(f"Components: {components}")

        update_schema_file(PATHS["schema"], new_flavor)
        update_flavor_factory(PATHS["flavor_factory"], new_flavor, new_flavor_description)
        update_yaml_descriptors(PATHS["descriptors"], components, new_flavor)
        logger.info("MegaLinter flavor update process completed successfully")

        logger.info("Starting build script execution")
        run_build_script()
        logger.info("Build script execution completed successfully")

        logger.info("Starting Docker image build")
        build_docker_image(new_flavor)
        logger.info("Docker image build completed successfully")

    except Exception as e:
        logger.error(f"MegaLinter update and build process failed: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()