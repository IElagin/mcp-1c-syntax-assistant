"""Конфигурация приложения."""

from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings
from typing import List, Optional, Tuple, Union
import ipaddress
import os
import re

from src.core.constants import REQUESTS_PER_HOUR, REQUESTS_PER_MINUTE

PLATFORM_VERSION = re.compile(r"\d+\.\d+\.\d+\.\d+")

IpNetwork = Union[ipaddress.IPv4Network, ipaddress.IPv6Network]


def split_versions(value: str) -> List[str]:
    """HELP_VERSIONS списком, без пустых и пробелов."""
    return [part.strip() for part in value.split(",") if part.strip()]


def parse_networks(value: str) -> Tuple[IpNetwork, ...]:
    """Адреса и сети через запятую: 172.20.0.1 или 172.16.0.0/12. Не адрес — ValueError с этим элементом."""
    networks = []
    for part in (item.strip() for item in value.split(",")):
        if not part:
            continue
        try:
            networks.append(ipaddress.ip_network(part, strict=False))
        except ValueError:
            raise ValueError(f"RATE_LIMIT_EXEMPT: {part!r} — не IP-адрес и не сеть вида 172.16.0.0/12") from None
    return tuple(networks)


class ElasticsearchConfig(BaseModel):
    """Конфигурация Elasticsearch."""
    url: str = "http://localhost:9200"
    index_name: str = "help1c_docs"
    timeout: int = 30
    max_retries: int = 3
    retry_min_wait: int = 2
    retry_max_wait: int = 30
    retry_multiplier: int = 1


class ServerConfig(BaseModel):
    """Конфигурация сервера."""
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1
    log_level: str = "INFO"


class DataConfig(BaseModel):
    """Конфигурация данных."""
    hbk_directory: str = "/app/data/hbk"
    logs_directory: str = "/app/logs"
    hbk_filename: str = "shcntx_ru.hbk"
    hbk_directory_en: str = "/app/data/hbk-en"
    hbk_filename_en: str = "shcntx_root.hbk"

    
