"""
Модуль ограничения скорости запросов (Rate Limiting).
"""

import time
import asyncio
import ipaddress
from typing import Dict, Optional, Tuple
from collections import defaultdict, deque
from dataclasses import dataclass
from src.core.config import IpNetwork
from src.core.constants import REQUESTS_PER_MINUTE, REQUESTS_PER_HOUR
from src.core.logging import get_logger

logger = get_logger(__name__)

# Запросы с самой машины не ограничиваются никогда: это проверки здоровья, тесты и локальные клиенты.
MACHINE_ADDRESSES: Tuple[IpNetwork, ...] = (ipaddress.ip_network("127.0.0.0/8"), ipaddress.ip_network("::1/128"))


@dataclass
class RateLimitConfig:
    """Конфигурация ограничения скорости."""
    requests_per_minute: int = REQUESTS_PER_MINUTE
    requests_per_hour: int = REQUESTS_PER_HOUR
    exempt_networks: Tuple[IpNetwork, ...] = ()
    enable_blocking: bool = True
    cleanup_interval: int = 300  # 5 минут


class RateLimitExceeded(Exception):
    """Исключение при превышении лимита запросов."""
    
    def __init__(self, message: str, retry_after: int):
        super().__init__(message)
        self.retry_after = retry_after


class RateLimiter:
    """Ограничитель скорости запросов."""
    
    def __init__(self, config: Optional[RateLimitConfig] = None):
        self.config = config or RateLimitConfig()
        
        self._requests: Dict[str, deque] = defaultdict(deque)
        self._last_cleanup = time.time()
        
        self._lock = asyncio.Lock()

    def is_exempt(self, client_id: str) -> bool:
        """Адрес без ограничения: сама машина или сеть из RATE_LIMIT_EXEMPT. Не IP-адрес — не исключение."""
        try:
            address = ipaddress.ip_address(client_id)
        except ValueError:
            return False
        if address.version == 6 and address.ipv4_mapped:
            address = address.ipv4_mapped
        return any(address in network for network in MACHINE_ADDRESSES + self.config.exempt_networks)

    async def check_rate_limit(self, client_id: str) -> bool:
        """
        Проверка лимита запросов для клиента.
        
        Args:
            client_id: Идентификатор клиента (обычно IP)
            
        Returns:
            True если запрос разрешен
            
        Raises:
            RateLimitExceeded: При превышении лимита
        """
        if self.is_exempt(client_id):
            return True

        async with self._lock:
            current_time = time.time()
            
            await self._cleanup_old_requests(current_time)
            
            client_requests = self._requests[client_id]
            
            minute_ago = current_time - 60
            minute_requests = sum(1 for req_time in client_requests if req_time > minute_ago)
            
            if minute_requests >= self.config.requests_per_minute:
                retry_after = 60 - (current_time - max(
                    req_time for req_time in client_requests if req_time > minute_ago
                ))
                
                logger.warning(f"Rate limit exceeded for {client_id}: {minute_requests} requests per minute")
                
                if self.config.enable_blocking:
                    raise RateLimitExceeded(
                        f"Превышен лимит запросов: {minute_requests}/{self.config.requests_per_minute} в минуту",
                        int(retry_after)
                    )
                
                return False
            
            hour_ago = current_time - 3600
            hour_requests = sum(1 for req_time in client_requests if req_time > hour_ago)
            
            if hour_requests >= self.config.requests_per_hour:
                retry_after = 3600 - (current_time - max(
                    req_time for req_time in client_requests if req_time > hour_ago
                ))
                
                logger.warning(f"Rate limit exceeded for {client_id}: {hour_requests} requests per hour")
                
                if self.config.enable_blocking:
                    raise RateLimitExceeded(
                        f"Превышен лимит запросов: {hour_requests}/{self.config.requests_per_hour} в час",
                        int(retry_after)
                    )
                
                return False
            
            client_requests.append(current_time)
            
            logger.debug(f"Rate limit check passed for {client_id}: {minute_requests+1}/{self.config.requests_per_minute} per minute")
            return True
    
    async def _cleanup_old_requests(self, current_time: float):
        """Очистка старых записей о запросах."""
        if current_time - self._last_cleanup < self.config.cleanup_interval:
            return
        
        hour_ago = current_time - 3600
        clients_to_remove = []
        
        for client_id, requests in self._requests.items():
            while requests and requests[0] < hour_ago:
                requests.popleft()
            
            if not requests:
                clients_to_remove.append(client_id)
        
        for client_id in clients_to_remove:
            del self._requests[client_id]
        
        self._last_cleanup = current_time
        
        if clients_to_remove:
            logger.debug(f"Cleaned up {len(clients_to_remove)} inactive clients from rate limiter")
    
    def get_client_stats(self, client_id: str) -> Dict[str, int]:
        """
        Получение статистики запросов клиента.
        
        Args:
            client_id: Идентификатор клиента
            
        Returns:
            Словарь со статистикой
        """
        current_time = time.time()
        client_requests = self._requests.get(client_id, deque())
        
        minute_ago = current_time - 60
        hour_ago = current_time - 3600
        
        minute_requests = sum(1 for req_time in client_requests if req_time > minute_ago)
        hour_requests = sum(1 for req_time in client_requests if req_time > hour_ago)
        
        return {
            'requests_per_minute': minute_requests,
            'requests_per_hour': hour_requests,
            'limit_per_minute': self.config.requests_per_minute,
            'limit_per_hour': self.config.requests_per_hour,
            'remaining_minute': max(0, self.config.requests_per_minute - minute_requests),
            'remaining_hour': max(0, self.config.requests_per_hour - hour_requests)
        }
    
    def get_global_stats(self) -> Dict[str, int]:
        """
        Получение глобальной статистики.
        
        Returns:
            Словарь с глобальной статистикой
        """
        return {
            'active_clients': len(self._requests),
            'total_requests_tracked': sum(len(requests) for requests in self._requests.values())
        }


_global_rate_limiter: Optional[RateLimiter] = None


def config_from_settings() -> RateLimitConfig:
    """Лимиты и исключения из переменных окружения (REQUESTS_PER_MINUTE, REQUESTS_PER_HOUR, RATE_LIMIT_EXEMPT)."""
    from src.core.config import settings

    return RateLimitConfig(
        requests_per_minute=settings.requests_per_minute,
        requests_per_hour=settings.requests_per_hour,
        exempt_networks=settings.rate_limit_exempt_networks,
    )


def get_rate_limiter(config: Optional[RateLimitConfig] = None) -> RateLimiter:
    """
    Получение глобального экземпляра rate limiter.
    
    Args:
        config: Конфигурация (используется только при первом вызове); нет — из настроек окружения

    Returns:
        Экземпляр RateLimiter
    """
    global _global_rate_limiter

    if _global_rate_limiter is None:
        _global_rate_limiter = RateLimiter(config or config_from_settings())
    
    return _global_rate_limiter


def reset_rate_limiter():
    """Сброс глобального rate limiter (для тестов)."""
    global _global_rate_limiter
    _global_rate_limiter = None
