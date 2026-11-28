"""Importing this module always raises, to test that real import errors
propagate through ``_load_storage_factory`` instead of being reported as
"Unable to import module"."""

raise ZeroDivisionError("boom")
