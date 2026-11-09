"""Part D: retrieval-grounded policy assistant and checkpointed ReAct refund agent."""
from __future__ import annotations
import json, re, sqlite3, time, uuid
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import mock_llm

ROOT=Path(__file__).resolve().parents[1]
POL=ROOT/'data'/'policies'; RAW=ROOT/'data'/'raw'; OUT=ROOT/'outputs'; STATE=ROOT/'state'; DB=ROOT/'data'/'instamart.db'


def load_chunks(overlap:int=10):
    chunks=[]
    for path in sorted(POL.glob('*.txt')):
        words=path.read_text(encoding='utf-8').split()
        start=0
        while start<len(words):
            block=words[start:start+40]
            chunks.append({'source':path.name,'text':' '.join(block)})
            if start+40>=len(words): break
            start+=40-overlap
    return chunks


def build_retriever(overlap:int=10):
    chunks=load_chunks(overlap)
    vectorizer=TfidfVectorizer()
    matrix=vectorizer.fit_transform([c['text'] for c in chunks])
    return chunks,vectorizer,matrix


CHUNKS,VECTORIZER,TFIDF_MATRIX=build_retriever(10)


def retrieve(query:str,k:int=3,chunks=None,vectorizer=None,matrix=None):
    chunks=CHUNKS if chunks is None else chunks
    vectorizer=VECTORIZER if vectorizer is None else vectorizer
    matrix=TFIDF_MATRIX if matrix is None else matrix
    q=vectorizer.transform([query])
    scores=cosine_similarity(q,matrix).ravel()
    idx=np.argsort(-scores,kind='stable')[:k]
    return [{'source':chunks[int(i)]['source'],'score':float(scores[int(i)]),'text':chunks[int(i)]['text']} for i in idx]


def answer(question:str):
    hits=retrieve(question,k=3)
    context='\n'.join(f"[{h['source']}] {h['text']}" for h in hits)
    messages=[
      {'role':'system','content':'POLICY ASSISTANT. Answer only from the supplied policy context. If the context does not contain the answer, say exactly that you could not find the information in the policy documents.'},
      {'role':'user','content':f'CONTEXT:\n{context}\nQUESTION:\n{question}'}
    ]
    response=mock_llm.chat(messages)
    return {'answer':response.choices[0].message.content,'sources':list(dict.fromkeys(h['source'] for h in hits)),
            'retrieved':hits,'tokens_used':int(response.usage.total_tokens)}


def evaluate_rag(overlap:int):
    chunks,vec,mat=build_retriever(overlap)
    ev=pd.read_csv(RAW/'policy_eval.csv',keep_default_na=False)
    answerable=ev[ev.expected_doc.ne('NONE')]
    unanswerable=ev[ev.expected_doc.eq('NONE')]
    retrieval_ok=0; grounding_ok=0; fallback_ok=0; failures=[]
    for r in ev.to_dict(orient='records'):
        hits=retrieve(r['question'],3,chunks,vec,mat)
        # Exact answer call, but pass in the selected vector space for overlap experiment.
        context='\n'.join(f"[{h['source']}] {h['text']}" for h in hits)
        response=mock_llm.chat([
            {'role':'system','content':'POLICY ASSISTANT. Answer only from the supplied context, otherwise say you could not find the information in the policy documents.'},
            {'role':'user','content':f"CONTEXT:\n{context}\nQUESTION:\n{r['question']}"}
        ])
        text=response.choices[0].message.content or ''
        if r['expected_doc']!='NONE':
            found=any(h['source']==r['expected_doc'] for h in hits)
            fact=r['expected_fact'] in text
            retrieval_ok+=int(found); grounding_ok+=int(fact)
            if not (found and fact): failures.append({'question':r['question'],'retrieved':[h['source'] for h in hits],'answer':text,'expected_fact':r['expected_fact']})
        else:
            fallback_ok+=int(text.startswith('I could not find'))
    return {'overlap':overlap,'chunks':len(chunks),'answerable':len(answerable),
            'expected_doc_in_top3':retrieval_ok,'expected_fact_in_answer':grounding_ok,
            'unanswerable':len(unanswerable),'fallback_correct':fallback_ok,'failures':failures}


