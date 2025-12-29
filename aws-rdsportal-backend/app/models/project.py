"""
Project ORM 模型
"""

from sqlalchemy import Column, BigInteger, String, DateTime, Text
from sqlalchemy.sql import func

from app.core.database import Base


class Project(Base):
    """
    Project ORM 模型

    字段：
        project_id: 项目 ID（雪花算法生成的 64 位整数）
        user_id: 用户 ID（Cognito sub，UUID 格式）
        created_at: 创建时间
        updated_at: 更新时间
        title: 项目标题
        video_url: 视频成片 URL
        key_concept: 核心创意（25字概述）
        poster_url: 海报图片 URL
        share_code: 分享码（用于公开分享链接）
        user_prompt: 用户原始提示词
        cover_url: 封面图 URL
        thumbnail_url: 缩略图 URL
        banner_url: 横幅图 URL
        share_poster_url: 分享海报 URL

    索引：
        idx_user_id: 按 user_id 查询优化
        idx_share_code: 按 share_code 查询优化（unique）
    """

    __tablename__ = "projects"

    project_id = Column(BigInteger, primary_key=True, comment="项目 ID（雪花算法）")
    user_id = Column(String(255), nullable=False, index=True, comment="用户 ID（Cognito sub）")
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, comment="创建时间"
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="更新时间",
    )
    title = Column(String(255), nullable=True, comment="项目标题")
    video_url = Column(String(2048), nullable=True, comment="视频成片 URL")
    key_concept = Column(String(500), nullable=True, comment="核心创意（25字概述）")
    poster_url = Column(String(2048), nullable=True, comment="海报图片 URL")
    share_code = Column(
        String(16), nullable=True, unique=True, index=True, comment="分享码（用于公开分享链接）"
    )
    user_prompt = Column(Text, nullable=True, comment="用户原始提示词")
    cover_url = Column(String(2048), nullable=True, comment="封面图 URL")
    thumbnail_url = Column(String(2048), nullable=True, comment="缩略图 URL")
    banner_url = Column(String(2048), nullable=True, comment="横幅图 URL")
    share_poster_url = Column(String(2048), nullable=True, comment="分享海报 URL")

    def __repr__(self):
        return f"<Project(project_id={self.project_id}, user_id={self.user_id})>"
