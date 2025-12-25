import string
from math import ceil
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
import logging

from app.core.database import get_db
from app.models.project import Project
from app.schemas.project import ProjectListResponse, ProjectResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/projects", tags=["Project"])


@router.get(
    "",
    response_model=ProjectListResponse,
    summary="分页获取项目列表",
    description="分页获取项目列表（内部使用），支持按用户ID、项目ID、时间段过滤",
)
def list_projects(
        # 分页参数
        page: int = Query(1, ge=1, description="页码，从 1 开始"),
        page_size: int = Query(20, ge=1, le=100, description="每页数量"),
        # 新增查询过滤参数
        user_id: str = Query(None, description="用户ID，过滤指定用户的项目"),
        project_id: int = Query(None, description="项目ID，精准查询某个项目"),
        start_time: datetime = Query(None, description="开始时间（UTC），格式：2025-01-01T00:00:00"),
        end_time: datetime = Query(None, description="结束时间（UTC），格式：2025-12-31T23:59:59"),
        # 数据库依赖
        db: Session = Depends(get_db),
):
    offset = (page - 1) * page_size

    # 构建查询条件
    query = db.query(Project)

    # 1. 按项目ID过滤（精准匹配）
    if project_id:
        query = query.filter(Project.project_id == project_id)

    # 2. 按用户ID过滤（假设Project模型有user_id字段）
    if user_id:
        query = query.filter(Project.user_id == user_id)

    # 3. 按时间段过滤（假设按created_at字段筛选，可替换为update_at等）
    if start_time and end_time:
        query = query.filter(and_(
            Project.created_at >= start_time,
            Project.created_at <= end_time
        ))
    elif start_time:  # 只有开始时间：大于等于开始时间
        query = query.filter(Project.created_at >= start_time)
    elif end_time:    # 只有结束时间：小于等于结束时间
        query = query.filter(Project.created_at <= end_time)

    # 获取总数（过滤后的总数）
    total = query.count()

    # 获取当前页数据（保持排序和分页）
    items = (
        query
        .order_by(Project.created_at.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )

    # 转换为响应模型
    items = [
        ProjectResponse.model_validate(p)
        for p in items
    ]

    # 计算总页数
    total_pages = ceil(total / page_size) if page_size != 0 else 0

    return ProjectListResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages
    )