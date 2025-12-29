"""
AWS 客户端（DynamoDB + S3 + SQS）
使用 boto3（同步） + asyncio.to_thread() 实现异步调用

相比 aioboto3 的优势：
- AWS 官方维护，凭证刷新更稳定
- 内置连接池管理
- 客户端复用，无需每次创建上下文
"""

from functools import lru_cache
from typing import Optional, Dict, Any

import boto3
from botocore.config import Config
from botocore.exceptions import EndpointConnectionError, ConnectTimeoutError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.core.logging import get_logger

logger = get_logger(__name__)

# 可重试的网络/基础设施异常
RETRYABLE_EXCEPTIONS = (
    EndpointConnectionError,
    ConnectTimeoutError,
)

# AWS 操作重试装饰器：最多重试3次，指数退避等待
aws_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
    reraise=True,
)

# boto3 客户端配置
BOTO3_CONFIG = Config(
    max_pool_connections=25,
    connect_timeout=5,
    read_timeout=30,
    retries={"max_attempts": 3, "mode": "adaptive"},
)


# ========== 缓存的 boto3 客户端/资源 ==========


@lru_cache(maxsize=1)
def _get_dynamodb_resource(region: str):
    """获取缓存的 DynamoDB resource"""
    logger.info("boto3_dynamodb_resource_created", region=region)
    return boto3.resource("dynamodb", region_name=region, config=BOTO3_CONFIG)


@lru_cache(maxsize=1)
def _get_s3_client(region: str):
    """获取缓存的 S3 client"""
    logger.info("boto3_s3_client_created", region=region)
    return boto3.client("s3", region_name=region, config=BOTO3_CONFIG)


@lru_cache(maxsize=1)
def _get_sqs_client(region: str):
    """获取缓存的 SQS client"""
    logger.info("boto3_sqs_client_created", region=region)
    return boto3.client("sqs", region_name=region, config=BOTO3_CONFIG)


# ========== DynamoDB Table 缓存 ==========

_table_cache: Dict[str, Any] = {}


def _get_table(dynamodb, table_name: str):
    """获取缓存的 DynamoDB Table 对象"""
    if table_name not in _table_cache:
        _table_cache[table_name] = dynamodb.Table(table_name)
        logger.debug("boto3_dynamodb_table_cached", table=table_name)
    return _table_cache[table_name]


class AWSClients:
    """AWS 客户端管理器（使用 boto3）"""

    def __init__(self, region: str):
        self.region = region
        # 获取缓存的客户端/资源
        self.dynamodb = _get_dynamodb_resource(region)
        self.s3 = _get_s3_client(region)
        self.sqs = _get_sqs_client(region)


# 全局实例
_aws_clients: Optional[AWSClients] = None


def get_aws_clients() -> AWSClients:
    """获取 AWS 客户端实例（懒加载）"""
    global _aws_clients
    if _aws_clients is None:
        from app.core.config import get_settings

        settings = get_settings()
        _aws_clients = AWSClients(region=settings.AWS_REGION)
    return _aws_clients
