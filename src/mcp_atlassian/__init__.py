import asyncio
import logging
import os
import sys

import click
from dotenv import load_dotenv

__version__ = "0.1.16"

logger = logging.getLogger("mcp-atlassian")


@click.command()
@click.option("-v", "--verbose", count=True, help="Increase verbosity (can be used multiple times)")
@click.option("--env-file", type=click.Path(exists=True, dir_okay=False), help="Path to .env file")
@click.option("--confluence-url", help="Confluence URL (e.g., https://your-domain.atlassian.net/wiki)")
@click.option("--confluence-username", help="Confluence username/email")
@click.option("--confluence-token", help="Confluence API token")
@click.option("--jira-url", help="Jira URL (e.g., https://your-domain.atlassian.net or https://jira.your-company.com)")
@click.option("--jira-username", help="Jira username/email (for Jira Cloud)")
@click.option("--jira-token", help="Jira API token (for Jira Cloud)")
@click.option("--jira-personal-token", help="Jira Personal Access Token (for Jira Server/Data Center)")
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
    """
    # Configure logging based on verbosity
    logging_level = logging.INFO
    if verbose == 1:
        logging_level = logging.INFO
    elif verbose >= 2:
        logging_level = logging.DEBUG

    logging.basicConfig(level=logging_level, stream=sys.stderr)

    # Load environment variables from file if specified, otherwise try default .env
    if env_file:
        logger.debug(f"Loading environment from file: {env_file}")
        load_dotenv(env_file)
    else:
        logger.debug("Attempting to load environment from default .env file")
        load_dotenv()

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

    from . import server

    # Run the server
    asyncio.run(server.main())


__all__ = ["main", "server", "__version__"]

if __name__ == "__main__":
    main()
