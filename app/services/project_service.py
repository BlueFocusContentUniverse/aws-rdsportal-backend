"""
项目服务（读取 DynamoDB + S3）
"""

import re
from typing import Dict, Any
from fastapi import HTTPException, status

from app.core.aws_clients import get_aws_clients
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class ProjectService:
    """项目服务 - 从 DynamoDB + S3 读取数据"""

    def __init__(self):
        self.aws = get_aws_clients()
        self.settings = get_settings()
        self.table_name = self.settings.DYNAMODB_PROJECTS_TABLE

    def _parse_s3_uri(self, s3_uri: str) -> tuple[str, str]:
        """解析并验证 S3 URI: s3://bucket/key → (bucket, key)

        Args:
            s3_uri: S3 URI 字符串

        Returns:
            (bucket, key) 元组

        Raises:
            ValueError: URI 格式无效或包含安全风险
        """
        match = re.match(r"s3://([^/]+)/(.+)", s3_uri)
        if not match:
            raise ValueError(f"Invalid S3 URI: {s3_uri}")

        bucket, key = match.group(1), match.group(2)

        # 验证 bucket 名称（AWS S3 命名规则）
        # - 3-63 字符
        # - 只能包含小写字母、数字、连字符、点
        # - 必须以字母或数字开头和结尾
        if not re.match(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", bucket):
            logger.warning("invalid_s3_bucket_name", bucket=bucket)
            raise ValueError(f"Invalid S3 bucket name: {bucket}")

        # 检查路径遍历攻击
        if ".." in key or key.startswith("/"):
            logger.warning("s3_path_traversal_detected", key=key)
            raise ValueError(f"Invalid S3 key: path traversal detected")

        return bucket, key

    async def get_project_metadata(self, project_id: int, user_id: str) -> Dict:
        """获取项目元数据（从 DynamoDB）"""
        item = await self._get_project_item(project_id, user_id)

        return {
            "project_id": int(item.get("ProjectId", project_id)),
            "user_id": item.get("UserId", user_id),
            "title": item.get("Title", "Untitled Project"),
            "status": item.get("Status", "UNKNOWN"),
            "progress": int(item.get("Progress", 0)),
            "version": int(item.get("Version", 1)),
            "ppm_ref": item.get("PPMRef"),
            "ppm_version": item.get("PPMVersion"),
            "script_ref": item.get("ScriptRef"),
            "created_at": item.get("CreatedAt"),
            "updated_at": item.get("UpdatedAt"),
            # Creative Studio 字段 (PascalCase)
            "draft_id": item.get("DraftId"),
            "creative_brief_url": item.get("CreativeBriefUrl"),
            "creative_brief_id": item.get("CreativeBriefId"),
            "creative_brief_version": item.get("CreativeBriefVersion"),
            "creative_brief_history": item.get("CreativeBriefHistory", []),
            "creative_brief_metadata": item.get("CreativeBriefMetadata"),
            # Assets Script 字段 (PascalCase)
            "assets_script_url": item.get("AssetsScriptUrl"),
            "assets_script_id": item.get("AssetsScriptId"),
            "assets_script_version": item.get("AssetsScriptVersion"),
            "assets_script_history": item.get("AssetsScriptHistory", []),
            # Deliverables 交付物
            "deliverables": item.get("Deliverables", []),
            # Session 管理字段 (snake_case - 与 chat_service.py 写入一致)
            "runtime_session_id": item.get("runtime_session_id"),
            "session_status": item.get("session_status"),
            "session_created_at": item.get("session_created_at"),
            "session_last_active": item.get("session_last_active"),
            "session_expires_at": item.get("session_expires_at"),
        }

    async def get_ppm(self, project_id: int, user_id: str) -> Dict:
        """获取完整 PPM"""
        return await self._get_s3_content(project_id, user_id, "PPMRef", "PPM")

    async def get_ppm_field(self, project_id: int, user_id: str, field: str) -> Any:
        """获取 PPM 的单个字段"""
        ppm = await self._get_s3_content(project_id, user_id, "PPMRef", "PPM")

        if field not in ppm:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"PPM field '{field}' not found"
            )

        return {field: ppm[field]}

    async def get_script(self, project_id: int, user_id: str) -> Dict:
        """获取 Script"""
        return await self._get_s3_content(project_id, user_id, "ScriptRef", "Script")

    async def get_assets(self, project_id: int, user_id: str) -> Dict:
        """获取资产列表"""
        item = await self._get_project_item(project_id, user_id)

        assets_raw = item.get("Assets", {})
        assets = {}

        for asset_id, asset_data in assets_raw.items():
            assets[asset_id] = {
                "asset_id": asset_data.get("asset_id", asset_id),
                "type": asset_data.get("type", "unknown"),
                "url": asset_data.get("url", ""),
                "scene_id": asset_data.get("scene_id"),
                "metadata": asset_data.get("metadata"),
                "created_at": asset_data.get("created_at"),
            }

        return {"assets": assets}

    async def _get_project_item(self, project_id: int, user_id: str) -> Dict:
        """获取项目 item（内部方法，包含权限验证）"""
        pk = f"USER#{user_id}"
        sk = f"PROJ#{project_id}"

        logger.info(
            "fetching_project_from_dynamodb",
            table=self.table_name,
            project_id=project_id,
            user_id=user_id[:8] + "...",
        )

        item = await self.aws.dynamodb_get_item(self.table_name, pk, sk)

        if not item:
            logger.warning("project_not_found", project_id=project_id, user_id=user_id[:8] + "...")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found or access denied"
            )

        return item

    async def _get_s3_content(
            self, project_id: int, user_id: str, ref_field: str, content_name: str
    ) -> Dict:
        """从 S3 获取内容"""
        item = await self._get_project_item(project_id, user_id)

        s3_ref = item.get(ref_field)
        if not s3_ref:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"{content_name} not found"
            )

        try:
            bucket, key = self._parse_s3_uri(s3_ref)
        except ValueError as e:
            logger.error("invalid_s3_uri", ref=s3_ref, error=str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Invalid {content_name} reference",
            )

        logger.info("fetching_content_from_s3", content=content_name, bucket=bucket, key=key)

        content = await self.aws.s3_get_json(bucket, key)

        if not content:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"{content_name} file not found in S3"
            )

        return content

    async def _get_s3_text_content(
            self, project_id: int, user_id: str, url_field: str, id_field: str, content_name: str
    ) -> Dict:
        """从 S3 获取 Markdown/文本内容"""
        item = await self._get_project_item(project_id, user_id)

        s3_url = item.get(url_field)
        if not s3_url:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"{content_name} not found"
            )

        try:
            bucket, key = self._parse_s3_uri(s3_url)
        except ValueError as e:
            logger.error("invalid_s3_uri", url=s3_url, error=str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Invalid {content_name} reference",
            )

        logger.info("fetching_text_content_from_s3", content=content_name, bucket=bucket, key=key)

        content = await self.aws.s3_get_text(bucket, key)

        if not content:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"{content_name} file not found in S3"
            )

        return {"content": content, "content_id": item.get(id_field)}

    async def get_creative_brief(self, project_id: int, user_id: str) -> Dict:
        """获取 Creative Brief (Markdown)"""
        return await self._get_s3_text_content(
            project_id, user_id, "CreativeBriefUrl", "CreativeBriefId", "Creative Brief"
        )

    async def get_assets_script(self, project_id: int, user_id: str) -> Dict:
        """获取 Assets Script (Markdown)"""
        return await self._get_s3_text_content(
            project_id, user_id, "AssetsScriptUrl", "AssetsScriptId", "Assets Script"
        )
