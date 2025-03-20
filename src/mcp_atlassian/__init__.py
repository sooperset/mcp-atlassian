import asyncio
import os

import click
from dotenv import load_dotenv

__version__ = "0.2.5"

# Import the advanced logging system
from .logging_config import log_operation, setup_logger

# Set up the advanced logger
logger = setup_logger()

# Set up loggers for main components
jira_logger = setup_logger("mcp-atlassian.jira")
confluence_logger = setup_logger("mcp-atlassian.confluence")

# Start the logging context for the application
with log_operation(logger, "initialization"):
    logger.info(f"Initializing MCP Atlassian SDK {__version__}")

# Set metrics configuration


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
    "--transport",
    type=click.Choice(["stdio", "http"]),
    default="stdio",
    help="Transport type (stdio or http)",
)
@click.option(
    "--port",
    default=8000,
    help="Port to listen on for HTTP transport",
)
@click.option(
    "--log-dir",
    help="Directory to store log files",
)
@click.option(
    "--log-to-file/--no-log-to-file",
    default=True,
    help="Enable/disable file logging",
)
@click.option(
    "--metrics/--no-metrics",
    default=True,
    help="Enable/disable metrics collection",
)
@click.option(
    "--confluence-url",
    help="Confluence URL (e.g., https://your-domain.atlassian.net/wiki)",
)
@click.option("--confluence-username", help="Confluence username/email")
@click.option("--confluence-token", help="Confluence API token")
@click.option(
    "--confluence-personal-token",
    help="Confluence Personal Access Token (for Confluence Server/Data Center)",
)
@click.option(
    "--confluence-ssl-verify/--no-confluence-ssl-verify",
    default=True,
    help="Verify SSL certificates for Confluence Server/Data Center (default: verify)",
)
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
    transport: str,
    port: int,
    log_dir: str | None,
    log_to_file: bool,
    metrics: bool,
    confluence_url: str | None,
    confluence_username: str | None,
    confluence_token: str | None,
    confluence_personal_token: str | None,
    confluence_ssl_verify: bool,
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
    logging_level = "INFO"
    if verbose == 1:
        logging_level = "INFO"
    elif verbose >= 2:
        logging_level = "DEBUG"

    # Configura o logger avançado
    setup_logger(
        name="mcp-atlassian",
        level=logging_level,
        log_to_file=log_to_file,
        log_dir=log_dir,
    )

    # Configura loggers para componentes principais
    setup_logger(name="mcp-atlassian.jira", level=logging_level)
    setup_logger(name="mcp-atlassian.confluence", level=logging_level)
    setup_logger(name="mcp-atlassian.preprocessing", level=logging_level)

    # Inicia o contexto de logging para a aplicação
    with log_operation(logger, "application_startup", app_version=__version__):
        # Load environment variables from file if specified, otherwise try default .env
        if env_file:
            logger.info(f"Loading environment from file: {env_file}")
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
        if confluence_personal_token:
            os.environ["CONFLUENCE_PERSONAL_TOKEN"] = confluence_personal_token
        if jira_url:
            os.environ["JIRA_URL"] = jira_url
        if jira_username:
            os.environ["JIRA_USERNAME"] = jira_username
        if jira_token:
            os.environ["JIRA_API_TOKEN"] = jira_token
        if jira_personal_token:
            os.environ["JIRA_PERSONAL_TOKEN"] = jira_personal_token
        if log_dir:
            os.environ["LOG_DIR"] = log_dir

        # Set SSL verification for Confluence Server/Data Center
        os.environ["CONFLUENCE_SSL_VERIFY"] = str(confluence_ssl_verify).lower()

        # Set SSL verification for Jira Server/Data Center
        os.environ["JIRA_SSL_VERIFY"] = str(jira_ssl_verify).lower()

        # Define configuração de métricas
        os.environ["METRICS_ENABLED"] = str(metrics).lower()

        from . import server

        logger.info(f"Starting MCP Atlassian v{__version__} with {transport} transport")

        # Run the server with specified transport
        asyncio.run(server.run_server(transport=transport, port=port))


__all__ = ["main", "server", "__version__", "setup_logger", "log_operation"]

if __name__ == "__main__":
    main()
