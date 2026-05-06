"""Comprehensive test suite for ForestGump tools.

Tests cover:
- Tool registry functionality
- Web tools (search, crawl)
- Code execution tool
- Delegate task system
"""

import pytest
import json
import time
from pathlib import Path

from forestgump.tools.registry import (
    ToolRegistry, ToolMetadata, ToolParameter, ToolCategory, ToolStatus,
    get_registry, reset_registry
)
from forestgump.tools.web_tools import (
    URLValidator, WebSearch, WebCrawler, SearchResult, CrawlResult,
    search_web, crawl_urls
)
from forestgump.tools.code_execution_tool import (
    SandboxedREPL, SubprocessExecutor, execute_python_code, evaluate_expression
)
from forestgump.tools.delegate_tool import (
    Task, TaskQueue, TaskDelegate, TaskStatus, TaskPriority,
    create_task, queue_task
)


# ============================================================================
# Tool Registry Tests
# ============================================================================

class TestToolRegistry:
    """Test the tool registry system."""
    
    def setup_method(self):
        """Reset registry before each test."""
        reset_registry()
    
    def test_registry_register_tool(self):
        """Test registering a tool."""
        registry = ToolRegistry()
        
        def dummy_tool(arg1: str) -> str:
            """Dummy tool for testing."""
            return f"Result: {arg1}"
        
        metadata = ToolMetadata(
            name="dummy_tool",
            description="A dummy tool",
            category=ToolCategory.UTILITY
        )
        
        registry.register("dummy_tool", dummy_tool, metadata)
        
        assert "dummy_tool" in registry
        assert registry.get("dummy_tool") is dummy_tool
    
    def test_registry_tool_aliases(self):
        """Test tool aliases."""
        registry = ToolRegistry()
        
        def my_func():
            return "result"
        
        metadata = ToolMetadata(
            name="my_func",
            description="Test",
            category=ToolCategory.UTILITY
        )
        
        registry.register("my_func", my_func, metadata, aliases=["mf", "test_func"])
        
        assert registry.get("my_func") is my_func
        assert registry.get("mf") is my_func
        assert registry.get("test_func") is my_func
    
    def test_registry_unregister_tool(self):
        """Test unregistering a tool."""
        registry = ToolRegistry()
        
        def tool():
            pass
        
        metadata = ToolMetadata(
            name="tool",
            description="Test",
            category=ToolCategory.UTILITY
        )
        
        registry.register("tool", tool, metadata)
        assert "tool" in registry
        
        registry.unregister("tool")
        assert "tool" not in registry
    
    def test_registry_invoke_tool(self):
        """Test invoking a tool."""
        registry = ToolRegistry()
        
        def add(a: int, b: int) -> int:
            return a + b
        
        metadata = ToolMetadata(
            name="add",
            description="Add two numbers",
            category=ToolCategory.UTILITY,
            parameters=[
                ToolParameter(name="a", type_="int", required=True),
                ToolParameter(name="b", type_="int", required=True),
            ]
        )
        
        registry.register("add", add, metadata)
        
        result = registry.invoke("add", a=5, b=3)
        assert result == 8
    
    def test_registry_list_tools_by_category(self):
        """Test listing tools by category."""
        registry = ToolRegistry()
        
        def web_tool():
            pass
        
        def code_tool():
            pass
        
        registry.register(
            "web_tool",
            web_tool,
            ToolMetadata(name="web_tool", description="", category=ToolCategory.WEB)
        )
        registry.register(
            "code_tool",
            code_tool,
            ToolMetadata(name="code_tool", description="", category=ToolCategory.CODE)
        )
        
        tools_by_cat = registry.list_by_category()
        assert "web_tool" in tools_by_cat[ToolCategory.WEB]
        assert "code_tool" in tools_by_cat[ToolCategory.CODE]
    
    def test_registry_tool_dependencies(self):
        """Test tool dependency validation."""
        registry = ToolRegistry()
        
        def tool_a():
            pass
        
        def tool_b():
            pass
        
        registry.register(
            "tool_a",
            tool_a,
            ToolMetadata(name="tool_a", description="", category=ToolCategory.UTILITY)
        )
        
        registry.register(
            "tool_b",
            tool_b,
            ToolMetadata(
                name="tool_b",
                description="",
                category=ToolCategory.UTILITY,
                dependencies=["tool_a", "tool_c"]
            )
        )
        
        is_valid, missing = registry.validate_dependencies("tool_b")
        assert not is_valid
        assert missing == "tool_c"
    
    def test_registry_export_metadata(self):
        """Test exporting tool metadata."""
        registry = ToolRegistry()
        
        def tool():
            pass
        
        metadata = ToolMetadata(
            name="tool",
            description="Test tool",
            category=ToolCategory.UTILITY,
            version="1.0.0",
            tags=["test", "utility"]
        )
        
        registry.register("tool", tool, metadata)
        
        exported = registry.export_metadata("tool")
        assert exported["name"] == "tool"
        assert exported["description"] == "Test tool"
        assert "test" in exported["tags"]