# Tool definitions are intentionally explicit for traceability.
TOOLS_SPEC=[
 {'name':'get_order','description':'Look up the final cleaned order record by order identifier.','parameters':{'type':'object','properties':{'order_id':{'type':'string'}},'required':['order_id']}},
 {'name':'search_policy','description':'Retrieve the three most relevant policy chunks for a question.','parameters':{'type':'object','properties':{'query':{'type':'string'}},'required':['query']}},
 {'name':'calculate_refund','description':'Calculate refund value using completed-order delivery rules.','parameters':{'type':'object','properties':{'order_amount':{'type':'number'},'delivery_minutes':{'type':'integer'}},'required':['order_amount','delivery_minutes']}},
 {'name':'issue_refund','description':'Record an automatically approved refund of INR 1000 or less.','parameters':{'type':'object','properties':{'order_id':{'type':'string'},'refund_inr':{'type':'number'}},'required':['order_id','refund_inr']}},
 {'name':'escalate_to_human','description':'Send a refund above INR 1000 to a human support lead.','parameters':{'type':'object','properties':{'order_id':{'type':'string'},'refund_inr':{'type':'number'}},'required':['order_id','refund_inr']}},
]


def get_order(order_id:str):
    with sqlite3.connect(DB) as conn:
        row=conn.execute('SELECT order_id,status,order_amount,delivery_minutes FROM orders WHERE order_id=?',(order_id,)).fetchone()
    if row is None: return {'error':'order not found'}
    return {'order_id':row[0],'status':row[1],'order_amount':float(row[2]),
            'delivery_minutes':None if row[3] is None else int(row[3])}


def search_policy(query:str): return {'results':retrieve(query,k=3)}


def calculate_refund(order_amount:float,delivery_minutes:int|None):
    amount=float(order_amount) if delivery_minutes is not None and int(delivery_minutes)>45 else 0.0
    return {'refund_inr':round(amount,2)}


def _ledger(tool_name:str,order_id:str,refund_inr:float):
    OUT.mkdir(exist_ok=True)
    record={'timestamp':datetime.now(timezone.utc).isoformat(),'tool_name':tool_name,
            'order_id':order_id,'refund_inr':round(float(refund_inr),2)}
    with (OUT/'refund_ledger.jsonl').open('a',encoding='utf-8') as f: f.write(json.dumps(record)+'\n')
    return {'refund_inr':round(float(refund_inr),2)}


def issue_refund(order_id:str,refund_inr:float): return _ledger('issue_refund',order_id,refund_inr)
def escalate_to_human(order_id:str,refund_inr:float): return _ledger('escalate_to_human',order_id,refund_inr)

TOOL_MAP={'get_order':get_order,'search_policy':search_policy,'calculate_refund':calculate_refund,
          'issue_refund':issue_refund,'escalate_to_human':escalate_to_human}

class SimulatedCrash(RuntimeError): pass


def _save_checkpoint(run_id,scenario_id,messages,tokens_used,steps,llm_calls,tools_executed):
    STATE.mkdir(exist_ok=True)
    payload={'run_id':run_id,'scenario_id':scenario_id,'messages':messages,'tokens_used':tokens_used,
             'step_number':len(steps),'llm_calls':llm_calls,'steps':steps,'tools_executed':tools_executed}
    (STATE/f'{run_id}.json').write_text(json.dumps(payload,indent=2,default=str),encoding='utf-8')


def _status_from_answer(text:str):
    return text.split(':',1)[0].strip() if ':' in (text or '') else 'COMPLETED'


