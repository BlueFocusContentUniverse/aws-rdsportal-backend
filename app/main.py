"""
FastAPI 主应用
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from app.api.v1.router import router as api_v1_router
from fastapi.middleware.cors import CORSMiddleware


from app.core.config import get_settings
from app.core.logging import setup_logging, get_logger

# 初始化日志系统
setup_logging()
logger = get_logger(__name__)

# 加载配置
settings = get_settings()


# ========== 应用生命周期管理 ==========
def _warmup_boto3_clients():
    """预热 boto3 客户端（同步调用，在启动时触发凭证获取）"""
    import boto3

    try:
        sts = boto3.client("sts", region_name=settings.AWS_REGION)
        identity = sts.get_caller_identity()
        logger.info(
            "boto3_credentials_warmed_up",
            account=identity.get("Account"),
            arn=identity.get("Arn", "").split("/")[-1],
        )
        return True
    except Exception as e:
        logger.warning("boto3_warmup_failed", error=str(e))
        return False


@asynccontextmanager
async def lifespan():
    """应用生命周期管理

    启动时：预热 boto3 客户端（触发凭证获取）、启动连接池监控
    关闭时：清理资源（HTTP Client、监控任务等）
    """
    logger.info("Application starting up...")

    # 预热 boto3 客户端（在启动时触发凭证获取，避免首次请求延迟）
    import asyncio

    await asyncio.to_thread(_warmup_boto3_clients)

# 创建 FastAPI app
app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description="AWS Cognito User Authentication Backend",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)


# todo 改为动态获取允许的域名
origins = [
    "http://localhost:5173",
    # 如果有其他域名也可以加进来
]

# CORS 中间件（最后添加，最先执行，确保错误响应也有 CORS 头）
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# ========== 健康检查端点 ==========

from fastapi import APIRouter

# 创建主路由器（用于添加环境前缀）
main_router = APIRouter()

main_router.include_router(api_v1_router)


# ========== 根路径 ==========

# 将主路由器挂载到应用
app.include_router(main_router)



# 启动事件
@app.on_event("startup")
async def startup_event():
    """应用启动时执行"""
    logger.info(
        "application_started",
        service=settings.PROJECT_NAME,
        environment=settings.ENVIRONMENT,
        aws_region=settings.AWS_REGION,
        use_parameter_store=settings.USE_AWS_PARAMETER_STORE,
    )


# 关闭事件
@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时执行"""
    logger.info("application_shutdown", service=settings.PROJECT_NAME)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # 开发环境启用热重载
        log_level=settings.LOG_LEVEL.lower(),
    )
