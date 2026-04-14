"""
Generic Registry Pattern Implementation

Provides reusable registry base classes for common patterns:
- Simple Registry: Basic name -> item mapping
- List Registry: For items that need to be iterated
- Class Registry: For registering class types
- Handler Registry: For event/command handlers

示例:
    # Simple Registry
    class ToolRegistry(Registry[BaseTool]):
        pass
    
    ToolRegistry.register("my_tool", tool_instance)
    tool = ToolRegistry.get("my_tool")
    
    # Handler Registry (multi-handler per key)
    class EventRegistry(HandlerRegistry[Callable]):
        pass
    
    EventRegistry.register("event_name", handler_func)
    EventRegistry.trigger("event_name", event_data)
"""

import logging
from typing import Dict, Generic, List, Set, Type, TypeVar, Any

logger = logging.getLogger(__name__)

T = TypeVar("T")
K = TypeVar("K", str, int)


class Registry(Generic[T]):
    """
    通用注册表基类
    
    提供基本的注册/获取功能，使用字典存储 name -> item 映射。
    
    示例:
        class PluginRegistry(Registry[Plugin]):
            pass
        
        PluginRegistry.register("my_plugin", plugin)
        plugin = PluginRegistry.get("my_plugin")
    """
    
    _items: Dict[str, T] = {}
    
    @classmethod
    def register(cls, name: str, item: T) -> None:
        """
        注册一个项目
        
        Args:
            name: 注册名称
            item: 要注册的项目
        """
        if name in cls._items:
            logger.warning(f"Overwriting existing registration for '{name}' in {cls.__name__}")
        cls._items[name] = item
        logger.debug(f"Registered '{name}' in {cls.__name__}")
    
    @classmethod
    def get(cls, name: str) -> T | None:
        """
        获取注册的项目
        
        Args:
            name: 注册名称
            
        Returns:
            注册的项目，如果不存在返回 None
        """
        return cls._items.get(name)
    
    @classmethod
    def unregister(cls, name: str) -> bool:
        """
        取消注册
        
        Args:
            name: 注册名称
            
        Returns:
            是否成功删除
        """
        if name in cls._items:
            del cls._items[name]
            logger.debug(f"Unregistered '{name}' from {cls.__name__}")
            return True
        return False
    
    @classmethod
    def has(cls, name: str) -> bool:
        """检查是否已注册"""
        return name in cls._items
    
    @classmethod
    def list(cls) -> List[str]:
        """获取所有注册名称"""
        return list(cls._items.keys())
    
    @classmethod
    def get_all(cls) -> List[T]:
        """获取所有注册的项目"""
        return list(cls._items.values())
    
    @classmethod
    def clear(cls) -> None:
        """清空注册表"""
        cls._items.clear()
        logger.debug(f"Cleared {cls.__name__}")
    
    @classmethod
    def count(cls) -> int:
        """获取注册数量"""
        return len(cls._items)


class ListRegistry(Generic[T]):
    """
    列表式注册表
    
    适用于需要遍历执行的场景，如插件、中间件等。
    保持注册顺序。
    
    示例:
        class MiddlewareRegistry(ListRegistry[Middleware]):
            pass
        
        MiddlewareRegistry.register(middleware)
        for mw in MiddlewareRegistry.get_all():
            mw.process()
    """
    
    _items: List[T] = []
    
    @classmethod
    def register(cls, item: T) -> None:
        """注册项目到列表"""
        cls._items.append(item)
        logger.debug(f"Registered item in {cls.__name__}")
    
    @classmethod
    def get_all(cls) -> list[T]:
        """获取所有项目"""
        return list(cls._items)
    
    @classmethod
    def clear(cls) -> None:
        """清空列表"""
        cls._items.clear()
    
    @classmethod
    def count(cls) -> int:
        """获取项目数量"""
        return len(cls._items)
    
    @classmethod
    def is_empty(cls) -> bool:
        """检查是否为空"""
        return len(cls._items) == 0
    
    @classmethod
    def remove(cls, item: T) -> bool:
        """移除特定项目"""
        if item in cls._items:
            cls._items.remove(item)
            return True
        return False


class ClassRegistry(Generic[T]):
    """
    类注册表
    
    用于注册类类型而非实例。获取时自动实例化。
    
    示例:
        class StrategyRegistry(ClassRegistry[BaseStrategy]):
            pass
        
        StrategyRegistry.register("aggressive", AggressiveStrategy)
        strategy = StrategyRegistry.create("aggressive")
    """
    
    _classes: Dict[str, Type[T]] = {}
    
    @classmethod
    def register(cls, name: str, item_class: Type[T]) -> None:
        """
        注册一个类
        
        Args:
            name: 注册名称
            item_class: 要注册的类
        """
        cls._classes[name] = item_class
        logger.debug(f"Registered class '{name}' in {cls.__name__}")
    
    @classmethod
    def get(cls, name: str) -> Type[T] | None:
        """获取注册的类"""
        return cls._classes.get(name)
    
    @classmethod
    def create(cls, name: str, *args, **kwargs) -> T | None:
        """
        创建实例
        
        Args:
            name: 注册名称
            *args, **kwargs: 传递给构造函数的参数
            
        Returns:
            创建的实例，如果类不存在返回 None
        """
        item_class = cls._classes.get(name)
        if item_class:
            return item_class(*args, **kwargs)
        return None
    
    @classmethod
    def list(cls) -> list[str]:
        """获取所有注册名称"""
        return list(cls._classes.keys())
    
    @classmethod
    def get_all_classes(cls) -> List[Type[T]]:
        """获取所有注册的类"""
        return list(cls._classes.values())
    
    @classmethod
    def clear(cls) -> None:
        """清空注册表"""
        cls._classes.clear()


