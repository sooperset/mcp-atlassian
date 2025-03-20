"""Base client module for Confluence API interactions."""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

from atlassian import Confluence

from ..utils import (
    ApiCache, 
    configure_ssl_verification, 
    run_async, 
    run_parallel, 
    gather_with_concurrency,
    with_timeout
)
from .config import ConfluenceConfig

# Configure logging
logger = logging.getLogger("mcp-atlassian")


class ConfluenceClient:
    """Base client for Confluence API interactions."""

    def __init__(self, config: ConfluenceConfig | None = None, lazy_init: bool = False) -> None:
        """Initialize the Confluence client with given or environment config.

        Args:
            config: Configuration for Confluence client. If None, will load from
                environment.
            lazy_init: If True, delay initialization of the API client until first use

        Raises:
            ValueError: If configuration is invalid or environment variables are missing
        """
        self.config = config or ConfluenceConfig.from_env()
        
        # Initialize API cache with default TTL from config or 5 minutes
        self._api_cache = ApiCache(
            default_ttl=getattr(self.config, "cache_ttl_seconds", 300)
        )
        
        # Configurações de timeout para operações assíncronas
        self.default_timeout = getattr(self.config, "default_timeout_seconds", 30)
        self.max_concurrent_requests = getattr(self.config, "max_concurrent_requests", 5)
        
        # For lazy initialization
        self._is_initialized = False
        self._confluence = None
        self._preprocessor = None
        
        # Initialize the client immediately if not lazy
        if not lazy_init:
            self._initialize_client()

    def _initialize_client(self) -> None:
        """Initialize the Confluence client and preprocessor."""
        if self._is_initialized:
            return
            
        logger.debug("Initializing Confluence client")

        # Initialize the Confluence client based on auth type
        if self.config.auth_type == "token":
            self._confluence = Confluence(
                url=self.config.url,
                token=self.config.personal_token,
                cloud=self.config.is_cloud,
                verify_ssl=self.config.ssl_verify,
            )
        else:  # basic auth
            self._confluence = Confluence(
                url=self.config.url,
                username=self.config.username,
                password=self.config.api_token,  # API token is used as password
                cloud=self.config.is_cloud,
            )

        # Configure SSL verification using the shared utility
        configure_ssl_verification(
            service_name="Confluence",
            url=self.config.url,
            session=self._confluence._session,
            ssl_verify=self.config.ssl_verify,
        )

        # Import here to avoid circular imports
        from ..preprocessing.confluence import ConfluencePreprocessor

        self._preprocessor = ConfluencePreprocessor(
            base_url=self.config.url, confluence_client=self._confluence
        )
        
        self._is_initialized = True

    @property
    def confluence(self) -> Confluence:
        """Get the Confluence API client, initializing it if necessary.
        
        Returns:
            Initialized Confluence API client
        """
        if not self._is_initialized:
            self._initialize_client()
        return self._confluence
        
    @property
    def preprocessor(self):
        """Get the Confluence text preprocessor, initializing it if necessary.
        
        Returns:
            Initialized ConfluencePreprocessor
        """
        if not self._is_initialized:
            self._initialize_client()
        return self._preprocessor
        
    def clear_cache(self) -> None:
        """Clear all cached data."""
        if hasattr(self, "_api_cache"):
            self._api_cache.clear()
    
    def invalidate_cache_by_prefix(self, prefix: str) -> None:
        """Invalidate cache entries that start with the given prefix.
        
        Args:
            prefix: Prefix to match cache keys against
        """
        if hasattr(self, "_api_cache"):
            self._api_cache.invalidate_by_prefix(prefix)

    async def async_request(self, func: callable, *args, **kwargs) -> Any:
        """Execute uma requisição assíncrona.
        
        Args:
            func: Função da API do Confluence para executar
            *args: Argumentos posicionais para a função
            **kwargs: Argumentos nomeados para a função
            
        Returns:
            Resultado da função
            
        Raises:
            TimeoutError: Se a operação exceder o timeout configurado
            Exception: Se ocorrer algum erro na requisição
        """
        # Guarantee initialization
        if not self._is_initialized:
            self._initialize_client()
            
        timeout = kwargs.pop('timeout', self.default_timeout)
        
        @with_timeout(timeout)
        async def _execute():
            # Executa a função em uma thread separada
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                lambda: func(*args, **kwargs)
            )
        
        try:
            return await _execute()
        except TimeoutError:
            raise
        except Exception as e:
            logger.error(f"Erro na requisição assíncrona para {func.__name__}: {str(e)}")
            raise

    def parallel_requests(self, requests_data: List[Tuple[callable, List, Dict]]) -> List[Any]:
        """Execute múltiplas requisições em paralelo.
        
        Args:
            requests_data: Lista de tuplas contendo (função, args, kwargs)
            
        Returns:
            Lista com os resultados das requisições na mesma ordem
        """
        # Guarantee initialization
        if not self._is_initialized:
            self._initialize_client()
            
        return run_parallel(requests_data, max_workers=self.max_concurrent_requests)

    def get_user_details_by_accountid(
        self, account_id: str, expand: str = None
    ) -> dict[str, Any]:
        """Get user details by account ID.

        Args:
            account_id: The account ID of the user
            expand: OPTIONAL expand for get status of user.
                Possible param is "status". Results are "Active, Deactivated"

        Returns:
            User details as a dictionary

        Raises:
            Various exceptions from the Atlassian API if user doesn't exist or
            if there are permission issues
        """
        # Make sure client is initialized
        if not self._is_initialized:
            self._initialize_client()
            
        return self.confluence.get_user_details_by_accountid(account_id, expand)

    def _process_html_content(
        self, html_content: str, space_key: str
    ) -> tuple[str, str]:
        """Process HTML content into both HTML and markdown formats.

        Args:
            html_content: Raw HTML content from Confluence
            space_key: The key of the space containing the content

        Returns:
            Tuple of (processed_html, processed_markdown)
        """
        # Make sure preprocessor is initialized
        if not self._is_initialized:
            self._initialize_client()
            
        return self.preprocessor.process_html_content(html_content, space_key)
