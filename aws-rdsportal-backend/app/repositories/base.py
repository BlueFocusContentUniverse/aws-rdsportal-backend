"""
Repository 层基础模块

提供数据访问抽象，实现以下目标：
1. 解耦 API 层与数据库实现
2. 便于单元测试（可 mock）
3. 集中管理数据访问逻辑
4. 支持未来切换数据库
"""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar, Optional, List

from sqlalchemy.orm import Session

# 泛型类型
T = TypeVar("T")  # 模型类型
ID = TypeVar("ID")  # 主键类型


class BaseRepository(ABC, Generic[T, ID]):
    """
    Repository 基类

    提供通用的 CRUD 操作接口
    """

    def __init__(self, db: Session):
        self.db = db

    @abstractmethod
    def get_by_id(self, id: ID) -> Optional[T]:
        """根据 ID 获取单个实体"""
        pass

    @abstractmethod
    def get_all(self, skip: int = 0, limit: int = 100) -> List[T]:
        """获取所有实体（分页）"""
        pass

    @abstractmethod
    def create(self, entity: T) -> T:
        """创建实体"""
        pass

    @abstractmethod
    def update(self, entity: T) -> T:
        """更新实体"""
        pass

    @abstractmethod
    def delete(self, id: ID) -> bool:
        """删除实体"""
        pass


class SQLAlchemyRepository(BaseRepository[T, ID]):
    """
    SQLAlchemy 实现的 Repository 基类

    子类只需指定 model_class 即可获得基础 CRUD 功能
    """

    model_class: type = None  # 子类必须指定

    def __init__(self, db: Session):
        super().__init__(db)
        if self.model_class is None:
            raise ValueError("model_class must be specified in subclass")

    def get_by_id(self, id: ID) -> Optional[T]:
        """根据主键获取实体"""
        return self.db.query(self.model_class).get(id)

    def get_all(self, skip: int = 0, limit: int = 100) -> List[T]:
        """获取所有实体（分页）"""
        return self.db.query(self.model_class).offset(skip).limit(limit).all()

    def create(self, entity: T) -> T:
        """创建实体"""
        self.db.add(entity)
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def update(self, entity: T) -> T:
        """更新实体"""
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def delete(self, id: ID) -> bool:
        """删除实体"""
        entity = self.get_by_id(id)
        if entity:
            self.db.delete(entity)
            self.db.commit()
            return True
        return False

    def exists(self, id: ID) -> bool:
        """检查实体是否存在"""
        return self.get_by_id(id) is not None
