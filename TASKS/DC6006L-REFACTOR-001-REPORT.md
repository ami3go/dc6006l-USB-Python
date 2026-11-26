# DC6006L-REFACTOR-001 — Completion report

**Branch:** `refactor/safety-protocol-hardening`
**Base:** `main` @ `54e8cbf` (task document r2 @ `93dd86d`)
**HIL status:** `NOT RUN` — runbook ready in `docs/HIL_RUNBOOK.md`, awaiting an authorised operator.

## 1. Changed files

| Path | Change |
|---|---|
| `dc6006l/` | new root-level package: `driver.py`, `transport.py`, `protocol.py`, `models.py`, `validation.py`, `exceptions.py` |
| `tests/` | fake serial device with fault injection + 157 tests |
| `examples/` | `basic_usage.py`, `monitor.py`, `square_wave.py`, `voltage_ramp.py` (replace `Example/`) |
| `docs/PROTOCOL.md` | replaces `command_list.md`; every fact marked observed / assumed / unknown |
| `docs/HIL_RUNBOOK.md` | new |
| `README.md` | rewritten: safety warning, API, units, exceptions, migration table |
| `pyproject.toml`, `MANIFEST.in` | new; only runtime dependency `pyserial>=3.4,<4` |
| `.github/workflows/ci.yml` | tests on Linux/Windows × Python 3.9/3.12/3.13, build + clean install |
| `.gitignore` | rewritten |
| removed | `src/dc6006l_class.py`, `src/__pycache__/`, `venv/` (869 files), `.idea/`, `requirements.txt`, `Example/` |

The old `dc6006l_class` API was removed rather than wrapped (task §3:
"do not preserve a broken API"); README contains a migration table.

## 2. Finding closure

| # | Finding | Fix | Tests |
|---|---|---|---|
| 1 | OVP/OCP setters parse outgoing command, never verify, truncate | `set_ovp`/`set_ocp` encode exact integer units, verify `ovp`/`ocp` from a fresh status frame | `test_setter_success_verified[set_ovp/set_ocp]`, `test_ovp_mismatch`, `test_ocp_malformed_readback`, `test_ocp_verified_against_current_not_voltage`, `test_every_protection_step_encodes_exactly` |
| 2 | Silent clamping; bool/NaN/inf accepted | `validation.to_units`: reject, never clamp or round | `test_out_of_range_rejected_not_clamped`, `test_non_numeric_rejected`, `test_off_resolution_rejected_not_rounded`, `test_invalid_input_writes_nothing` (28 cases, asserts zero writes) |
| 3 | Setter encoding truncation; periodic frame accepted as ack; inconsistent tolerance | integer units, golden encoders; no command-reply parsing; exact readback of `voltage_set`/`current_set`; fail-safe output OFF on mismatch; no blind resend | `test_every_current_step_encodes_exactly`, `test_every_voltage_step_encodes_exactly`, `test_golden_encoding`, `test_voltage_mismatch_raises_and_disables_output`, `test_setter_dropped_command_is_mismatch_not_success`, `test_setter_no_readback_is_indeterminate_and_not_resent` |
| 4 | `output_enable` returns `None` / `TypeError`; needs reporting | `output_on/off` return confirmed `Status` or raise `OutputStateError` (`last_status=None` ⇒ UNKNOWN); independent of reporting | `test_output_on_off`, `test_output_on_works_with_reporting_disabled`, `test_output_retry_exhaustion_unknown_state`, `test_output_on_refused_by_device_error` |
| 5 | `output_disable` trusts stale buffered frames | input dropped before each command; confirmation only from a status frame requested after it | `test_output_off_stale_off_frames_not_trusted`, `test_get_status_ignores_stale_buffered_status`, `test_read_report_is_fresh`, `test_output_off_retry_then_success` |
| 6 | No transaction lock | `RLock` held for whole transactions | `test_concurrent_callers_do_not_interleave` |
| 7 | Fixed-size reads + sleeps | `FrameScanner` (grammar-based, fragment-tolerant, resyncs), monotonic deadlines | `test_scanner_*`, `test_get_status_fragmented`, `test_get_status_ignores_truncated_frame` |
| 8 | Blanket buffer resets | explicit `discard_input()` only right before a command, logged | covered by #5 tests |
| 9 | Parsers do not validate | `fullmatch` grammar, enum checks, timer checks; unknown error code preserved, not invented | `test_malformed_report_rejected`, `test_malformed_status_rejected`, `test_unknown_safety_enum_rejected`, `test_unknown_error_code_preserved_not_invented`, `test_invalid_status_extension_rejected`, `test_get_status_only_malformed` |
| 10 | Mixed returns; `close()` before `init()` fails; misleading messages | typed returns + exception hierarchy; idempotent `open`/`close`; logging instead of print | `test_close_before_open_and_twice`, `test_open_is_idempotent_and_stops_reporting`, `test_reopen_after_close`, `test_operations_after_close_raise`, `test_port_not_found`, `test_*_failure_*`, `test_short_write_is_transport_error` |
| 11 | Reporting toggled implicitly | explicit `start/stop_reporting`; `get_status` restores prior state | `test_get_status_and_reporting_restored`, `test_get_status_keeps_reporting_when_enabled`, `test_read_report_requires_reporting`, `test_stop_reporting` |
| 12 | Inconsistent verification | single exact comparison in integer units/Decimal | covered by #1/#3 tests |
| 13 | `requirements.txt` system dump | `pyproject.toml`, pyserial only | clean build/install (§3) |
| 14 | `venv/`, caches, IDE tracked | removed, `.gitignore` | `git ls-files` |
| 15 | Broken examples | rewritten, all results checked, safe shutdown | `test_example_compiles`, `test_example_help_runs`, `test_example_runs_against_fake` |
| 16 | Inconsistent docs | README + `docs/PROTOCOL.md` rewritten | review |

