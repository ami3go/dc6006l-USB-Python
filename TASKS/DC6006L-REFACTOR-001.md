# DC6006L-USB-Python — Safety and Reliability Refactoring Task

**Task ID:** DC6006L-REFACTOR-001  
**Priority:** P0 safety / P1 correctness / P2 maintainability  
**Target branch:** `refactor/safety-protocol-hardening`  
**Base branch:** `main`  
**Scope:** Python USB/serial control library for the FNIRSI DC6006L  
**Execution rule:** Software-only tests first. No live-output, load, protection-trip, or other hardware test without an explicitly authorised operator and a documented safe HIL procedure.  
**Revision:** r2 (2026-11-26) — findings re-verified against `src/dc6006l_class.py` at `54e8cbf` by executing each failure path against a fake serial port. Corrected: exception raised by the protection setters, the "fixed-width" framing claim, the attribution of the historical voltage bug. Added: float-truncation encoding errors, stale-frame false success in `output_disable`, reporting dependency of `output_enable`, ack/periodic-frame ambiguity, broken example/README API references, and existing OVP/OCP readback evidence.

## 1. Objective

Refactor the existing driver into a deterministic, testable and fail-safe library. The driver must never silently transform an invalid request into a different output setting, must never report success without a valid device acknowledgement/readback, and must handle malformed, delayed, truncated or missing serial data without crashing or continuing as if the operation succeeded.

The protocol was reverse-engineered from serial traffic; it is not an officially published FNIRSI protocol specification. Preserve observed command encodings only where supported by repository evidence or controlled protocol captures. Do not invent undocumented commands, response fields, or device limits.

## 2. Current implementation findings and risks

The following findings are based on static inspection of `src/dc6006l_class.py`, `command_list.md`, `README.md`, `requirements.txt`, and the example scripts on `main`. They are code-level findings, not claims of a live instrument test.

### P0 — Output-setting and protection safety

1. **Protection setters are defective (`set_volt_protect`, `set_current_protect`).**
   - Both methods write a command, read 27 bytes, then derive purported limits from slices of the outgoing command string rather than from the received response.
   - Verified behaviour: if exactly 27 bytes arrive, `int(txt[0:4])` evaluates `int("B050")` and raises `ValueError` before the undefined-variable comparison is reached (the comparison against the undefined `v_out`/`voltage` would otherwise raise `NameError`). If fewer bytes arrive, the method falls through and returns `None`. **The methods can never return `True`**: protection is never confirmed, and callers that ignore the return value (all current examples) proceed without verified OVP/OCP.
   - The current-protection method compares `voltage` (undefined in that scope) rather than the requested current limit.
   - Encoding truncates instead of rounding: `int(voltage * 100)` / `int(current * 1000)`. Verified: 287 of the 0.01 V OVP values in 0.2–61 V are sent 10 mV low (e.g. `0.29` → `B0028`, `0.57` → `B0056`); 48 of the 1 mA OCP values are sent 1 mA low (e.g. `1.001` → `D1000`).
   - `set_volt_protect` contains its own duplicated clamp (0.2–61 V) in addition to `range_check`.
   - The meaning of the 27-byte reply after `B`/`D` is undocumented; it is most likely just the next periodic status frame, which carries no limit fields.
   - Existing evidence for readback: the 66-byte status frame parsed by `get_status()` contains `v_lim`, `i_lim` and `p_lim` fields. These are the evidence-based readback path for OVP/OCP/OPP verification (field meaning to be confirmed by a controlled capture in Step 0).
   - Consequence: OVP/OCP configuration may not be applied or verified, and there is no way for the caller to know. A fault or incorrect setpoint may then reach the load before the operator notices.
   - Required change: encode with correct rounding in integer protocol units; never parse the outgoing command; after sending, read back `v_lim`/`i_lim` from a validated full status frame and compare with the requested value at the documented resolution; return a typed result or raise a specific exception. If the readback cannot be obtained or interpreted, report an indeterminate/failed operation—never success.

