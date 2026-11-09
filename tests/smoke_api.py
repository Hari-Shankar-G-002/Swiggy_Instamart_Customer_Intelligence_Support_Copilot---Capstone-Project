"""Run after starting `python src/api/server.py`; verifies live JSON endpoints."""
import json
from urllib.request import Request, urlopen
BASE='http://127.0.0.1:8000'

def get(path):
    with urlopen(BASE+path,timeout=20) as response:
        assert response.status==200
        return json.load(response)

health=get('/api/health')
assert health['status']=='ok'
overview=get('/api/overview')
assert overview['kpis']['total_orders']==12309
assert overview['kpis']['total_revenue_inr']==2998668.8
customers=get('/api/customers')
assert len(customers['customers'])==1175
monitoring=get('/api/monitoring')
assert monitoring['rag_agent']['correct_retrieval']==12
assert len(monitoring['execution_status'])==4
request=Request(BASE+'/api/policy/answer',data=json.dumps({'question':'Who approves refunds above INR 1000?'}).encode(),
                headers={'Content-Type':'application/json'},method='POST')
with urlopen(request,timeout=20) as response:
    answer=json.load(response)
assert 'human support lead' in answer['answer']
print('API SMOKE TESTS PASSED')
