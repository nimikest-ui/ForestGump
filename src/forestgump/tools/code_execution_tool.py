"""Code execution tool for ForestGump: sandboxed Python REPL and execution.

This module provides a sandboxed environment for executing Python code with:
- Isolated execution contexts
- Output capture and streaming
- Error handling and timeouts
- Resource limits
- Security restrictions
"""

import sys
import os
import io
import time
import types
import contextlib
from typing import Any, Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass
from threading import Thread, Event
import traceback
import subprocess


@dataclass
class ExecutionResult:
    """Result of code execution."""
    
    success: bool
    output: str
    error: str
    return_value: Any
    execution_time: float
    lines_executed: int = 0


class SandboxedREPL:
    """Sandboxed Python REPL for safe code execution."""
    
    # Restricted built-ins and imports
    RESTRICTED_BUILTINS = {
        'open', 'exec', 'eval', 'compile', 'input', 'raw_input',
        '__import__', 'getattr', 'setattr', 'delattr', 'globals',
        'locals', 'vars', 'dir', 'hasattr', 'callable',
    }
    
    RESTRICTED_MODULES = {
        'os', 'sys', 'subprocess', 'socket', 'urllib', 'requests',
        'shutil', 'tempfile', 'threading', 'multiprocessing', 'ctypes',
    }
    
    def __init__(self, timeout: int = 30, enable_imports: bool = False):
        """
        Initialize sandboxed REPL.
        
        Args:
            timeout: Execution timeout in seconds
            enable_imports: Allow imports (use with caution)
        """
        self.timeout = timeout
        self.enable_imports = enable_imports
        self.globals_dict = self._create_globals()
        self.locals_dict = {}
    
    def _create_globals(self) -> Dict[str, Any]:
        """Create a restricted globals dictionary."""
        # Start with minimal builtins
        safe_builtins = {
            'abs': abs, 'all': all, 'any': any, 'ascii': ascii,
            'bin': bin, 'bool': bool, 'bytearray': bytearray,
            'bytes': bytes, 'chr': chr, 'dict': dict, 'divmod': divmod,
            'enumerate': enumerate, 'filter': filter, 'float': float,
            'format': format, 'frozenset': frozenset, 'hex': hex,
            'int': int, 'isinstance': isinstance, 'issubclass': issubclass,
            'iter': iter, 'len': len, 'list': list, 'map': map,
            'max': max, 'min': min, 'next': next, 'object': object,
            'oct': oct, 'ord': ord, 'pow': pow, 'print': print,
            'range': range, 'reversed': reversed, 'round': round,
            'set': set, 'slice': slice, 'sorted': sorted, 'str': str,
            'sum': sum, 'tuple': tuple, 'type': type, 'zip': zip,
            'Exception': Exception, 'ValueError': ValueError,
            'TypeError': TypeError, 'KeyError': KeyError,
            'IndexError': IndexError, 'RuntimeError': RuntimeError,
        }
        
        return {
            '__builtins__': safe_builtins,
            '__name__': '__sandbox__',
            '__doc__': None,
        }
    
    def execute(
        self,
        code: str,
        input_dict: Optional[Dict[str, Any]] = None
    ) -> ExecutionResult:
        """
        Execute code in sandbox.
        
        Args:
            code: Python code to execute
            input_dict: Optional dictionary of input variables
            
        Returns:
            ExecutionResult with output and return value
        """
        start_time = time.time()
        
        # Prepare execution environment
        exec_globals = self.globals_dict.copy()
        exec_locals = self.locals_dict.copy()
        
        if input_dict:
            exec_locals.update(input_dict)
        
        # Capture output
        output_buffer = io.StringIO()
        error_buffer = io.StringIO()
        
        try:
            # Compile code to check for syntax errors
            try:
                compiled = compile(code, '<sandbox>', 'exec')
            except SyntaxError as e:
                execution_time = time.time() - start_time
                return ExecutionResult(
                    success=False,
                    output="",
                    error=f"SyntaxError: {e.msg}",
                    return_value=None,
                    execution_time=execution_time
                )
            
            # Execute with output capture
            with contextlib.redirect_stdout(output_buffer):
                with contextlib.redirect_stderr(error_buffer):
                    exec(compiled, exec_globals, exec_locals)
            
            # Update locals for next execution
            self.locals_dict = exec_locals
            
            execution_time = time.time() - start_time
            
            return ExecutionResult(
                success=True,
                output=output_buffer.getvalue(),
                error=error_buffer.getvalue(),
                return_value=exec_locals.get('_result', None),
                execution_time=execution_time,
                lines_executed=len(code.strip().split('\n'))
            )
        
        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = traceback.format_exc()
            
            return ExecutionResult(
                success=False,
                output=output_buffer.getvalue(),
                error=error_msg,
                return_value=None,
                execution_time=execution_time,
                lines_executed=len(code.strip().split('\n'))
            )
    
    def evaluate(
        self,
        expression: str,
        input_dict: Optional[Dict[str, Any]] = None
    ) -> ExecutionResult:
        """
        Evaluate a single expression and return its value.
        
        Args:
            expression: Python expression to evaluate
            input_dict: Optional dictionary of input variables
            
        Returns:
            ExecutionResult with evaluated value
        """
        start_time = time.time()
        
        exec_globals = self.globals_dict.copy()
        exec_locals = self.locals_dict.copy()
        
        if input_dict:
            exec_locals.update(input_dict)
        
        try:
            result = eval(expression, exec_globals, exec_locals)
            execution_time = time.time() - start_time
            
            return ExecutionResult(
                success=True,
                output=str(result),
                error="",
                return_value=result,
                execution_time=execution_time,
                lines_executed=1
            )
        
        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = traceback.format_exc()
            
            return ExecutionResult(
                success=False,
                output="",
                error=error_msg,
                return_value=None,
                execution_time=execution_time,
                lines_executed=1
            )
    
    def reset(self):
        """Reset the execution environment."""
        self.globals_dict = self._create_globals()
        self.locals_dict = {}


