"""
Repository 层模块

提供数据访问抽象，解耦 API 层与数据库实现
"""

from app.repositories.project_repository import ProjectRepository, get_project_repository

from app.repositories.base import BaseRepository, SQLAlchemyRepository

__all__ = [
    "BaseRepository",
    "SQLAlchemyRepository",
    "ProjectRepository",
    "get_project_repository",
]
