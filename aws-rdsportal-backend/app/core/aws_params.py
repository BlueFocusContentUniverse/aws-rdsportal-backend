"""
AWS Parameter Store 参数加载器
"""

from typing import Dict

import boto3
import structlog

logger = structlog.get_logger(__name__)


def load_parameters_from_aws_sync(
    path: str = "/database-monitor/database-url", region: str = "us-west-2"
    ) -> Dict[str, str]:
    """
    从 AWS Systems Manager Parameter Store 批量加载参数（同步版本）

    Args:
        path: Parameter Store 路径前缀
        region: AWS Region

    Returns:
        参数字典，key 为参数名（不含路径前缀），value 为参数值

    Example:
        /database-monitor/database-url/cognito/user_pool_id -> {"cognito_user_pool_id": "us-west-2_xxx"}
    """
    ssm = boto3.client("ssm", region_name=region)

    try:
        parameters = {}
        next_token = None

        # 分页获取所有参数
        while True:
            if next_token:
                response = ssm.get_parameters_by_path(
                    Path=path, Recursive=True, WithDecryption=True, NextToken=next_token
                )
            else:
                response = ssm.get_parameters_by_path(
                    Path=path, Recursive=True, WithDecryption=True
                )

            for param in response["Parameters"]:
                # 提取参数名（去掉路径前缀）
                # /database-monitor/database-url/cognito/user_pool_id -> cognito_user_pool_id
                name = param["Name"].replace(path, "").lstrip("/").replace("/", "_")
                value = param["Value"]
                parameters[name] = value

            # 检查是否还有更多参数
            next_token = response.get("NextToken")
            if not next_token:
                break

        # 只记录加载的参数数量，不记录任何具体值
        logger.info(
            "aws_params_loaded",
            path=path,
            region=region,
            param_count=len(parameters),
        )
        return parameters

    except Exception as e:
        logger.error(
            "aws_params_load_failed",
            path=path,
            region=region,
            error=str(e),
        )
        return {}


async def load_parameters_from_aws(
    path: str = "/database-monitor/database-url", region: str = "us-west-2"
    ) -> Dict[str, str]:
    """
    从 AWS Systems Manager Parameter Store 批量加载参数（异步版本）

    Note: boto3 本身不支持异步，这里使用 asyncio.to_thread 包装同步调用
    """
    import asyncio

    return await asyncio.to_thread(load_parameters_from_aws_sync, path, region)
