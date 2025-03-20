"""Utility functions for the MCP Atlassian integration."""

import logging
from typing import Any, Callable, Dict, Generic, Optional, TypeVar, Iterable, List, Generator, Tuple
from urllib.parse import urlparse
import time
from datetime import datetime, timedelta
from functools import wraps

from requests.adapters import HTTPAdapter
from requests.sessions import Session

import asyncio
import functools
from concurrent.futures import ThreadPoolExecutor

import re
from html import escape as html_escape
from itertools import islice

# Configure logging
logger = logging.getLogger("mcp-atlassian")

T = TypeVar('T')

class CacheItem(Generic[T]):
    """Cache item with timestamp for expiration checks."""

    def __init__(self, value: T, ttl_seconds: int = 300):
        """Initialize cache item with value and expiration time.
        
        Args:
            value: The value to store in cache
            ttl_seconds: Time to live in seconds (default: 5 minutes)
        """
        self.value = value
        self.timestamp = datetime.now()
        self.ttl_seconds = ttl_seconds

    def is_expired(self) -> bool:
        """Check if the item has expired.
        
        Returns:
            True if the item has expired, False otherwise
        """
        return datetime.now() > self.timestamp + timedelta(seconds=self.ttl_seconds)


class ApiCache:
    """Generic cache for API responses with TTL-based invalidation."""

    def __init__(self, default_ttl: int = 300):
        """Initialize the cache.
        
        Args:
            default_ttl: Default time to live in seconds (default: 5 minutes)
        """
        self._cache: Dict[str, CacheItem] = {}
        self.default_ttl = default_ttl

    def get(self, key: str) -> Optional[Any]:
        """Get a value from the cache if it exists and is not expired.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found or expired
        """
        item = self._cache.get(key)
        if item is None or item.is_expired():
            if item is not None:
                # Clear expired item
                del self._cache[key]
            return None
        return item.value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set a value in the cache with specified TTL.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (default: None, uses instance default)
        """
        self._cache[key] = CacheItem(value, ttl or self.default_ttl)

    def delete(self, key: str) -> None:
        """Delete a value from the cache.
        
        Args:
            key: Cache key to delete
        """
        if key in self._cache:
            del self._cache[key]

    def invalidate_by_prefix(self, prefix: str) -> None:
        """Invalidate all keys that start with the given prefix.
        
        Args:
            prefix: Key prefix to match
        """
        keys_to_delete = [k for k in self._cache.keys() if k.startswith(prefix)]
        for key in keys_to_delete:
            del self._cache[key]

    def clear(self) -> None:
        """Clear the entire cache."""
        self._cache.clear()

    def size(self) -> int:
        """Get the current size of the cache.
        
        Returns:
            Number of cached items
        """
        return len(self._cache)


def cached(key_prefix: str, ttl_seconds: Optional[int] = None):
    """Decorator for caching function results.
    
    Example usage:
        @cached("projects", 3600)
        def get_all_projects(self):
            # Function implementation
    
    Args:
        key_prefix: Prefix for cache key
        ttl_seconds: Time to live in seconds
        
    Returns:
        Decorator function
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            # Generate a unique cache key based on function args
            arg_string = "_".join([str(arg) for arg in args])
            kwarg_string = "_".join([f"{k}={v}" for k, v in sorted(kwargs.items())])
            cache_key = f"{key_prefix}_{func.__name__}_{arg_string}_{kwarg_string}"
            
            # Try to get from cache first
            # Access the instance cache from the instance self
            cache = getattr(self, "_api_cache", None)
            if cache:
                cached_value = cache.get(cache_key)
                if cached_value is not None:
                    return cached_value
            
            # If not in cache or no cache available, execute function
            result = func(self, *args, **kwargs)
            
            # Store in cache if cache is available
            if cache:
                ttl = ttl_seconds if ttl_seconds is not None else cache.default_ttl
                cache.set(cache_key, result, ttl)
                
            return result
        return wrapper
    return decorator