def _continue_agent(run_id,scenario_id,user_message,messages,tokens_used,steps,llm_calls,tools_executed,
                    max_iterations=6,token_limit=6000,time_limit_seconds=10,crash_after_tools=None):
    started=time.monotonic()
    def fallback(code,detail):
        return {'status':code,'final_answer':f'{code}: {detail}. Hand off the case to a human support agent.',
                'steps':steps,'llm_calls':llm_calls,'tokens_used':tokens_used,
                'tools_executed':tools_executed,'run_id':run_id}
    while llm_calls<max_iterations:
        if time.monotonic()-started>=time_limit_seconds:
            return fallback('FALLBACK_TIMEOUT','time limit reached before the next model call')
        response=mock_llm.chat(messages,tools=TOOLS_SPEC)
        llm_calls+=1
        tokens_used+=int(response.usage.total_tokens)
        if tokens_used>token_limit:
            return fallback('FALLBACK_TOKEN_LIMIT','token budget exceeded before executing the requested tool')
        msg=response.choices[0].message
        tool_calls=msg.tool_calls or []
        if not tool_calls:
            final=msg.content or ''
            return {'status':_status_from_answer(final),'final_answer':final,'steps':steps,
                    'llm_calls':llm_calls,'tokens_used':tokens_used,'tools_executed':tools_executed,'run_id':run_id}
        serial_calls=[]
        for call in tool_calls:
            name=call.name; args=call.arguments
            serial_calls.append({'id':call.id,'name':name,'arguments':args})
        messages.append({'role':'assistant','content':None,'tool_calls':serial_calls})
        for call in serial_calls:
            name=call['name']; args=call['arguments']
            if name not in TOOL_MAP:
                observation={'error':f'unknown tool: {name}'}
            else:
                observation=TOOL_MAP[name](**args)
            tools_executed.append(name)
            steps.append({'tool':name,'arguments':args,'observation':observation})
            messages.append({'role':'tool','tool_call_id':call['id'],'name':name,'content':json.dumps(observation,default=str)})
            # Save only after the tool observation is durably appended, so resume never repeats it.
            _save_checkpoint(run_id,scenario_id,messages,tokens_used,steps,llm_calls,tools_executed)
            if crash_after_tools is not None and len(tools_executed)>=crash_after_tools:
                raise SimulatedCrash(f'Simulated crash after {len(tools_executed)} tool executions')
    return fallback('FALLBACK_MAX_ITERATIONS','maximum model-call iterations reached without a final answer')


def run_agent(user_message:str,scenario_id:str, max_iterations:int=6,token_limit:int=6000,
              time_limit_seconds:float=10,run_id:str|None=None,crash_after_tools:int|None=None):
    run_id=run_id or f'{scenario_id.lower()}_{uuid.uuid4().hex[:8]}'
    messages=[{'role':'system','content':'AGENT. Handle refund requests by looking up the order, checking refund policy, calculating the refund, then issuing or escalating when eligible.'},
              {'role':'user','content':user_message}]
    return _continue_agent(run_id,scenario_id,user_message,messages,0,[],0,[],max_iterations,token_limit,time_limit_seconds,crash_after_tools)


def resume_agent(run_id:str,max_iterations:int=6,token_limit:int=6000,time_limit_seconds:float=10):
    checkpoint_path=STATE/f'{run_id}.json'
    payload=json.loads(checkpoint_path.read_text(encoding='utf-8'))
    messages=payload['messages']; scenario_id=payload['scenario_id']
    user_message=next(m['content'] for m in messages if m['role']=='user')
    return _continue_agent(run_id,scenario_id,user_message,messages,payload['tokens_used'],payload['steps'],
                           payload['llm_calls'],payload['tools_executed'],max_iterations,token_limit,time_limit_seconds)