class HandlerRegistry(Generic[T]):
    """
    处理器注册表（支持多处理器）
    
    一个 key 可以对应多个 handler，适用于事件监听等场景。
    
    示例:
        class EventRegistry(HandlerRegistry[Callable]):
            pass
        
        EventRegistry.register("on_start", handler1)
        EventRegistry.register("on_start", handler2)
        EventRegistry.trigger("on_start", event_data)
    """
    
    _handlers: Dict[str, List[T]] = {}
    
    @classmethod
    def register(cls, key: str, handler: T) -> None:
        """
        注册处理器
        
        Args:
            key: 事件/命令 key
            handler: 处理器
        """
        if key not in cls._handlers:
            cls._handlers[key] = []
        cls._handlers[key].append(handler)
        logger.debug(f"Registered handler for '{key}' in {cls.__name__}")
    
    @classmethod
    def get(cls, key: str) -> list[T]:
        """
        获取 key 对应的所有处理器
        
        Args:
            key: 事件/命令 key
            
        Returns:
            处理器列表，如果没有返回空列表
        """
        return list(cls._handlers.get(key, []))
    
    @classmethod
    def unregister(cls, key: str, handler: T) -> bool:
        """
        取消注册特定处理器
        
        Args:
            key: 事件/命令 key
            handler: 要移除的处理器
            
        Returns:
            是否成功移除
        """
        if key in cls._handlers and handler in cls._handlers[key]:
            cls._handlers[key].remove(handler)
            if not cls._handlers[key]:
                del cls._handlers[key]
            return True
        return False
    
    @classmethod
    def clear_key(cls, key: str) -> None:
        """清空特定 key 的所有处理器"""
        if key in cls._handlers:
            del cls._handlers[key]
    
    @classmethod
    def list_keys(cls) -> List[str]:
        """获取所有注册的 key"""
        return list(cls._handlers.keys())
    
    @classmethod
    def clear(cls) -> None:
        """清空所有处理器"""
        cls._handlers.clear()
    
    @classmethod
    def trigger(cls, key: str, *args, **kwargs) -> List[Any]:
        """
        触发所有处理器
        
        执行 key 对应的所有处理器，返回结果列表。
        
        Args:
            key: 事件/命令 key
            *args, **kwargs: 传递给处理器的参数
            
        Returns:
            各处理器的结果列表
        """
        results = []
        handlers = cls._handlers.get(key, [])
        for handler in handlers:
            try:
                result = handler(*args, **kwargs)
                results.append(result)
            except Exception as e:
                logger.error(f"Handler failed for '{key}': {e}")
        return results


class AutoDiscoverRegistry(ListRegistry[T]):
    """
    自动发现注册表
    
    支持自动扫描包并注册符合条件的项目。
    需要子类实现 discover 方法。
    
    示例:
        class ToolRegistry(AutoDiscoverRegistry[BaseTool]):
            @classmethod
            def discover(cls, package_name: str) -> list[BaseTool]:
                # 扫描包并返回发现的工具
                tools = []
                ...
                return tools
        
        ToolRegistry.discover("app.tools")
    """
    
    _scanned_packages: Set[str] = set()
    
    @classmethod
    def discover(cls, package_name: str) -> list[T]:
        """
        扫描包发现项目
        
        子类必须实现此方法。
        
        Args:
            package_name: 包名
            
        Returns:
            发现的项目列表
        """
        raise NotImplementedError("Subclasses must implement discover()")
    
    @classmethod
    def scan(cls, package_name: str) -> int:
        """
        扫描并注册项目
        
        Args:
            package_name: 要扫描的包名
            
        Returns:
            注册的项目数量
        """
        if package_name in cls._scanned_packages:
            return 0
        
        cls._scanned_packages.add(package_name)
        
        try:
            items = cls.discover(package_name)
            for item in items:
                cls.register(item)
            return len(items)
        except Exception as e:
            logger.error(f"Failed to scan package '{package_name}': {e}")
            return 0
    
    @classmethod
    def is_scanned(cls, package_name: str) -> bool:
        """检查包是否已扫描"""
        return package_name in cls._scanned_packages
    
    @classmethod
    def reset_scan(cls) -> None:
        """重置扫描状态，允许重新扫描"""
        cls._scanned_packages.clear()


# 便捷函数
def create_registry(name: str) -> Type[Registry[Any]]:
    """
    动态创建注册表类
    
    示例:
        MyRegistry = create_registry("MyRegistry")
        MyRegistry.register("key", value)
    """
    return type(name, (Registry,), {})
