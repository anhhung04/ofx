# Runner review — findings and fixes

Scope: `src/ofx/runner/**` (executors, handlers, services, registry backends),
adjacent consumers (`ofx/runner/api.py`, `ofx/modules/runner.py`,
`ofx/commands/flow/*`, `ofx/cloud/sessions/*`), and runner-focused tests.
Axes: performance, consistency, reliability, idempotency.

Legend: ✅ fixed (evidence cited)

## HIGH

- ✅ **H1 — Every runner closes the *shared* registry on finalize.**
  `lifecycle.py:156-160` runs `cleanup_registry(runner._registry)` for every
  runner; children share the parent's registry (`job.py:86-91`,
  `step.py:35-40`, `cloud_step.py:116-122`). With redis/etcd/memcached
  backends the first finished step breaks every later registry access.
  File/memory backends are unaffected (no-op close) — why the CLI hides it.
  Fix: `_finalize_execution` now cleans up only when
  `self._runner.parent is None` (root runner). See
  `test_finalize_execution_child_runner_keeps_shared_registry_open` + the
  existing root-cleanup test both green.

- ✅ **H2 — Unnamed jobs collide in the registry namespace.**
  Fix: models/workflow.py — validate_jobs backfills Job.name from jid. Tests: test_unnamed_jobs_backfill_name_from_jid, test_unnamed_jobs_have_distinct_namespace_prefixes, test_unnamed_jobs_do_not_cross_contaminate_registry_outputs.
  `runner.py:328-346` namespaces by `Job.name`, which defaults to `""`
  (`models/job.py:17`); `Workflow.validate_jobs` sets `jid` but never
  backfills `name`. Two unnamed jobs share the prefix and cross-contaminate
  `outputs`/`result`/`execution` — silent data corruption.

- ✅ **H3 — `run_if` uses raw `eval` with unrestricted builtins.**
  `runner.py:202-214`. A workflow YAML `if:`/`run_if:` string can execute
  arbitrary code (`__import__('os').system(...)`), unlike the sandboxed pipe
  evaluator (`executors/pipe.py:70-100`).
  Fix: `Runner._evaluate_run_if` now evaluates through a duplicated
  `_safe_run_if_eval` sandbox (AST walk rejecting `__import__`/`eval`/
  `open`/`compile`/dunder attribute access; restricted builtins). See
  `test_evaluate_run_if_rejects_arbitrary_code`,
  `test_evaluate_run_if_rejects_dunder_attribute_access`,
  `test_evaluate_run_if_supports_run_if_context_callables`.

- ✅ **H4 — Step timeouts bypass retry.**
  Fix: executors/step.py — timeout counts as a retryable attempt; timeout-specific error only after the final attempt. Tests: test_timeout_counts_as_attempt_then_succeeds, test_always_times_out_raises_timeout_error_after_final_attempt.
  `executors/step.py:68-71`: the `TimeoutError` branch raises immediately,
  outside the retry loop; a step with `retry: 3` that times out runs once.

- ✅ **H5 — Cloud-step 30s network grace is unreachable.**
  Fix: executors/step.py + cloud_step.py — grace moved to outer wait_for via _network_grace_seconds; inner +30 removed. Tests: test_cloud_handler_child_budget_includes_grace, test_local_child_budget_keeps_plain_timeout.
  `executors/step.py:37,59` outer `wait_for(timeout)` always expires 30s
  before `cloud_step.py:43,64-70` inner `wait_for(timeout+30)`.

## MEDIUM

- ✅ **M1 — Durable resume skips finalization; bogus duration.**
  `lifecycle.py:93-95` returns before the try/finally: no `runner_finish`
  event, no registry cleanup, no checkpoint write/push. `_finished_at` never
  set on restore (`services/checkpoint.py:88-90`) → `duration_ms()` ≈ 0.
  Fix: `execute()` restructured so the resume branch participates in the
  shared `try/finally` → `_finalize_execution(resumed)` runs `runner_finish`,
  root-only registry cleanup, final checkpoints, and `auto_commit_push`.
  `_capture_restored_duration` parses restored UTC timestamps into
  `_restored_duration_ms`, surfaced by `duration_ms()`. See
  `test_execute_resume_runs_finalization_and_reports_restored_duration`,
  `test_execute_resume_skips_run_side_effects`; `restore_from_checkpoint`
  contract tests intact.

