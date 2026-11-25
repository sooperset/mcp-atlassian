import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]


def test_dockerfile_injects_version_before_project_install() -> None:
    lines = (ROOT / "Dockerfile").read_text().splitlines()

    arg_index = lines.index("ARG VERSION")
    copy_index = lines.index("COPY . /app")
    rewrite_index = next(i for i, line in enumerate(lines) if "sed -i" in line)
    install_indices = [
        i for i, line in enumerate(lines) if "uv sync" in line and "--no-dev" in line
    ]

    assert arg_index < copy_index < rewrite_index < install_indices[-1]
    assert 'fallback-version = \\"[^\\"]*\\"' in lines[rewrite_index]
    assert 'fallback-version = \\"$VERSION\\"' in lines[rewrite_index]


@pytest.mark.parametrize(
    "starting_line",
    [
        'fallback-version = "0.0.0"',
        'fallback-version = "1.2.3"',
        'fallback-version = "0.24.4.dev3+gabc123"',
        'fallback-version = ""',
    ],
)
def test_dockerfile_rewrite_replaces_any_fallback_version(starting_line: str) -> None:
    lines = (ROOT / "Dockerfile").read_text().splitlines()
    sed_line = next(line for line in lines if "sed -i" in line)
    expression = sed_line.split('sed -i "', 1)[1].split('" pyproject.toml', 1)[0]
    _, pattern, replacement, _ = expression.replace('\\"', '"').split("/")

    rewritten = re.sub(pattern, replacement.replace("$VERSION", "9.9.9"), starting_line)

    assert rewritten == 'fallback-version = "9.9.9"'


def test_docker_workflow_passes_version_and_guards_manual_tag() -> None:
    workflow = (ROOT / ".github" / "workflows" / "docker-publish.yml").read_text()

    assert "VERSION=${{ steps.meta.outputs.version }}" in workflow
    assert (
        "github.event_name == 'workflow_dispatch' && github.ref_type == 'branch'"
    ) in workflow
