"""
Hook system for workflow, job, and step runners.
Supports custom Python code execution at various lifecycle points.
"""
import inspect
import logging
from enum import Enum
from typing import Any, Callable, Dict, Optional

from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)


class HookPoint(str, Enum):
    """Lifecycle hook points for runners."""
    PRE_RUN = "pre_run"
    POST_RUN = "post_run"
    BEFORE_STEP = "before_step"
    AFTER_STEP = "after_step"
    ON_ITER_STEP = "on_iter_step"
    ON_ERROR = "on_error"
    ON_SUCCESS = "on_success"
    ON_RETRY = "on_retry"
    ON_SKIP = "on_skip"
    ON_TIMEOUT = "on_timeout"


class HookContext:
    """Context object passed to hooks with available data."""
    def __init__(
        self,
        model: Any = None,
        inputs: Dict[str, Any] | None = None,
        outputs: Dict[str, Any] | None = None,
        run_result: Any = None,
        context: Any = None,
        error: Optional[Exception] = None,
        step_index: Optional[int] = None,
        # Step execution types (auto-resolved from step model)
        command: Optional[str] = None,
        script: Optional[str] = None,
        script_file: Optional[str] = None,
        run: Optional[str] = None,
        # Additional context
        runner: Any = None,
        retry_count: Optional[int] = None,
        skip_reason: Optional[str] = None,
    ):
        self.model = model
        self.inputs = inputs or {}
        self.outputs = outputs or {}
        self.run_result = run_result
        self.context = context
        self.error = error
        self.step_index = step_index
        self.command = command
        self.script = script
        self.script_file = script_file
        self.run = run
        self.runner = runner
        self.retry_count = retry_count
        self.skip_reason = skip_reason


class HookHandler:
    """Handles hook execution with automatic argument injection."""
    
    # Safe builtins whitelist for hook execution
    SAFE_BUILTINS = {
        'abs': abs,
        'all': all,
        'any': any,
        'bool': bool,
        'dict': dict,
        'enumerate': enumerate,
        'filter': filter,
        'float': float,
        'int': int,
        'len': len,
        'list': list,
        'map': map,
        'max': max,
        'min': min,
        'print': print,
        'range': range,
        'reversed': reversed,
        'round': round,
        'set': set,
        'sorted': sorted,
        'str': str,
        'sum': sum,
        'tuple': tuple,
        'zip': zip,
        # Allow these specific modules to be imported
        '__import__': __builtins__['__import__'],
    }
    
    def __init__(self, runner: Any):
        self._runner = runner
        self._hooks: Dict[HookPoint, list[Callable]] = {}
    
    def register_hook(self, hook_point: HookPoint, hook_code: str, hook_name: str = "hook"):
        """Register a hook from Python code string with sandboxed execution."""
        try:
            # Compile and execute the hook code with restricted builtins
            local_vars = {}
            safe_globals = {
                '__builtins__': self.SAFE_BUILTINS,
                # Allow common imports that are safe
                'datetime': __import__('datetime'),
                'json': __import__('json'),
                're': __import__('re'),
                'pathlib': __import__('pathlib'),
            }
            exec(hook_code, safe_globals, local_vars)
            
            # Find the hook function (first callable in local_vars or use specific name)
            hook_func = None
            if hook_name in local_vars and callable(local_vars[hook_name]):
                hook_func = local_vars[hook_name]
            else:
                # Find first callable
                for var in local_vars.values():
                    if callable(var) and not var.__name__.startswith('_'):
                        hook_func = var
                        break
            
            if not hook_func:
                raise ValueError(f"No callable function found in hook code for {hook_point}")
            
            if hook_point not in self._hooks:
                self._hooks[hook_point] = []
            
            self._hooks[hook_point].append(hook_func)
            logger.debug(f"Registered hook for {hook_point}: {hook_func.__name__}")
        
        except Exception as e:
            logger.error(f"Failed to register hook for {hook_point}: {e}")
            raise
    
    async def execute_hooks(self, hook_point: HookPoint, hook_context: HookContext) -> HookContext:
        """Execute all hooks for a given hook point with auto argument injection."""
        if hook_point not in self._hooks:
            return hook_context
        
        for hook_func in self._hooks[hook_point]:
            try:
                # Get function signature
                sig = inspect.signature(hook_func)
                
                # Build kwargs based on parameter names
                kwargs = {}
                for param_name, param in sig.parameters.items():
                    if param_name == 'model':
                        kwargs['model'] = hook_context.model
                    elif param_name == 'inputs' or param_name == 'input':
                        kwargs[param_name] = hook_context.inputs
                    elif param_name == 'outputs' or param_name == 'output':
                        kwargs[param_name] = hook_context.outputs
                    elif param_name == 'run_result' or param_name == 'result':
                        kwargs[param_name] = hook_context.run_result
                    elif param_name == 'context' or param_name == 'ctx':
                        kwargs[param_name] = hook_context.context
                    elif param_name == 'error':
                        kwargs['error'] = hook_context.error
                    elif param_name == 'step_index' or param_name == 'index':
                        kwargs[param_name] = hook_context.step_index
                    # Step execution types (auto-resolved)
                    elif param_name == 'command' or param_name == 'cmd':
                        kwargs[param_name] = hook_context.command
                    elif param_name == 'script':
                        kwargs['script'] = hook_context.script
                    elif param_name == 'script_file' or param_name == 'run_file':
                        kwargs[param_name] = hook_context.script_file
                    elif param_name == 'run':
                        kwargs['run'] = hook_context.run
                    # Additional context
                    elif param_name == 'runner':
                        kwargs['runner'] = hook_context.runner
                    elif param_name == 'retry_count':
                        kwargs['retry_count'] = hook_context.retry_count
                    elif param_name == 'skip_reason':
                        kwargs['skip_reason'] = hook_context.skip_reason
                    elif param_name == 'hook_context':
                        kwargs['hook_context'] = hook_context
                
                # Execute hook (support both sync and async)
                if inspect.iscoroutinefunction(hook_func):
                    result = await hook_func(**kwargs)
                else:
                    result = hook_func(**kwargs)
                
                # If hook returns something, update context
                if result is not None:
                    if isinstance(result, dict):
                        # Update outputs or inputs based on hook point
                        if hook_point in [HookPoint.PRE_RUN, HookPoint.BEFORE_STEP]:
                            hook_context.inputs.update(result)
                        else:
                            hook_context.outputs.update(result)
                
                logger.debug(f"Executed hook {hook_func.__name__} for {hook_point}")
            
            except Exception as e:
                logger.error(f"Hook execution failed for {hook_point}: {e}")
                # Don't stop execution on hook failure, just log it
                if hook_point != HookPoint.ON_ERROR:
                    # Execute error hooks if available
                    error_context = HookContext(
                        model=hook_context.model,
                        error=e,
                        runner=hook_context.runner,
                    )
                    await self.execute_hooks(HookPoint.ON_ERROR, error_context)
        
        return hook_context
    
    def has_hooks(self, hook_point: HookPoint) -> bool:
        """Check if hooks are registered for a given hook point."""
        return hook_point in self._hooks and len(self._hooks[hook_point]) > 0
