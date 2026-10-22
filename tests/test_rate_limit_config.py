"""Ограничение частоты: лимиты из окружения и адреса без лимита."""

import asyncio

import pytest
from pydantic import ValidationError

from src.core.config import Settings
from src.core.constants import REQUESTS_PER_HOUR, REQUESTS_PER_MINUTE
from src.core.rate_limiter import RateLimitConfig, RateLimitExceeded, RateLimiter


def burst(limiter: RateLimiter, client_id: str, count: int) -> None:
    """count запросов подряд от одного клиента."""

    async def run():
        for _ in range(count):
            await limiter.check_rate_limit(client_id)

    asyncio.run(run())


@pytest.mark.unit
def test_limits_default_to_constants():
    """Без переменных — прежние лимиты из constants.py."""
    settings = Settings()
    assert (settings.requests_per_minute, settings.requests_per_hour) == (REQUESTS_PER_MINUTE, REQUESTS_PER_HOUR)


@pytest.mark.unit
def test_empty_limit_is_default():
    """compose передаёт пустую строку, когда переменная не задана: это не ошибка, а значение по умолчанию."""
    settings = Settings(requests_per_minute="", requests_per_hour=" ")
    assert (settings.requests_per_minute, settings.requests_per_hour) == (REQUESTS_PER_MINUTE, REQUESTS_PER_HOUR)


@pytest.mark.unit
def test_limits_from_environment(monkeypatch):
    """REQUESTS_PER_MINUTE и REQUESTS_PER_HOUR читаются из окружения."""
    monkeypatch.setenv("REQUESTS_PER_MINUTE", "600")
    monkeypatch.setenv("REQUESTS_PER_HOUR", "20000")
    settings = Settings()
    assert (settings.requests_per_minute, settings.requests_per_hour) == (600, 20000)


@pytest.mark.unit
@pytest.mark.parametrize("value", ["0", "-5"])
def test_non_positive_limit_fails_start(value):
    """Лимит ноль или меньше запретил бы все запросы: старт падает с понятной причиной."""
    with pytest.raises(ValidationError, match="REQUESTS_PER_MINUTE"):
        Settings(requests_per_minute=value)


@pytest.mark.unit
def test_exempt_parses_addresses_and_networks():
    """Адрес и сеть через запятую, пробелы и пустые элементы не мешают."""
    settings = Settings(rate_limit_exempt=" 172.20.0.1 , ,172.16.0.0/12,fd00::/8")
    assert [str(n) for n in settings.rate_limit_exempt_networks] == ["172.20.0.1/32", "172.16.0.0/12", "fd00::/8"]


@pytest.mark.unit
def test_exempt_typo_fails_start():
    """Опечатка в адресе роняет старт, а не оставляет лимит там, где его хотели снять."""
    with pytest.raises(ValidationError, match="172.300.0.1"):
        Settings(rate_limit_exempt="172.300.0.1")


@pytest.mark.unit
@pytest.mark.parametrize("client_id", ["127.0.0.1", "127.0.0.5", "::1", "::ffff:127.0.0.1"])
def test_machine_addresses_are_never_limited(client_id):
    """Запросы с самой машины не ограничиваются даже без RATE_LIMIT_EXEMPT."""
    limiter = RateLimiter(RateLimitConfig(requests_per_minute=2, requests_per_hour=3))
    burst(limiter, client_id, 10)
    assert limiter.is_exempt(client_id)


@pytest.mark.unit
def test_exempt_network_is_not_limited_and_others_are():
    """Шлюз docker из RATE_LIMIT_EXEMPT без лимита, чужой адрес — с лимитом, как раньше."""
    networks = Settings(rate_limit_exempt="172.16.0.0/12").rate_limit_exempt_networks
    limiter = RateLimiter(RateLimitConfig(requests_per_minute=2, requests_per_hour=100, exempt_networks=networks))
    burst(limiter, "172.20.0.1", 10)
    with pytest.raises(RateLimitExceeded):
        burst(limiter, "203.0.113.7", 3)


@pytest.mark.unit
def test_not_an_address_is_limited():
    """Клиент без адреса («unknown») не получает исключения: лимит действует."""
    limiter = RateLimiter(RateLimitConfig(requests_per_minute=1, requests_per_hour=100))
    assert not limiter.is_exempt("unknown")
    with pytest.raises(RateLimitExceeded):
        burst(limiter, "unknown", 2)
