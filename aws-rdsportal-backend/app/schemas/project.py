"""
Project Pydantic 模型
"""

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field, field_serializer


class ProjectIdResponse(BaseModel):
    """
    生成 Project ID 响应模型
    """

    project_id: int = Field(..., description="雪花算法生成的 Project ID")

    model_config = {"json_schema_extra": {"examples": [{"project_id": 7234567890123456789}]}}


class ProjectResponse(BaseModel):
    """
    Project 响应模型

    字段：
        project_id: 项目 ID
        user_id: 用户 ID（Cognito sub）
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
        created_at: 创建时间
        updated_at: 更新时间
    """

    project_id: int = Field(..., description="项目 ID")
    user_id: str = Field(..., description="用户 ID（Cognito sub）")
    title: Optional[str] = Field(None, description="项目标题")
    video_url: Optional[str] = Field(None, description="视频成片 URL")
    key_concept: Optional[str] = Field(None, description="核心创意（25字概述）")
    poster_url: Optional[str] = Field(None, description="海报图片 URL")
    share_code: Optional[str] = Field(None, description="分享码（用于公开分享链接）")
    user_prompt: Optional[str] = Field(None, description="用户原始提示词")
    cover_url: Optional[str] = Field(None, description="封面图 URL")
    thumbnail_url: Optional[str] = Field(None, description="缩略图 URL")
    banner_url: Optional[str] = Field(None, description="横幅图 URL")
    share_poster_url: Optional[str] = Field(None, description="分享海报 URL")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")

    @field_serializer("project_id")
    def serialize_project_id(self, v: int) -> str:
        return str(v)

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "examples": [
                {
                    "project_id": 7234567890123456789,
                    "user_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    "title": "My Animation Project",
                    "video_url": "https://s3.amazonaws.com/bucket/video.mp4",
                    "key_concept": "圣诞前夜，吉他新手收获成长礼物",
                    "poster_url": "https://s3.amazonaws.com/bucket/poster.jpg",
                    "share_code": "xK9_2mNpQwA",
                    "user_prompt": "帮我创建一个产品介绍视频",
                    "cover_url": "https://s3.amazonaws.com/bucket/cover.jpg",
                    "thumbnail_url": "https://s3.amazonaws.com/bucket/thumbnail.jpg",
                    "banner_url": "https://s3.amazonaws.com/bucket/banner.jpg",
                    "share_poster_url": "https://s3.amazonaws.com/bucket/share_poster.jpg",
                    "created_at": "2024-12-05T03:00:00Z",
                    "updated_at": "2024-12-05T03:00:00Z",
                }
            ]
        },
    }

class ProjectListResponse(BaseModel):
    """
    项目列表响应（支持分页）

    字段：
        total: 用户项目总数（不受 limit 限制）
        page: 当前页码（从 1 开始）
        page_size: 每页数量
        total_pages: 总页数
        items: 项目列表
    """

    total: int = Field(..., description="用户项目总数")
    page: int = Field(..., description="当前页码（从 1 开始）")
    page_size: int = Field(..., description="每页数量")
    total_pages: int = Field(..., description="总页数")
    items: List[ProjectResponse] = Field(..., description="项目列表")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "total": 42,
                    "page": 1,
                    "page_size": 10,
                    "total_pages": 5,
                    "items": [
                        {
                            "project_id": 7234567890123456789,
                            "user_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                            "title": "My Animation Project",
                            "video_url": "https://s3.amazonaws.com/bucket/video.mp4",
                            "key_concept": "圣诞前夜，吉他新手收获成长礼物",
                            "poster_url": "https://s3.amazonaws.com/bucket/poster.jpg",
                            "share_code": "xK9_2mNpQwA",
                            "user_prompt": "帮我创建一个产品介绍视频",
                            "created_at": "2024-12-05T03:00:00Z",
                            "updated_at": "2024-12-05T03:00:00Z",
                        }
                    ],
                }
            ]
        }
    }


class ProjectShareResponse(BaseModel):
    """
    项目分享响应模型（公开端点，无需认证）

    字段：
        project_id: 项目 ID
        title: 项目标题
        video_url: 视频成片 URL
        poster_url: 海报图片 URL
        key_concept: 核心创意（25字概述）
        username: 创建者用户名
    """

    project_id: int = Field(..., description="项目 ID")
    title: Optional[str] = Field(None, description="项目标题")
    video_url: Optional[str] = Field(None, description="视频成片 URL")
    poster_url: Optional[str] = Field(None, description="海报图片 URL")
    key_concept: Optional[str] = Field(None, description="核心创意（25字概述）")
    username: Optional[str] = Field(None, description="创建者用户名")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "project_id": 7234567890123456789,
                    "title": "My Animation Project",
                    "video_url": "https://s3.amazonaws.com/bucket/video.mp4",
                    "poster_url": "https://s3.amazonaws.com/bucket/poster.jpg",
                    "key_concept": "圣诞前夜，吉他新手收获成长礼物",
                    "username": "testuser",
                }
            ]
        }
    }
