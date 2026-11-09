"""Part C: privacy-safe support ticket classification, validation and routing."""
from __future__ import annotations
import json, random, re, time
from pathlib import Path
import pandas as pd
import mock_llm

ROOT=Path(__file__).resolve().parents[1]
RAW=ROOT/'data'/'raw'; OUT=ROOT/'outputs'; LOG=ROOT/'logs'
MAX_INPUT_TOKENS=400
TOKEN_BUDGET=100000
CATEGORIES={'billing','delivery','technical','fraud'}
PATTERNS=[('email',re.compile(r'[\w.+-]+@[\w-]+\.[\w.]+'), '[EMAIL]'),
          ('phone',re.compile(r'\b[6-9]\d{9}\b'), '[PHONE]'),
          ('order_id',re.compile(r'ORD-\d{6}'), '[ORDER_ID]')]
ZERO_PROMPT=("You are a support ticket classifier. CLASSIFY each ticket into exactly one allowed category: billing, delivery, technical, fraud. "
             'Return JSON only in the form {"category": "...", "reason": "..."}. Do not add markdown or prose.')
FEW_PROMPT=("You are a support ticket classifier. CLASSIFY each ticket into exactly one allowed category: billing, delivery, technical, fraud. "
            'Return JSON only in the form {"category": "...", "reason": "..."}. Do not add markdown or prose.\n'
            'EXAMPLES:\nTicket: My card shows an unauthorized transaction. -> {"category":"fraud","reason":"unauthorized transaction"}\n'
            'Ticket: The app crashes when I open the cart. -> {"category":"technical","reason":"app crash"}\n'
            'Ticket: My delivery is late and the rider is not answering. -> {"category":"delivery","reason":"late delivery"}')


def redact(text: str):
    counts={}
    value=text or ''
    for name,pattern,replacement in PATTERNS:
        value,n=pattern.subn(replacement,value)
        counts[name]=n
    return value,counts


def has_pii(text: str) -> bool:
    return any(p.search(text or '') for _,p,_ in PATTERNS)