class Settings(BaseSettings):
    """Основные настройки приложения."""
    
    elasticsearch_host: str = "localhost"
    elasticsearch_port: str = "9200"
    elasticsearch_url: str = "http://localhost:9200"
    elasticsearch_index: str = "help1c_docs"
    elasticsearch_timeout: int = 30
    elasticsearch_max_retries: str = "3"
    elasticsearch_retry_min_wait: str = "2"
    elasticsearch_retry_max_wait: str = "30"
    elasticsearch_retry_multiplier: str = "1"
    
    server_host: str = "0.0.0.0"
    server_port: int = 8000
    log_level: str = "INFO"

    # CORS: список источников через запятую. "*" — разрешить все.
    cors_allow_origins: str = "*"

    hbk_directory: str = "data/hbk"
    logs_directory: str = "data/logs"

    hbk_filename: str = "shcntx_ru.hbk"

    hbk_directory_en: str = "data/hbk-en"
    hbk_filename_en: str = "shcntx_root.hbk"

    elasticsearch_index_en: str = "help1c_docs_en"

    default_help_lang: str = "ru"

    help_versions: str = ""
    default_help_version: str = ""

    reindex_on_startup: str = "false"

    # Ограничение частоты на один адрес клиента. Пустое значение — лимит по умолчанию.
    requests_per_minute: int = REQUESTS_PER_MINUTE
    requests_per_hour: int = REQUESTS_PER_HOUR
    # Адреса и сети без ограничения частоты, через запятую; запросы с самой машины не ограничиваются всегда.
    rate_limit_exempt: str = ""

    debug: bool = False
    
    force_reindex: bool = False
    
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )

    @field_validator("default_help_lang")
    @classmethod
    def _known_language(cls, value: str) -> str:
        """Язык проверяется на старте, а не при первом запросе.

        Сервер, поднявшийся с опечаткой в DEFAULT_HELP_LANG, отвечал бы
        русскими карточками англоязычной команде и выглядел исправным.

        Регистр и обрамляющие пробелы значения не несут: DEFAULT_HELP_LANG=EN —
        написание, которое человек выберет наравне с en, потому что остальные
        значения в .env.example заглавные. Регистрозависимая проверка роняла бы
        старт сервера, и сообщение уходило бы в лог контейнера, а не тому, кто
        правил .env. Нормализация здесь — то же правило, что у соседнего
        should_reindex_on_startup (.lower()), а не вторая конвенция в одном файле.
        """
        normalized = value.strip().lower()
        if normalized not in ("ru", "en"):
            raise ValueError(
                f"DEFAULT_HELP_LANG={value!r}: допустимы только 'ru' и 'en'"
            )
        return normalized

    @field_validator("help_versions")
    @classmethod
    def _versions_are_platform_numbers(cls, value: str) -> str:
        """Версии — номера платформы через запятую; опечатка роняет старт, а не ответы."""
        for version in split_versions(value):
            if not PLATFORM_VERSION.fullmatch(version):
                raise ValueError(f"HELP_VERSIONS: {version!r} — не номер платформы вида 8.3.27.2342")
        return value

    @field_validator("requests_per_minute", "requests_per_hour", mode="before")
    @classmethod
    def _empty_limit_is_default(cls, value, info: ValidationInfo):
        """Пустая переменная — лимит по умолчанию: compose передаёт пустую строку, когда переменная не задана."""
        if isinstance(value, str) and not value.strip():
            return cls.model_fields[info.field_name].default
        return value

    @field_validator("requests_per_minute", "requests_per_hour")
    @classmethod
    def _limit_is_positive(cls, value: int, info: ValidationInfo) -> int:
        """Лимит ноль или меньше запретил бы все запросы: такая опечатка роняет старт, а не сервис."""
        if value < 1:
            raise ValueError(f"{info.field_name.upper()}={value}: лимит — целое число больше нуля")
        return value

    @field_validator("rate_limit_exempt")
    @classmethod
    def _exempt_are_networks(cls, value: str) -> str:
        """Опечатка в адресе роняет старт, а не оставляет лимит там, где его хотели снять."""
        parse_networks(value)
        return value

    @property
    def rate_limit_exempt_networks(self) -> Tuple[IpNetwork, ...]:
        """RATE_LIMIT_EXEMPT как сети; сами адреса машины (127.0.0.1, ::1) добавляет ограничитель."""
        return parse_networks(self.rate_limit_exempt)

    @model_validator(mode="after")
    def _default_version_is_configured(self) -> "Settings":
        """Версия по умолчанию — одна из HELP_VERSIONS."""
        default = self.default_help_version.strip()
        if default and default not in split_versions(self.help_versions):
            raise ValueError(
                f"DEFAULT_HELP_VERSION={default!r} нет в HELP_VERSIONS={self.help_versions!r}"
            )
        return self

    @property
    def elasticsearch(self) -> ElasticsearchConfig:
        """Получить конфигурацию Elasticsearch."""
        es_url = f"http://{self.elasticsearch_host}:{self.elasticsearch_port}"
        
        return ElasticsearchConfig(
            url=es_url,
            index_name=self.elasticsearch_index,
            timeout=self.elasticsearch_timeout,
            max_retries=int(self.elasticsearch_max_retries),
            retry_min_wait=int(self.elasticsearch_retry_min_wait),
            retry_max_wait=int(self.elasticsearch_retry_max_wait),
            retry_multiplier=int(self.elasticsearch_retry_multiplier)
        )
    
    @property
    def server(self) -> ServerConfig:
        """Получить конфигурацию сервера."""
        return ServerConfig(
            host=self.server_host,
            port=self.server_port,
            log_level=self.log_level
        )
    
    @property
    def data(self) -> DataConfig:
        """Получить конфигурацию данных."""
        return DataConfig(
            hbk_directory=self.hbk_directory,
            logs_directory=self.logs_directory,
            hbk_filename=self.hbk_filename,
            hbk_directory_en=self.hbk_directory_en,
            hbk_filename_en=self.hbk_filename_en
        )
    
    @property
    def should_reindex_on_startup(self) -> bool:
        """Проверить, нужна ли переиндексация при запуске."""
        if self.force_reindex:
            return True
        return self.reindex_on_startup.lower() in ("true", "1", "yes")

    def enable_force_reindex(self) -> None:
        """Включить принудительную переиндексацию при следующем запуске."""
        self.force_reindex = True

    @property
    def cors_origins(self) -> list:
        """Разрешённые источники запросов как список."""
        return [
            origin.strip()
            for origin in self.cors_allow_origins.split(",")
            if origin.strip()
        ]


settings = Settings()
