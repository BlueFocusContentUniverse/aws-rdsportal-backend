"""
应用配置管理（仅数据库相关）
支持：
- .env 文件
- AWS Parameter Store
- AWS Secrets Manager 注入的数据库环境变量
"""

import urllib.parse
from typing import Optional, List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置"""

    # ===== 基础环境 =====
    ENVIRONMENT: str = Field(default="development", description="运行环境")
    LOG_LEVEL: str = Field(default="INFO", description="日志级别")

    # ===== AWS =====
    AWS_REGION: str = Field(default="us-west-2", description="AWS Region")
    USE_AWS_PARAMETER_STORE: bool = Field(
        default=False, description="是否从 AWS Parameter Store 加载配置"
    )

    # ===== APP =====
    PROJECT_NAME: str = Field(default="AWS User Backend", description="项目名称")
    ALLOWED_ORIGINS: List[str] = Field(
        default=[
            "https://pntqeuwnmfco.h5master.com",
            "http://localhost:3000",
            "http://localhost:8080",
        ],
        description="CORS 允许的源",
    )



    # ===== Database =====
    # 方式一：完整 DATABASE_URL（本地 / Parameter Store）
    DATABASE_URL: str = Field(default="", description="PostgreSQL 数据库连接 URL")

    # 方式二：Secrets Manager 注入（ECS / EKS 推荐）
    DB_HOST: str = Field(default="", description="数据库主机")
    DB_PORT: str = Field(default="5432", description="数据库端口")
    DB_USERNAME: str = Field(default="", description="数据库用户名")
    DB_PASSWORD: str = Field(default="", description="数据库密码")
    DB_NAME: str = Field(default="postgres", description="数据库名")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


# 全局配置实例（懒加载）
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """获取配置实例（懒加载）"""
    global _settings

    if _settings is None:
        _settings = Settings()

        # ===== 环境约束 =====
        if _settings.ENVIRONMENT in ("production", "staging"):
            if not _settings.USE_AWS_PARAMETER_STORE:
                raise RuntimeError(
                    f"[CONFIG ERROR] ENVIRONMENT={_settings.ENVIRONMENT} "
                    f"必须启用 USE_AWS_PARAMETER_STORE=true，禁止使用 .env"
                )

        # ===== Parameter Store =====
        if _settings.USE_AWS_PARAMETER_STORE:
            from app.core.aws_params import load_parameters_from_aws_sync

            params = load_parameters_from_aws_sync(
                path="/database-monitor/database",
                region=_settings.AWS_REGION,
            )

            if not params:
                raise RuntimeError(
                    "[CONFIG ERROR] 未能从 AWS Parameter Store 加载数据库配置"
                )

            if "database_url" in params:
                _settings.DATABASE_URL = params["database_url"]

        # ===== Secrets Manager 构建 DATABASE_URL（优先级最高）=====
        if _settings.DB_HOST and _settings.DB_PASSWORD:
            encoded_password = urllib.parse.quote(
                _settings.DB_PASSWORD, safe=""
            )
            _settings.DATABASE_URL = (
                f"postgresql://{_settings.DB_USERNAME}:{encoded_password}"
                f"@{_settings.DB_HOST}:{_settings.DB_PORT}/{_settings.DB_NAME}"
                f"?sslmode=require"
            )

        # todo 后续修改为正确的数据库配置
        # ===== 最终校验 =====
        if not _settings.DATABASE_URL:
            # ===== 本地测试配置 ======
            print("[CONFIG WARNING] 使用本地测试配置")
            db_username = "postgres"
            db_password = "Kox#Agent2025!Db"
            db_name = "postgres"
            db_port = "5432"
            db_host = "database-1.c3o2mgg6e22t.us-west-2.rds.amazonaws.com"
            _settings.DATABASE_URL = (
                f"postgresql://{db_username}:{db_password}"
                f"@{db_host}:{db_port}/{db_name}"
                f"?sslmode=require"
            )
            # raise RuntimeError(
            #     "[CONFIG ERROR] DATABASE_URL 未配置。"
            #     "请通过 Parameter Store 或 Secrets Manager 提供数据库连接信息"
            # )

    return _settings