def run() -> dict:
    OUT.mkdir(exist_ok=True); STATE.mkdir(exist_ok=True)
    (OUT/'refund_ledger.jsonl').write_text('',encoding='utf-8')
    (OUT/'agent_runs.jsonl').write_text('',encoding='utf-8')
    eval_overlap=evaluate_rag(10); eval_zero=evaluate_rag(0)
    policy_eval={'overlap_10':eval_overlap,'overlap_0':eval_zero}
    policy_eval_path=OUT/'policy_eval_results.json'; policy_eval_path.write_text(json.dumps(policy_eval,indent=2),encoding='utf-8')
    scenarios=pd.read_csv(RAW/'agent_scenarios.csv',keep_default_na=False)
    run_results=[]
    for row in scenarios.to_dict(orient='records'):
        result=run_agent(row['message'],row['scenario_id'],run_id=f"{row['scenario_id'].lower()}_standard")
        result['scenario_id']=row['scenario_id']
        result['expected_outcome']=row['expected_outcome']
        result['expected_refund_inr']=float(row['expected_refund_inr'])
        refund=0.0
        m=re.search(r'INR\s+([0-9]+(?:\.[0-9]+)?)',result['final_answer'])
        if result['status']=='ESCALATE':
            hit=next((s for s in result['steps'] if s['tool']=='escalate_to_human'),None)
            refund=float(hit['arguments']['refund_inr']) if hit else 0.0
        elif m: refund=float(m.group(1))
        result['refund_inr']=round(refund,2)
        if row['scenario_id']!='S7':
            assert result['status']==row['expected_outcome'], (row['scenario_id'],result['status'],row['expected_outcome'])
            assert abs(result['refund_inr']-float(row['expected_refund_inr']))<.01
        else:
            assert result['status']=='FALLBACK_MAX_ITERATIONS'
        run_results.append(result)
        record={k:result[k] for k in ['scenario_id','status','final_answer','llm_calls','tokens_used'] if k in result}
        record['scenario_id']=row['scenario_id']; record['steps']=result['steps']
        with (OUT/'agent_runs.jsonl').open('a',encoding='utf-8') as f: f.write(json.dumps(record,default=str)+'\n')
    # Safe-stop demonstrations.
    s1=scenarios[scenarios.scenario_id.eq('S1')].iloc[0]
    token_demo=run_agent(s1.message,'S1_TOKEN_LIMIT',token_limit=200,run_id='s1_token_demo')
    timeout_demo=run_agent(s1.message,'S1_TIMEOUT',time_limit_seconds=0,run_id='s1_timeout_demo')
    assert token_demo['status']=='FALLBACK_TOKEN_LIMIT'
    assert timeout_demo['status']=='FALLBACK_TIMEOUT'
    # Crash after the second executed tool, then continue from the saved observation checkpoint.
    crashed=False
    try:
        run_agent(s1.message,'S1_CRASH_RESUME',run_id='crash_resume_s1',crash_after_tools=2)
    except SimulatedCrash:
        crashed=True
    assert crashed
    resumed=resume_agent('crash_resume_s1')
    expected_tools=['get_order','search_policy','calculate_refund','issue_refund']
    assert resumed['tools_executed']==expected_tools,(resumed['tools_executed'])
    assert resumed['status']=='REFUND' and abs(float(re.search(r'INR\s+([0-9.]+)',resumed['final_answer']).group(1))-128.25)<.01
    demo={'token_limit_demo':{'status':token_demo['status'],'llm_calls':token_demo['llm_calls'],'tokens_used':token_demo['tokens_used']},
          'timeout_demo':{'status':timeout_demo['status'],'llm_calls':timeout_demo['llm_calls'],'tokens_used':timeout_demo['tokens_used']},
          'crash_resume':{'crashed_after_tools':2,'resumed_status':resumed['status'],'final_answer':resumed['final_answer'],
                          'tools_executed':resumed['tools_executed'],'llm_calls':resumed['llm_calls'],'tokens_used':resumed['tokens_used']}}
    (OUT/'part_d_demos.json').write_text(json.dumps(demo,indent=2),encoding='utf-8')
    report={'chunks':len(CHUNKS),'chunk_counts_by_source':pd.Series([c['source'] for c in CHUNKS]).value_counts().to_dict(),
            'top3_refund_policy':[x['source'] for x in retrieve('refund policy late delivery',3)],
            'rag_evaluation':policy_eval,'scenarios':[
              {'scenario_id':x['scenario_id'],'status':x['status'],'refund_inr':x['refund_inr'],
               'llm_calls':x['llm_calls'],'tokens_used':x['tokens_used']} for x in run_results],
            'demos':demo,'refund_ledger_lines':len((OUT/'refund_ledger.jsonl').read_text(encoding='utf-8').splitlines())}
    (OUT/'part_d_report.json').write_text(json.dumps(report,indent=2,default=str),encoding='utf-8')
    return report

if __name__=='__main__':
    r=run(); print('Part D complete:',r['chunks'],'policy chunks; scenarios=',[(x['scenario_id'],x['status']) for x in r['scenarios']])
