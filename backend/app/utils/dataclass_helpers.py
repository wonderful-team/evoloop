"""
Dataclass 序列化辅助工具

提供通用的序列化/反序列化 Mixin，减少重复代码。

示例:
    @dataclass
    class MyElement(SerializableMixin):
        role: str = ""
        label: str = ""
        
    # 使用
    element = MyElement(role="button", label="Save")
    data = element.to_dict()
    restored = MyElement.from_dict(data)
"""

from dataclasses import asdict
from datetime import datetime
from typing import TypeVar, Type, Any, get_type_hints

T = TypeVar("T")


class SerializableMixin:
    """
    为 dataclass 提供自动序列化支持
    
    提供基础的 to_dict/from_dict 实现，支持:
    - 自动字段映射
    - 类型过滤（忽略无效字段）
    - 嵌套对象支持（如果嵌套对象也有 SerializableMixin）
    """
    
    def to_dict(self) -> dict[str, Any]:
        """
        将实例转换为字典
        
        Returns:
            包含所有字段的字典
        """
        return asdict(self)
    
    @classmethod
    def from_dict(cls: Type[T], data: dict[str, Any]) -> T:
        """
        从字典创建实例
        
        自动过滤掉 dataclass 中不存在的字段
        
        Args:
            data: 包含字段数据的字典
            
        Returns:
            新创建的实例
        """
        # 获取有效的字段名
        valid_fields = set(cls.__dataclass_fields__.keys())
        
        # 过滤掉无效的字段
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        
        return cls(**filtered)


class NestedSerializableMixin(SerializableMixin):
    """
    支持嵌套序列化的 Mixin
    
    适用于包含其他 SerializableMixin 实例的类
    会自动递归转换嵌套对象
    
    示例:
        @dataclass
        class AtlasState(NestedSerializableMixin):
            elements: list[AtlasElement]  # AtlasElement 也有 SerializableMixin
    """
    
    def to_dict(self) -> dict[str, Any]:
        """
        递归转换为字典
        
        如果字段值有 to_dict 方法，会递归调用
        """
        result: dict[str, Any] = {}
        for key, value in asdict(self).items():
            if value is None:
                result[key] = None
            elif hasattr(value, 'to_dict'):
                result[key] = value.to_dict()
            elif isinstance(value, list):
                result[key] = [
                    item.to_dict() if hasattr(item, 'to_dict') else item
                    for item in value
                ]
            elif isinstance(value, dict):
                result[key] = {
                    k: v.to_dict() if hasattr(v, 'to_dict') else v
                    for k, v in value.items()
                }
            elif isinstance(value, datetime):
                result[key] = value.isoformat()
            else:
                result[key] = value
        return result


class AutoConvertMixin(SerializableMixin):
    """
    自动类型转换 Mixin
    
    在 from_dict 时尝试自动转换类型，如:
    - ISO 格式字符串 -> datetime
    - 字典 -> 嵌套 dataclass
    
    注意：需要正确标注类型注解
    """
    
    @classmethod
    def from_dict(cls: Type[T], data: dict[str, Any]) -> T:
        """
        从字典创建实例，支持自动类型转换
        """
        if not hasattr(cls, '__dataclass_fields__'):
            return cls(**data)  # type: ignore
        
        valid_fields = cls.__dataclass_fields__
        type_hints = get_type_hints(cls)
        
        converted: dict[str, Any] = {}
        for key, value in data.items():
            if key not in valid_fields:
                continue
            
            field_type = type_hints.get(key)
            if field_type is None:
                converted[key] = value
                continue
            
            # 尝试类型转换
            converted[key] = cls._convert_value(value, field_type)
        
        return cls(**converted)
    
    @classmethod
    def _convert_value(cls, value: Any, target_type: Any) -> Any:
        """尝试将值转换为目标类型"""
        if value is None:
            return None
        
        # 处理 datetime
        if target_type is datetime and isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return value
        
        # 处理列表
        origin = getattr(target_type, '__origin__', None)
        if origin is list and isinstance(value, list):
            args = getattr(target_type, '__args__', ())
            if args:
                item_type = args[0]
                return [
                    cls._convert_value(item, item_type) for item in value
                ]
        
        # 处理 Optional
        if origin is not None and type(None) in getattr(target_type, '__args__', ()):
            # 是 Optional[T]，尝试转换 T
            args = [a for a in getattr(target_type, '__args__', ()) if a is not type(None)]
            if args and value is not None:
                return cls._convert_value(value, args[0])
        
        return value


# 便捷函数
def to_dict_list(items: list[Any]) -> list[dict]:
    """
    将对象列表转换为字典列表
    
    Args:
        items: 包含 to_dict 方法的对象列表
        
    Returns:
        字典列表
    """
    return [
        item.to_dict() if hasattr(item, 'to_dict') else item
        for item in items
    ]


def from_dict_list(cls: Type[T], data_list: list[dict]) -> list[T]:
    """
    从字典列表创建对象列表
    
    Args:
        cls: 目标类（需要实现 from_dict）
        data_list: 字典列表
        
    Returns:
        对象列表
    """
    return [
        cls.from_dict(data) if hasattr(cls, 'from_dict') else cls(**data)
        for data in data_list
    ]