class SSLIgnoreAdapter(HTTPAdapter):
    """HTTP adapter that ignores SSL verification.

    A custom transport adapter that disables SSL certificate verification for specific domains.

    The adapter overrides the cert_verify method to force verify=False, ensuring SSL verification
    is bypassed regardless of the verify parameter passed to the request. This only affects
    domains where the adapter is explicitly mounted.

    Example:
        session = requests.Session()
        adapter = SSLIgnoreAdapter()
        session.mount('https://example.com', adapter)  # Disable SSL verification for example.com

    Warning:
        Only use this adapter when SSL verification must be disabled for specific use cases.
        Disabling SSL verification reduces security by making the connection vulnerable to
        man-in-the-middle attacks.
    """

    def cert_verify(self, conn: Any, url: str, verify: bool, cert: Any | None) -> None:
        """Override cert verification to disable SSL verification.

        Args:
            conn: The connection
            url: The URL being requested
            verify: The original verify parameter (ignored)
            cert: Client certificate path
        """
        super().cert_verify(conn, url, verify=False, cert=cert)


def configure_ssl_verification(
    service_name: str, url: str, session: Session, ssl_verify: bool
) -> None:
    """Configure SSL verification for a specific service.

    If SSL verification is disabled, this function will configure the session
    to use a custom SSL adapter that bypasses certificate validation for the
    service's domain.

    Args:
        service_name: Name of the service for logging (e.g., "Confluence", "Jira")
        url: The base URL of the service
        session: The requests session to configure
        ssl_verify: Whether SSL verification should be enabled
    """
    if not ssl_verify:
        logger.warning(
            f"SSL verification is disabled for {service_name}. This may be insecure."
        )

        # Get the domain from the configured URL
        domain = urlparse(url).netloc

        # Mount the adapter to handle requests to this domain
        adapter = SSLIgnoreAdapter()
        session.mount(f"https://{domain}", adapter)
        session.mount(f"http://{domain}", adapter)

def paginated_iterator(
    fetch_function: Callable[[int, int], Tuple[List[Any], int]], 
    start_at: int = 0, 
    max_per_page: int = 50, 
    max_total: int = None
) -> Generator[Any, None, None]:
    """
    Create a generator that handles pagination automatically for API results.
    
    Args:
        fetch_function: Function that takes (start_at, max_results) parameters and returns (items, total)
        start_at: Starting index for pagination
        max_per_page: Maximum number of items to fetch per page
        max_total: Maximum total number of items to return (None for all)
        
    Yields:
        Individual items from the paginated results
    """
    total_items_seen = 0
    current_start = start_at
    total_available = None
    
    while True:
        # Check if we've reached the requested maximum
        if max_total is not None and total_items_seen >= max_total:
            break
            
        # Adjust max_results for the final page if needed
        if max_total is not None:
            remaining = max_total - total_items_seen
            current_max = min(max_per_page, remaining)
        else:
            current_max = max_per_page
            
        # Fetch the current page
        items, total_available = fetch_function(current_start, current_max)
        
        # If no items returned or empty response, we're done
        if not items:
            break
            
        # Yield each item
        for item in items:
            yield item
            total_items_seen += 1
            
            # Check again if we've hit the maximum
            if max_total is not None and total_items_seen >= max_total:
                break
                
        # If we've seen all available items, we're done
        if total_available is not None and current_start + len(items) >= total_available:
            break
            
        # Move to the next page
        current_start += len(items)
        
        # If no items were returned but we haven't reached the total,
        # something is wrong - prevent infinite loop
        if len(items) == 0:
            break

def chunked_request(items: List[Any], chunk_size: int = 50) -> Generator[List[Any], None, None]:
    """
    Split a large list into chunks for processing in batches.
    
    Args:
        items: List of items to chunk
        chunk_size: Maximum size of each chunk
        
    Yields:
        Lists of items, each with at most chunk_size items
    """
    for i in range(0, len(items), chunk_size):
        yield items[i:i + chunk_size]

