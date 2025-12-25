"""
AWS Cognito Client
使用 boto3（同步） + asyncio.to_thread() 实现异步调用

相比 aioboto3 的优势：
- AWS 官方维护，凭证刷新更稳定
- 内置连接池管理
- 客户端复用，无需每次创建上下文
"""

import hmac
import hashlib
import base64
import asyncio
import boto3
from functools import lru_cache
from typing import Dict, Optional

import structlog
from botocore.exceptions import ClientError, EndpointConnectionError, ConnectTimeoutError
from botocore.config import Config
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.core.monitoring import track_aws_latency

logger = structlog.get_logger(__name__)

# 可重试的网络/基础设施异常（不包括业务错误）
RETRYABLE_EXCEPTIONS = (
    EndpointConnectionError,
    ConnectTimeoutError,
)

# 重试装饰器：最多重试3次，指数退避等待
cognito_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
    reraise=True,
)

# boto3 客户端配置
BOTO3_CONFIG = Config(
    max_pool_connections=25,
    connect_timeout=5,
    read_timeout=30,
    retries={"max_attempts": 3, "mode": "adaptive"},
)


# ========== 缓存的 boto3 客户端 ==========


@lru_cache(maxsize=1)
def _get_cognito_client(region: str):
    """获取缓存的 Cognito IDP client"""
    logger.info("boto3_cognito_client_created", region=region)
    return boto3.client("cognito-idp", region_name=region, config=BOTO3_CONFIG)


class CognitoException(Exception):
    """Cognito相关异常基类"""

    pass


class UserNotFoundException(CognitoException):
    """用户不存在"""

    pass


class InvalidCredentialsException(CognitoException):
    """用户名或密码错误"""

    pass


class UserNotConfirmedException(CognitoException):
    """用户未验证邮箱"""

    pass