- ✅ **M2 — Re-running a finished runner raises a misleading FSM error.**
  No guard in `Runner.run()`; second `execute()` fails
  `transition(RUNNING)` from COMPLETED, then `_handle_terminal_error`
  re-raises a second `ValueError` (`lifecycle.py:216-224`). No idempotency
  guard; `_pre_run` side effects re-run first.
  Fix: `Runner.run()` now returns the cached result (debug-logged) when
  `self._state_machine.is_terminal`, so a finished/failed/canceled runner
  does not re-enter the lifecycle or re-run `_pre_run` side effects. See
  `test_rerun_completed_runner_returns_cached_result_without_crash`,
  `test_rerun_failed_runner_returns_cached_result_without_crash`.

- ✅ **M3 — `log_level` is write-only.**
  Fix: logging.py — StructuredLogger honors runner.log_level per record. Tests: tests/test_runner_logging_level.py (6 tests). Contract updates: test_flowrun.py (3 tests) + test_script_file.py assert via captured step outputs.
  Set at `api.py:210-211` and `executors/job.py:71`; never consulted by
  `StructuredLogger._log` (`logging.py:76-95`). `quiet=True` and per-step
  CRITICAL suppression do nothing.

- ✅ **M4 — Successful jobs re-run `_post_run()` when a workflow fails.**
  Fix: executors/workflow.py — failure path skips COMPLETED jobs. Test: test_do_run_failure_skips_post_run_for_completed_jobs.
  `executors/workflow.py:170-180` loops over **all** job runners on failure;
  completed jobs already ran post_run in their lifecycle. For cloud jobs this
  repeats `download_outputs`/`destroy_instance`.

- ✅ **M5 — Time-window guard task leaks on the failure path.**
  Fix: executors/workflow.py — shared _stop_time_guard in post_run and on_failure. Test: test_on_failure_stops_time_window_guard.
  Started at `executors/workflow.py:50-56`; stopped only in `post_run`
  (`:192-193`), never in `on_failure` — leaked poller per failed workflow.

- ✅ **M6 — `FleetExecutor.post_run` references non-existent `runner._logger`.**
  Fix: executors/fleet.py — uses runner._log_debug. Test: test_fleet_post_run_logs_cleanup_errors_via_runner_log_debug.
  `executors/fleet.py:53-57`; `Runner.__slots__` has no `_logger` →
  `AttributeError` from the cleanup error handler masks the real error.

- ✅ **M7 — `_update` is a non-atomic read-modify-write on serialized backends.**
  Fix: registry_adapter.py — per-instance asyncio.Lock around read-modify-write; file.py holds filelock across read+write. Tests: tests/test_registry_update_atomicity.py (8 tests).
  `registry_adapter.py:206-212` (redis/etcd/memcached) and
  `file.py:109-114` do get→write as two unlocked round trips; parallel jobs
  can lose updates. Only `memory.py` is atomic.

- ✅ **M8 — Memory gate busy-waits holding a concurrency slot; `%%` literal bug.**
  Fix: workflow_execution.py — %% literal fixed, unavailable logged once, gate moved outside the job semaphore. Tests: test_wait_for_memory_logs_single_percent_not_literal_double, test_wait_for_memory_logs_unavailable_once_after_high_usage_poll, test_memory_wait_happens_outside_job_semaphore_slot.
  `workflow_execution.py:67-109`: gate awaited inside the job semaphore;
  non-Linux path debug-logs every poll; `:87` renders literal `%%`.

## LOW / consistency