# ============================================================================
# Web Tools Tests
# ============================================================================

class TestURLValidator:
    """Test URL validation."""
    
    def test_valid_url(self):
        """Test valid URL validation."""
        assert URLValidator.is_valid("https://example.com")
        assert URLValidator.is_valid("http://example.com/path")
        assert URLValidator.is_valid("https://sub.example.com")
    
    def test_invalid_url(self):
        """Test invalid URL detection."""
        assert not URLValidator.is_valid("not a url")
        assert not URLValidator.is_valid("example.com")
        assert not URLValidator.is_valid("")
    
    def test_url_normalization(self):
        """Test URL normalization."""
        assert URLValidator.normalize("example.com") == "https://example.com"
        assert URLValidator.normalize("http://example.com") == "http://example.com"
        assert URLValidator.normalize("  https://example.com  ") == "https://example.com"


class TestSearchResult:
    """Test search result dataclass."""
    
    def test_search_result_creation(self):
        """Test creating search results."""
        result = SearchResult(
            title="Example",
            url="https://example.com",
            snippet="Test snippet",
            source="test"
        )
        
        assert result.title == "Example"
        assert result.url == "https://example.com"
        assert result.timestamp is not None


class TestCrawlResult:
    """Test crawl result dataclass."""
    
    def test_crawl_result_creation(self):
        """Test creating crawl results."""
        result = CrawlResult(
            url="https://example.com",
            status_code=200,
            content_type="text/html",
            title="Example",
            links=["https://example.com/page"]
        )
        
        assert result.url == "https://example.com"
        assert result.status_code == 200
        assert len(result.links) == 1


# ============================================================================
# Code Execution Tests
# ============================================================================

class TestSandboxedREPL:
    """Test sandboxed Python REPL."""
    
    def test_simple_execution(self):
        """Test simple code execution."""
        repl = SandboxedREPL()
        
        result = repl.execute("x = 5 + 3")
        
        assert result.success
        assert result.lines_executed == 1
        assert result.execution_time > 0
    
    def test_print_output(self):
        """Test capturing print output."""
        repl = SandboxedREPL()
        
        result = repl.execute("print('Hello, World!')")
        
        assert result.success
        assert "Hello, World!" in result.output
    
    def test_syntax_error(self):
        """Test syntax error handling."""
        repl = SandboxedREPL()
        
        result = repl.execute("x = ")
        
        assert not result.success
        assert "SyntaxError" in result.error
    
    def test_runtime_error(self):
        """Test runtime error handling."""
        repl = SandboxedREPL()
        
        result = repl.execute("x = 1 / 0")
        
        assert not result.success
        assert "ZeroDivisionError" in result.error
    
    def test_expression_evaluation(self):
        """Test expression evaluation."""
        repl = SandboxedREPL()
        
        result = repl.evaluate("2 ** 8")
        
        assert result.success
        assert result.return_value == 256
    
    def test_repl_state_persistence(self):
        """Test state persistence across executions."""
        repl = SandboxedREPL()
        
        repl.execute("x = 10")
        result = repl.evaluate("x * 2")
        
        assert result.success
        assert result.return_value == 20
    
    def test_restricted_builtins(self):
        """Test that restricted builtins are disabled."""
        repl = SandboxedREPL()
        
        # Try to access file operations
        result = repl.execute("open('/etc/passwd')")
        
        # Should fail or not access the file
        assert "'open' is not defined" in result.error or "not defined" in result.error
    
    def test_reset(self):
        """Test resetting REPL state."""
        repl = SandboxedREPL()
        
        repl.execute("x = 42")
        repl.reset()
        result = repl.evaluate("x")
        
        assert not result.success  # x should not exist


