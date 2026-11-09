"""Local dashboard server. Uses Python's built-in HTTP server only."""
from __future__ import annotations
import json, sqlite3, sys
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
FRONTEND=ROOT/'frontend'
sys.path.insert(0,str(ROOT))
from src.part_d import answer as policy_answer


def load_json(path,default=None):
    try: return json.loads(path.read_text(encoding='utf-8'))
    except (OSError,json.JSONDecodeError): return {} if default is None else default


def overview_payload():
    with sqlite3.connect(ROOT/'data'/'instamart.db') as conn:
        orders=pd.read_sql_query('SELECT * FROM orders',conn)
        customers=pd.read_sql_query('SELECT * FROM customers',conn)
        products=pd.read_sql_query('SELECT * FROM products',conn)
    orders['order_amount']=pd.to_numeric(orders.order_amount)
    done=orders[orders.status.eq('completed')].copy()
    revenue=float(done.order_amount.sum())
    city=done.merge(customers[['customer_id','city']],on='customer_id').groupby('city').order_amount.sum().sort_index()
    volume=orders.merge(customers[['customer_id','city']],on='customer_id').groupby('city').size().sort_index()
    category=done.merge(products[['product_id','category']],on='product_id').groupby('category').order_amount.sum().sort_index()
    daily=done.assign(day=done.order_ts.str[:10]).groupby('day').order_amount.sum().sort_index()
    tickets=pd.read_csv(ROOT/'data'/'raw'/'tickets.csv',keep_default_na=False)
    segments=pd.read_csv(ROOT/'outputs'/'customer_segments.csv')
    return {
      'kpis':{'total_customers':len(customers),'total_products':len(products),'total_orders':len(orders),
        'completed_orders':int((orders.status=='completed').sum()),'cancelled_orders':int((orders.status=='cancelled').sum()),
        'total_revenue_inr':round(revenue,2),'average_order_value_inr':round(revenue/len(done),2),'total_support_tickets':len(tickets)},
      'revenue_by_city':[{'label':str(k),'value':round(float(v),2)} for k,v in city.items()],
      'order_status':[{'label':str(k).title(),'value':int(v)} for k,v in orders.status.value_counts().items()],
      'revenue_by_category':[{'label':str(k),'value':round(float(v),2)} for k,v in category.items()],
      'daily_revenue':[{'label':str(k),'value':round(float(v),2)} for k,v in daily.items()],
      'segment_distribution':[{'label':str(k),'value':int(v)} for k,v in segments.segment_name.value_counts().items()],
      'order_volume_by_city':[{'label':str(k),'value':int(v)} for k,v in volume.items()],
    }


def customers_payload():
    customers=pd.read_csv(ROOT/'data'/'clean'/'customers.csv')
    seg=pd.read_csv(ROOT/'outputs'/'customer_segments.csv')
    scores=pd.read_csv(ROOT/'outputs'/'customer_lapse_scores.csv')
    table=seg.merge(customers[['customer_id','city']],on='customer_id',how='left').merge(
        scores[['customer_id','lapse_probability']],on='customer_id',how='left')
    table['is_premium']=table.is_premium.astype(bool)
    city_counts=table.groupby('city').size().sort_index()
    segment_counts=table.groupby('segment_name').size().sort_values(ascending=False)
    avg_money=table.groupby('segment_name').monetary.mean().sort_values(ascending=False)
    high=table.dropna(subset=['lapse_probability']).sort_values('lapse_probability',ascending=False).head(10)
    customer_view=table[['customer_id','city','segment_name','recency','frequency','monetary','is_premium','lapse_probability']].astype(object)
    customer_view=customer_view.where(pd.notna(customer_view),None)
    return {
      'kpis':{'customers_with_completed_orders':len(seg),'segment_count':int(seg.segment_name.nunique()),
       'premium_customers':int(seg.is_premium.sum()),'average_frequency':round(float(seg.frequency.mean()),2),
       'average_monetary_inr':round(float(seg.monetary.mean()),2),'average_recency_days':round(float(seg.recency.mean()),2)},
      'segment_distribution':[{'label':str(k),'value':int(v),'pct':round(float(v/len(table)*100),1)} for k,v in segment_counts.items()],
      'average_monetary_by_segment':[{'label':str(k),'value':round(float(v),2)} for k,v in avg_money.items()],
      'recency_monetary_scatter':[{'x':float(r.recency),'y':float(r.monetary),'group':r.segment_name} for r in table.itertuples()],
      'frequency_monetary_scatter':[{'x':float(r.frequency),'y':float(r.monetary),'group':r.segment_name} for r in table.itertuples()],
      'customer_count_by_city':[{'label':str(k),'value':int(v)} for k,v in city_counts.items()],
      'top_risk':[{'label':str(r.customer_id),'value':round(float(r.lapse_probability)*100,2)} for r in high.itertuples()],
      'customers':customer_view.to_dict(orient='records')
    }


