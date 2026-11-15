# Cactus server adapter (prepared 2026-11-15)

Deployment target: `/root/autodl-tmp/foreagent/cactus-20261115`.
The existing source remains at `/root/autodl-tmp/foreagent/preflight/upstream/mle-bench/agents/aide` and the frozen rootfs remains at `/root/autodl-tmp/foreagent/author-bundle/rootfs`.

## Files and boundaries

- `controller.py` loads the author's `ForeAgent/DeepSeek-V3.2` settings and default config, using the same published 43,200-second / 5,000-step parameters in smoke and formal phases. It substitutes the server-local transport, worker hardware/data preview, model-provider routing, and observability.
- `bridge.py` runs subprocesses on the same server. It invokes the unchanged `worker.py` inside the original PRoot setup, archives each execution request/result/console, and copies each submission with a SHA-256 check.
- `guest.sh` uses a distinct task, worker tree and NVIDIA link directory. Existing Stanford scripts/directories remain inputs only. The worker runs as `foreagentx` with the existing restricted setup.
- `worker.py` is an exact copy of the frozen runtime worker, SHA-256 `42fdad8e0b205e269cae8004e6243ce30a528cbaaa3f3fd7066100cd2c61017e`.
- `baked-instructions.txt` matches the original image instructions (SHA-256 checked on launch). Cactus description and the original DA report are separate task inputs.

The compressed-image adaptation is explicit: the original controller's `prep_agent_workspace` unpacks the public data; `bridge.py` mirrors that public `input` directory to the worker before preview/execution. Candidate programs see the same prepared/extracted image files under `./input`.

## Required server preparation

1. Restore access to the old worker paths using the separately approved environment repair. This adapter performs no `/root` ACL changes.
2. Deploy these files into the target directory. Top-level runtime/worker path components must be traversable by `foreagentx`; run/API output directories are private to the controller.
3. Reuse the validated server controller venv and capture `pip freeze` / `pip check`. `requirements-controller.in` is a historical author-pin reference, rather than the deployed environment lockfile. Rebuild the observed controller from the run's `pip-freeze-start.txt`. Candidate package versions come from the unchanged OCI rootfs.
4. Place only public prepared Cactus inputs in `task/`: `train.csv`, `train.zip`, `test.zip`, `sample_submission.csv`, `description.md`, and the author's `da_report.txt`. Keep held-out answers outside this tree.
5. Keep provider keys outside the runtime directory. Default files: `/root/.config/foreagent/openai.key` and `siliconflow.key`. Configure a verified server OpenAI outlet before paid preflight. `model-config.example.json` shows optional independent provider proxies and full completion URLs. Actual configuration belongs in `/root/.config/foreagent/runtime.json` or an explicit `--model-config` path.

Only `FOREAGENT_RUN` and `FOREAGENT_DEADLINE` are set internally by the controller. Provider proxy selection uses the explicit config, rather than ambient proxy variables. The original model-name to SiliconFlow `enable_thinking` mapping is retained.

## Entrypoints

Use a fresh scope for every phase. The following are server-side examples after preparation:

```bash
cd /root/autodl-tmp/foreagent/cactus-20261115
controller-venv/bin/python controller.py --scope cactus-preflight-v1 --phase preflight
controller-venv/bin/python controller.py --scope cactus-smoke-v1 --phase smoke
controller-venv/bin/python controller.py --scope cactus-formal-v1 --phase formal
```

`preflight` makes zero model calls and checks GPU execution, config construction, public-data preprocessing and the actual Linux worker preview. Separate paid code/comparator/feedback preflight should follow connectivity validation.

`smoke` keeps the published algorithm/parameters. It finishes at the next outer step boundary after at least three draft nodes and one completed tournament. The author's completed step is saved by the original `save_run` before the stop. A diagnostic 7,200-second outer wall-clock cap bounds this phase while its author config/prompt retain 43,200 seconds. A generated training program may reach this diagnostic cap; that is a partial smoke run, with acceptance still pending. Record alarm termination and partial outputs separately. A smoke pass also requires submission ID/finite-value checks and official held-out grading outside the agent's workspace.

`formal` starts from a fresh journal and has a 43,200-second wall-clock alarm, including API waiting/retries. The default SIGALRM termination prevents upstream retry/exception handlers from swallowing the deadline; the persistent supervisor must record alarm exit because Python finalizers do not execute for this termination. Every worker additionally has a timeout tied to the same deadline and an eight-second termination grace, matching the prior bridge. A normal early step-budget end remains possible. Launch under a persistent server-side supervisor so SSH client lifetime does not govern the experiment.

## Records

Each `runs/<scope>/` contains hardware, effective config, instruction text, hashes of critical original source files, start/deadline metadata, progress/completion records (completion for normal/handled exits; alarm exit recorded by the supervisor), original `logs/exp/`, `workspaces/exp/`, per-execution task records, and `api.jsonl`. API request, routed request, and response bodies are under private `api-records/`; authorization headers are excluded and provider key text is redacted defensively. Request start/end/error events have identifiers and timestamps, enabling waiting-time monitoring. Worker raw requests/results/consoles remain under `workers/<scope>/jobs/`.

## Preparation validation

Python syntax compilation and `bash -n guest.sh` passed locally. Worker bytes match the frozen runtime. Route checks cover the three original roles and thinking flags. Linux imports, CUDA, data preparation, model connectivity, live API parsing and full end-to-end behavior require the server checks above.

## Persistent supervision and exact execution archives

Launch `supervisor.py --scope <fresh-scope> --phase smoke|formal` under the server's persistent process manager. It launches the controller in a new session, creates supervision records separately from the fresh run directory, starts `monitor.py` after `started.json`, records signal exits and worker PIDs after the termination grace, freezes runtime files and dependencies at start/end, and enforces an outer cap plus 20 seconds. Each invocation runs only the specified phase.

`tasks/<job>/submission.csv` permanently preserves each produced execution submission. `execution.json` stores exact code hash, job ID, worker wall-clock times, original execution duration, full node ID, and feedback timing. A thin wrapper forwards the original `parse_exec_result` call and return/exception while associating its node with the just-completed execution. `node-artifacts.json` covers all preserved candidates and prefers full node-ID linkage, with explicitly marked code-hash fallback for partial/legacy records. Duplicate code across nodes therefore retains separate execution timelines.

`grade_run.py --scope <scope>` checks the agent-selected best against the original private-answer checksum, 3,325 rows, exact columns, unique/matching IDs and finite scores. It computes both the unmodified official grade and independent ID-aligned ROC AUC, preserves the selected CSV, and writes success/failure records under `external-grading/<scope>/`. Those scores stay outside the agent-visible input/workspace and preserve its original selection.

The validated server controller uses Python 3.12, host PyTorch 2.5.1+cu124, OpenAI 2.14.0, httpx 0.27.2, pandas 2.2.3, NumPy 1.26.4, scikit-learn 1.4.2 and SciPy 1.13.1. The original worker rootfs uses Python 3.11.13 and PyTorch 2.2.0+cu121. These controller dependency differences are disclosed separately from the preserved original algorithm and parameters; exact installed packages and dependency validation are recorded by the supervisor.
