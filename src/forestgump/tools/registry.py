"""Tool registry and management system for ForestGump.

This module implements a modular tool registry pattern adapted from Hermes,
enabling ForestGump to dynamically manage, discover, and invoke tools.

Features:
- Tool registration and discovery
- Tool metadata management
- Tool validation and error handling
- Hierarchical tool organization
- Tool dependency management
"""

import inspect
from typing import (
    Any, Callable, Dict, List, Optional, Type, Union, Tuple
)
from dataclasses import dataclass, field, asdict
from enum import Enum
import json


class ToolCategory(str, Enum):
    """Tool categories for organization and filtering."""
    
    WEB = "web"
    CODE = "code"
    SYSTEM = "system"
    ANALYSIS = "analysis"
    RECON = "recon"
    EXPLOIT = "exploit"
    UTILITY = "utility"


class ToolStatus(str, Enum):
    """Tool operational status."""
    
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    EXPERIMENTAL = "experimental"
    DISABLED = "disabled"


@dataclass
class ToolParameter:
    """Parameter definition for a tool."""
    
    name: str
    type_: str = "str"
    required: bool = True
    description: str = ""
    default: Optional[Any] = None
    choices: Optional[List[Any]] = None
    
    def validate(self, value: Any) -> Tuple[bool, Optional[str]]:
        """
        Validate a value against this parameter definition.
        
        Args:
            value: Value to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if self.choices and value not in self.choices:
            return False, f"Value must be one of {self.choices}"
        
        # Basic type checking
        type_map = {
            "str": str,
            "int": int,
            "float": float,
            "bool": bool,
            "list": list,
            "dict": dict,
        }
        
        expected_type = type_map.get(self.type_)
        if expected_type and not isinstance(value, expected_type):
            return False, f"Expected {self.type_}, got {type(value).__name__}"
        
        return True, None


@dataclass
class ToolMetadata:
    """Metadata for a registered tool."""
    
    name: str
    description: str
    category: ToolCategory
    parameters: List[ToolParameter] = field(default_factory=list)
    status: ToolStatus = ToolStatus.ACTIVE
    version: str = "1.0.0"
    author: str = "ForestGump"
    tags: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    timeout: Optional[int] = None
    require_auth: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metadata to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolMetadata":
        """Create metadata from dictionary."""
        # Convert nested objects
        parameters = [
            ToolParameter(**p) if isinstance(p, dict) else p 
            for p in data.get("parameters", [])
        ]
        
        return cls(
            name=data["name"],
            description=data["description"],
            category=ToolCategory(data.get("category", "utility")),
            parameters=parameters,
            status=ToolStatus(data.get("status", "active")),
            version=data.get("version", "1.0.0"),
            author=data.get("author", "ForestGump"),
            tags=data.get("tags", []),
            dependencies=data.get("dependencies", []),
            timeout=data.get("timeout"),
            require_auth=data.get("require_auth", False),
        )


class ToolRegistry:
    """Central registry for managing tools."""
    
    def __init__(self):
        """Initialize the tool registry."""
        self._tools: Dict[str, Callable] = {}
        self._metadata: Dict[str, ToolMetadata] = {}
        self._aliases: Dict[str, str] = {}
        self._categories: Dict[ToolCategory, List[str]] = {
            cat: [] for cat in ToolCategory
        }
    
    def register(
        self,
        name: str,
        func: Callable,
        metadata: Union[ToolMetadata, Dict[str, Any]],
        aliases: Optional[List[str]] = None,
    ) -> None:
        """
        Register a tool function.
        
        Args:
            name: Unique tool name
            func: Callable tool function
            metadata: Tool metadata (ToolMetadata or dict)
            aliases: Optional list of alternative names
            
        Raises:
            ValueError: If tool name already exists or invalid metadata
            TypeError: If func is not callable
        """
        if not callable(func):
            raise TypeError(f"Tool {name} must be callable, got {type(func)}")
        
        if name in self._tools:
            raise ValueError(f"Tool '{name}' already registered")
        
        # Convert dict to ToolMetadata if needed
        if isinstance(metadata, dict):
            metadata = ToolMetadata.from_dict(metadata)
        elif not isinstance(metadata, ToolMetadata):
            raise TypeError(f"metadata must be ToolMetadata or dict, got {type(metadata)}")
        
        # Validate metadata consistency
        if metadata.name != name:
            metadata.name = name
        
        # Register the tool
        self._tools[name] = func
        self._metadata[name] = metadata
        self._categories[metadata.category].append(name)
        
        # Register aliases
        if aliases:
            for alias in aliases:
                if alias in self._aliases:
                    raise ValueError(f"Alias '{alias}' already in use")
                self._aliases[alias] = name
    
    def unregister(self, name: str) -> None:
        """
        Unregister a tool.
        
        Args:
            name: Tool name to unregister
            
        Raises:
            KeyError: If tool not found
        """
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' not registered")
        
        metadata = self._metadata[name]
        category = metadata.category
        
        # Remove from registry
        del self._tools[name]
        del self._metadata[name]
        if name in self._categories[category]:
            self._categories[category].remove(name)
        
        # Remove aliases
        aliases_to_remove = [
            alias for alias, target in self._aliases.items() if target == name
        ]
        for alias in aliases_to_remove:
            del self._aliases[alias]
    
    def get(self, name: str) -> Optional[Callable]:
        """
        Get a tool function by name or alias.
        
        Args:
            name: Tool name or alias
            
        Returns:
            Tool function or None if not found
        """
        # Resolve alias
        real_name = self._aliases.get(name, name)
        return self._tools.get(real_name)
    
    def get_metadata(self, name: str) -> Optional[ToolMetadata]:
        """
        Get tool metadata by name or alias.
        
        Args:
            name: Tool name or alias
            
        Returns:
            Tool metadata or None if not found
        """
        real_name = self._aliases.get(name, name)
        return self._metadata.get(real_name)
    
    def invoke(
        self,
        name: str,
        *args,
        **kwargs
    ) -> Any:
        """
        Invoke a tool by name.
        
        Args:
            name: Tool name or alias
            *args: Positional arguments for the tool
            **kwargs: Keyword arguments for the tool
            
        Returns:
            Tool result
            
        Raises:
            KeyError: If tool not found
            ValueError: If validation fails
        """
        tool = self.get(name)
        if tool is None:
            raise KeyError(f"Tool '{name}' not found")
        
        metadata = self.get_metadata(name)
        
        # Validate parameters if metadata exists
        if metadata:
            # Check required parameters
            for param in metadata.parameters:
                if param.required and param.name not in kwargs:
                    if not args:  # No positional args to fill it
                        raise ValueError(f"Required parameter '{param.name}' missing")
            
            # Validate parameter values
            for param in metadata.parameters:
                if param.name in kwargs:
                    is_valid, error = param.validate(kwargs[param.name])
                    if not is_valid:
                        raise ValueError(f"Parameter '{param.name}': {error}")
        
        # Invoke the tool
        return tool(*args, **kwargs)
    
    def list_tools(
        self,
        category: Optional[ToolCategory] = None,
        status: Optional[ToolStatus] = None,
    ) -> List[str]:
        """
        List registered tools.
        
        Args:
            category: Optional filter by category
            status: Optional filter by status
            
        Returns:
            List of tool names
        """
        tools = list(self._tools.keys())
        
        if category:
            tools = [t for t in tools if self._metadata[t].category == category]
        
        if status:
            tools = [t for t in tools if self._metadata[t].status == status]
        
        return sorted(tools)
    
    def list_by_category(self) -> Dict[ToolCategory, List[str]]:
        """Get tools organized by category."""
        return {cat: sorted(tools) for cat, tools in self._categories.items() if tools}
    
    def export_metadata(self, name: str) -> Dict[str, Any]:
        """
        Export metadata for a tool.
        
        Args:
            name: Tool name
            
        Returns:
            Tool metadata as dictionary
            
        Raises:
            KeyError: If tool not found
        """
        metadata = self.get_metadata(name)
        if metadata is None:
            raise KeyError(f"Tool '{name}' not found")
        
        return metadata.to_dict()
    
    def export_all_metadata(self) -> Dict[str, Dict[str, Any]]:
        """Export metadata for all tools."""
        return {
            name: self._metadata[name].to_dict()
            for name in self._tools.keys()
        }
    
    def get_docstring(self, name: str) -> Optional[str]:
        """
        Get docstring of a tool function.
        
        Args:
            name: Tool name or alias
            
        Returns:
            Docstring or None
        """
        tool = self.get(name)
        if tool is None:
            return None
        
        return inspect.getdoc(tool)
    
    def get_signature(self, name: str) -> Optional[inspect.Signature]:
        """
        Get function signature of a tool.
        
        Args:
            name: Tool name or alias
            
        Returns:
            Function signature or None
        """
        tool = self.get(name)
        if tool is None:
            return None
        
        return inspect.signature(tool)
    
    def validate_dependencies(self, name: str) -> Tuple[bool, Optional[str]]:
        """
        Check if all tool dependencies are registered.
        
        Args:
            name: Tool name
            
        Returns:
            Tuple of (all_present, missing_dependency_name)
        """
        metadata = self.get_metadata(name)
        if metadata is None:
            return False, f"Tool '{name}' not found"
        
        for dep in metadata.dependencies:
            if dep not in self._tools:
                return False, dep
        
        return True, None
    
    def to_json(self) -> str:
        """Export registry to JSON string."""
        data = {
            "tools": {
                name: {
                    "metadata": self._metadata[name].to_dict(),
                    "signature": str(self.get_signature(name)),
                    "docstring": self.get_docstring(name),
                }
                for name in self._tools.keys()
            },
            "aliases": self._aliases,
        }
        return json.dumps(data, indent=2, default=str)
    
    def __len__(self) -> int:
        """Return number of registered tools."""
        return len(self._tools)
    
    def __contains__(self, name: str) -> bool:
        """Check if tool is registered."""
        return name in self._tools or name in self._aliases
    
    def __repr__(self) -> str:
        """String representation of registry."""
        return f"ToolRegistry({len(self._tools)} tools)"


# Global registry instance
_global_registry: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    """Get or create the global tool registry."""
    global _global_registry
    if _global_registry is None:
        _global_registry = ToolRegistry()
    return _global_registry


def reset_registry() -> None:
    """Reset the global registry (useful for testing)."""
    global _global_registry
    _global_registry = None