- ✅ **L1 — Registry-key literals bypass `RunnerRegistryKeys`** (lifecycle part).
  `execution_summary.py:43`, `runner.py:299`, `executors/cloud.py:88`,
  `lifecycle.py:101-108`.
  Note: scoped here to the lifecycle part only. Fix: added `METADATA =
  "metadata"` and `CONTEXT = "context"` members to `RunnerRegistryKeys`
  (stored strings identical) and `lifecycle.py` now uses the members in its
  `reg_set_many` metadata/context registration. Other sites are owned by
  other slices. See `test_execute_registers_metadata_and_context_via_registry_key_members`.
- ✅ **L2 — Two conflicting timeout defaults** (`error_helpers.py:8-13` →
  Fix: error_helpers.py + step_mixin.py — unified to 1440 min. Test: test_invalid_timeout_resolution_falls_back_and_warns.
  1440 min vs `step_mixin.py:20` → 60 min for unparseable timeout).
- ✅ **L3 — Inconsistent failure semantics:** `_resolve_template_fields`
  fail-fast (`runner.py:236-243`) vs `_resolve_job_outputs` fail-soft
  (`runner.py:221-228`).
  Fix: no behavior change; added explicit docstrings + code comments at each
  site documenting the deliberate fail-fast (config fields) vs fail-soft
  (output fields) contract. See
  `test_template_field_failure_propagates_but_output_failure_is_soft`.
- ✅ **L4 — `PipeRunner`/`ToolInstallerRunner` get a private registry**
  Fix: pipe.py + tool_installer.py — reuse parent registry when present, private memory registry standalone. Tests: test_pipe_runner_reuses_parent_registry, test_tool_installer_runner_reuses_parent_registry (+ standalone fallbacks).
  (`pipe.py:37-42`, `tool_installer.py:44-49`) instead of the parent's.
- ✅ **L5 — `reg_set_many` is sequential; each `FileRegistry.set` rewrites
  Fix: runner.py — reg_set_many fans out via asyncio.gather (backends serialize per-key). FileRegistry verified single-write per call (no redundant rewrite).
  the whole file** (`runner.py:317-319`, `file.py:86-91`) — O(steps²) bytes.
- ✅ **L6 — Deepcopy amplification:** `get_result()` deep-copies outputs for
  Fix: executors/step.py debug get_result() gated on effective log level; executors/workflow.py uses status.value instead of a full get_result() copy. Tests: test_get_result_not_fetched_when_debug_disabled, test_post_run_debug_log_does_not_deepcopy_full_result.
  debug logging (`executors/step.py:59`, `executors/workflow.py:236`).
- ✅ **L7 — `MemoryJobRegistry._update` skips the capacity check**
  Fix: memory.py — capacity check applied on new keys in _update. Tests: TestMemoryRegistryUpdateCapacity (2 tests).
  (`memory.py:60-66` vs `:47-48`) — can exceed `maxsize` silently.
- ✅ **L8 — `_RemoteHandlerRunner.is_success` is constant `True`**
  Fix: cloud_step.py — is_success is a property reflecting result.status. Tests: test_is_success_before_run_is_false, test_is_success_reflects_completed_result, test_is_success_reflects_failed_result.
  (`cloud_step.py:53-56`) — StepExecutor's success branch carries no
  information for cloud steps.
- ✅ **L9 — Event sink opened per event** (`services/event_emitter.py:49-53`)
  Fix: services/event_emitter.py — lazy single open, reuse, close(). Tests: test_event_emitter.py additions (5 tests).
  — O(steps) file opens/mkdirs.
- ✅ **L10 — `max_parallel: null` crashes** with `TypeError` at
  Fix: executors/parallel.py — None treated as unbounded (no Semaphore). Tests: test_run_limited_fail_fast_treats_none_max_parallel_as_unbounded, test_parallel_run_settings_none_max_parallel_falls_back_to_item_count.
  `Semaphore(None)` (`executors/parallel.py:29,76-81`,
  `models/strategy.py:47-54`).
- ✅ **L11 — Canceled children are retried** (`executors/step.py:60-67`
  Fix: executors/step.py — CANCELED raises ConditionNotMetError immediately, never retried. Test: test_canceled_child_propagates_without_retry.
  treats any non-COMPLETED as retryable).