## 3. Commands and results

```
$ python -m pytest -q                          # Python 3.14.8, pyserial 3.5
157 passed

$ uv run --python 3.9 --with pytest --with pyserial --with . python -m pytest -q
157 passed

$ python -m build
Successfully built dc6006l-1.0.0.tar.gz and dc6006l-1.0.0-py3-none-any.whl
  (no deprecation warnings)

$ python -m venv clean && clean/bin/pip install dist/*.whl
$ cd /tmp && clean/bin/python -c "import dc6006l; print(dc6006l.__version__)"
1.0.0
```

CI workflow added but not yet executed (branch not pushed).

## 4. Remaining protocol uncertainties and risks

1. **Status-frame field meanings** (`voltage_set`, `current_set`, `ovp`,
   `ocp`) come from the original author's reverse engineering. All
   verification depends on them. Must be confirmed by HIL step 3.
2. The device may apply a wrong value before readback detects it (historic
   0.7 V → 7 V report). The driver can only detect it and switch the output
   OFF; independent OVP hardware remains advisable.
3. Report frame rate and `KB`/`x` field meanings are unknown; timeouts are
   configurable (default 1 s per status request, 3 attempts).
4. A status frame delayed by more than `status_timeout` can arrive during a
   later transaction. It always reflects a state after an earlier command, and
   output confirmation requires the *target* state, so a false success needs a
   late frame, an external state change and a lost command together. Low
   probability, documented.
5. The 0.1 s command pacing is a precaution carried over from the old driver,
   not a verified requirement.
6. Limits (60 V / 6 A / OVP 0.2–61 V) are nominal, not verified per revision.
7. Each confirmed operation costs ~0.3–0.5 s (W, Q, W pacing); fast switching
   (square wave) is limited accordingly.

## 5. HIL evidence

`NOT RUN`. No physical device was connected during this work.
