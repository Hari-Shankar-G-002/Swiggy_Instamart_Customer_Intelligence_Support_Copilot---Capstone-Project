"""Standalone Part A checkpoint validator; prints exactly one success line."""
from pathlib import Path
import sqlite3
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]

def validate(quiet=False):
    customers=pd.read_csv(ROOT/'data'/'clean'/'customers.csv')
    orders=pd.read_csv(ROOT/'data'/'clean'/'orders.csv')
    with sqlite3.connect(ROOT/'data'/'instamart.db') as conn:
        names={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        completed=conn.execute("SELECT COUNT(*) FROM orders WHERE status='completed'").fetchone()[0]
        cancelled=conn.execute("SELECT COUNT(*) FROM orders WHERE status='cancelled'").fetchone()[0]
        revenue=conn.execute("SELECT ROUND(SUM(order_amount),2) FROM orders WHERE status='completed'").fetchone()[0]
    assert {'customers','products','orders'} <= names
    assert len(customers)==1200 and customers.city.nunique()==6
    assert customers.age.notna().all() and customers.age.between(18,60).all()
    assert len(orders)==12309 and orders.order_id.nunique()==12309
    assert 'pending' not in set(orders.status)
    assert completed==11110 and cancelled==1199
    assert orders.order_amount.notna().all()
    assert orders.loc[orders.status.eq('completed'),'delivery_minutes'].notna().all()
    assert orders.loc[orders.status.eq('cancelled'),'delivery_minutes'].isna().all()
    assert round(float(revenue),2)==2998668.80
    if not quiet:
        print('ALL CHECKPOINTS PASSED')

if __name__=='__main__': validate()
