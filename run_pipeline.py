"""Run all capstone parts A-D in dependency order from one command."""
from __future__ import annotations
import json, subprocess, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))


def main():
    started=time.time()
    raw_required=[ROOT/'data'/'raw'/x for x in ['customers.csv','products.csv','orders.csv','tickets.csv','policy_eval.csv','agent_scenarios.csv']]
    policy_required=list((ROOT/'data'/'policies').glob('*.txt')) if (ROOT/'data'/'policies').exists() else []
    if not all(p.exists() for p in raw_required) or len(policy_required)!=5:
        subprocess.run([sys.executable,str(ROOT/'generate_data.py')],cwd=ROOT,check=True)
    # Import after generation: Part D fits its TF-IDF matrix from the policy files at module load.
    from src import part_a, part_b, part_c, part_d
    from src.validate_part_a import validate as validate_part_a
    status={'pipeline':'INSTAMART Customer Intelligence & Support Copilot','stages':{},'started_unix':started}
    for name,func in [('Part A — Data Foundation',part_a.run),('Part B — Customer Intelligence',part_b.run),
                      ('Part C — Support Ticket Intelligence',part_c.run),('Part D — Policy RAG and Refund Agent',part_d.run)]:
        stage_start=time.time()
        func()
        if name.startswith('Part A'):
            validate_part_a(quiet=True)
        status['stages'][name]={'status':'passed','seconds':round(time.time()-stage_start,3)}
        print(f"{name}: PASSED")
    required=[
      'data/clean/customers.csv','data/clean/products.csv','data/clean/orders.csv','data/instamart.db','sql/queries.sql',
      'outputs/customer_segments.csv','outputs/lapse_model.joblib','outputs/retention_list.csv',
      'outputs/triage_results.csv','outputs/triage_budget_demo.csv','outputs/agent_runs.jsonl','outputs/refund_ledger.jsonl',
      'outputs/part_a_report.json','outputs/part_b_report.json','outputs/part_c_report.json','outputs/part_d_report.json',
      'src/validate_part_a.py'
    ]
    missing=[x for x in required if not (ROOT/x).exists()]
    if missing: raise FileNotFoundError(f'Missing required outputs: {missing}')
    status['overall_status']='passed'
    status['required_outputs_checked']=len(required)
    status['elapsed_seconds']=round(time.time()-started,3)
    (ROOT/'outputs'/'pipeline_status.json').write_text(json.dumps(status,indent=2),encoding='utf-8')
    print('INTEGRATED PIPELINE PASSED — Parts A, B, C and D completed.')
    return status

if __name__=='__main__': main()
