"""
Tests for the registry module.

Tests the various registry base classes:
- Registry: Basic name -> item mapping
- ListRegistry: Ordered list of items
- ClassRegistry: Name -> class mapping
- HandlerRegistry: Multi-handler per key
- AutoDiscoverRegistry: With automatic discovery
"""

import pytest
from typing import Dict, List, Set, Type
from app.utils.registry import (
    AutoDiscoverRegistry,
    ClassRegistry,
    HandlerRegistry,
    ListRegistry,
    Registry,
    create_registry,
)


class TestRegistry:
    """Tests for the basic Registry class"""

    def setup_method(self):
        """Create a fresh registry for each test"""
        class TestReg(Registry[str]):
            _items: Dict[str, str] = {}

        self.TestReg = TestReg

    def teardown_method(self):
        """Clear registry after each test"""
        self.TestReg.clear()

    def test_register_and_get(self):
        """Test basic register/get operations"""
        self.TestReg.register("key1", "value1")
        assert self.TestReg.get("key1") == "value1"
        assert self.TestReg.get("nonexistent") is None

    def test_has(self):
        """Test has() method"""
        self.TestReg.register("key1", "value1")
        assert self.TestReg.has("key1")
        assert not self.TestReg.has("key2")

    def test_list(self):
        """Test listing registered keys"""
        self.TestReg.register("key1", "value1")
        self.TestReg.register("key2", "value2")
        keys = self.TestReg.list()
        assert sorted(keys) == ["key1", "key2"]

    def test_get_all(self):
        """Test getting all registered values"""
        self.TestReg.register("key1", "value1")
        self.TestReg.register("key2", "value2")
        values = self.TestReg.get_all()
        assert sorted(values) == ["value1", "value2"]

    def test_unregister(self):
        """Test unregister operation"""
        self.TestReg.register("key1", "value1")
        assert self.TestReg.unregister("key1")
        assert self.TestReg.get("key1") is None
        assert not self.TestReg.unregister("nonexistent")

    def test_clear(self):
        """Test clearing all registrations"""
        self.TestReg.register("key1", "value1")
        self.TestReg.register("key2", "value2")
        self.TestReg.clear()
        assert self.TestReg.count() == 0
        assert self.TestReg.list() == []

    def test_count(self):
        """Test counting registrations"""
        assert self.TestReg.count() == 0
        self.TestReg.register("key1", "value1")
        assert self.TestReg.count() == 1
        self.TestReg.register("key2", "value2")
        assert self.TestReg.count() == 2

    def test_overwrite_warning(self, caplog):
        """Test that overwriting logs a warning"""
        self.TestReg.register("key1", "value1")
        with caplog.at_level("WARNING"):
            self.TestReg.register("key1", "value2")
        assert "Overwriting existing registration" in caplog.text


class TestListRegistry:
    """Tests for the ListRegistry class"""

    def setup_method(self):
        """Create a fresh registry for each test"""
        class TestListReg(ListRegistry[str]):
            _items: List[str] = []

        self.TestListReg = TestListReg

    def teardown_method(self):
        """Clear registry after each test"""
        self.TestListReg.clear()

    def test_register_and_get_all(self):
        """Test registering items and getting all"""
        self.TestListReg.register("item1")
        self.TestListReg.register("item2")
        assert self.TestListReg.get_all() == ["item1", "item2"]

    def test_count(self):
        """Test counting items"""
        assert self.TestListReg.count() == 0
        self.TestListReg.register("item1")
        assert self.TestListReg.count() == 1

    def test_is_empty(self):
        """Test is_empty check"""
        assert self.TestListReg.is_empty()
        self.TestListReg.register("item1")
        assert not self.TestListReg.is_empty()

    def test_remove(self):
        """Test removing specific items"""
        self.TestListReg.register("item1")
        self.TestListReg.register("item2")
        assert self.TestListReg.remove("item1")
        assert self.TestListReg.get_all() == ["item2"]
        assert not self.TestListReg.remove("nonexistent")

    def test_clear(self):
        """Test clearing all items"""
        self.TestListReg.register("item1")
        self.TestListReg.register("item2")
        self.TestListReg.clear()
        assert self.TestListReg.count() == 0


