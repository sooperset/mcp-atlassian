"""Módulo de métricas para monitoramento de desempenho."""

import logging
import time
import threading
import functools
import os
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar, Union, cast
import json
import weakref
from contextlib import contextmanager

# Type for callable return values
T = TypeVar('T')

logger = logging.getLogger("mcp-atlassian")


class Metrics:
    """
    Sistema de coleta e análise de métricas de desempenho.
    
    Fornece funcionalidades para:
    - Medir tempo de execução de operações
    - Rastrear uso de memória
    - Monitorar taxas de acerto/erro de cache
    - Acompanhar tempos de resposta de APIs externas
    """
    
    _instance = None
    _lock = threading.RLock()
    
    def __new__(cls, *args, **kwargs):
        """Implementa padrão Singleton para as métricas."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance
    
    def __init__(self):
        """Inicializa o sistema de métricas."""
        # Evita reinicialização do singleton
        if hasattr(self, '_initialized') and self._initialized:
            return
            
        self._initialized = True
        
        # Armazenamento de métricas por categoria
        self.api_response_times: Dict[str, List[float]] = {}
        self.operation_durations: Dict[str, List[float]] = {}
        self.cache_metrics: Dict[str, Dict[str, int]] = {
            'hits': {},
            'misses': {},
            'errors': {}
        }
        self.memory_samples: List[Tuple[datetime, float]] = []
        
        # Configurações
        self.max_samples = 1000  # Máximo de amostras para cada métrica
        self.enabled = True  # Flag para ativar/desativar coleta
        self.sampling_interval = 60  # Intervalo de amostragem em segundos
        
        # Inicia thread de amostragem em background
        self._start_background_sampling()
    
    def _start_background_sampling(self):
        """Inicia thread de amostragem em background."""
        self._stop_sampling = False
        self._sampling_thread = threading.Thread(
            target=self._background_sampling,
            daemon=True,
            name="metrics_sampling"
        )
        self._sampling_thread.start()
    
    def _background_sampling(self):
        """Executa amostragem periódica em background."""
        while not self._stop_sampling:
            if self.enabled:
                try:
                    # Coleta uso de memória
                    self.sample_memory_usage()
                    
                    # Limpa métricas antigas se necessário
                    self._prune_old_metrics()
                except Exception as e:
                    logger.warning(f"Erro na coleta de métricas em background: {str(e)}")
            
            # Aguarda próximo ciclo
            time.sleep(self.sampling_interval)
    
    def _prune_old_metrics(self):
        """Remove métricas antigas para controlar uso de memória."""
        # Limita o número de amostras de tempo de resposta
        for api, times in self.api_response_times.items():
            if len(times) > self.max_samples:
                self.api_response_times[api] = times[-self.max_samples:]
        
        # Limita o número de amostras de duração de operações
        for op, durations in self.operation_durations.items():
            if len(durations) > self.max_samples:
                self.operation_durations[op] = durations[-self.max_samples:]
        
        # Limita o número de amostras de uso de memória
        if len(self.memory_samples) > self.max_samples:
            self.memory_samples = self.memory_samples[-self.max_samples:]
    
    def sample_memory_usage(self):
        """Coleta amostra do uso atual de memória."""
        try:
            # Obtém uso de memória do processo atual
            import psutil
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / (1024 * 1024)  # Converte para MB
            
            self.memory_samples.append((datetime.now(), memory_mb))
        except ImportError:
            # Fallback se psutil não estiver disponível
            logger.debug("psutil não disponível para métricas de memória")
        except Exception as e:
            logger.warning(f"Erro ao coletar uso de memória: {str(e)}")
    
    def record_api_call(self, api_name: str, response_time: float, success: bool = True):
        """
        Registra tempo de resposta de uma chamada de API.
        
        Args:
            api_name: Nome da API chamada
            response_time: Tempo de resposta em segundos
            success: Indica se a chamada foi bem-sucedida
        """
        if not self.enabled:
            return
            
        with self._lock:
            # Inicializa lista se necessário
            if api_name not in self.api_response_times:
                self.api_response_times[api_name] = []
            
            # Registra tempo de resposta
            self.api_response_times[api_name].append(response_time)
            
            # Limita o tamanho da lista
            if len(self.api_response_times[api_name]) > self.max_samples:
                self.api_response_times[api_name] = self.api_response_times[api_name][-self.max_samples:]
    
    def record_operation(self, operation_name: str, duration: float):
        """
        Registra duração de uma operação.
        
        Args:
            operation_name: Nome da operação
            duration: Duração em segundos
        """
        if not self.enabled:
            return
            
        with self._lock:
            # Inicializa lista se necessário
            if operation_name not in self.operation_durations:
                self.operation_durations[operation_name] = []
            
            # Registra duração
            self.operation_durations[operation_name].append(duration)
            
            # Limita o tamanho da lista
            if len(self.operation_durations[operation_name]) > self.max_samples:
                self.operation_durations[operation_name] = self.operation_durations[operation_name][-self.max_samples:]
    
    def record_cache_hit(self, cache_name: str):
        """
        Registra acerto de cache.
        
        Args:
            cache_name: Nome do cache
        """
        if not self.enabled:
            return
            
        with self._lock:
            if cache_name not in self.cache_metrics['hits']:
                self.cache_metrics['hits'][cache_name] = 0
            self.cache_metrics['hits'][cache_name] += 1
    
    def record_cache_miss(self, cache_name: str):
        """
        Registra erro de cache.
        
        Args:
            cache_name: Nome do cache
        """
        if not self.enabled:
            return
            
        with self._lock:
            if cache_name not in self.cache_metrics['misses']:
                self.cache_metrics['misses'][cache_name] = 0
            self.cache_metrics['misses'][cache_name] += 1
    
    def record_cache_error(self, cache_name: str):
        """
        Registra erro ao acessar cache.
        
        Args:
            cache_name: Nome do cache
        """
        if not self.enabled:
            return
            
        with self._lock:
            if cache_name not in self.cache_metrics['errors']:
                self.cache_metrics['errors'][cache_name] = 0
            self.cache_metrics['errors'][cache_name] += 1
    
    def get_api_response_stats(self, api_name: Optional[str] = None) -> Dict[str, Dict[str, float]]:
        """
        Obtém estatísticas de tempo de resposta de APIs.
        
        Args:
            api_name: Nome específico da API ou None para todas
            
        Returns:
            Dicionário com estatísticas
        """
        with self._lock:
            result = {}
            
            if api_name:
                # Estatísticas para uma API específica
                if api_name in self.api_response_times and self.api_response_times[api_name]:
                    times = self.api_response_times[api_name]
                    result[api_name] = {
                        'avg': sum(times) / len(times),
                        'min': min(times),
                        'max': max(times),
                        'count': len(times),
                        'p90': sorted(times)[int(len(times) * 0.9)] if len(times) >= 10 else sum(times) / len(times)
                    }
            else:
                # Estatísticas para todas as APIs
                for name, times in self.api_response_times.items():
                    if times:
                        result[name] = {
                            'avg': sum(times) / len(times),
                            'min': min(times),
                            'max': max(times),
                            'count': len(times),
                            'p90': sorted(times)[int(len(times) * 0.9)] if len(times) >= 10 else sum(times) / len(times)
                        }
            
            return result
    
    def get_operation_stats(self, operation_name: Optional[str] = None) -> Dict[str, Dict[str, float]]:
        """
        Obtém estatísticas de duração de operações.
        
        Args:
            operation_name: Nome específico da operação ou None para todas
            
        Returns:
            Dicionário com estatísticas
        """
        with self._lock:
            result = {}
            
            if operation_name:
                # Estatísticas para uma operação específica
                if operation_name in self.operation_durations and self.operation_durations[operation_name]:
                    durations = self.operation_durations[operation_name]
                    result[operation_name] = {
                        'avg': sum(durations) / len(durations),
                        'min': min(durations),
                        'max': max(durations),
                        'count': len(durations),
                        'p90': sorted(durations)[int(len(durations) * 0.9)] if len(durations) >= 10 else sum(durations) / len(durations)
                    }
            else:
                # Estatísticas para todas as operações
                for name, durations in self.operation_durations.items():
                    if durations:
                        result[name] = {
                            'avg': sum(durations) / len(durations),
                            'min': min(durations),
                            'max': max(durations),
                            'count': len(durations),
                            'p90': sorted(durations)[int(len(durations) * 0.9)] if len(durations) >= 10 else sum(durations) / len(durations)
                        }
            
            return result
    
    def get_cache_stats(self, cache_name: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """
        Obtém estatísticas de uso de cache.
        
        Args:
            cache_name: Nome específico do cache ou None para todos
            
        Returns:
            Dicionário com estatísticas
        """
        with self._lock:
            result = {}
            
            if cache_name:
                # Estatísticas para um cache específico
                hits = self.cache_metrics['hits'].get(cache_name, 0)
                misses = self.cache_metrics['misses'].get(cache_name, 0)
                errors = self.cache_metrics['errors'].get(cache_name, 0)
                
                total = hits + misses
                hit_rate = (hits / total) * 100 if total > 0 else 0
                
                result[cache_name] = {
                    'hits': hits,
                    'misses': misses,
                    'errors': errors,
                    'hit_rate': hit_rate,
                    'total': total
                }
            else:
                # Estatísticas para todos os caches
                all_cache_names = set()
                all_cache_names.update(self.cache_metrics['hits'].keys())
                all_cache_names.update(self.cache_metrics['misses'].keys())
                all_cache_names.update(self.cache_metrics['errors'].keys())
                
                for name in all_cache_names:
                    hits = self.cache_metrics['hits'].get(name, 0)
                    misses = self.cache_metrics['misses'].get(name, 0)
                    errors = self.cache_metrics['errors'].get(name, 0)
                    
                    total = hits + misses
                    hit_rate = (hits / total) * 100 if total > 0 else 0
                    
                    result[name] = {
                        'hits': hits,
                        'misses': misses,
                        'errors': errors,
                        'hit_rate': hit_rate,
                        'total': total
                    }
            
            return result
    
    def get_memory_usage_stats(self) -> Dict[str, Any]:
        """
        Obtém estatísticas de uso de memória.
        
        Returns:
            Dicionário com estatísticas
        """
        with self._lock:
            if not self.memory_samples:
                return {'avg': 0, 'min': 0, 'max': 0, 'current': 0, 'samples': 0}
            
            memory_values = [sample[1] for sample in self.memory_samples]
            current = memory_values[-1] if memory_values else 0
            
            return {
                'avg': sum(memory_values) / len(memory_values),
                'min': min(memory_values),
                'max': max(memory_values),
                'current': current,
                'samples': len(memory_values)
            }
    
    def get_all_metrics(self) -> Dict[str, Any]:
        """
        Obtém todas as métricas coletadas.
        
        Returns:
            Dicionário com todas as métricas
        """
        return {
            'api_response': self.get_api_response_stats(),
            'operations': self.get_operation_stats(),
            'cache': self.get_cache_stats(),
            'memory': self.get_memory_usage_stats(),
            'timestamp': datetime.now().isoformat(),
            'uptime_seconds': (datetime.now() - self.memory_samples[0][0]).total_seconds() if self.memory_samples else 0
        }
    
    def reset(self):
        """Limpa todas as métricas coletadas."""
        with self._lock:
            self.api_response_times = {}
            self.operation_durations = {}
            self.cache_metrics = {'hits': {}, 'misses': {}, 'errors': {}}
            self.memory_samples = []
    
    def export_metrics(self, file_path: Optional[str] = None) -> str:
        """
        Exporta métricas para JSON.
        
        Args:
            file_path: Caminho para salvar o arquivo JSON (opcional)
            
        Returns:
            String JSON com as métricas
        """
        metrics_data = self.get_all_metrics()
        json_data = json.dumps(metrics_data, indent=2)
        
        if file_path:
            try:
                with open(file_path, 'w') as f:
                    f.write(json_data)
                logger.info(f"Métricas exportadas para {file_path}")
            except Exception as e:
                logger.error(f"Erro ao exportar métricas: {str(e)}")
        
        return json_data
    
    def stop(self):
        """Interrompe coleta de métricas em background."""
        self._stop_sampling = True
        if hasattr(self, '_sampling_thread') and self._sampling_thread.is_alive():
            self._sampling_thread.join(timeout=1.0)


# Decoradores e gerenciadores de contexto para métricas

def timed_operation(operation_name: str):
    """
    Decorador para medir tempo de execução de funções.
    
    Args:
        operation_name: Nome da operação para registrar
        
    Returns:
        Decorador configurado
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            metrics = Metrics()
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                metrics.record_operation(operation_name, duration)
        return wrapper
    return decorator


def timed_api_call(api_name: str):
    """
    Decorador para medir tempo de chamadas de API.
    
    Args:
        api_name: Nome da API para registrar
        
    Returns:
        Decorador configurado
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            metrics = Metrics()
            start_time = time.time()
            success = False
            try:
                result = func(*args, **kwargs)
                success = True
                return result
            finally:
                duration = time.time() - start_time
                metrics.record_api_call(api_name, duration, success)
        return wrapper
    return decorator


@contextmanager
def measure_operation(operation_name: str):
    """
    Gerenciador de contexto para medir tempo de um bloco de código.
    
    Args:
        operation_name: Nome da operação para registrar
    """
    metrics = Metrics()
    start_time = time.time()
    try:
        yield
    finally:
        duration = time.time() - start_time
        metrics.record_operation(operation_name, duration)


@contextmanager
def measure_api_call(api_name: str):
    """
    Gerenciador de contexto para medir tempo de chamada de API.
    
    Args:
        api_name: Nome da API para registrar
    """
    metrics = Metrics()
    start_time = time.time()
    success = False
    try:
        yield
        success = True
    finally:
        duration = time.time() - start_time
        metrics.record_api_call(api_name, duration, success) 