2. **Range validation silently clamps requests (`range_check`).**
   - Requests above/below the allowed range are changed to the nearest boundary and then transmitted.
   - For example, an invalid request can become a valid but unintended 60 V or 6 A command.
   - Verified: `set_v_out(100)` transmits `V6000`; `set_i_out(-5)` transmits `I0000`; `set_v_out(True)` transmits `V0100` (1 V); `+inf` is clamped to the maximum; NaN passes the checks and only fails later in `int()`. The current-range message wrongly says "V".
   - The helper uses parameter names `min` and `max`, shadowing Python built-ins, and does not reject NaN or infinity.
   - Consequence: calling code may believe it requested one value while the instrument receives another. In a power-supply context this can damage a DUT, load, wiring, or connected measurement equipment.
   - Required change: replace clamping with strict validation. Reject out-of-range, non-numeric, boolean, NaN and infinite values before any serial write. Raise `ValueError` (or a documented domain exception) containing the parameter, requested value and supported range. Do not silently clamp. Limits must be model/protocol-derived and clearly documented; do not assume the nominal 60 V / 6 A values are guaranteed for every hardware revision.

3. **Voltage/current command encoding and acknowledgement need hardening.**
   - The fixed-width 4-digit command format (`V0100`, `I0500`) is the observed protocol and is **not** itself a defect; keep it, but generate it from validated integer units and assert the width.
   - `set_i_out` truncates instead of rounding (`int(round(current, 5) * 1000)`). Verified: 48 of the 6001 valid 1 mA setpoints are transmitted 1 mA low (e.g. `1.001` → `I1000`, `1.003` → `I1002`); the exact-equality check then reports a spurious mismatch. `set_v_out` rounds first and encodes all 0.01 V steps correctly.
   - Both setters accept any 10 bytes with `A` at positions 4 and 9. The first 10 bytes of every periodic status frame (`VVVVAIIIIA`, measured V/I) have the same shape, so with reporting enabled a status frame can be accepted as the acknowledgement. Whether the real acknowledgement echoes the setpoint or the measured value is unverified.
   - `set_v_out` accepts a mismatch up to 0.1 V (10× the 0.01 V resolution), while its exact-equality branch and the current setter use different comparison behaviour.
   - Neither setter has an explicit failure return for malformed/empty replies: an empty reply returns `None`; non-numeric fields raise `ValueError`.
   - The README records a historical issue where a requested voltage (e.g. 0.7 V) was applied as 7 V or 70 V. Its root cause (firmware parsing vs. serial corruption) is **unknown**; do not attribute it to the driver's framing without evidence. It is a known project risk and must remain prominent until understood.
   - Consequence: wrong setpoint transmitted for some values, a stale or unrelated frame accepted as confirmation, or a false-positive/ambiguous return.
   - Required change: centralise command formatting and response validation; enforce exact field widths and allowed characters; use `Decimal` or integer base units for setpoint conversion; define per-parameter device resolution and verification tolerance; reject malformed/truncated/extra data; require a valid acknowledgement/readback before returning success. If protocol behaviour cannot be proven, fail closed and document the uncertainty.

4. **Output-enable path can fail ambiguously.**
   - `output_enable` retries four times but has no explicit final `False` return, so exhaustion returns `None`.
   - `__output_enable_p` assumes `get_state()` returns a mapping and immediately indexes `state["Output"]`; a timeout or malformed response returns `None` and raises `TypeError`.
   - `get_state()` only works while periodic reporting (`Q`) is enabled. Verified: with reporting off, `output_enable()` always raises `TypeError` on the first attempt (after the `N` command has already been sent, so the output may be ON).
   - Consequence: callers cannot distinguish confirmed ON from a failed/unknown state. Exception paths may interrupt a controlled shutdown/startup sequence.
   - Required change: make enable/disable operations return a consistent typed result or raise a specific exception; validate state object and output field; ensure a fresh status source is available (reporting enabled or an explicit status request) before confirming; retry only on explicitly retryable transport/protocol failures; after each attempt read back the output state; after final failure report state as unknown and do not claim success.

