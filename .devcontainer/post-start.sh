#! /bin/bash

set -xe

source .venv/bin/activate

uv sync --frozen --all-extras --dev
pre-commit install
