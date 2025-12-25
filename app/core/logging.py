"""
结构化日志配置模块

功能:
- 使用 structlog 实现结构化日志
- JSON 格式输出（生产环境）
- 彩色控制台输出（开发环境）
- 自动添加 timestamp、level、logger name
- 敏感信息脱敏
- Request ID 追踪支持
"""

import sys
from contextvars import ContextVar
from typing import Optional

import structlog
from structlog.types import EventDict, Processor

import logging
from app.core.config import get_settings

# 请求 ID 上下文变量
request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


# 敏感字段列表（将被脱敏）
SENSITIVE_FIELDS = {
    # 认证相关
    "password",
    "new_password",
    "old_password",
    "token",
    "access_token",
    "refresh_token",
    "id_token",
    "secret",
    "secret_hash",
    "authorization",
    "api_key",
    "client_secret",
    "verification_code",
    "code",
    "confirmation_code",
    # AWS/云服务相关
    "cognito_app_client_secret",
    "aws_secret_access_key",
    "aws_session_token",
    # 数据库相关
    "database_url",
    "db_password",
    "connection_string",
    # SMS相关
    "sms_app_key",
    "sms_sdk_app_id",
    # 其他敏感信息
    "credit_card",
    "ssn",
    "phone_number",  # 部分脱敏
}


def mask_sensitive_data(
    logger: logging.Logger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """脱敏敏感数据的处理器"""
    for key in list(event_dict.keys()):
        if key.lower() in SENSITIVE_FIELDS:
            value = event_dict[key]
            if isinstance(value, str) and len(value) > 8:
                # 保留前4位和后4位，中间用 * 替代
                event_dict[key] = f"{value[:4]}****{value[-4:]}"
            else:
                event_dict[key] = "****"
    return event_dict


def add_request_id(
    logger: logging.Logger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """添加请求 ID 到日志"""
    request_id = request_id_var.get()
    if request_id:
        event_dict["request_id"] = request_id
    return event_dict


def setup_logging() -> None:
    """配置结构化日志"""
    settings = get_settings()
    is_development = settings.ENVIRONMENT == "development"

    # 共享的处理器
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        add_request_id,
        mask_sensitive_data,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if is_development:
        # 开发环境：彩色控制台输出
        shared_processors.append(structlog.dev.ConsoleRenderer(colors=True))
    else:
        # 生产环境：JSON 格式
        shared_processors.append(structlog.processors.format_exc_info)
        shared_processors.append(structlog.processors.JSONRenderer())

    # 配置 structlog
    structlog.configure(
        processors=shared_processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # 配置标准 logging
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    # 设置根 logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # 清除现有 handlers
    root_logger.handlers.clear()

    # 添加 handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)

    if is_development:
        # 开发环境使用简单格式
        formatter = logging.Formatter("%(message)s")
    else:
        # 生产环境使用 JSON 格式（由 structlog 处理）
        formatter = logging.Formatter("%(message)s")

    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # 降低第三方库的日志级别
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)


def get_logger(name: str = __name__) -> structlog.stdlib.BoundLogger:
    """获取 structlog logger"""
    return structlog.get_logger(name)


def set_request_id(request_id: str) -> None:
    """设置当前请求的 Request ID"""
    request_id_var.set(request_id)


def get_request_id() -> Optional[str]:
    """获取当前请求的 Request ID"""
    return request_id_var.get()


def clear_request_id() -> None:
    """清除当前请求的 Request ID"""
    request_id_var.set(None)