5. **`output_disable` can report OFF from stale buffered status frames.**
   - `output_disable` writes `F` without discarding previously received bytes, then `get_state()` reads the oldest 27 bytes in the input buffer. With periodic reporting enabled, the buffer can hold old frames captured before the command.
   - Verified with a fake serial port: buffered OFF frames followed by an ON frame (i.e. `F` lost, output still ON) → `output_disable()` returns `True`. The same applies to `output_enable` with stale ON frames.
   - Consequence: the application believes the output is OFF while it is still energised. This is the most direct safety hazard in the current driver.
   - Required change: a confirmation must come from a frame received **after** the command was written (sequence/timestamp ordering in the reader), never from data buffered before it. If no post-command frame is received before the deadline, the state is unknown.

### P1 — Protocol, transport and state correctness

6. **Serial transactions are not protected against concurrent access.**
   - `send` and `query` operate directly on the shared serial object without a lock or transaction abstraction.
   - Note: no code in the repository currently uses the driver from more than one thread, so this is a latent rather than an observed defect. A single `threading.Lock` around each transaction is sufficient; do not build an async/queue architecture for it.
   - Consequence: two threads/tasks can interleave command writes and reads. A reply can be consumed by the wrong caller, potentially causing a false acknowledgement or wrong interpretation of a setpoint.
   - Required change: implement one transaction lock covering write, response collection and parsing. Document that one physical serial connection supports one in-flight transaction. If asynchronous support is ever added, use a single command queue/worker rather than parallel direct reads.

7. **Response framing relies on fixed-size reads and sleeps.**
   - `query` uses fixed byte counts and a fixed 150 ms delay; `get_status` and `get_state` assume 66- and 27-byte messages.
   - `query` decodes without explicit error handling and may return partial data after the serial timeout.
   - Consequence: slow USB scheduling, OS load, device timing variation or fragmented USB packets can cause truncated responses, timeouts, decode errors or accidental consumption of a later message.
   - Required change: implement a documented framing reader using the protocol's verified terminator/length rules and a monotonic deadline. Accumulate fragmented reads until a complete frame or deadline. Distinguish timeout, framing error, decode error and device error. Do not use arbitrary sleeps as the correctness mechanism.

8. **Input/output buffer resets can discard meaningful traffic.**
   - `send` resets the output buffer; `query` resets both input and output buffers before commands. The protocol also supports periodic state reporting (`Q`/`W`).
   - Consequence: a reset can discard a pending response or asynchronous status frame. The next command may then consume stale or misaligned data.
   - Required change: define explicit ownership and lifecycle for periodic reporting. Do not clear buffers as a generic synchronisation strategy. Drain/parse known unsolicited frames safely, and only discard bytes in a documented recovery path with diagnostics.

9. **Status parsers are insufficiently defensive.**
   - `get_status` checks whether the string contains `KB`, replaces it, splits on `A`, and immediately converts fixed indexes to integers without verifying the expected field count, widths, numeric characters, units, or ranges.
   - `get_state` checks selected delimiter positions (not the ones at indices 24 and 26) but then indexes split fields without validating count and contents. It reads fixed 27-byte chunks with no resynchronisation, so if frames carry a terminator (e.g. `\r\n`, unverified) or a read starts mid-frame, all subsequent reads are misaligned. Verified: a non-numeric field raises `ValueError`.
   - `get_status(var_name)` raises `KeyError` for an unknown name; `get_status` and `get_state` use different key names for the same quantities (`v_out`/`on_off` vs `Vout`/`Output`).
   - Consequence: corrupt or partial data can raise `IndexError`/`ValueError`; a coincidental substring can be treated as a valid frame; callers may crash while controlling the supply.
   - Required change: separate framing from parsing. Parse into immutable typed status models. Validate field count, exact grammar, numeric bounds, status enumerations and device error codes. Malformed frames must raise a protocol exception or produce an explicit invalid-frame result; never return partially populated status.