def monitoring_payload():
    a=load_json(ROOT/'outputs'/'part_a_report.json')
    b=load_json(ROOT/'outputs'/'part_b_report.json')
    c=load_json(ROOT/'outputs'/'part_c_report.json')
    d=load_json(ROOT/'outputs'/'part_d_report.json')
    status=load_json(ROOT/'outputs'/'pipeline_status.json')
    triage=pd.read_csv(ROOT/'outputs'/'triage_results.csv')
    with sqlite3.connect(ROOT/'data'/'instamart.db') as conn:
        clean_orders = pd.read_sql_query('SELECT status FROM orders', conn)
    policy_eval = pd.read_csv(ROOT/'data'/'raw'/'policy_eval.csv')
    triage_status=triage.status.value_counts().to_dict()
    triage_categories=triage.category.fillna('').replace('', 'Human review').value_counts().to_dict()
    scenarios=d.get('scenarios',[])
    outcome_counts={}
    for s in scenarios: outcome_counts[s['status']]=outcome_counts.get(s['status'],0)+1
    rag=d.get('rag_evaluation',{}).get('overlap_10',{})
    lapse=b.get('lapse',{})
    raw=a.get('audit',{}).get('raw_checks',{})
    cleaned=a.get('cleaning',{})
    statuses=status.get('stages',{})
    return {
      'data':{'raw_customers':a.get('audit',{}).get('customers',{}).get('shape',[0])[0],
        'raw_orders':raw.get('orders_rows',0),'clean_orders':len(clean_orders),
        'duplicates_removed':cleaned.get('exact_duplicates_removed',0)+cleaned.get('older_order_versions_removed',0),
        'completed_orders':int((clean_orders.status=='completed').sum()),
        'cancelled_orders':int((clean_orders.status=='cancelled').sum()),
        'validation_status':'PASSED' if all(a.get('validation',{}).values()) else 'FAILED',
        'sql_status':'PASSED' if all(a.get('sql_validation',{}).values()) else 'FAILED'},
      'ml':{'segments':b.get('chosen_k',0),'pca_explained_variance':sum(b.get('pca_explained_variance_ratio',[])),
        'logistic_f1':lapse.get('logistic',{}).get('test',{}).get('f1',0),
        'random_forest_f1':lapse.get('random_forest',{}).get('test',{}).get('f1',0),
        'baseline_f1':lapse.get('baseline',{}).get('f1',0),'selected_model':lapse.get('selected_model',''),
        'high_risk_customers':len(pd.read_csv(ROOT/'outputs'/'retention_list.csv'))},
      'support':{'total_tickets':len(triage),'successfully_classified':int(triage.status.isin(['classified_json','classified_keyword']).sum()),
        'invalid_outputs':int((triage.status=='flagged_invalid_output').sum()),'empty_skipped':int((triage.status=='skipped_empty').sum()),
        'long_flagged':int((triage.status=='flagged_long').sum()),'human_review':int((triage.route=='human_review').sum()),
        'security_team':int((triage.route=='security_team').sum()),'premium_desk':int((triage.route=='premium_desk').sum()),
        'processing_status':[{'label':str(k),'value':int(v)} for k,v in triage_status.items()],
        'classification_status':[{'label':str(k),'value':int(v)} for k,v in triage_categories.items()]},
      'rag_agent':{'policy_questions':len(policy_eval),'correct_retrieval':rag.get('expected_doc_in_top3',0),
        'grounded_answers':rag.get('expected_fact_in_answer',0),'unanswerable_handled':rag.get('fallback_correct',0),
        'refund_scenarios':len(scenarios),'outcomes':outcome_counts,'refund_outcomes':[{'label':k,'value':v} for k,v in outcome_counts.items()],
        'escalations':outcome_counts.get('ESCALATE',0),'denied':outcome_counts.get('DENIED',0),
        'not_found':outcome_counts.get('NOT_FOUND',0),'fallbacks':sum(v for k,v in outcome_counts.items() if 'FALLBACK' in k)},
      'execution_status':[{'label':k,'status':v.get('status','not executed')} for k,v in statuses.items()],
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(FRONTEND),**kwargs)
    def log_message(self,fmt,*args): print('[http]',fmt%args)
    def send_json(self,payload,status=200):
        body=json.dumps(payload,allow_nan=False,default=str).encode('utf-8')
        self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(body))); self.send_header('Cache-Control','no-store')
        self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        path=urlparse(self.path).path
        try:
            if path=='/api/health': self.send_json({'status':'ok','project':'Instamart Customer Intelligence & Support Copilot'}); return
            if path=='/api/overview': self.send_json(overview_payload()); return
            if path=='/api/customers': self.send_json(customers_payload()); return
            if path=='/api/monitoring': self.send_json(monitoring_payload()); return
        except Exception as exc:
            self.send_json({'error':str(exc)},500); return
        if path=='/': self.path='/index.html'
        return super().do_GET()
    def do_POST(self):
        if urlparse(self.path).path!='/api/policy/answer':
            self.send_json({'error':'not found'},404); return
        try:
            length=int(self.headers.get('Content-Length','0'))
            payload=json.loads(self.rfile.read(length) or b'{}')
            question=str(payload.get('question','')).strip()
            if not question: self.send_json({'error':'Please enter a policy question.'},400); return
            self.send_json(policy_answer(question))
        except Exception as exc:
            self.send_json({'error':str(exc)},500)


def main():
    host='127.0.0.1'; port=8000
    print(f'Instamart Copilot dashboard: http://{host}:{port}')
    ThreadingHTTPServer((host,port),Handler).serve_forever()

if __name__=='__main__': main()