class TestSubprocessExecutor:
    """Test subprocess executor."""
    
    def test_simple_subprocess_execution(self):
        """Test simple subprocess execution."""
        executor = SubprocessExecutor()
        
        result = executor.execute("print('Hello from subprocess')")
        
        assert result.success
        assert "Hello from subprocess" in result.output
    
    def test_subprocess_error(self):
        """Test subprocess error handling."""
        executor = SubprocessExecutor()
        
        result = executor.execute("raise ValueError('Test error')")
        
        assert not result.success
        assert result.error


# ============================================================================
# Task Delegation Tests
# ============================================================================

class TestTask:
    """Test Task dataclass."""
    
    def test_task_creation(self):
        """Test creating a task."""
        task = Task(
            task_id="task_1",
            name="Test Task",
            description="A test task",
            instructions="Do something"
        )
        
        assert task.task_id == "task_1"
        assert task.status == TaskStatus.PENDING
    
    def test_task_serialization(self):
        """Test task serialization."""
        task = Task(
            task_id="task_1",
            name="Test",
            description="Test task",
            instructions="Do it",
            priority=TaskPriority.HIGH
        )
        
        data = task.to_dict()
        assert data["priority"] == "high"
        assert data["status"] == "pending"
        
        task2 = Task.from_dict(data)
        assert task2.priority == TaskPriority.HIGH
    
    def test_task_duration(self):
        """Test task duration calculation."""
        task = Task(
            task_id="task_1",
            name="Test",
            description="Test",
            instructions="Test"
        )
        
        task.started_at = time.time()
        time.sleep(0.1)
        task.completed_at = time.time()
        
        duration = task.get_duration()
        assert duration >= 0.1


class TestTaskQueue:
    """Test TaskQueue."""
    
    def test_add_task(self):
        """Test adding tasks to queue."""
        queue = TaskQueue()
        
        task = Task(
            task_id="task_1",
            name="Test",
            description="Test task",
            instructions="Do something"
        )
        
        queue.add_task(task)
        
        assert len(queue.tasks) == 1
        assert queue.get_task("task_1") is task
    
    def test_task_status_update(self):
        """Test updating task status."""
        queue = TaskQueue()
        
        task = Task(
            task_id="task_1",
            name="Test",
            description="Test",
            instructions="Test"
        )
        
        queue.add_task(task)
        queue.update_task_status("task_1", TaskStatus.RUNNING)
        
        task = queue.get_task("task_1")
        assert task.status == TaskStatus.RUNNING
        assert task.started_at is not None
    
    def test_pending_tasks(self):
        """Test getting pending tasks."""
        queue = TaskQueue()
        
        task1 = Task(task_id="t1", name="T1", description="", instructions="")
        task2 = Task(task_id="t2", name="T2", description="", instructions="")
        
        queue.add_task(task1)
        queue.add_task(task2)
        queue.update_task_status("t1", TaskStatus.RUNNING)
        
        pending = queue.get_pending_tasks()
        
        assert len(pending) == 1
        assert pending[0].task_id == "t2"
    
    def test_task_dependencies(self):
        """Test task dependency resolution."""
        queue = TaskQueue()
        
        task1 = Task(task_id="t1", name="T1", description="", instructions="")
        task2 = Task(
            task_id="t2",
            name="T2",
            description="",
            instructions="",
            dependencies=["t1"]
        )
        
        queue.add_task(task1)
        queue.add_task(task2)
        
        # Task 2 should not be runnable yet
        runnable = queue.get_runnable_tasks()
        assert len(runnable) == 1
        assert runnable[0].task_id == "t1"
        
        # Complete task 1
        queue.update_task_status("t1", TaskStatus.COMPLETED)
        
        # Now task 2 should be runnable
        runnable = queue.get_runnable_tasks()
        assert len(runnable) == 1
        assert runnable[0].task_id == "t2"
    
    def test_priority_ordering(self):
        """Test task priority ordering."""
        queue = TaskQueue()
        
        task1 = Task(
            task_id="t1",
            name="Low",
            description="",
            instructions="",
            priority=TaskPriority.LOW
        )
        task2 = Task(
            task_id="t2",
            name="High",
            description="",
            instructions="",
            priority=TaskPriority.HIGH
        )
        
        queue.add_task(task1)
        queue.add_task(task2)
        
        runnable = queue.get_runnable_tasks()
        assert runnable[0].priority == TaskPriority.HIGH
    
    def test_queue_stats(self):
        """Test queue statistics."""
        queue = TaskQueue()
        
        task1 = Task(task_id="t1", name="T1", description="", instructions="")
        task2 = Task(task_id="t2", name="T2", description="", instructions="")
        
        queue.add_task(task1)
        queue.add_task(task2)
        queue.update_task_status("t1", TaskStatus.COMPLETED)
        
        stats = queue.get_stats()
        
        assert stats["total_tasks"] == 2
        assert stats["pending"] == 1
        assert stats["completed"] == 1