10. **Return contracts and errors are inconsistent.**
   - Methods mix `True`, `False`, `None`, dictionaries and exceptions; `get_status` returns `False` on an invalid reply, while callers may expect a dictionary.
   - `close` assumes `self.ser` exists and is open (verified: `close()` before `init()` raises `AttributeError`); `send`, `query` and status methods do not consistently check connection state.
   - `init` prints a misleading “COM port connected” message when the requested port is absent.
   - Consequence: errors are easy to miss and may turn into secondary exceptions far from the original failure.
   - Required change: define public API contracts. Use explicit exception classes (connection, timeout, protocol, device rejection, validation) and documented return models. Make `close` idempotent. Guard every transport operation against an uninitialised/closed connection. Replace print-based library diagnostics with logging.

11. **State-reporting mode is manipulated implicitly by status reads.**
    - `get_status` disables and re-enables reporting as part of the call and leaves reporting **enabled** afterwards, which silently changes the buffering behaviour that finding 5 depends on.
    - Consequence: a caller's reporting state can be changed unexpectedly, and unsolicited frames may race with request/response traffic.
    - Required change: model reporting as explicit connection state. Provide an explicit start/stop reporting API and one parser/reader path that owns incoming bytes. Document whether periodic reporting is required for `get_state` and how it interacts with command acknowledgements.

12. **Setpoint verification semantics are inconsistent.**
    - Voltage comparison includes an unexplained 0.1 V allowance; current uses exact float equality.
    - Floating-point conversion truncates in `set_i_out`, `set_volt_protect` and `set_current_protect` (see findings 1 and 3), so valid values are transmitted wrongly and then fail verification.
    - Consequence: callers receive inconsistent results for equivalent operations and may accept a materially different setpoint.
    - Required change: represent values in integer protocol units or `Decimal`; define resolution and tolerance for each quantity from observed device behaviour; use one shared verification function; include requested and measured values in failure diagnostics.

### P2 — Packaging, examples and maintainability

13. **Dependency file is an environment snapshot, not a project dependency list.**
    - `requirements.txt` contains a large set of unrelated OS/Jupyter/system packages and does not declare the actual required PySerial dependency.
    - Consequence: installation may fail on other platforms/Python versions, install unnecessary packages, or omit the library's real runtime dependency.
    - Required change: declare only direct runtime dependencies (at minimum the verified serial dependency, with a supported version range); separate development/test dependencies; add a `pyproject.toml` and verify clean installation in a fresh virtual environment.

14. **A virtual environment and generated artifacts are tracked.**
    - The repository root contains a `venv/` directory and `src/__pycache__/`; `.idea/` is also present.
    - Consequence: repository bloat, machine-specific files, accidental interpreter/package leakage and non-reproducible installations.
    - Required change: remove generated environment/cache/IDE artifacts from version control, extend `.gitignore`, and document reproducible environment creation. Do not remove user-authored project files.

15. **Examples do not match the implementation's return types.**
    - `Example/dc6006l_class_test.py` treats `get_state()` as a list (`state[1]`, `state[0]`), but the implementation returns a dictionary with keys such as `Iout` and `Vout`.
    - All examples store the result of `init` but continue regardless of whether connection succeeded, and ignore every setter/protection return value.
    - `Example/dc6006l_class_test2.py` calls `set_v_out2`, which does not exist (`AttributeError`), and calls `output_enable()` **before** setting the voltage, so the output is energised at whatever setpoint was previously stored in the supply.
    - Examples import `src.dc6006l_class`, which fails with `ModuleNotFoundError` when run as `python Example/<file>.py` (the repository root is not on `sys.path`).
    - Consequence: examples can crash or continue after failed connection, encouraging unsafe copy/paste usage.
    - Required change: update every example to the documented API, check connection and all operation results, use `try/finally` or a context manager, disable output in a best-effort cleanup path, and never assume an output state if readback failed.

