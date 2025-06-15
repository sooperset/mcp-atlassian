"""Custom assertions and helpers for MCP Atlassian tests."""

from typing import Any, Dict, Optional, Union
from unittest.mock import MagicMock, call


def assert_api_called_with(mock: MagicMock, method: str, **expected_kwargs) -> None:
    """Assert API method was called with expected parameters."""
    mock.assert_called_once()
    actual_kwargs = mock.call_args.kwargs if mock.call_args else {}
    
    for key, expected_value in expected_kwargs.items():
        assert key in actual_kwargs, f"Expected parameter '{key}' not found in call"
        assert actual_kwargs[key] == expected_value, (
            f"Parameter '{key}': expected {expected_value}, got {actual_kwargs[key]}"
        )


def assert_mock_called_with_partial(mock: MagicMock, **partial_kwargs) -> None:
    """Assert mock was called with at least the specified kwargs."""
    assert mock.called, "Mock was not called"
    
    if mock.call_args is None:
        raise AssertionError("Mock was called but call_args is None")
    
    actual_kwargs = mock.call_args.kwargs
    for key, expected_value in partial_kwargs.items():
        assert key in actual_kwargs, f"Expected parameter '{key}' not found"
        assert actual_kwargs[key] == expected_value, (
            f"Parameter '{key}': expected {expected_value}, got {actual_kwargs[key]}"
        )


def assert_environment_vars_set(env_dict: Dict[str, str], **expected_vars) -> None:
    """Assert environment variables are set to expected values."""
    for var_name, expected_value in expected_vars.items():
        assert var_name in env_dict, f"Environment variable '{var_name}' not set"
        assert env_dict[var_name] == expected_value, (
            f"Environment variable '{var_name}': expected '{expected_value}', "
            f"got '{env_dict[var_name]}'"
        )


def assert_config_contains(config: Dict[str, Any], **expected_config) -> None:
    """Assert configuration contains expected key-value pairs."""
    for key, expected_value in expected_config.items():
        assert key in config, f"Configuration key '{key}' not found"
        assert config[key] == expected_value, (
            f"Configuration '{key}': expected {expected_value}, got {config[key]}"
        )


def assert_exception_chain(exception: Exception, expected_cause: Optional[type] = None) -> None:
    """Assert exception has expected cause in chain."""
    if expected_cause is None:
        assert exception.__cause__ is None, "Expected no exception cause"
    else:
        assert exception.__cause__ is not None, "Expected exception cause but found none"
        assert isinstance(exception.__cause__, expected_cause), (
            f"Expected cause type {expected_cause}, got {type(exception.__cause__)}"
        )


def assert_log_contains(caplog, level: str, message: str) -> None:
    """Assert log contains message at specified level."""
    records = [r for r in caplog.records if r.levelname == level.upper()]
    messages = [r.message for r in records]
    
    assert any(message in msg for msg in messages), (
        f"Expected log message containing '{message}' at level {level}, "
        f"got messages: {messages}"
    )


def assert_dict_subset(subset: Dict[str, Any], full_dict: Dict[str, Any]) -> None:
    """Assert that subset is contained within full_dict."""
    for key, value in subset.items():
        assert key in full_dict, f"Key '{key}' not found in dictionary"
        if isinstance(value, dict) and isinstance(full_dict[key], dict):
            assert_dict_subset(value, full_dict[key])
        else:
            assert full_dict[key] == value, (
                f"Key '{key}': expected {value}, got {full_dict[key]}"
            )