class TestTaskDelegate:
    """Test TaskDelegate."""
    
    def test_create_task(self):
        """Test creating a task through delegate."""
        delegate = TaskDelegate()
        
        task = delegate.create_task(
            name="Test Task",
            instructions="Do something"
        )
        
        assert task.name == "Test Task"
        assert task.status == TaskStatus.PENDING
    
    def test_execute_task(self):
        """Test executing a task."""
        delegate = TaskDelegate(executor=lambda x: f"Executed: {x}")
        
        task = delegate.create_task(
            name="Test",
            instructions="Do it"
        )
        
        result = delegate.execute_task(task.task_id)
        
        assert result.success
        assert "Executed" in result.output
    
    def test_queue_status(self):
        """Test getting queue status."""
        delegate = TaskDelegate()
        
        delegate.create_task(name="T1", instructions="Do it")
        delegate.create_task(name="T2", instructions="Do it")
        
        status = delegate.get_queue_status()
        
        assert status["stats"]["total_tasks"] == 2
        assert len(status["runnable_tasks"]) > 0


# ============================================================================
# Integration Tests
# ============================================================================

class TestToolsIntegration:
    """Integration tests for all tools."""
    
    def test_registry_with_all_tools(self):
        """Test registering all tool types."""
        reset_registry()
        registry = get_registry()
        
        # Register different tool types
        def search(query: str):
            return {"results": []}
        
        def execute(code: str):
            return {"output": ""}
        
        def delegate(task: str):
            return {"task_id": "123"}
        
        registry.register(
            "search",
            search,
            ToolMetadata(
                name="search",
                description="Search tool",
                category=ToolCategory.WEB
            )
        )
        
        registry.register(
            "execute",
            execute,
            ToolMetadata(
                name="execute",
                description="Execute tool",
                category=ToolCategory.CODE
            )
        )
        
        registry.register(
            "delegate",
            delegate,
            ToolMetadata(
                name="delegate",
                description="Delegate tool",
                category=ToolCategory.UTILITY
            )
        )
        
        assert len(registry) == 3
        assert "search" in registry
        assert "execute" in registry
        assert "delegate" in registry
    
    def test_end_to_end_code_execution(self):
        """Test end-to-end code execution."""
        result = execute_python_code(
            "x = [1, 2, 3, 4, 5]\ny = sum(x)\nprint(f'Sum: {y}')"
        )
        
        assert result["success"]
        assert "Sum: 15" in result["output"]
    
    def test_end_to_end_task_delegation(self):
        """Test end-to-end task delegation."""
        result = queue_task(
            name="Test Task",
            instructions="Execute test"
        )
        
        assert result["status"] == "pending"
        assert "task_id" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