16. **README and protocol documentation are incomplete/inconsistent.**
    - README documents `set_v_out_retry` and `set_i_out_retry`, which do not exist; documents `get_state()` as returning a list; documents `set_volt_protect` but not `set_current_protect`; uses inconsistent status key naming compared with `get_state`, and contains a warning about potentially severe voltage-setting errors without a modern safety guide.
    - `command_list.md` is the only protocol reference and includes ambiguous unit/field descriptions; `D0500` is labelled "voltage protection" although it sets current protection; the 66-byte full-status frame (with `v_set`, `i_set`, `v_lim`, `i_lim`, `p_lim`, timer fields and the leading `KB` marker) is not documented at all; `E` (power protection) and the timer commands are documented but not implemented.
    - Consequence: users can call undocumented or misunderstood functions and infer incorrect units, protection behaviour or status meanings.
    - Required change: document connection setup, supported OS/Python versions, exact public API, units, value ranges and source of each limit, command/response framing, device error mapping, firmware/model assumptions, known limitations and safe operation. Mark undocumented protocol assumptions explicitly.

### Priority and proportionality

The driver is a single ~400-line file. Fix order should follow risk, and the fixes for P0 items must not wait for the full architecture:

1. Findings 5 and 4 (output state false success / crash), 1 (protection never verified), 2 and 3 (wrong values transmitted).
2. Findings 7–12 (framing, parsing, contracts, reporting lifecycle).
3. Finding 6 (lock — cheap, latent).
4. Findings 13–16 (packaging, examples, docs).

The module split in section 3 is a suggestion; a smaller structure is acceptable if responsibilities (validation, encoding, framing/parsing, transport) stay separately testable.

## 3. Required architecture

Keep the public API simple, but separate responsibilities. The package directory must remain at repository root (do not introduce a `src/` layout).

Suggested structure (names may be adjusted if the resulting separation is equally clear):

```text
dc6006l/
    __init__.py
    driver.py             # public DC6006L class and high-level operations
    transport.py          # serial lifecycle, locking, framed read/write
    protocol.py           # command encoding and response framing/parsing
    models.py             # immutable status/result data models
    exceptions.py         # typed driver exceptions
    validation.py         # strict numeric and range validation
tests/
    unit/
    protocol/
    integration/
examples/
pyproject.toml
README.md
```

Do not preserve a broken API merely for compatibility. If compatibility wrappers are retained, deprecate them and test them. Use a single public naming convention (PEP 8 preferred), with a documented compatibility story for the existing `dc6006l_class` import/class name.

## 4. Execution plan — perform in this order

### Step 0 — Baseline and protocol evidence
1. Record the base commit SHA and inspect all tracked files, branches and existing tests.
2. Capture the existing public API and current observed command formats from `command_list.md`, README and source.
3. Identify which protocol facts are verified by source/capture and which are assumptions. Known evidence in the repository: command formats in `command_list.md`; 27-byte periodic frame layout (`VVVVA IIIIA PPPPA xA TTTA mA eA oA`); 66-byte full-status layout in `get_status()` including `v_lim`/`i_lim`/`p_lim`. Open questions: content of the reply to `V`/`I` (setpoint echo vs measured), content of the reply to `B`/`D`/`E`, whether frames are terminated, periodic frame rate, meaning of the `KB` marker and of field `P1`.
4. Do not change protocol encodings based only on guesswork. If a response format is unknown, create a clearly marked open question and make the relevant operation fail safely until resolved.
5. Add a baseline test inventory and record current failures.

**Exit criteria:** protocol assumptions are listed; no unverified command format is silently treated as fact.

### Step 1 — Establish strict validation and API contracts
1. Implement numeric conversion that rejects booleans, strings unless explicitly supported, NaN and infinity.
2. Define per-quantity units, resolution, min/max and tolerance from reliable device evidence.
3. Replace clamping with exceptions before any I/O.
4. Define typed result/status models and exception hierarchy.
5. Define behaviour for disconnected/closed driver instances.