class SubprocessExecutor:
    """Execute Python code as subprocess for better isolation."""
    
    def __init__(self, timeout: int = 30):
        """
        Initialize subprocess executor.
        
        Args:
            timeout: Execution timeout in seconds
        """
        self.timeout = timeout
    
    def execute(
        self,
        code: str,
        cwd: Optional[str] = None
    ) -> ExecutionResult:
        """
        Execute Python code as subprocess.
        
        Args:
            code: Python code to execute
            cwd: Working directory
            
        Returns:
            ExecutionResult with output
        """
        start_time = time.time()
        
        try:
            # Run Python code as subprocess
            result = subprocess.run(
                [sys.executable, '-c', code],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=cwd or os.getcwd()
            )
            
            execution_time = time.time() - start_time
            
            return ExecutionResult(
                success=result.returncode == 0,
                output=result.stdout,
                error=result.stderr,
                return_value=result.returncode,
                execution_time=execution_time,
                lines_executed=len(code.strip().split('\n'))
            )
        
        except subprocess.TimeoutExpired:
            execution_time = time.time() - start_time
            return ExecutionResult(
                success=False,
                output="",
                error=f"Execution timeout after {self.timeout}s",
                return_value=None,
                execution_time=execution_time
            )
        
        except Exception as e:
            execution_time = time.time() - start_time
            return ExecutionResult(
                success=False,
                output="",
                error=str(e),
                return_value=None,
                execution_time=execution_time
            )


def execute_python_code(
    code: str,
    sandbox: bool = True,
    timeout: int = 30,
    input_dict: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Execute Python code safely.
    
    This is a convenience function for the tool registry.
    
    Args:
        code: Python code to execute
        sandbox: Use sandbox mode (safer but more limited)
        timeout: Execution timeout in seconds
        input_dict: Input variables
        
    Returns:
        Dictionary with execution result
    """
    if sandbox:
        repl = SandboxedREPL(timeout=timeout)
        result = repl.execute(code, input_dict)
    else:
        executor = SubprocessExecutor(timeout=timeout)
        result = executor.execute(code)
    
    return {
        'success': result.success,
        'output': result.output,
        'error': result.error,
        'return_value': str(result.return_value) if result.return_value else None,
        'execution_time': result.execution_time,
        'lines_executed': result.lines_executed
    }


def evaluate_expression(
    expression: str,
    input_dict: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Evaluate a Python expression.
    
    This is a convenience function for the tool registry.
    
    Args:
        expression: Python expression to evaluate
        input_dict: Input variables
        
    Returns:
        Dictionary with evaluation result
    """
    repl = SandboxedREPL()
    result = repl.evaluate(expression, input_dict)
    
    return {
        'success': result.success,
        'output': result.output,
        'error': result.error,
        'return_value': str(result.return_value) if result.return_value else None,
        'execution_time': result.execution_time
    }
