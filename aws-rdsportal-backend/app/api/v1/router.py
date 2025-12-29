"""
API v1 Router
"""

from fastapi import APIRouter

from app.api.v1 import projects

router = APIRouter()

# 包含各个模块的路由
router.include_router(projects.router)