class TestClassRegistry:
    """Tests for the ClassRegistry class"""

    class MyClass:
        def __init__(self, value: str = "default"):
            self.value = value

    def setup_method(self):
        """Create a fresh registry for each test"""
        test_class = self.MyClass

        class TestClassReg(ClassRegistry[test_class]):  # type: ignore
            _classes: Dict[str, Type[test_class]] = {}  # type: ignore

        self.TestClassReg = TestClassReg
        self.MyClass = test_class

    def teardown_method(self):
        """Clear registry after each test"""
        self.TestClassReg.clear()

    def test_register_and_get(self):
        """Test registering and getting classes"""
        self.TestClassReg.register("myclass", self.MyClass)
        assert self.TestClassReg.get("myclass") == self.MyClass
        assert self.TestClassReg.get("nonexistent") is None

    def test_create_instance(self):
        """Test creating instances"""
        self.TestClassReg.register("myclass", self.MyClass)
        instance = self.TestClassReg.create("myclass")
        assert isinstance(instance, self.MyClass)
        assert instance.value == "default"

    def test_create_with_args(self):
        """Test creating instances with arguments"""
        self.TestClassReg.register("myclass", self.MyClass)
        instance = self.TestClassReg.create("myclass", value="custom")
        assert isinstance(instance, self.MyClass)
        assert instance.value == "custom"

    def test_create_nonexistent(self):
        """Test creating from nonexistent key"""
        assert self.TestClassReg.create("nonexistent") is None

    def test_list(self):
        """Test listing registered classes"""
        self.TestClassReg.register("myclass1", self.MyClass)
        self.TestClassReg.register("myclass2", self.MyClass)
        keys = self.TestClassReg.list()
        assert sorted(keys) == ["myclass1", "myclass2"]

    def test_get_all_classes(self):
        """Test getting all registered classes"""
        class AnotherClass:
            pass

        self.TestClassReg.register("myclass", self.MyClass)
        self.TestClassReg.register("another", AnotherClass)
        classes = self.TestClassReg.get_all_classes()
        assert self.MyClass in classes
        assert AnotherClass in classes


class TestHandlerRegistry:
    """Tests for the HandlerRegistry class"""

    def setup_method(self):
        """Create a fresh registry for each test"""
        class TestHandlerReg(HandlerRegistry[callable]):  # type: ignore
            _handlers: Dict[str, List[callable]] = {}  # type: ignore

        self.TestHandlerReg = TestHandlerReg

    def teardown_method(self):
        """Clear registry after each test"""
        self.TestHandlerReg.clear()

    def test_register_and_get(self):
        """Test registering and getting handlers"""
        handler1 = lambda x: x + 1
        handler2 = lambda x: x + 2

        self.TestHandlerReg.register("event", handler1)
        self.TestHandlerReg.register("event", handler2)

        handlers = self.TestHandlerReg.get("event")
        assert len(handlers) == 2
        assert handler1 in handlers
        assert handler2 in handlers

    def test_get_empty(self):
        """Test getting handlers for nonexistent key"""
        assert self.TestHandlerReg.get("nonexistent") == []

    def test_unregister(self):
        """Test unregistering specific handlers"""
        handler1 = lambda x: x + 1
        handler2 = lambda x: x + 2

        self.TestHandlerReg.register("event", handler1)
        self.TestHandlerReg.register("event", handler2)
        assert self.TestHandlerReg.unregister("event", handler1)
        assert len(self.TestHandlerReg.get("event")) == 1
        assert not self.TestHandlerReg.unregister("event", handler1)

    def test_clear_key(self):
        """Test clearing all handlers for a key"""
        handler = lambda x: x

        self.TestHandlerReg.register("event1", handler)
        self.TestHandlerReg.register("event2", handler)
        self.TestHandlerReg.clear_key("event1")

        assert self.TestHandlerReg.get("event1") == []
        assert len(self.TestHandlerReg.get("event2")) == 1

    def test_list_keys(self):
        """Test listing all registered keys"""
        handler = lambda x: x

        self.TestHandlerReg.register("event1", handler)
        self.TestHandlerReg.register("event2", handler)

        keys = self.TestHandlerReg.list_keys()
        assert sorted(keys) == ["event1", "event2"]

    def test_trigger(self):
        """Test triggering handlers"""
        results = []

        def handler1(x):
            results.append(1)
            return x + 1

        def handler2(x):
            results.append(2)
            return x + 2

        self.TestHandlerReg.register("event", handler1)
        self.TestHandlerReg.register("event", handler2)

        results = self.TestHandlerReg.trigger("event", 10)
        assert sorted(results) == [11, 12]

    def test_trigger_no_handlers(self):
        """Test triggering with no handlers"""
        results = self.TestHandlerReg.trigger("nonexistent")
        assert results == []

    def test_trigger_error_handling(self, caplog):
        """Test error handling during trigger"""
        def good_handler(x):
            return x + 1

        def bad_handler(x):
            raise ValueError("test error")

        self.TestHandlerReg.register("event", good_handler)
        self.TestHandlerReg.register("event", bad_handler)

        with caplog.at_level("ERROR"):
            results = self.TestHandlerReg.trigger("event", 10)

        assert results == [11]  # Good handler still runs
        assert "Handler failed" in caplog.text