**Tests:** below-minimum, above-maximum, boundary, bool, string, NaN, +infinity, -infinity, precision/resolution and no-write-on-validation-failure.

### Step 2 — Build a deterministic serial transport
1. Encapsulate PySerial in a transport class.
2. Add a lock around complete command/response transactions.
3. Use monotonic deadlines and framed reads; support fragmented serial reads.
4. Distinguish timeout, empty reply, malformed frame and device rejection.
5. Avoid blanket buffer resets; implement an explicit recovery/resynchronisation policy.
6. Make open/close idempotent and ensure exceptions do not leave inconsistent connection state.
7. Add structured logging with command names and safe redaction; do not log secrets (none expected) or claim a command succeeded merely because bytes were written.

**Tests:** fake serial transport, fragmented reads, delayed reads, partial frames, no response, extra bytes, stale frame, concurrent callers, write failure, read failure, close twice and call while disconnected.

### Step 3 — Implement protocol codec and defensive parsers
1. Centralise command encoders for voltage, current, OVP, OCP, output state and reporting.
2. Use integer protocol units or Decimal; validate fixed-width numeric fields and command terminators.
3. Implement separate parsers for command acknowledgements and periodic status frames.
4. Validate exact grammar, field count, field widths, numeric conversion, enumerations and plausible ranges.
5. Preserve raw frames in diagnostic exceptions/logging where safe.
6. Do not infer the meaning of unknown fields; retain them as explicitly unknown or omit them from the public model.

**Tests:** golden valid frames, each malformed delimiter/field, truncated and extended frames, non-ASCII bytes, invalid numeric data, unknown enum values and boundary values.

### Step 4 — Reimplement setpoint and protection operations
1. Make voltage/current setters validate first, encode once, send under transaction lock and wait for the correct acknowledgement.
2. Read back the relevant setpoint and compare using documented resolution/tolerance.
3. Return success only when the device response and readback are valid and consistent.
4. Reimplement OVP/OCP setters only after their response semantics are verified. Verification should use the `v_lim`/`i_lim` fields of a fresh, fully validated 66-byte status frame unless a capture proves the direct reply carries the limit.
5. Never parse outgoing command bytes as if they were a device response.
6. On timeout or ambiguous acknowledgement, report an indeterminate result and do not blindly repeat a non-idempotent/uncertain command.
7. Ensure a failure in one operation does not leave a stale reply to be consumed by the next operation.

**Tests:** command byte-for-byte golden tests, correct units/scaling, response mismatch, timeout, wrong reply, stale reply, device rejection and no false-positive success.

### Step 5 — Reimplement output control and status handling
1. Implement output enable/disable with explicit confirmation and bounded retry policy. Confirmation must come from a status frame received after the command was written; frames buffered before the command must never be used.
2. Validate returned status before accessing fields.
3. Provide a clear “unknown state” outcome when readback is unavailable.
4. Separate periodic reporting lifecycle from ordinary status reads.
5. Map device error/protection flags without inventing meanings.
6. Ensure cleanup paths attempt output disable only when connection is usable and report cleanup failure.

**Tests:** stale buffered OFF frames followed by ON frame after `F` (must not report OFF), output_enable with reporting disabled, output already ON/OFF, state timeout, malformed status, retry success, retry exhaustion, device protection/error flags and reporting start/stop interactions.

### Step 6 — Packaging and examples
1. Create a root-level installable package and `pyproject.toml`.
2. Replace environment-snapshot requirements with minimal runtime and development dependencies.
3. Remove tracked venv/cache/IDE-generated artifacts and update `.gitignore`.
4. Update examples to use only the public API, check all failures, and clean up safely.
5. Update README and protocol docs with units, limits, exceptions, examples, compatibility and known protocol caveats.
6. Verify installation from a clean environment and import from outside the repository root.

**Tests:** build wheel/sdist, install into clean virtual environment, import smoke test, run example syntax checks without connecting to hardware.