def run_async(func: Callable, *args, **kwargs) -> Any:
    """
    Execute uma função de forma assíncrona em um loop de eventos.
    
    Args:
        func: Função a ser executada
        *args: Argumentos posicionais para a função
        **kwargs: Argumentos nomeados para a função
        
    Returns:
        Resultado da função
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        if asyncio.iscoroutinefunction(func):
            return loop.run_until_complete(func(*args, **kwargs))
        else:
            return loop.run_until_complete(asyncio.to_thread(func, *args, **kwargs))
    finally:
        loop.close()

async def gather_with_concurrency(limit: int, *tasks) -> List[Any]:
    """
    Execute tarefas assíncronas com limite de concorrência.
    
    Args:
        limit: Número máximo de tarefas concorrentes
        *tasks: Tarefas assíncronas (coroutines)
        
    Returns:
        Lista com os resultados das tarefas
    """
    semaphore = asyncio.Semaphore(limit)
    
    async def sem_task(task):
        async with semaphore:
            return await task
    
    return await asyncio.gather(*(sem_task(task) for task in tasks))

def run_parallel(funcs_with_args: List[Tuple[Callable, List, Dict]], max_workers: int = None) -> List[Any]:
    """
    Execute múltiplas funções em paralelo usando ThreadPoolExecutor.
    
    Args:
        funcs_with_args: Lista de tuplas contendo (função, args, kwargs)
        max_workers: Número máximo de workers
        
    Returns:
        Lista com os resultados das funções na mesma ordem
    """
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for func, args, kwargs in funcs_with_args:
            if not args:
                args = []
            if not kwargs:
                kwargs = {}
            futures.append(executor.submit(func, *args, **kwargs))
        
        return [future.result() for future in futures]

def with_timeout(timeout_seconds: int):
    """
    Decorador para adicionar timeout a uma função assíncrona.
    
    Args:
        timeout_seconds: Tempo máximo de execução em segundos
        
    Returns:
        Decorador
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout_seconds)
            except asyncio.TimeoutError:
                logger.warning(f"Função {func.__name__} excedeu o timeout de {timeout_seconds}s")
                raise TimeoutError(f"Operação excedeu o limite de {timeout_seconds} segundos")
        return wrapper
    return decorator

class TextChunker:
    """Utilitário para processamento incremental de grandes blocos de texto."""
    
    def __init__(self, chunk_size: int = 5000, overlap: int = 200):
        """
        Inicializa o chunker de texto.
        
        Args:
            chunk_size: Tamanho máximo de cada chunk em caracteres
            overlap: Sobreposição entre chunks para evitar quebras em entidades
        """
        self.chunk_size = chunk_size
        self.overlap = overlap
    
    def _find_break_point(self, text: str, position: int) -> int:
        """
        Encontra um ponto adequado para quebrar o texto próximo à posição.
        Procura por quebras de linha, parágrafos ou sentenças.
        
        Args:
            text: Texto a ser dividido
            position: Posição aproximada para a quebra
            
        Returns:
            Posição exata para a quebra
        """
        # Preferência 1: quebra de parágrafo
        for i in range(min(200, position), 0, -1):
            check_pos = position - i
            if check_pos >= 0 and text[check_pos:check_pos+2] == '\n\n':
                return check_pos + 2
        
        # Preferência 2: quebra de linha
        for i in range(min(200, position), 0, -1):
            check_pos = position - i
            if check_pos >= 0 and text[check_pos] == '\n':
                return check_pos + 1
        
        # Preferência 3: fim de frase
        for i in range(min(200, position), 0, -1):
            check_pos = position - i
            if check_pos >= 0 and text[check_pos] in '.!?' and (check_pos + 1 >= len(text) or text[check_pos+1] == ' '):
                return check_pos + 1
        
        # Se não encontrou nenhum ponto ideal, retorna a posição original
        return position
    
    def chunk_text(self, text: str) -> list[str]:
        """
        Divide o texto em chunks mantendo estruturas semânticas.
        
        Args:
            text: Texto a ser dividido
            
        Returns:
            Lista de chunks de texto
        """
        if len(text) <= self.chunk_size:
            return [text]
            
        chunks = []
        start = 0
        
        while start < len(text):
            # Determina o final do chunk atual
            end = min(start + self.chunk_size, len(text))
            
            # Encontra um ponto adequado para quebrar o texto
            if end < len(text):
                end = self._find_break_point(text, end)
            
            # Adiciona o chunk atual
            chunks.append(text[start:end])
            
            # Atualiza a posição de início para o próximo chunk
            # Subtrai a sobreposição para manter contexto entre chunks
            start = end - min(self.overlap, end - start)
            
            # Evita loops infinitos
            if start >= end:
                start = end
        
        return chunks
    
    def process_text_in_chunks(self, text: str, processor: callable) -> str:
        """
        Processa texto em chunks e recombina o resultado.
        
        Args:
            text: Texto a ser processado
            processor: Função que processa cada chunk
            
        Returns:
            Texto processado combinado
        """
        # Para textos pequenos, processa diretamente
        if len(text) <= self.chunk_size:
            return processor(text)
            
        # Divide em chunks
        chunks = self.chunk_text(text)
        
        # Processa cada chunk
        processed_chunks = []
        for chunk in chunks:
            processed_chunks.append(processor(chunk))
            
        # Combina os resultados
        return ''.join(processed_chunks)


