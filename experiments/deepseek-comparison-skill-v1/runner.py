"""Call the registered SiliconFlow judge on a blind, paired prompt/position design."""
import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
import fcntl
import hashlib
import http.client
import json
import os
from pathlib import Path
import random
import ssl
import sys
import time
import urllib.error
import urllib.request

import certifi

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from run_coverage import read_stream
from run_smoke import MODEL, MAX_TOKENS, THINKING_BUDGET
from vendor.foreagent import prompt

TASKS = ROOT / "data/reward-model/corpus-6b322cb-raw-v1/tasks"
ENDPOINT = "https://api.siliconflow.cn/v1/chat/completions"
RESULTS = HERE / "results"
MARKER = "- Response format:"
ARMS = ("original", "skill")
ORDERS = ("AB", "BA")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def append_row(path, row):
    with path.open("a", encoding="utf-8") as target:
        target.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
        target.flush()
        os.fsync(target.fileno())


def prepare():
    manifest = HERE / "blind_manifest.json"
    skill_path = HERE / "skill.txt"
    skill = skill_path.read_text().strip()
    pairs = json.loads(manifest.read_bytes())["pairs"]
    if len(pairs) != 24 or len({p["pair_id"] for p in pairs}) != 24 or not skill:
        raise ValueError("Expected 24 unique blind pairs and a skill")
    calls = []
    for pair in pairs:
        paths = [ROOT / pair[k+"_path"] for k in ("a","b")]
        for side,path in zip(("a","b"),paths):
            if digest(path.read_bytes()) != pair[side+"_sha256"]:
                raise ValueError("Candidate hash mismatch")
        resources = prompt.load_task_resources(pair["task"], tasks_root=str(TASKS))
        if not all(resources[k] for k in ("task_desc","data_analysis")):
            raise ValueError(f'Missing task context: {pair["task"]}')
        group = []
        for order in ORDERS:
            direction = 1 if order=="AB" else -1
            displayed = [pair["a_id"], pair["b_id"]][::direction]
            user = prompt.build_user_prompt(pair["task"], {"paths":[str(p) for p in paths[::direction]]},
                str(TASKS.parent), tasks_root=str(TASKS), allow_cot=True, prompt_boost=True)
            if user.count(MARKER)!=1 or "# Could not read file:" in user:
                raise ValueError("Upstream prompt missing the insertion point or code")
            for arm in ARMS:
                content = user if arm=="original" else user.replace(MARKER, skill+"\n"+MARKER, 1)
                messages = [{"role":"system","content":prompt.BENCH_SYSTEM_PROMPT_COT},
                            {"role":"user","content":content}]
                payload = {"model":MODEL,"messages":messages,"temperature":1.0,"enable_thinking":True,
                           "thinking_budget":THINKING_BUDGET,"max_tokens":MAX_TOKENS,"stream":True}
                data = json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
                row = {"pair_id":pair["pair_id"],"task":pair["task"],"arm":arm,"order":order,
                       "presented_ids":displayed,"request_sha256":digest(data),"request_model":MODEL}
                group.append((row,data))
        random.Random("deepseek-comparison-skill-v1|"+str(pair["pair_id"])).shuffle(group)
        calls.extend(group)
    return calls


