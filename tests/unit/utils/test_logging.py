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