### Step 7 — Regression, security and HIL readiness review
1. Run all unit, protocol, integration-with-fake-serial and static checks.
2. Add regression tests for every issue listed in section 2.
3. Review all code paths that can change voltage, current, OVP, OCP or output state.
4. Confirm invalid input never writes to the serial port.
5. Confirm no malformed/partial response can produce success.
6. Produce a HIL runbook with operator-controlled setup, independent voltage/current measurement, current-limited/load-safe conditions, emergency output-disable and power-disconnect procedure, expected readings, stop criteria and evidence capture.
7. Do not execute HIL tests as part of this software task unless separately authorised. A software test pass is not hardware qualification.

**Exit criteria:** all automated tests pass; protocol assumptions are documented; HIL runbook is reviewed; no live hardware validation is claimed unless evidence exists.

## 5. Minimum regression matrix

| Area | Required cases | Expected behaviour |
|---|---|---|
| Input validation | min/max, outside range, bool, NaN, infinity | Invalid input rejected before serial write |
| Voltage/current encoding | zero, resolution boundaries, max, rounding; every 1 mA / 0.01 V step | Exact documented command bytes (e.g. `1.001` A → `I1001`, OVP `0.29` V → `B0029`) |
| Acknowledgement | valid, mismatch, empty, partial, malformed | Only valid matching response succeeds |
| OVP/OCP | valid response, mismatch, timeout, malformed | Never report configured without verified readback |
| Status parser | valid frame, missing field, extra field, invalid number | Typed status or explicit protocol error |
| Output control | ON/OFF confirmation, timeout, retry exhaustion, stale buffered frames, reporting disabled | Confirmed state from post-command frame or explicit unknown/failure |
| Transport | delayed/fragmented data, concurrent calls, disconnect | No response cross-talk; bounded failure |
| Lifecycle | open twice, close twice, call after close | Predictable documented behaviour |
| Packaging | clean install, import, examples | Reproducible install; no hardware required; no example calls a non-existent method |

## 6. Safety requirements — non-negotiable

- Never silently clamp a setpoint or protection value.
- Never claim success based only on a successful serial write.
- Never treat an empty, partial, stale or malformed response as a valid acknowledgement.
- Never retry blindly when command delivery/acceptance is ambiguous; first resynchronise and determine state where protocol allows.
- Never allow concurrent callers to interleave serial transactions.
- Never assume the output is OFF when status is unavailable. Represent it as unknown.
- Do not disable or weaken hardware protections to make tests pass.
- Do not add a firmware flashing, bootloader, undocumented command or firmware-modification feature in this refactor.
- Do not run live output/HIL tests without explicit operator authorisation and a reviewed procedure.
- Keep `main` unchanged; work only on the designated feature branch until reviewed.

## 7. Definition of done

- [ ] All P0/P1 findings are fixed with regression tests.
- [ ] Every public method has documented inputs, units, return type and exceptions.
- [ ] All numeric validation happens before serial I/O.
- [ ] Serial transactions are atomic and bounded by deadlines.
- [ ] All protocol parsers validate complete frames before returning data.
- [ ] OVP/OCP setters verify actual device readback using verified protocol semantics.
- [ ] Output state is confirmed or explicitly unknown; never silently assumed.
- [ ] Unit/protocol/fake-serial tests pass in CI.
- [ ] Package installs cleanly from a built distribution.
- [ ] Examples and README match the implemented API.
- [ ] Generated environment files are no longer tracked.
- [ ] HIL runbook exists and clearly separates software evidence from hardware evidence.
- [ ] No changes have been merged into `main` as part of this task.

## 8. Required completion report

When implementation is complete, provide:
1. Commit/PR references and changed-file summary.
2. A finding-by-finding closure table linking each original issue to code and tests.
3. Exact commands used for tests and their results.
4. Clean-install/build results.
5. Remaining protocol uncertainties and unresolved risks.
6. HIL status: `NOT RUN`, `READY FOR AUTHORISED OPERATOR`, or `COMPLETED WITH EVIDENCE`. Never use the last status without attached evidence.
