help:
  @echo "Install just, and uv"
  @just --list

pc:
  uv run pre-commit

test-like-CI:
  uv run pytest -v -k "not test_real_api_validation"