class TestAutoDiscoverRegistry:
    """Tests for the AutoDiscoverRegistry class"""

    def setup_method(self):
        """Create a fresh registry for each test"""
        class TestAutoReg(AutoDiscoverRegistry[str]):
            _items: List[str] = []
            _scanned_packages: Set[str] = set()

            @classmethod
            def discover(cls, package_name: str) -> List[str]:
                if package_name == "test_package":
                    return ["item1", "item2"]
                raise ImportError(f"Package {package_name} not found")

        self.TestAutoReg = TestAutoReg

    def teardown_method(self):
        """Clear registry after each test"""
        self.TestAutoReg.clear()
        self.TestAutoReg.reset_scan()

    def test_scan_and_discover(self):
        """Test scanning a package"""
        count = self.TestAutoReg.scan("test_package")
        assert count == 2
        assert self.TestAutoReg.get_all() == ["item1", "item2"]

    def test_scan_already_scanned(self):
        """Test that double scanning is skipped"""
        self.TestAutoReg.scan("test_package")
        count = self.TestAutoReg.scan("test_package")
        assert count == 0  # Already scanned

    def test_is_scanned(self):
        """Test checking if package was scanned"""
        assert not self.TestAutoReg.is_scanned("test_package")
        self.TestAutoReg.scan("test_package")
        assert self.TestAutoReg.is_scanned("test_package")

    def test_scan_error(self, caplog):
        """Test error handling during scan"""
        with caplog.at_level("ERROR"):
            count = self.TestAutoReg.scan("bad_package")
        assert count == 0
        assert "Failed to scan package" in caplog.text

    def test_reset_scan(self):
        """Test resetting scan status"""
        self.TestAutoReg.scan("test_package")
        assert self.TestAutoReg.is_scanned("test_package")
        self.TestAutoReg.reset_scan()
        assert not self.TestAutoReg.is_scanned("test_package")

    def test_discover_not_implemented(self):
        """Test that discover must be implemented"""
        class BadRegistry(AutoDiscoverRegistry[str]):
            _items: List[str] = []
            _scanned_packages: Set[str] = set()

        with pytest.raises(NotImplementedError):
            BadRegistry.discover("test")


class TestCreateRegistry:
    """Tests for the create_registry helper"""

    def test_create_registry(self):
        """Test dynamically creating a registry"""
        MyRegistry = create_registry("MyRegistry")
        assert MyRegistry.__name__ == "MyRegistry"
        assert issubclass(MyRegistry, Registry)

        MyRegistry.register("key", "value")
        assert MyRegistry.get("key") == "value"
