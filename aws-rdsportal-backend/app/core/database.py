"""
数据库连接管理

连接池配置说明:
- pool_size: 连接池保持的连接数（默认5，生产环境建议10-20）
- max_overflow: 超出 pool_size 后允许创建的额外连接（默认10）
- pool_recycle: 连接回收时间（秒），避免数据库（如 RDS）关闭长时间空闲连接
- pool_timeout: 获取连接的超时时间（秒）
- pool_pre_ping: 使用前检查连接是否有效
"""

from typing import Dict

from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import Pool

from app.core.config import get_settings
from app.core.logging import get_logger

settings = get_settings()
logger = get_logger(__name__)

# 创建数据库引擎（生产级连接池配置）
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,  # 使用前检查连接是否有效
    pool_size=20,  # 连接池大小
    max_overflow=40,  # 超出 pool_size 后最多创建的额外连接
    pool_recycle=3600,  # 每小时回收连接，避免 RDS 空闲超时（默认8小时）
    pool_timeout=30,  # 获取连接超时时间（秒）
    echo=False,  # 生产环境不输出 SQL
)


# ========== 连接池监控 ==========


@event.listens_for(Pool, "checkout")
def on_checkout(dbapi_conn, connection_record, connection_proxy):
    """连接被取出时记录"""
    pool = engine.pool
    logger.debug(
        "db_connection_checkout",
        pool_size=pool.size(),
        checked_in=pool.checkedin(),
        checked_out=pool.checkedout(),
        overflow=pool.overflow(),
    )


@event.listens_for(Pool, "checkin")
def on_checkin(dbapi_conn, connection_record):
    """连接归还时记录"""
    pool = engine.pool
    logger.debug(
        "db_connection_checkin",
        pool_size=pool.size(),
        checked_in=pool.checkedin(),
        checked_out=pool.checkedout(),
        overflow=pool.overflow(),
    )


def get_pool_status() -> Dict:
    """获取连接池状态（用于健康检查和监控）

    Returns:
        连接池状态字典，包含:
        - pool_size: 配置的连接池大小
        - checked_in: 当前空闲连接数
        - checked_out: 当前使用中的连接数
        - overflow: 当前溢出连接数
        - max_overflow: 配置的最大溢出数
    """
    pool = engine.pool
    return {
        "pool_size": pool.size(),
        "checked_in": pool.checkedin(),
        "checked_out": pool.checkedout(),
        "overflow": pool.overflow(),
        "max_overflow": engine.pool._max_overflow,
    }


# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ORM 基类
Base = declarative_base()


def get_db():
    """
    依赖注入：获取数据库会话

    用法：
    ```python
    @router.get("/items")
    async def get_items(db: Session = Depends(get_db)):
        items = db.query(Item).all()
        return items
    ```
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