class CognitoClient:
    """AWS Cognito User Pool 客户端（使用 boto3）"""

    def __init__(
        self, region: str, user_pool_id: str, client_id: str, client_secret: Optional[str] = None
    ):
        self.region = region
        self.user_pool_id = user_pool_id
        self.client_id = client_id
        self.client_secret = client_secret
        # 获取缓存的 boto3 客户端
        self.client = _get_cognito_client(region)

    def _escape_filter_value(self, value: str) -> str:
        """转义 Cognito Filter 中的特殊字符"""
        return value.replace("\\", "\\\\").replace('"', '\\"')

    def _get_secret_hash(self, username: str) -> Optional[str]:
        """计算 SECRET_HASH（如果配置了 client_secret）"""
        if not self.client_secret:
            return None

        message = bytes(username + self.client_id, "utf-8")
        key = bytes(self.client_secret, "utf-8")
        secret_hash = base64.b64encode(
            hmac.new(key, message, digestmod=hashlib.sha256).digest()
        ).decode()
        return secret_hash

    @cognito_retry
    @track_aws_latency("cognito", "sign_up")
    async def sign_up(
        self, email: str, username: str, password: str, name: Optional[str] = None
    ) -> Dict:
        """注册新用户"""
        try:
            user_attributes = [{"Name": "email", "Value": email}]
            if name:
                user_attributes.append({"Name": "name", "Value": name})

            params = {
                "ClientId": self.client_id,
                "Username": username,
                "Password": password,
                "UserAttributes": user_attributes,
            }

            if self.client_secret:
                params["SecretHash"] = self._get_secret_hash(username)

            response = await asyncio.to_thread(self.client.sign_up, **params)

            return {
                "UserSub": response["UserSub"],
                "UserConfirmed": response["UserConfirmed"],
            }

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "UsernameExistsException":
                raise CognitoException("Username already exists")
            elif error_code == "InvalidParameterException":
                raise CognitoException(f"Invalid parameter: {e.response['Error']['Message']}")
            elif error_code == "InvalidPasswordException":
                raise CognitoException("Password does not meet requirements")
            else:
                raise CognitoException(f"Sign up failed: {e.response['Error']['Message']}")

    @cognito_retry
    @track_aws_latency("cognito", "sign_in")
    async def sign_in(self, username: str, password: str) -> Dict:
        """用户登录"""
        try:
            params = {
                "AuthFlow": "USER_PASSWORD_AUTH",
                "ClientId": self.client_id,
                "AuthParameters": {
                    "USERNAME": username,
                    "PASSWORD": password,
                },
            }

            if self.client_secret:
                params["AuthParameters"]["SECRET_HASH"] = self._get_secret_hash(username)

            logger.info(
                "cognito_sign_in_attempt",
                username=username,
                has_secret_hash="SECRET_HASH" in params["AuthParameters"],
            )

            response = await asyncio.to_thread(self.client.initiate_auth, **params)

            if "AuthenticationResult" not in response:
                raise CognitoException("Authentication failed: No tokens returned")

            return response

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "NotAuthorizedException":
                raise InvalidCredentialsException("Incorrect username or password")
            elif error_code == "UserNotFoundException":
                raise UserNotFoundException("User not found")
            elif error_code == "UserNotConfirmedException":
                raise UserNotConfirmedException("User not confirmed. Please verify your email.")
            else:
                raise CognitoException(f"Sign in failed: {e.response['Error']['Message']}")

    @cognito_retry
    @track_aws_latency("cognito", "refresh_tokens")
    async def refresh_tokens(self, refresh_token: str, username: str) -> Dict:
        """刷新 access token"""
        try:
            params = {
                "AuthFlow": "REFRESH_TOKEN_AUTH",
                "ClientId": self.client_id,
                "AuthParameters": {"REFRESH_TOKEN": refresh_token},
            }

            if self.client_secret:
                params["AuthParameters"]["SECRET_HASH"] = self._get_secret_hash(username)

            response = await asyncio.to_thread(self.client.initiate_auth, **params)
            return response

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "NotAuthorizedException":
                raise CognitoException("Invalid or expired refresh token")
            else:
                raise CognitoException(f"Token refresh failed: {e.response['Error']['Message']}")

    @cognito_retry
    @track_aws_latency("cognito", "get_user")
    async def get_user(self, access_token: str) -> Dict:
        """通过 access token 获取用户信息"""
        try:
            response = await asyncio.to_thread(self.client.get_user, AccessToken=access_token)
            return response

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "NotAuthorizedException":
                raise CognitoException("Invalid or expired access token")
            else:
                raise CognitoException(f"Get user failed: {e.response['Error']['Message']}")

    @cognito_retry
    async def global_sign_out(self, access_token: str) -> bool:
        """全局登出（使所有 refresh token 失效）"""
        try:
            await asyncio.to_thread(self.client.global_sign_out, AccessToken=access_token)
            return True

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "NotAuthorizedException":
                raise CognitoException("Invalid or expired access token")
            else:
                raise CognitoException(f"Sign out failed: {e.response['Error']['Message']}")

    @cognito_retry
    async def confirm_sign_up(self, username: str, confirmation_code: str) -> bool:
        """确认用户注册（邮箱验证）"""
        try:
            params = {
                "ClientId": self.client_id,
                "Username": username,
                "ConfirmationCode": confirmation_code,
            }

            if self.client_secret:
                params["SecretHash"] = self._get_secret_hash(username)

            await asyncio.to_thread(self.client.confirm_sign_up, **params)
            return True

        except ClientError as e:
            raise CognitoException(f"Confirmation failed: {e.response['Error']['Message']}")

    @cognito_retry
    async def resend_confirmation_code(self, username: str) -> bool:
        """重新发送确认码"""
        try:
            params = {
                "ClientId": self.client_id,
                "Username": username,
            }

            if self.client_secret:
                params["SecretHash"] = self._get_secret_hash(username)

            await asyncio.to_thread(self.client.resend_confirmation_code, **params)
            return True

        except ClientError as e:
            raise CognitoException(f"Resend code failed: {e.response['Error']['Message']}")

    # ============ SMS Authentication Methods ============

    @cognito_retry
    async def sign_up_with_phone(self, phone_number: str, username: str) -> Dict:
        """使用手机号注册（无密码，用于 SMS 验证码登录）"""
        import secrets

        temp_password = secrets.token_urlsafe(32) + "Aa1!"

        try:
            placeholder_email = f"{phone_number.replace('+', '')}@sms.placeholder.com"

            params = {
                "ClientId": self.client_id,
                "Username": username,
                "Password": temp_password,
                "UserAttributes": [
                    {"Name": "phone_number", "Value": phone_number},
                    {"Name": "email", "Value": placeholder_email},
                ],
            }

            if self.client_secret:
                params["SecretHash"] = self._get_secret_hash(username)

            response = await asyncio.to_thread(self.client.sign_up, **params)

            return {
                "UserSub": response["UserSub"],
                "UserConfirmed": response["UserConfirmed"],
                "existing": False,
                "temp_password": temp_password,
            }

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "UsernameExistsException":
                return {
                    "UserSub": None,
                    "UserConfirmed": True,
                    "existing": True,
                    "temp_password": None,
                }
            raise CognitoException(f"Phone sign up failed: {e.response['Error']['Message']}")

    @cognito_retry
    async def admin_confirm_sign_up(self, username: str) -> bool:
        """管理员确认用户注册"""
        try:
            await asyncio.to_thread(
                self.client.admin_confirm_sign_up, UserPoolId=self.user_pool_id, Username=username
            )
            return True

        except ClientError as e:
            raise CognitoException(f"Admin confirm failed: {e.response['Error']['Message']}")

    @cognito_retry
    async def admin_set_user_password(
        self, username: str, password: str, permanent: bool = True
    ) -> bool:
        """管理员设置用户密码"""
        try:
            await asyncio.to_thread(
                self.client.admin_set_user_password,
                UserPoolId=self.user_pool_id,
                Username=username,
                Password=password,
                Permanent=permanent,
            )
            return True

        except ClientError as e:
            raise CognitoException(f"Set password failed: {e.response['Error']['Message']}")

    @cognito_retry
    @track_aws_latency("cognito", "admin_initiate_auth")
    async def admin_initiate_auth(self, username: str, password: str) -> Dict:
        """管理员发起认证（替用户登录，不需要 SRP）"""
        try:
            params = {
                "UserPoolId": self.user_pool_id,
                "ClientId": self.client_id,
                "AuthFlow": "ADMIN_NO_SRP_AUTH",
                "AuthParameters": {
                    "USERNAME": username,
                    "PASSWORD": password,
                },
            }

            if self.client_secret:
                params["AuthParameters"]["SECRET_HASH"] = self._get_secret_hash(username)

            response = await asyncio.to_thread(self.client.admin_initiate_auth, **params)
            return response

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "NotAuthorizedException":
                raise InvalidCredentialsException("Authentication failed")
            elif error_code == "UserNotFoundException":
                raise UserNotFoundException("User not found")
            elif error_code == "UserNotConfirmedException":
                raise UserNotConfirmedException("User not confirmed")
            raise CognitoException(f"Admin auth failed: {e.response['Error']['Message']}")

    @cognito_retry
    async def admin_update_user_attributes(self, username: str, attributes: list) -> bool:
        """管理员更新用户属性"""
        try:
            await asyncio.to_thread(
                self.client.admin_update_user_attributes,
                UserPoolId=self.user_pool_id,
                Username=username,
                UserAttributes=attributes,
            )
            return True

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "UserNotFoundException":
                raise UserNotFoundException("User not found")
            elif error_code == "AliasExistsException":
                raise CognitoException("Phone number already bound to another account")
            raise CognitoException(
                f"Update user attributes failed: {e.response['Error']['Message']}"
            )

    @cognito_retry
    @track_aws_latency("cognito", "list_users_by_phone")
    async def list_users_by_phone(self, phone_number: str) -> Optional[Dict]:
        """按手机号查找用户"""
        try:
            filter_str = f'phone_number = "{self._escape_filter_value(phone_number)}"'
            logger.info("list_users_by_phone_query", phone_number=phone_number, filter=filter_str)

            response = await asyncio.to_thread(
                self.client.list_users, UserPoolId=self.user_pool_id, Filter=filter_str, Limit=1
            )

            users = response.get("Users", [])
            logger.info(
                "list_users_by_phone_result", phone_number=phone_number, users_count=len(users)
            )
            if users:
                user = users[0]
                attributes = {attr["Name"]: attr["Value"] for attr in user.get("Attributes", [])}
                return {
                    "Username": user["Username"],
                    "UserStatus": user.get("UserStatus"),
                    "Attributes": attributes,
                }
            return None

        except ClientError as e:
            raise CognitoException(f"List users failed: {e.response['Error']['Message']}")

    # ============ Account Linking Methods ============

    @cognito_retry
    async def link_phone_to_user(self, username: str, phone_number: str) -> bool:
        """将手机号关联到已有账户"""
        attributes = [
            {"Name": "phone_number", "Value": phone_number},
            {"Name": "phone_number_verified", "Value": "true"},
        ]
        return await self.admin_update_user_attributes(username, attributes)

    @cognito_retry
    async def link_email_to_user(self, username: str, email: str) -> bool:
        """将邮箱关联到已有账户"""
        attributes = [
            {"Name": "email", "Value": email},
            {"Name": "email_verified", "Value": "true"},
        ]
        return await self.admin_update_user_attributes(username, attributes)

    @cognito_retry
    async def list_users_by_email(self, email: str) -> Optional[Dict]:
        """按邮箱查找用户"""
        try:
            response = await asyncio.to_thread(
                self.client.list_users,
                UserPoolId=self.user_pool_id,
                Filter=f'email = "{self._escape_filter_value(email)}"',
                Limit=1,
            )

            users = response.get("Users", [])
            if users:
                user = users[0]
                attributes = {attr["Name"]: attr["Value"] for attr in user.get("Attributes", [])}
                return {
                    "Username": user["Username"],
                    "UserStatus": user.get("UserStatus"),
                    "Attributes": attributes,
                }
            return None

        except ClientError as e:
            raise CognitoException(f"List users failed: {e.response['Error']['Message']}")

    @cognito_retry
    async def get_user_by_sub(self, sub: str) -> Optional[Dict]:
        """按 Cognito sub（用户 ID）查找用户"""
        try:
            response = await asyncio.to_thread(
                self.client.list_users,
                UserPoolId=self.user_pool_id,
                Filter=f'sub = "{self._escape_filter_value(sub)}"',
                Limit=1,
            )

            users = response.get("Users", [])
            if users:
                user = users[0]
                attributes = {attr["Name"]: attr["Value"] for attr in user.get("Attributes", [])}
                return {
                    "Username": user["Username"],
                    "UserStatus": user.get("UserStatus"),
                    "Attributes": attributes,
                }
            return None

        except ClientError as e:
            raise CognitoException(f"List users failed: {e.response['Error']['Message']}")

    @cognito_retry
    async def get_user_attribute_verification_code(
        self, access_token: str, attribute_name: str
    ) -> Dict:
        """获取用户属性验证码"""
        try:
            response = await asyncio.to_thread(
                self.client.get_user_attribute_verification_code,
                AccessToken=access_token,
                AttributeName=attribute_name,
            )
            return response
        except ClientError as e:
            raise CognitoException(
                f"Get verification code failed: {e.response['Error']['Message']}"
            )

    @cognito_retry
    async def verify_user_attribute(
        self, access_token: str, attribute_name: str, code: str
    ) -> bool:
        """验证用户属性（邮箱/手机号）"""
        try:
            await asyncio.to_thread(
                self.client.verify_user_attribute,
                AccessToken=access_token,
                AttributeName=attribute_name,
                Code=code,
            )
            return True
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "CodeMismatchException":
                raise CognitoException("Invalid verification code")
            elif error_code == "ExpiredCodeException":
                raise CognitoException("Verification code expired")
            raise CognitoException(f"Verify attribute failed: {e.response['Error']['Message']}")

    # ============ Password Reset Methods ============

    @cognito_retry
    async def forgot_password(self, username: str) -> Dict:
        """发起忘记密码流程"""
        try:
            params = {
                "ClientId": self.client_id,
                "Username": username,
            }

            if self.client_secret:
                params["SecretHash"] = self._get_secret_hash(username)

            response = await asyncio.to_thread(self.client.forgot_password, **params)

            return {
                "delivery": response.get("CodeDeliveryDetails", {}),
                "message": "Password reset code sent",
            }

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "UserNotFoundException":
                raise UserNotFoundException("User not found")
            raise CognitoException(f"Forgot password failed: {e.response['Error']['Message']}")

    @cognito_retry
    async def confirm_forgot_password(self, username: str, code: str, new_password: str) -> bool:
        """确认忘记密码（使用验证码重置密码）"""
        try:
            params = {
                "ClientId": self.client_id,
                "Username": username,
                "ConfirmationCode": code,
                "Password": new_password,
            }

            if self.client_secret:
                params["SecretHash"] = self._get_secret_hash(username)

            await asyncio.to_thread(self.client.confirm_forgot_password, **params)
            return True

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "CodeMismatchException":
                raise CognitoException("Invalid verification code")
            elif error_code == "ExpiredCodeException":
                raise CognitoException("Verification code expired")
            raise CognitoException(f"Reset password failed: {e.response['Error']['Message']}")