class HTMLProcessor:
    """Utilitário para processamento eficiente de conteúdo HTML."""
    
    @staticmethod
    def strip_tags(html: str) -> str:
        """
        Remove todas as tags HTML mantendo o texto.
        Mais eficiente que usar BeautifulSoup para grandes blocos de texto.
        
        Args:
            html: HTML para limpar
            
        Returns:
            Texto sem tags HTML
        """
        # Padrão para detectar tags HTML
        tag_pattern = re.compile(r'<[^>]*>')
        return tag_pattern.sub('', html)
    
    @staticmethod
    def extract_text_from_html(html: str) -> str:
        """
        Extrai texto de HTML preservando quebras de linha para parágrafos, listas, etc.
        
        Args:
            html: HTML para processar
            
        Returns:
            Texto extraído com quebras de linha semânticas
        """
        # Substitui tags de bloco por quebras de linha
        block_tags = re.compile(r'</(p|div|h\d|ul|ol|li|blockquote|pre)[^>]*>', re.IGNORECASE)
        html = block_tags.sub('\n', html)
        
        # Remove todas as outras tags
        html = HTMLProcessor.strip_tags(html)
        
        # Limpa quebras de linha múltiplas
        html = re.sub(r'\n\s*\n', '\n\n', html)
        
        # Decodifica entidades HTML comuns
        html = html.replace('&nbsp;', ' ')
        html = html.replace('&lt;', '<')
        html = html.replace('&gt;', '>')
        html = html.replace('&amp;', '&')
        html = html.replace('&quot;', '"')
        html = html.replace('&#39;', "'")
        
        return html.strip()
    
    @staticmethod
    def generate_excerpt(html: str, max_length: int = 200) -> str:
        """
        Gera um resumo do conteúdo HTML.
        
        Args:
            html: HTML para processar
            max_length: Tamanho máximo do resumo
            
        Returns:
            Resumo do texto
        """
        text = HTMLProcessor.extract_text_from_html(html)
        
        # Trunca no tamanho máximo, tentando preservar palavras completas
        if len(text) <= max_length:
            return text
            
        # Trunca na última palavra completa
        truncated = text[:max_length]
        last_space = truncated.rfind(' ')
        
        if last_space > max_length * 0.7:  # Só trunca em espaço se estiver a pelo menos 70% do tamanho desejado
            truncated = truncated[:last_space]
            
        return truncated + '...'


