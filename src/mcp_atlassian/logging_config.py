"""Configuração avançada de logging para o MCP Atlassian."""

import logging
import os
import sys
import threading
import time
import uuid
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, Optional, TypeVar, cast

# Type for callable return value
T = TypeVar('T')

# Configuração padrão do logger
DEFAULT_FORMAT = "%(asctime)s [%(levelname)s] [%(name)s] [%(context)s] %(message)s"
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_DIRECTORY = "logs"
MAX_LOG_SIZE = 10 * 1024 * 1024  # 10 MB
LOG_BACKUP_COUNT = 5


class ContextualLogger(logging.Logger):
    """Logger que mantém contexto entre operações relacionadas."""
    
    def __init__(self, name: str, level: int = 0):
        """Inicializa o logger contextual."""
        super().__init__(name, level)
        self._context_data = threading.local()
    
    def _get_context_str(self) -> str:
        """Obtém a string de contexto atual."""
        context_data = getattr(self._context_data, "data", {})
        if not context_data:
            return "no-context"
            
        # Formata contexto como: operation=X,trace_id=Y,...
        return ",".join(f"{k}={v}" for k, v in context_data.items())
    
    def _log(self, level, msg, args, exc_info=None, extra=None, stack_info=False, stacklevel=1):
        """Sobrescreve método _log para incluir contexto."""
        if extra is None:
            extra = {}
            
        # Adiciona informações de contexto
        if "context" not in extra:
            extra["context"] = self._get_context_str()
            
        # Passa para implementação original
        super()._log(level, msg, args, exc_info, extra, stack_info, stacklevel + 1)
    
    def set_context(self, **kwargs) -> None:
        """
        Define valores de contexto para o logger.
        
        Args:
            **kwargs: Pares chave-valor para adicionar ao contexto
        """
        if not hasattr(self._context_data, "data"):
            self._context_data.data = {}
            
        # Atualiza contexto
        self._context_data.data.update(kwargs)
    
    def clear_context(self) -> None:
        """Remove todos os dados de contexto do logger."""
        if hasattr(self._context_data, "data"):
            self._context_data.data = {}
    
    def with_context(self, **context):
        """
        Retorna um decorador que executa uma função com contexto específico.
        
        Args:
            **context: Dados de contexto para a função
            
        Returns:
            Decorador configurado
        """
        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            @wraps(func)
            def wrapper(*args, **kwargs) -> T:
                # Salva contexto atual
                old_context = getattr(self._context_data, "data", {}).copy()
                
                # Define novo contexto
                self.set_context(**context)
                
                # Adiciona trace_id se não existir
                if "trace_id" not in getattr(self._context_data, "data", {}):
                    self.set_context(trace_id=str(uuid.uuid4())[:8])
                
                try:
                    return func(*args, **kwargs)
                finally:
                    # Restaura contexto anterior
                    self._context_data.data = old_context
            return wrapper
        return decorator


class LoggingContextManager:
    """Gerenciador de contexto para logging com rastreamento."""
    
    def __init__(self, logger: ContextualLogger, operation: str, **context):
        """
        Inicializa o gerenciador de contexto de logging.
        
        Args:
            logger: O logger contextual a ser usado
            operation: Nome da operação sendo executada
            **context: Dados adicionais de contexto
        """
        self.logger = logger
        self.operation = operation
        self.context = context
        self.start_time = 0.0
        self.trace_id = context.get("trace_id", str(uuid.uuid4())[:8])
        
    def __enter__(self):
        """Inicia o contexto de logging."""
        # Salva contexto atual
        old_context = getattr(self.logger._context_data, "data", {}).copy()
        self._old_context = old_context
        
        # Define contexto para esta operação
        context = {
            "operation": self.operation,
            "trace_id": self.trace_id,
            **self.context
        }
        self.logger.set_context(**context)
        
        # Registra início da operação
        self.start_time = time.time()
        self.logger.debug(f"Iniciando operação: {self.operation}")
        
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Finaliza o contexto de logging."""
        # Calcula duração
        duration = time.time() - self.start_time
        
        # Registra fim da operação
        if exc_type:
            self.logger.error(
                f"Operação falhou: {self.operation} após {duration:.3f}s - {exc_val}"
            )
        else:
            self.logger.debug(
                f"Operação concluída: {self.operation} em {duration:.3f}s"
            )
            
        # Restaura contexto anterior
        self.logger._context_data.data = self._old_context


def setup_logger(
    name: str = "mcp-atlassian",
    level: str = None,
    log_to_file: bool = True,
    log_dir: str = None,
    log_format: str = None
) -> ContextualLogger:
    """
    Configura e retorna um logger contextual.
    
    Args:
        name: Nome do logger
        level: Nível de log (DEBUG, INFO, etc.)
        log_to_file: Se True, registra logs em arquivo
        log_dir: Diretório para armazenar arquivos de log
        log_format: Formato do log
        
    Returns:
        Logger contextual configurado
    """
    # Substitui o factory padrão para usar o ContextualLogger
    logging.setLoggerClass(ContextualLogger)
    
    # Cria/obtém o logger
    logger = logging.getLogger(name)
    
    # Define nível de log
    log_level = level or os.getenv("LOG_LEVEL", DEFAULT_LOG_LEVEL)
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # Define formato
    formatter = logging.Formatter(
        log_format or os.getenv("LOG_FORMAT", DEFAULT_FORMAT)
    )
    
    # Handler para console
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Handler para arquivo se necessário
    if log_to_file:
        log_directory = log_dir or os.getenv("LOG_DIR", DEFAULT_LOG_DIRECTORY)
        
        # Garante que o diretório existe
        Path(log_directory).mkdir(parents=True, exist_ok=True)
        
        # Cria handler com rotação de arquivos
        from logging.handlers import RotatingFileHandler
        
        log_file = Path(log_directory) / f"{name}.log"
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=MAX_LOG_SIZE,
            backupCount=LOG_BACKUP_COUNT
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    # Evita propagação para o logger root
    logger.propagate = False
    
    return cast(ContextualLogger, logger)


def log_operation(logger: ContextualLogger, operation: str, **context):
    """
    Cria um gerenciador de contexto para logging de operação.
    
    Args:
        logger: Logger contextual
        operation: Nome da operação
        **context: Dados adicionais de contexto
        
    Returns:
        Gerenciador de contexto configurado
    """
    return LoggingContextManager(logger, operation, **context)


def log_function(operation: str = None, **context):
    """
    Decorador para logging automático de função.
    
    Args:
        operation: Nome da operação (padrão: nome da função)
        **context: Dados adicionais de contexto
        
    Returns:
        Decorador configurado
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        op_name = operation or func.__name__
        
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            # Obtém o logger apropriado
            logger_name = func.__module__
            logger = logging.getLogger(logger_name)
            
            # Usa logger contextual se disponível, caso contrário usa logger normal
            if isinstance(logger, ContextualLogger):
                ctx_logger = cast(ContextualLogger, logger)
                with log_operation(ctx_logger, op_name, **context):
                    return func(*args, **kwargs)
            else:
                # Fallback para logger padrão
                logger.debug(f"Iniciando: {op_name}")
                start_time = time.time()
                try:
                    result = func(*args, **kwargs)
                    logger.debug(f"Concluído: {op_name} em {time.time() - start_time:.3f}s")
                    return result
                except Exception as e:
                    logger.error(f"Falha: {op_name} - {str(e)}")
                    raise
                    
        return wrapper
    return decorator 