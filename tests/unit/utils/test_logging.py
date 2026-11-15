import io
import logging

from mcp_atlassian.utils.logging import setup_logging


def test_setup_logging_default_level():
    """Test setup_logging with default WARNING level"""
    logger = setup_logging()

    # Check logger level is set to WARNING
    assert logger.level == logging.WARNING

    # Check root logger is configured
    root_logger = logging.getLogger()
    assert root_logger.level == logging.WARNING

    # Verify handler and formatter
    assert len(root_logger.handlers) == 1
    handler = root_logger.handlers[0]
    assert isinstance(handler, logging.Handler)
    assert handler.formatter._fmt == "%(levelname)s - %(name)s - %(message)s"


def test_setup_logging_custom_level():
    """Test setup_logging with custom DEBUG level"""
    logger = setup_logging(logging.DEBUG)

    # Check logger level is set to DEBUG
    assert logger.level == logging.DEBUG

    # Check root logger is configured
    root_logger = logging.getLogger()
    assert root_logger.level == logging.DEBUG


def test_setup_logging_removes_existing_handlers():
    """Test that setup_logging removes existing handlers"""
    # Add a test handler
    root_logger = logging.getLogger()
    test_handler = logging.StreamHandler()
    root_logger.addHandler(test_handler)
    initial_handler_count = len(root_logger.handlers)

    # Setup logging should remove existing handler
    setup_logging()

    # Verify only one handler remains
    assert len(root_logger.handlers) == 1
    assert test_handler not in root_logger.handlers


def test_setup_logging_logger_name():
    """Test that setup_logging creates logger with correct name"""
    logger = setup_logging()
    assert logger.name == "mcp-atlassian"


def test_setup_logging_logging_stream():
    """Test that setup_logging uses the correct stream"""
    stream = io.StringIO()
    logger = setup_logging(logging.DEBUG, stream)
    logger.debug("test")
    assert stream.getvalue() == f"DEBUG - {logger.name} - test\n"


class TestGetMaskedSessionHeaders:
    """Header values are redacted unless the header is known to be harmless."""

    def test_redacts_lowercase_and_custom_secret_headers(self):
        from mcp_atlassian.utils.logging import get_masked_session_headers

        masked = get_masked_session_headers(
            {
                "authorization": "Bearer SYNTHETIC_SECRET",
                "cookie": "session=SYNTHETIC_COOKIE",
                "X-Gateway-Secret": "SYNTHETIC_GATEWAY",
                "PROXY-AUTHORIZATION": "Basic SYNTHETIC_PROXY",
            }
        )

        rendered = str(masked)
        for secret in (
            "SYNTHETIC_SECRET",
            "SYNTHETIC_COOKIE",
            "SYNTHETIC_GATEWAY",
            "SYNTHETIC_PROXY",
        ):
            assert secret not in rendered
        assert masked["authorization"] == "Bearer <redacted>"
        assert masked["PROXY-AUTHORIZATION"] == "Basic <redacted>"
        assert masked["X-Gateway-Secret"] == "<redacted>"

    def test_keeps_allowlisted_standard_headers(self):
        from mcp_atlassian.utils.logging import get_masked_session_headers

        masked = get_masked_session_headers(
            {"User-Agent": "mcp-atlassian/1.0", "accept": "application/json"}
        )

        assert masked == {
            "User-Agent": "mcp-atlassian/1.0",
            "accept": "application/json",
        }

    def test_authorization_without_scheme_is_fully_redacted(self):
        from mcp_atlassian.utils.logging import get_masked_session_headers

        masked = get_masked_session_headers({"Authorization": "RAWTOKENVALUE"})

        assert masked == {"Authorization": "<redacted>"}

    def test_accepts_requests_case_insensitive_dict(self):
        from requests.structures import CaseInsensitiveDict

        from mcp_atlassian.utils.logging import get_masked_session_headers

        headers = CaseInsensitiveDict({"x-api-key": "SYNTHETIC_KEY"})

        assert "SYNTHETIC_KEY" not in str(get_masked_session_headers(headers))
