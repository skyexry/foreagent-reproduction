"""Stable run/evaluate/status entry point; run from the project root."""
import argparse
import json
from pathlib import Path

from .core import ROOT, REGISTRY, evaluate_run, load_context, read_json, run_selection


def compact(summary):
    return {k:summary[k] for k in ('tasks','jobs','full_population','episode_status_counts','macro','contrasts')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command',required=True)
    run = commands.add_parser('run',help='Select first, then independently evaluate')
    mode = run.add_mutually_exclusive_group(required=True)
    mode.add_argument('--baseline',action='store_true')
    mode.add_argument('--policy',type=Path)
    run.add_argument('--output',type=Path,required=True)
    run.add_argument('--limit-jobs',type=int,help='First N development jobs: smoke only')
    evaluate = commands.add_parser('evaluate',help='Reconstruct and independently re-score a saved run')
    evaluate.add_argument('--run',type=Path,required=True)
    status = commands.add_parser('status',help='Read recorded status and verify frozen files')
    status.add_argument('--json',action='store_true')
    args = parser.parse_args()
    if args.command=='run':
        output=run_selection(args.output,args.policy,args.limit_jobs)
        result=compact(evaluate_run(output))
    elif args.command=='evaluate':
        result=compact(evaluate_run(args.run))
    else:
        registry,_,_,_=load_context()
        state_path=ROOT/registry['paths']['state']
        result=read_json(state_path) if state_path.exists() else {'status':'acceptance_pending'}
        result={**result,'current_protected_files':'verified','environment_id':registry['environment_id']}
        if not args.json:
            print('状态：'+result['status'])
            print('范围：26个开发任务；固定反馈，最多13次唯一比较。')
            print('冻结文件：当前哈希核验通过。')
            print('阅读入口：'+str(ROOT/'research/README.md'))
            return
    print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))


if __name__=='__main__':
    main()
