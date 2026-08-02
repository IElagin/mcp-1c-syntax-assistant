"""Конфигурация приложения."""

from pydantic import BaseModel, ConfigDict
from pydantic_settings import BaseSettings
from typing import Optional
import os


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

    
class Settings(BaseSettings):
    """Основные настройки приложения."""
    
    # Elasticsearch настройки
    elasticsearch_host: str = "localhost"
    elasticsearch_port: str = "9200"
    elasticsearch_url: str = "http://localhost:9200"
    elasticsearch_index: str = "help1c_docs"
    elasticsearch_timeout: int = 30
    elasticsearch_max_retries: str = "3"
    elasticsearch_retry_min_wait: str = "2"
    elasticsearch_retry_max_wait: str = "30"
    elasticsearch_retry_multiplier: str = "1"
    
    # Сервер настройки
    server_host: str = "0.0.0.0"
    server_port: int = 8000
    log_level: str = "INFO"

    # CORS: список источников через запятую. "*" — разрешить все.
    cors_allow_origins: str = "*"

    # Пути к данным
    hbk_directory: str = "data/hbk"
    logs_directory: str = "data/logs"

    # Имя книги справки для индексации. В каталоге могут лежать и другие .hbk:
    # английская shcntx_root.hbk, книги по языку запросов. Выбор должен быть
    # явным, иначе он зависит от порядка файлов в каталоге.
    hbk_filename: str = "shcntx_ru.hbk"

    # Индексация
    reindex_on_startup: str = "false"

    # Режим разработки
    debug: bool = False
    
    # Runtime параметры (устанавливаются программно)
    force_reindex: bool = False
    
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )
    
    @property
    def elasticsearch(self) -> ElasticsearchConfig:
        """Получить конфигурацию Elasticsearch."""
        # Формируем URL из host и port
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
            hbk_filename=self.hbk_filename
        )
    
    @property
    def should_reindex_on_startup(self) -> bool:
        """Проверить, нужна ли переиндексация при запуске."""
        # Приоритет: force_reindex > reindex_on_startup
        if self.force_reindex:
            return True
        return self.reindex_on_startup.lower() in ("true", "1", "yes")

    @property
    def cors_origins(self) -> list:
        """Разрешённые источники запросов как список."""
        return [
            origin.strip()
            for origin in self.cors_allow_origins.split(",")
            if origin.strip()
        ]


# Глобальный экземпляр настроек
settings = Settings()
