import uuid
import logging

from typing import Any, Optional

from ofx.models.step import Step
from ofx.models.workflow import Workflow
from ofx.models.job import Job
from ofx.settings import settings
from ofx.runner.core.models import RunnerStatus, RunContext, RunResult
from ofx.runner.core.template import TemplateEngine
from ofx.runner.core.hooks import HookHandler, HookPoint, HookContext

logger = logging.getLogger(settings.app_branding)


class BaseRunner:
    """Abstract base class for all runners (Workflow, Job, Step).
    
    Implements the Template Method pattern with hooks for lifecycle events.
    Provides common functionality for execution, context management, and result tracking.
    
    Attributes:
        _id: Unique identifier for this runner instance
        _status: Current execution status (IDLE, RUNNING, COMPLETED, FAILED, CANCELED)
        _error: Error message if execution failed
        _ctx: Execution context with inputs, outputs, secrets, environment
        _parent: Parent runner in the hierarchy (if any)
        _model: Workflow/Job/Step model being executed
        _result: Execution result object
        _template_engine: Template resolution engine
        _hook_handler: Hook execution handler
    """
    def __init__(
        self, name: Any, ctx: RunContext, parent: Optional["BaseRunner"] = None
    ):
        name = str(name)
        self._id = f"{name}-{str(uuid.uuid4())}"
        self._status = RunnerStatus.IDLE
        self._error = None
        self._ctx = ctx
        self._parent = parent
        self._model = None
        self._result = RunResult(status=self.status, run_id=self._id, name=name)
        self._template_engine = TemplateEngine(self)
        self._hook_handler = HookHandler(self)

    async def run(self):
        """Run the workflow/job/step and return the result.
        
        This is the main entry point that orchestrates the execution lifecycle:
        1. Execute pre_run hooks and setup
        2. Run the actual execution (_do_run)
        3. Execute post_run hooks and cleanup
        4. Handle errors and status updates
        
        Returns:
            RunResult: Execution result with status, outputs, and metadata
            
        Raises:
            Exception: Any unhandled exceptions during execution
        """
        try:
            self._ctx.vars.update({"self": self._model})
            await self._pre_run()
            self._status = RunnerStatus.RUNNING
            await self._do_run()
            self._status = RunnerStatus.COMPLETED
        except Exception as e:
            self._error = str(e)
        if self._error and self._status != RunnerStatus.CANCELED:
            self._status = RunnerStatus.FAILED
        try:
            await self._post_run()
        except Exception as e:
            logger.error(self._produce_log(f"Error in post-run: {e}"))
            self._status = RunnerStatus.FAILED
        return self.get_result()

    async def _do_run(self):
        raise NotImplementedError("Subclasses should implement _do_run method.")

    async def _pre_run(self):
        raise NotImplementedError("Subclasses should implement _pre_run method.")

    async def _post_run(self):
        raise NotImplementedError("Subclasses should implement _post_run method.")

    def _register_hooks_from_model(self):
        """Register hooks from model - common pattern across all runners."""
        if not hasattr(self._model, 'hooks') or not self._model.hooks:
            return
        
        for hook_name, hook_code in self._model.hooks.items():
            try:
                hook_point = HookPoint(hook_name)
                self._hook_handler.register_hook(hook_point, hook_code)
            except ValueError:
                logger.warning(f"Unknown hook point: {hook_name}")
    
    async def _execute_pre_run_hooks(self) -> HookContext:
        """Execute pre_run hooks and return modified context."""
        hook_ctx = HookContext(
            model=self._model,
            inputs=self._ctx.inputs,
            context=self._ctx,
            runner=self,
        )
        hook_ctx = await self._hook_handler.execute_hooks(HookPoint.PRE_RUN, hook_ctx)
        self._ctx.inputs.update(hook_ctx.inputs)
        return hook_ctx
    
    async def _execute_post_run_hooks(self) -> HookContext:
        """Execute post_run hooks with error/success handling."""
        hook_ctx = HookContext(
            model=self._model,
            inputs=self._ctx.inputs,
            outputs=self._result.outputs,
            run_result=self._result,
            context=self._ctx,
            error=Exception(self._error) if self._error else None,
            runner=self,
        )
        
        # Execute error or success hooks
        if self._error:
            hook_ctx = await self._hook_handler.execute_hooks(HookPoint.ON_ERROR, hook_ctx)
        else:
            hook_ctx = await self._hook_handler.execute_hooks(HookPoint.ON_SUCCESS, hook_ctx)
        
        # Execute post_run hook
        hook_ctx = await self._hook_handler.execute_hooks(HookPoint.POST_RUN, hook_ctx)
        self._result.outputs.update(hook_ctx.outputs)
        return hook_ctx

    def _resolve_template(self, value: Any) -> Any:
        return self._template_engine.resolve(value)

    def _resolve_template_fields(self, fields: list[str]):
        self._template_engine.resolve_model_fields(self._model, fields)

    def _produce_log(self, message: Any) -> str:
        raise NotImplementedError("Subclasses should implement _produce_log method.")

    @property
    def model(self) -> Workflow | Job | Step | None:
        return self._model

    @property
    def status(self) -> RunnerStatus:
        return self._status

    @property
    def is_finished(self) -> bool:
        return self._status in {
            RunnerStatus.COMPLETED,
            RunnerStatus.FAILED,
            RunnerStatus.CANCELED,
        }

    @property
    def is_success(self) -> bool:
        return self._status == RunnerStatus.COMPLETED and self._error is None

    @property
    def run_id(self) -> str:
        return self._id

    def get_result(self) -> RunResult:
        """
        Get the result of the workflow run.
        """
        self._result.status = self.status
        self._result.error = self._error
        return self._result
    
    def _process_inputs(self, provided: dict, schema: dict) -> dict:
        """Process and validate inputs against schema.
        
        Args:
            provided: User-provided input values
            schema: Input schema with required fields and defaults
            
        Returns:
            Dictionary of validated and processed inputs
            
        Raises:
            ValueError: If required inputs are missing
        """
        processed = {}
        for key, config in schema.items():
            value = provided.get(key)
            
            # Handle required inputs
            if config.required and value is None:
                if hasattr(config, 'default') and config.default is not None:
                    value = config.default
                else:
                    raise ValueError(f"Required input '{key}' is missing")
            
            # Use default if not provided
            if value is None and hasattr(config, 'default'):
                value = config.default
            
            if value is not None:
                processed[key] = value
        
        return processed
    
    def _safe_eval(self, expression: str | bool, context_name: str = "condition") -> bool:
        """Safely evaluate run_if conditions with sandboxing.
        
        Args:
            expression: Boolean expression or boolean value
            context_name: Name of the context for error messages
            
        Returns:
            Boolean result of the evaluation
            
        Note:
            Only allows basic boolean expressions (True, False, and, or, not)
            to prevent code injection attacks.
        """
        if isinstance(expression, bool):
            return expression
        
        try:
            # Convert to string and evaluate
            expr_str = str(expression)
            # Simple safety check - only allow basic boolean expressions
            allowed_chars = set('TrueFalse0123456789 ()andornot')
            if not all(c in allowed_chars for c in expr_str.replace('True', '').replace('False', '')):
                logger.warning(f"Potentially unsafe {context_name}: {expr_str}")
            
            result = eval(expr_str, {"__builtins__": {}})
            return bool(result)
        except Exception as e:
            logger.error(f"Error evaluating {context_name} '{expression}': {e}")
            return False
    
    @property
    def ctx_vars(self) -> RunContext:
        """Get the run context for convenient access."""
        return self._ctx
    
    @property
    def ctx(self) -> RunContext:
        """Alias for ctx_vars for convenience."""
        return self._ctx
    
    @property
    def ctx(self) -> RunContext:
        """Alias for ctx_vars."""
        return self._ctx

    @property
    def ctx_vars(self) -> RunContext:
        """
        Get the context variables for the workflow run.
        """
        return self._ctx

    @property
    def parent(self) -> "BaseRunner | None":
        return self._parent