class MarkdownOptimizer:
    """Utilitário para otimizar operações com Markdown."""
    
    # Cache para conversões frequentes
    _md_to_html_cache = {}
    _html_to_md_cache = {}
    
    @staticmethod
    def optimize_markdown_tables(markdown: str) -> str:
        """
        Otimiza tabelas em Markdown ajustando alinhamento.
        
        Args:
            markdown: Texto em Markdown
            
        Returns:
            Markdown com tabelas otimizadas
        """
        # Identifica linhas de tabela
        lines = markdown.split('\n')
        in_table = False
        table_start = 0
        tables = []
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Detecta início de tabela
            if not in_table and stripped.startswith('|') and stripped.endswith('|'):
                in_table = True
                table_start = i
            
            # Detecta fim de tabela
            elif in_table and (not stripped.startswith('|') or not stripped.endswith('|')):
                in_table = False
                tables.append((table_start, i - 1))
        
        # Finaliza a última tabela se estiver no final do texto
        if in_table:
            tables.append((table_start, len(lines) - 1))
        
        # Processa cada tabela
        for start, end in tables:
            if end - start < 2:  # Tabela precisa ter pelo menos header e separador
                continue
                
            table_lines = lines[start:end+1]
            
            # Processa apenas se tiver linha de separação com hífens
            if not re.match(r'\s*\|(\s*[-:]+\s*\|)+\s*$', table_lines[1]):
                continue
                
            # Otimiza cada tabela
            optimized_table = MarkdownOptimizer._optimize_table_format(table_lines)
            
            # Substitui a tabela original pela otimizada
            lines[start:end+1] = optimized_table
        
        return '\n'.join(lines)
    
    @staticmethod
    def _optimize_table_format(table_lines: list[str]) -> list[str]:
        """
        Otimiza o formato de uma única tabela Markdown.
        
        Args:
            table_lines: Linhas da tabela
            
        Returns:
            Linhas da tabela otimizada
        """
        # Divide as células
        cells = []
        for line in table_lines:
            # Remove o primeiro e último pipe e divide
            parts = [cell.strip() for cell in line.strip()[1:-1].split('|')]
            cells.append(parts)
        
        # Determina o tamanho máximo de cada coluna
        col_sizes = []
        for row in cells:
            for i, cell in enumerate(row):
                if i >= len(col_sizes):
                    col_sizes.append(len(cell))
                else:
                    col_sizes[i] = max(col_sizes[i], len(cell))
        
        # Reconstrói a tabela com tamanhos de coluna uniformes
        result = []
        for i, row in enumerate(cells):
            line_parts = []
            
            # Para cada célula na linha
            for j, cell in enumerate(row):
                # Cabeçalho de separação
                if i == 1:
                    # Preserva alinhamento
                    if cell.startswith(':') and cell.endswith(':'):
                        formatted = ':' + '-' * (col_sizes[j] - 2) + ':'
                    elif cell.startswith(':'):
                        formatted = ':' + '-' * (col_sizes[j] - 1)
                    elif cell.endswith(':'):
                        formatted = '-' * (col_sizes[j] - 1) + ':'
                    else:
                        formatted = '-' * col_sizes[j]
                else:
                    # Usa o tamanho da coluna para padding
                    formatted = cell.ljust(col_sizes[j])
                
                line_parts.append(formatted)
            
            result.append('| ' + ' | '.join(line_parts) + ' |')
        
        return result
        
    @staticmethod
    def remove_empty_markdown_links(markdown: str) -> str:
        """
        Remove links vazios ou quebrados do Markdown.
        
        Args:
            markdown: Texto em Markdown
            
        Returns:
            Markdown sem links vazios
        """
        # Remove links com URLs vazias
        markdown = re.sub(r'\[([^\]]*)\]\(\s*\)', r'\1', markdown)
        
        # Remove links com texto e URL idênticos (redundantes)
        markdown = re.sub(r'\[([^\]]+)\]\(\1\)', r'\1', markdown)
        
        return markdown