def classify_batch(mode: str, token_budget: int|None=None) -> tuple[pd.DataFrame,dict]:
    tickets=pd.read_csv(RAW/'tickets.csv',keep_default_na=False)
    segments=pd.read_csv(OUT/'customer_segments.csv')
    segment_lookup=segments.set_index('customer_id')[['segment_name','is_premium']].to_dict('index')
    system=ZERO_PROMPT if mode=='zero' else FEW_PROMPT
    mock_llm.reset()  # required immediately before each independent full batch
    rng=random.Random(42)
    running_tokens=0; rows=[]; retry_lines=[]; total_calls=0; total_errors=0
    redaction_totals={'email':0,'phone':0,'order_id':0}
    redacted_records=[]
    for ticket in tickets.to_dict(orient='records'):
        text=ticket['text']
        safe,counts=redact(text)
        for k,v in counts.items(): redaction_totals[k]+=v
        redacted_records.append(safe)
        status=''; category=''; reason=''; tokens_used=0; attempts=0
        # Guardrails are evaluated before any model call.
        if not text.strip():
            status='skipped_empty'
        elif mock_llm.est_tokens(text)>MAX_INPUT_TOKENS:
            status='flagged_long'
        else:
            if has_pii(safe):
                raise AssertionError(f"PII remains after redaction for {ticket['ticket_id']}")
            while True:
                if token_budget is not None and running_tokens>=token_budget:
                    status='budget_exhausted'; break
                try:
                    response=mock_llm.chat([{'role':'system','content':system},{'role':'user','content':safe}])
                    total_calls+=1; tokens_used=int(response.usage.total_tokens); running_tokens+=tokens_used
                    content=response.choices[0].message.content or ''
                    try:
                        obj=json.loads(content)
                        if isinstance(obj,dict) and obj.get('category') in CATEGORIES:
                            category=obj['category']; reason=str(obj.get('reason','')); status='classified_json'
                        else:
                            status='flagged_invalid_output'
                    except (json.JSONDecodeError,TypeError):
                        words=set(re.findall(r'[a-z]+',content.lower()))
                        found=words & CATEGORIES
                        if len(found)==1:
                            category=next(iter(found)); reason='category recovered from validated keyword'; status='classified_keyword'
                        else:
                            status='flagged_invalid_output'
                    break
                except mock_llm.TransientLLMError:
                    total_errors+=1
                    if attempts>=3:
                        status='flagged_invalid_output'; break
                    wait=0.05*(2**attempts)*rng.uniform(.9,1.15)
                    retry_lines.append({'ticket_id':ticket['ticket_id'],'retry_number':attempts,'wait_seconds':wait})
                    LOG.mkdir(exist_ok=True)
                    with (LOG/'triage_retries.jsonl').open('a',encoding='utf-8') as f:
                        f.write(json.dumps(retry_lines[-1])+'\n')
                    time.sleep(wait)
                    attempts+=1
        seg=segment_lookup.get(ticket['customer_id'],{})
        segment_name=seg.get('segment_name','')
        is_premium=bool(seg.get('is_premium',False))
        if status in {'skipped_empty','flagged_long','flagged_invalid_output','budget_exhausted'}:
            route='human_review'; priority='NORMAL'
        elif category=='fraud':
            route='security_team'; priority='HIGH'
        elif is_premium:
            route='premium_desk'; priority='HIGH'
        else:
            route='support_queue'; priority='NORMAL'
        rows.append({'ticket_id':ticket['ticket_id'],'customer_id':ticket['customer_id'],
                     'status':status,'category':category,'segment_name':segment_name,
                     'priority':priority,'route':route,'tokens_used':tokens_used,
                     'true_category':ticket['true_category']})
    assert all(not has_pii(x) for x in redacted_records), 'PII pattern found in redacted corpus'
    df=pd.DataFrame(rows)
    classified=df[df.status.isin(['classified_json','classified_keyword'])]
    accuracy=float((classified.category==classified.true_category).mean()) if len(classified) else 0.0
    confusion=pd.crosstab(classified.true_category,classified.category,dropna=False).reindex(
        index=['billing','delivery','technical','fraud'],columns=['billing','delivery','technical','fraud'],fill_value=0)
    summary={'mode':mode,'total_tickets':len(df),'classified':len(classified),
             'status_counts':df.status.value_counts().to_dict(),'accuracy':accuracy,
             'total_tokens':running_tokens,'tokens_per_classified_ticket':running_tokens/len(classified) if len(classified) else 0,
             'model_successful_calls':total_calls,'transient_errors':total_errors,
             'retry_count':len(retry_lines),'redactions':redaction_totals,
             'redactions_total':sum(redaction_totals.values()),'pii_left_after_redaction':0,
             'confusion_matrix':confusion.to_dict(), 'retry_log':retry_lines}
    return df,summary


def run() -> dict:
    OUT.mkdir(exist_ok=True); LOG.mkdir(exist_ok=True)
    retry_path=LOG/'triage_retries.jsonl'
    retry_path.write_text('',encoding='utf-8')
    zero_df,zero=classify_batch('zero',None)
    few_df,few=classify_batch('few',None)
    budget_df,budget=classify_batch('zero',6000)
    final_df,final=classify_batch('few',TOKEN_BUDGET)
    # Persist only the assignment-required columns in the final triage output.
    final_df[['ticket_id','customer_id','status','category','segment_name','priority','route','tokens_used']].to_csv(OUT/'triage_results.csv',index=False)
    budget_df[['ticket_id','customer_id','status','category','segment_name','priority','route','tokens_used']].to_csv(OUT/'triage_budget_demo.csv',index=False)
    report={'redaction_totals':few['redactions'],'redactions_total':few['redactions_total'],
            'zero_shot':zero,'few_shot':few,'budget_demo':{k:v for k,v in budget.items() if k!='retry_log'},
            'final_triage':{'status_counts':final['status_counts'],'tokens':final['total_tokens'],
                'route_counts':final_df.route.value_counts().to_dict(),
                'priority_counts':final_df.priority.value_counts().to_dict()},
            'retry_log_lines':len(retry_path.read_text(encoding='utf-8').splitlines())}
    (OUT/'part_c_report.json').write_text(json.dumps(report,indent=2,default=str),encoding='utf-8')
    return report

if __name__=='__main__':
    r=run(); print('Part C complete:',r['final_triage']['status_counts'],'zero-shot accuracy',round(r['zero_shot']['accuracy']*100,1),'few-shot accuracy',round(r['few_shot']['accuracy']*100,1))