def judge(item, key, tls):
    row,data = item
    request = urllib.request.Request(ENDPOINT, data=data, headers={
        "Authorization":"Bearer "+key,"Content-Type":"application/json","Accept":"text/event-stream"})
    started = time.monotonic()
    result = {**row,"response_model":None,"finish_reason":None,"reasoning_present":None,"usage":None,
              "estimated_cost_cny":None,"final_answer":None,"parsed":{},"predicted_id":None,
              "predicted_index":None,"valid":False,"error":None,"http_status":None,
              "response_id":None,"completion_received":False,"attempt":1}
    try:
        with urllib.request.urlopen(request,context=tls,timeout=240) as response:
            result["http_status"] = response.status
            body = read_stream(response)
        choice = body["choices"][0]
        message = choice["message"]
        usage = body["usage"]
        cached = usage.get("prompt_cache_hit_tokens", usage.get("prompt_tokens_details",{}).get("cached_tokens",0))
        result.update(response_id=body.get("id"), completion_received=True,
                      response_model=body.get("model"),finish_reason=choice["finish_reason"],
                      reasoning_present=bool(message.get("reasoning_content")),usage=usage,
                      final_answer=message["content"],
                      estimated_cost_cny=(4*(usage["prompt_tokens"]-cached)+0.4*cached+6*usage["completion_tokens"])/1e6)
        if result["response_model"] != MODEL or result["finish_reason"]!="stop":
            result["error"] = "response_model_mismatch" if result["response_model"] != MODEL else "incomplete_generation"
        else:
            parsed = prompt.parse_response(message["content"],2)
            idx = parsed.get("predicted_best_index")
            if idx not in (0,1):
                raise ValueError("Invalid winner")
            result.update(valid=True,parsed=parsed,predicted_index=idx,predicted_id=row["presented_ids"][idx])
    except urllib.error.HTTPError as exc:
        result.update(error="http_error",http_status=exc.code)
    except (urllib.error.URLError, TimeoutError, http.client.HTTPException, OSError) as exc:
        result["error"] = "transport_"+type(exc).__name__
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        result["error"] = "stream_or_parse_"+type(exc).__name__
    result["seconds"] = round(time.monotonic()-started,3)
    result["finished_utc"] = datetime.now(timezone.utc).isoformat()
    return result


def execute(calls, workers):
    RESULTS.mkdir(exist_ok=True)
    ledger_path = RESULTS / "dispatch.jsonl"
    record_path = RESULTS / "judgments.jsonl"
    # A persistent lock file also protects against simultaneous resume processes.
    with (RESULTS/".runner.lock").open("a+") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        dispatched = read_rows(ledger_path)
        finished = read_rows(record_path)
        known = {row["request_sha256"] for row,_ in calls}
        sent = {row["request_sha256"] for row in dispatched}
        done = {row["request_sha256"] for row in finished}
        if len(sent)!=len(dispatched) or len(done)!=len(finished) or not done<=sent<=known:
            raise RuntimeError("Ledger contains duplicated, changed or unknown requests")
        if sent != done:
            raise RuntimeError("An earlier send has unknown outcome; reconcile dispatch ledger before resuming")
        key = (Path.home()/".config/foreagent/siliconflow.key").read_text().strip()
        tls = ssl.create_default_context(cafile=certifi.where())
        pending = iter((r,d) for r,d in calls if r["request_sha256"] not in done)
        stop = False
        count = len(done)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            active = set()
            while True:
                while not stop and len(active)<workers:
                    item = next(pending,None)
                    if item is None:
                        break
                    row,_ = item
                    append_row(ledger_path,{**row,"dispatched_utc":datetime.now(timezone.utc).isoformat()})
                    active.add(pool.submit(judge,item,key,tls))
                if not active:
                    break
                ready,active = wait(active,return_when=FIRST_COMPLETED)
                for future in ready:
                    result = future.result()
                    append_row(record_path,result)
                    count+=1
                    print(f'{count}/{len(calls)} {result["pair_id"]} {result["arm"]}/{result["order"]} '
                          f'valid={result["valid"]} HTTP={result["http_status"]} error={result["error"]}',flush=True)
                    if result["http_status"] in (400,401,402,403,404) or result["error"]=="response_model_mismatch":
                        stop=True
        if stop:
            raise SystemExit("Dispatch stopped after a configuration, authorization, quota, or model error")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run",action="store_true",help="Make paid API calls; default validates without API calls")
    p.add_argument("--workers",type=int,default=8,choices=range(1,13))
    args = p.parse_args()
    calls=prepare()
    schedule = "\n".join(row["request_sha256"] for row,_ in calls).encode()
    print(f'Validated {len(calls)} blind calls; ordered request SHA256 {digest(schedule)}',flush=True)
    if args.run:
        execute(calls,args.workers)


if __name__=="__main__":
    main()
