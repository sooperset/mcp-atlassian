"""Metrics module for performance monitoring."""

import functools
import json
import logging
import os
import threading
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, TypeVar

# Type for callable return values
T = TypeVar("T")

logger = logging.getLogger("mcp-atlassian")


class Metrics:
    """
    Performance metrics collection and analysis system.

    Provides functionalities to:
    - Measure operation execution times
    - Track memory usage
    - Monitor cache hit/miss rates
    - Track external API response times
    """

    _instance = None
    _lock = threading.RLock()

    def __new__(cls, *args: Any, **kwargs: Any) -> "Metrics":
        """Implements Singleton pattern for metrics."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance

    def __init__(self) -> None:
        """Initializes the metrics system."""
        # Avoids re-initialization of the singleton
        if hasattr(self, "_initialized") and self._initialized:
            return

        self._initialized = True

        # Storage for metrics by category
        self.api_response_times: dict[str, list[float]] = {}
        self.operation_durations: dict[str, list[float]] = {}
        self.cache_metrics: dict[str, dict[str, int]] = {
            "hits": {},
            "misses": {},
            "errors": {},
        }
        self.memory_samples: list[tuple[datetime, float]] = []

        # Configurations
        self.max_samples = 1000  # Maximum samples for each metric
        self.enabled = True  # Flag to enable/disable collection
        self.sampling_interval = 60  # Sampling interval in seconds

        # Starts background sampling thread
        self._start_background_sampling()

    def _start_background_sampling(self) -> None:
        """Starts background sampling thread."""
        self._stop_sampling = False
        self._sampling_thread = threading.Thread(
            target=self._background_sampling, daemon=True, name="metrics_sampling"
        )
        self._sampling_thread.start()

    def _background_sampling(self) -> None:
        """Executes periodic background sampling."""
        while not self._stop_sampling:
            if self.enabled:
                try:
                    # Collects memory usage
                    self.sample_memory_usage()

                    # Prunes old metrics if necessary
                    self._prune_old_metrics()
                except Exception as e:
                    logger.warning(f"Error in background metrics collection: {str(e)}")

            # Waits for next cycle
            time.sleep(self.sampling_interval)

    def _prune_old_metrics(self) -> None:
        """Removes old metrics to control memory usage."""
        # Limits the number of response time samples
        for api, times in self.api_response_times.items():
            if len(times) > self.max_samples:
                self.api_response_times[api] = times[-self.max_samples :]

        # Limits the number of operation duration samples
        for op, durations in self.operation_durations.items():
            if len(durations) > self.max_samples:
                self.operation_durations[op] = durations[-self.max_samples :]

        # Limits the number of memory samples
        if len(self.memory_samples) > self.max_samples:
            self.memory_samples = self.memory_samples[-self.max_samples :]

    def sample_memory_usage(self) -> None:
        """Collects current memory usage sample."""
        try:
            # Tries to use psutil (if available)
            import psutil

            # Gets current process
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / (1024 * 1024)  # Converts to MB

            self.memory_samples.append((datetime.now(timezone.utc), memory_mb))
        except ImportError:
            # Fallback if psutil is not available
            used = "N/A"
            self.memory_samples.append((datetime.now(timezone.utc), -1))
        except Exception as e:
            logger.warning(f"Error collecting memory usage: {str(e)}")

    def record_api_call(
        self, api_name: str, response_time: float, success: bool = True
    ) -> None:
        """
        Records API response time.

        Args:
            api_name: Name of the API called
            response_time: Response time in seconds
            success: Indicates if the call was successful
        """
        if not self.enabled:
            return

        with self._lock:
            # Initializes list if necessary
            if api_name not in self.api_response_times:
                self.api_response_times[api_name] = []

            # Records response time
            self.api_response_times[api_name].append(response_time)

            # Limits list size
            if len(self.api_response_times[api_name]) > self.max_samples:
                self.api_response_times[api_name] = self.api_response_times[api_name][
                    -self.max_samples :
                ]

    def record_operation(self, operation_name: str, duration: float) -> None:
        """
        Records operation duration.

        Args:
            operation_name: Name of the operation
            duration: Duration in seconds
        """
        if not self.enabled:
            return

        with self._lock:
            # Initializes list if necessary
            if operation_name not in self.operation_durations:
                self.operation_durations[operation_name] = []

            # Records duration
            self.operation_durations[operation_name].append(duration)

            # Limits list size
            if len(self.operation_durations[operation_name]) > self.max_samples:
                self.operation_durations[operation_name] = self.operation_durations[
                    operation_name
                ][-self.max_samples :]

    def record_cache_hit(self, cache_name: str) -> None:
        """
        Records cache hit.

        Args:
            cache_name: Name of the cache
        """
        if not self.enabled:
            return

        with self._lock:
            if cache_name not in self.cache_metrics["hits"]:
                self.cache_metrics["hits"][cache_name] = 0
            self.cache_metrics["hits"][cache_name] += 1

    def record_cache_miss(self, cache_name: str) -> None:
        """
        Records cache miss.

        Args:
            cache_name: Name of the cache
        """
        if not self.enabled:
            return

        with self._lock:
            if cache_name not in self.cache_metrics["misses"]:
                self.cache_metrics["misses"][cache_name] = 0
            self.cache_metrics["misses"][cache_name] += 1

    def record_cache_error(self, cache_name: str) -> None:
        """
        Records cache access error.

        Args:
            cache_name: Name of the cache
        """
        if not self.enabled:
            return

        with self._lock:
            if cache_name not in self.cache_metrics["errors"]:
                self.cache_metrics["errors"][cache_name] = 0
            self.cache_metrics["errors"][cache_name] += 1

    def get_api_response_stats(
        self, api_name: str | None = None
    ) -> dict[str, dict[str, float]]:
        """
        Gets API response time statistics.

        Args:
            api_name: Specific API name or None for all

        Returns:
            Dictionary with statistics
        """
        with self._lock:
            result = {}

            if api_name:
                # Statistics for a specific API
                if (
                    api_name in self.api_response_times
                    and self.api_response_times[api_name]
                ):
                    times = self.api_response_times[api_name]
                    result[api_name] = {
                        "avg": sum(times) / len(times),
                        "min": min(times),
                        "max": max(times),
                        "count": len(times),
                        "p90": sorted(times)[int(len(times) * 0.9)]
                        if len(times) >= 10
                        else sum(times) / len(times),
                    }
            else:
                # Statistics for all APIs
                for name, times in self.api_response_times.items():
                    if times:
                        result[name] = {
                            "avg": sum(times) / len(times),
                            "min": min(times),
                            "max": max(times),
                            "count": len(times),
                            "p90": sorted(times)[int(len(times) * 0.9)]
                            if len(times) >= 10
                            else sum(times) / len(times),
                        }

            return result

    def get_operation_stats(
        self, operation_name: str | None = None
    ) -> dict[str, dict[str, float]]:
        """
        Gets operation duration statistics.

        Args:
            operation_name: Specific operation name or None for all

        Returns:
            Dictionary with statistics
        """
        with self._lock:
            result = {}

            if operation_name:
                # Statistics for a specific operation
                if (
                    operation_name in self.operation_durations
                    and self.operation_durations[operation_name]
                ):
                    durations = self.operation_durations[operation_name]
                    result[operation_name] = {
                        "avg": sum(durations) / len(durations),
                        "min": min(durations),
                        "max": max(durations),
                        "count": len(durations),
                        "p90": sorted(durations)[int(len(durations) * 0.9)]
                        if len(durations) >= 10
                        else sum(durations) / len(durations),
                    }
            else:
                # Statistics for all operations
                for name, durations in self.operation_durations.items():
                    if durations:
                        result[name] = {
                            "avg": sum(durations) / len(durations),
                            "min": min(durations),
                            "max": max(durations),
                            "count": len(durations),
                            "p90": sorted(durations)[int(len(durations) * 0.9)]
                            if len(durations) >= 10
                            else sum(durations) / len(durations),
                        }

            return result

    def get_cache_stats(
        self, cache_name: str | None = None
    ) -> dict[str, dict[str, Any]]:
        """
        Gets cache usage statistics.

        Args:
            cache_name: Specific cache name or None for all

        Returns:
            Dictionary with statistics
        """
        with self._lock:
            result = {}

            if cache_name:
                # Statistics for a specific cache
                hits = self.cache_metrics["hits"].get(cache_name, 0)
                misses = self.cache_metrics["misses"].get(cache_name, 0)
                errors = self.cache_metrics["errors"].get(cache_name, 0)

                total = hits + misses
                hit_rate = (hits / total) * 100 if total > 0 else 0

                result[cache_name] = {
                    "hits": hits,
                    "misses": misses,
                    "errors": errors,
                    "hit_rate": hit_rate,
                    "total": total,
                }
            else:
                # Statistics for all caches
                all_cache_names = set()
                all_cache_names.update(self.cache_metrics["hits"].keys())
                all_cache_names.update(self.cache_metrics["misses"].keys())
                all_cache_names.update(self.cache_metrics["errors"].keys())

                for name in all_cache_names:
                    hits = self.cache_metrics["hits"].get(name, 0)
                    misses = self.cache_metrics["misses"].get(name, 0)
                    errors = self.cache_metrics["errors"].get(name, 0)

                    total = hits + misses
                    hit_rate = (hits / total) * 100 if total > 0 else 0

                    result[name] = {
                        "hits": hits,
                        "misses": misses,
                        "errors": errors,
                        "hit_rate": hit_rate,
                        "total": total,
                    }

            return result

    def get_memory_usage_stats(self) -> dict[str, Any]:
        """
        Gets memory usage statistics.

        Returns:
            Dictionary with statistics
        """
        with self._lock:
            if not self.memory_samples:
                return {"avg": 0, "min": 0, "max": 0, "current": 0, "samples": 0}

            memory_values = [sample[1] for sample in self.memory_samples]
            current = memory_values[-1] if memory_values else 0

            return {
                "avg": sum(memory_values) / len(memory_values),
                "min": min(memory_values),
                "max": max(memory_values),
                "current": current,
                "samples": len(memory_values),
            }

    def get_all_metrics(self) -> dict[str, Any]:
        """
        Gets all collected metrics.

        Returns:
            Dict with all metrics
        """
        with self._lock:
            return {
                "api": self.get_api_response_stats(),
                "operations": self.get_operation_stats(),
                "cache": self.get_cache_stats(),
                "memory": self.get_memory_usage_stats(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "uptime_seconds": (
                    datetime.now(timezone.utc) - self.memory_samples[0][0]
                ).total_seconds()
                if self.memory_samples
                else 0,
            }

    def reset(self) -> None:
        """Clears all collected metrics."""
        with self._lock:
            self.api_response_times = {}
            self.operation_durations = {}
            self.cache_metrics = {"hits": {}, "misses": {}, "errors": {}}
            self.memory_samples = []

    def export_metrics(self, file_path: str | None = None) -> str:
        """
        Exports metrics to JSON.

        Args:
            file_path: Path to save JSON file (optional)

        Returns:
            String JSON with metrics
        """
        metrics_data = self.get_all_metrics()
        json_data = json.dumps(metrics_data, indent=2)

        if file_path:
            try:
                with open(file_path, "w") as f:
                    f.write(json_data)
                logger.info(f"Metrics exported to {file_path}")
            except Exception as e:
                logger.error(f"Error exporting metrics: {str(e)}")

        return json_data

    def stop(self) -> None:
        """Stops background metrics collection."""
        self._stop_sampling = True
        if self._sampling_thread and self._sampling_thread.is_alive():
            self._sampling_thread.join(timeout=1.0)


# Decorators and context managers for metrics


def timed_operation(
    operation_name: str,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator to measure function execution time.

    Args:
        operation_name: Name of the operation for registration

    Returns:
        Configured decorator
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
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


def timed_api_call(api_name: str) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator to measure API call time.

    Args:
        api_name: Name of the API being called

    Returns:
        Configured decorator
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            metrics = Metrics()
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                # Records response time and success
                metrics.record_api_call(
                    api_name, time.time() - start_time, success=True
                )
                return result
            except Exception as e:
                # Records response time and failure
                metrics.record_api_call(
                    api_name, time.time() - start_time, success=False
                )
                raise

        return wrapper

    return decorator


@contextmanager
def measure_operation(operation_name: str) -> Generator[None, None, None]:
    """
    Context manager to measure time of a code block.

    Args:
        operation_name: Name of the operation to register

    Yields:
        None
    """
    metrics = Metrics()
    start_time = time.time()
    try:
        yield
    finally:
        duration = time.time() - start_time
        metrics.record_operation(operation_name, duration)


@contextmanager
def measure_api_call(api_name: str) -> Generator[None, None, None]:
    """
    Context manager to measure API call time.

    Args:
        api_name: Name of the API being called

    Yields:
        None
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