- ✅ **L12 — Key prefix cached before `name` resolution**
  (`lifecycle.py:99` before `:109`) — keys can embed raw Jinja text.
  Fix: `_resolve_template_fields` invalidates `self._cached_key_prefix` when
  `name` is among the resolved fields, so the next key lookup recomputes the
  prefix from the resolved name. See
  `test_resolve_template_fields_invalidates_cached_key_prefix_for_name`.
- ✅ **L13 — `__slots__` on `Runner` is decorative** (`runner.py:33-55`) —
  Fix: runner.py — decorative base __slots__ removed, documented why (subclasses rely on __dict__). Test: test_runner_supports_dynamic_executor_attributes.
  subclasses all have `__dict__`; executors rely on setting undeclared attrs.
- ✅ **L14 — Runner construction reconfigures global logging**
  (`runner.py:89` → `logging.py:99-104`).
  Fix: `Runner.__init__` no longer calls `get_logger()`; `_log_level` is
  captured only when an explicit logger is provided, otherwise resolved lazily
  via a `_DeferredLogger` proxy passed to `StructuredLogger` and via the
  `log_level` getter (which calls `get_logger()` on first read). See
  `test_runner_construction_does_not_touch_global_logging`,
  `test_runner_log_level_resolves_lazily_on_first_read`,
  `test_runner_logging_emits_after_lazy_init`.
- ✅ **L15 — Blocking network I/O in `post_run`:** `timeline._source_host()`
  Fix: timeline.py — _source_host_async offloads the lookup via asyncio.to_thread; StepExecutor.post_run awaits log_step_async. Tests: tests/test_timeline_async.py (4 tests).
  does up to 3 urllib requests (2s each) on first use inside
  `StepExecutor.post_run` (`timeline.py:63-95`).
- ✅ **L16 — Direct mutation where helpers exist:**
  Fix: executors/workflow.py — output_path set via update_context helper; matrix expansion works on a Job.strategy copy. Tests: test_pre_run_sets_output_path_via_context_update_helper, test_expand_list_inputs_to_matrix_does_not_mutate_shared_strategy.
  `executors/workflow.py:91-92` assigns `ctx.output_path` directly;
  `:345-375` mutates shared `Job.strategy` in place.

## Invariants preserved (locked by tests)

- Registry key format + caching (`test_registry_key_namespace.py`,
  `test_runner_models.py:196-210`).
- FSM transition table, terminal-error preference, `mark_finish` once-only,
  checkpoint double-write rule, finalize emits one `runner_finish` + cleanup
  (`test_lifecycle_manager.py`).
- Step execution payload shape; retry log wording and exhaustion message
  (`test_step_executor.py`).
- `process_inputs` alias/type behavior (`test_workflow_executor.py`).
- `attach_indexed_job_runner` contract (`test_job_runner_helpers.py`).
- `log_level` assignments stay observable (`test_job_executor.py:61,319`,
  `test_flowrun.py:602`).
- `restore_from_checkpoint` contract (`test_checkpoint_service.py`).
- `Runner.__init__` positional order; `ofx.runner` re-exports; private attrs
  `_registry`/`_cached_key_prefix`/`_state_machine`/`_error`; duck-typed
  hooks `_create_runner`/`_handler_registry`/`_outputs_file`/`_temp_file`;
  public `run_workflow(registry_backend=...)` signature.

## Follow-up hardening (post-review)

- ✅ **Registry backends exercised end-to-end.** File-backend workflow tests
  added (`TestFileBackendEndToEnd`): a two-step workflow with template
  resolution and two parallel jobs with no cross-contamination. The memory
  backend remains the default; the file backend now has full-workflow
  coverage (previously only unit-level).
- ✅ **Duplicate child-runner keys rejected.** `Runner.register_runner` is
  now the single registration path (`job.py`, `workflow_execution.py`,
  `executors/job.py` migrated); a duplicate key raises instead of silently
  clobbering an earlier child's outputs (the H2 class of bug). Regression
  tests: `TestRegisterRunner`.
