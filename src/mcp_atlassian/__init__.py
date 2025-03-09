import asyncio
import logging
import os
import sys

import click
from dotenv import load_dotenv

__version__ = "0.1.16"

logger = logging.getLogger("mcp-atlassian")


@click.command()
@click.option(
    "-v",
    "--verbose",
    count=True,
    help="Increase verbosity (can be used multiple times)",
)
@click.option(
    "--env-file", type=click.Path(exists=True, dir_okay=False), help="Path to .env file"
)
@click.option(
    "--confluence-url",
    help="Confluence URL (e.g., https://your-domain.atlassian.net/wiki)",
)
@click.option("--confluence-username", help="Confluence username/email")
@click.option("--confluence-token", help="Confluence API token")
@click.option(
    "--jira-url",
    help="Jira URL (e.g., https://your-domain.atlassian.net or https://jira.your-company.com)",
)
@click.option("--jira-username", help="Jira username/email (for Jira Cloud)")
@click.option("--jira-token", help="Jira API token (for Jira Cloud)")
@click.option(
    "--jira-personal-token",
    help="Jira Personal Access Token (for Jira Server/Data Center)",
)
@click.option(
    "--jira-ssl-verify/--no-jira-ssl-verify",
    default=True,
    help="Verify SSL certificates for Jira Server/Data Center (default: verify)",
)
def main(
    verbose: bool,
    env_file: str | None,
    confluence_url: str | None,
    confluence_username: str | None,
    confluence_token: str | None,
    jira_url: str | None,
    jira_username: str | None,
    jira_token: str | None,
    jira_personal_token: str | None,
    jira_ssl_verify: bool,
) -> None:
    """MCP Atlassian Server - Jira and Confluence functionality for MCP

    Supports both Atlassian Cloud and Jira Server/Data Center deployments.

    Args:
        verbose: Enable verbose logging output
        env_file: Path to .env file for configuration
        confluence_url: Confluence URL
        confluence_username: Confluence username
        confluence_token: Confluence API token
        jira_url: Jira URL
        jira_username: Jira username/email (for Jira Cloud)
        jira_token: Jira API token (for Jira Cloud)
        jira_personal_token: Jira personal access token (for Jira Server/Data Center)
        jira_ssl_verify: Whether to verify SSL certificates for Jira connections
    """
    # Set up logging based on verbosity
    _setup_logging(verbose)

    # Load environment variables
    _load_environment_variables(env_file)

    # Set environment variables from command line arguments
    _set_environment_from_args(
        confluence_url=confluence_url,
        confluence_username=confluence_username,
        confluence_token=confluence_token,
        jira_url=jira_url,
        jira_username=jira_username,
        jira_token=jira_token,
        jira_personal_token=jira_personal_token,
        jira_ssl_verify=jira_ssl_verify,
    )

    # Import the server module after environment setup
    from . import server

    # Run the server
    asyncio.run(server.main())


def _setup_logging(verbose: int) -> None:
    """
    Configure logging based on verbosity level.

    Args:
        verbose: Verbosity level (0=INFO, 1=INFO, 2+=DEBUG)
    """
    logging_level = logging.INFO
    if verbose == 1:
        logging_level = logging.INFO
    elif verbose >= 2:
        logging_level = logging.DEBUG

    logging.basicConfig(level=logging_level, stream=sys.stderr)


def _load_environment_variables(env_file: str | None) -> None:
    """
    Load environment variables from file.

    Args:
        env_file: Optional path to .env file
    """
    if env_file:
        logger.debug(f"Loading environment from file: {env_file}")
        load_dotenv(env_file)
    else:
        logger.debug("Attempting to load environment from default .env file")
        load_dotenv()


def _set_environment_from_args(
    confluence_url: str | None,
    confluence_username: str | None,
    confluence_token: str | None,
    jira_url: str | None,
    jira_username: str | None,
    jira_token: str | None,
    jira_personal_token: str | None,
    jira_ssl_verify: bool,
) -> None:
    """
    Set environment variables from command line arguments.

    Args:
        confluence_url: Confluence URL
        confluence_username: Confluence username
        confluence_token: Confluence API token
        jira_url: Jira URL
        jira_username: Jira username
        jira_token: Jira API token
        jira_personal_token: Jira personal access token
        jira_ssl_verify: Whether to verify SSL certificates for Jira connections
    """
    # Set environment variables from command line arguments if provided
    if confluence_url:
        os.environ["CONFLUENCE_URL"] = confluence_url
    if confluence_username:
        os.environ["CONFLUENCE_USERNAME"] = confluence_username
    if confluence_token:
        os.environ["CONFLUENCE_API_TOKEN"] = confluence_token
    if jira_url:
        os.environ["JIRA_URL"] = jira_url
    if jira_username:
        os.environ["JIRA_USERNAME"] = jira_username
    if jira_token:
        os.environ["JIRA_API_TOKEN"] = jira_token
    if jira_personal_token:
        os.environ["JIRA_PERSONAL_TOKEN"] = jira_personal_token

    # Set SSL verification for Jira Server/Data Center
    os.environ["JIRA_SSL_VERIFY"] = str(jira_ssl_verify).lower()


__all__ = ["main", "server", "__version__"]

if __name__ == "__main__":
    main()
