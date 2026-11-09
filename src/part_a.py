"""Part A: audited, cleaned, persisted and queried synthetic Instamart data."""
from __future__ import annotations
import json, sqlite3
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data' / 'raw'
CLEAN = ROOT / 'data' / 'clean'
OUT = ROOT / 'outputs'
DB = ROOT / 'data' / 'instamart.db'

SQL_TEXT = r'''-- Q1: WHERE then HAVING
SELECT customer_id, SUM(order_amount) AS qualifying_spend
FROM orders
WHERE status='completed' AND order_amount > 500
GROUP BY customer_id
HAVING SUM(order_amount) > 8000;

-- Q2: Revenue by city and product category
SELECT c.city, p.category, ROUND(SUM(o.order_amount),2) AS revenue_inr
FROM orders o JOIN customers c USING(customer_id)
JOIN products p USING(product_id)
WHERE o.status='completed'
GROUP BY c.city, p.category
ORDER BY c.city, p.category;

-- Q3: Products priced above average catalogue price
SELECT product_id, product_name, price_inr
FROM products
WHERE price_inr > (SELECT AVG(price_inr) FROM products)
ORDER BY price_inr DESC;

-- Q4: Customers with no completed order
SELECT c.customer_id, c.city
FROM customers c LEFT JOIN orders o
ON c.customer_id=o.customer_id AND o.status='completed'
WHERE o.order_id IS NULL;

-- Q5: Above-average completed spend
WITH customer_spend AS (
  SELECT customer_id, SUM(order_amount) AS total_spend
  FROM orders WHERE status='completed' GROUP BY customer_id
), average_spend AS (
  SELECT AVG(total_spend) AS avg_spend FROM customer_spend
)
SELECT cs.customer_id, cs.total_spend, av.avg_spend
FROM customer_spend cs CROSS JOIN average_spend av
WHERE cs.total_spend > av.avg_spend;

-- Q6: Ranking window functions within each city
WITH customer_spend AS (
  SELECT c.customer_id, c.city, SUM(o.order_amount) AS total_spend
  FROM customers c JOIN orders o USING(customer_id)
  WHERE o.status='completed'
  GROUP BY c.customer_id, c.city
)
SELECT customer_id, city, ROUND(total_spend,2) AS total_spend,
       RANK() OVER(PARTITION BY city ORDER BY total_spend DESC) AS spend_rank,
       DENSE_RANK() OVER(PARTITION BY city ORDER BY total_spend DESC) AS dense_rank,
       ROW_NUMBER() OVER(PARTITION BY city ORDER BY total_spend DESC) AS row_num
FROM customer_spend;

-- Q7: Daily revenue and running total
WITH daily AS (
  SELECT substr(order_ts,1,10) AS day, SUM(order_amount) AS revenue
  FROM orders WHERE status='completed' GROUP BY substr(order_ts,1,10)
)
SELECT day, ROUND(revenue,2) AS revenue,
       ROUND(SUM(revenue) OVER(ORDER BY day ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW),2) AS cumulative_revenue
FROM daily ORDER BY day;
'''


def audit_frame(df: pd.DataFrame) -> dict:
    return {
        'shape': list(df.shape),
        'dtypes': {c: str(t) for c, t in df.dtypes.items()},
        'missing': {c: {'count': int(df[c].isna().sum()), 'pct': round(float(df[c].isna().mean()*100), 3)} for c in df.columns},
    }


def run() -> dict:
    CLEAN.mkdir(parents=True, exist_ok=True); OUT.mkdir(parents=True, exist_ok=True); (ROOT/'sql').mkdir(exist_ok=True)
    customers_raw = pd.read_csv(RAW/'customers.csv', dtype={'age':'string'})
    products = pd.read_csv(RAW/'products.csv')
    orders_raw = pd.read_csv(RAW/'orders.csv')
    # Raw audit is retained for README/reporting.
    age_num = pd.to_numeric(customers_raw['age'].replace('', np.nan), errors='coerce')
    amount_num = pd.to_numeric(orders_raw['order_amount'], errors='coerce')
    delivery_num = pd.to_numeric(orders_raw['delivery_minutes'].replace('', np.nan), errors='coerce')
    audit = {
        'customers': audit_frame(customers_raw), 'products': audit_frame(products), 'orders': audit_frame(orders_raw),
        'raw_checks': {
            'orders_rows': int(len(orders_raw)),
            'exact_duplicate_rows': int(orders_raw.duplicated().sum()),
            'pending_rows': int((orders_raw.status == 'pending').sum()),
            'distinct_order_id': int(orders_raw.order_id.nunique()),
            'non_numeric_amounts': int(amount_num.isna().sum()),
            'negative_delivery_minutes': int((delivery_num < 0).sum()),
            'blank_delivery_minutes': int(orders_raw.delivery_minutes.fillna('').astype(str).str.strip().eq('').sum()),
            'blank_age': int(customers_raw.age.fillna('').astype(str).str.strip().eq('').sum()),
            'age_outside_10_100': int(((age_num < 10) | (age_num > 100)).sum()),
            'raw_city_spellings': int(customers_raw.city.nunique()),
            'raw_nonblank_gender_spellings': int(customers_raw.loc[customers_raw.gender.fillna('').astype(str).str.strip().ne(''), 'gender'].nunique()),
            'blank_gender': int(customers_raw.gender.fillna('').astype(str).str.strip().eq('').sum()),
        }
    }
    # Customer cleaning
    customers = customers_raw.copy()
    customers['city'] = customers.city.astype(str).str.strip().str.title()
    customers['gender'] = customers.gender.fillna('').astype(str).str.strip().str.lower().map(
        lambda x: 'male' if x in {'male','m'} else ('female' if x in {'female','f'} else 'unknown'))
    customers['age'] = pd.to_numeric(customers.age.replace('', np.nan), errors='coerce').astype(float)
    customers.loc[(customers.age < 10) | (customers.age > 100), 'age'] = np.nan
    city_medians = customers.groupby('city').age.transform('median')
    customers['age'] = customers.age.fillna(city_medians).round().astype(int)
    customers['signup_date'] = pd.to_datetime(customers.signup_date)

    # Order cleaning in the exact required order.
    orders = orders_raw.copy()
    orders['order_ts'] = pd.to_datetime(orders.order_ts)
    before_exact = len(orders)
    orders = orders.drop_duplicates().copy()
    removed_exact = before_exact - len(orders)
    before_order_dedupe = len(orders)
    orders = orders.sort_values(['order_id','order_ts']).drop_duplicates('order_id', keep='last').copy()
    removed_order_versions = before_order_dedupe - len(orders)
    orders['quantity'] = pd.to_numeric(orders.quantity, errors='coerce')
    orders['discount_pct'] = pd.to_numeric(orders.discount_pct, errors='coerce')
    orders['order_amount'] = pd.to_numeric(orders.order_amount, errors='coerce')
    orders['delivery_minutes'] = pd.to_numeric(orders.delivery_minutes.replace('', np.nan), errors='coerce')
    orders['delivery_minutes'] = orders.delivery_minutes.mask(orders.delivery_minutes < 0)
    completed_imputation_count = int(orders.loc[orders.status.eq('completed'),'delivery_minutes'].isna().sum())
    price = products[['product_id','price_inr','category']]
    orders = orders.merge(price, on='product_id', how='left', validate='many_to_one')
    amount_missing = int(orders.order_amount.isna().sum())
    calc_amount = (orders.price_inr * orders.quantity * (1 - orders.discount_pct/100)).round(2)
    orders['order_amount'] = orders.order_amount.fillna(calc_amount).round(2)
    # Only completed orders are imputed; cancelled orders remain missing.
    completed_median = orders.loc[orders.status.eq('completed')].groupby('category').delivery_minutes.transform('median')
    completed_mask = orders.status.eq('completed')
    orders.loc[completed_mask, 'delivery_minutes'] = orders.loc[completed_mask, 'delivery_minutes'].fillna(completed_median)
    orders['delivery_minutes'] = orders.delivery_minutes.round().astype('Int64')
    orders = orders.drop(columns=['price_inr','category'])
    orders['order_ts'] = orders.order_ts.dt.strftime('%Y-%m-%d %H:%M:%S')
    products['price_inr'] = pd.to_numeric(products.price_inr)
    # stable output ordering for reproducibility
    customers = customers.sort_values('customer_id').reset_index(drop=True)
    products = products.sort_values('product_id').reset_index(drop=True)
    orders = orders.sort_values('order_id').reset_index(drop=True)
    customers['signup_date'] = customers.signup_date.dt.strftime('%Y-%m-%d')
    for name, df in [('customers',customers),('products',products),('orders',orders)]:
        df.to_csv(CLEAN/f'{name}.csv', index=False)
    if DB.exists(): DB.unlink()
    with sqlite3.connect(DB) as conn:
        customers.to_sql('customers', conn, index=False, if_exists='replace')
        products.to_sql('products', conn, index=False, if_exists='replace')
        orders.to_sql('orders', conn, index=False, if_exists='replace')
    (ROOT/'sql'/'queries.sql').write_text(SQL_TEXT, encoding='utf-8')

    # SQL execution and result metrics
    queries = [q.strip() for q in SQL_TEXT.split(';') if q.strip()]
    sql_results = {}
    with sqlite3.connect(DB) as conn:
        for i, q in enumerate(queries, 1):
            q = '\n'.join(line for line in q.splitlines() if not line.lstrip().startswith('--'))
            if q.strip():
                sql_results[f'Q{i}'] = pd.read_sql_query(q, conn)
    completed = orders.loc[orders.status.eq('completed')].copy()
    completed['order_amount'] = completed.order_amount.astype(float)
    completed['discount_pct'] = completed.discount_pct.astype(float)
    completed['quantity'] = completed.quantity.astype(int)
    completed['delivery_minutes'] = completed.delivery_minutes.astype(float)
    pivot_orders = orders.merge(customers[['customer_id','city']], on='customer_id').merge(products[['product_id','category']], on='product_id')
    pivot_orders = pivot_orders[pivot_orders.status.eq('completed')]
    pivot = pd.pivot_table(pivot_orders, values='order_amount', index='city', columns='category', aggfunc='sum', fill_value=0, margins=True)
    city_stats = completed.merge(customers[['customer_id','city']], on='customer_id').groupby('city').order_amount.agg(
        sum='sum', mean='mean', count='count').reset_index()
    q1, q3 = completed.order_amount.quantile([.25,.75])
    iqr = q3-q1; lower = q1-1.5*iqr; upper = q3+1.5*iqr
    correlations = completed[['order_amount','discount_pct','quantity','delivery_minutes']].corr()
    corr_pairs = correlations.where(np.triu(np.ones(correlations.shape),1).astype(bool)).stack()
    largest_pair = corr_pairs.abs().idxmax()
    stats = {
        'completed_mean': float(completed.order_amount.mean()), 'completed_median': float(completed.order_amount.median()),
        'completed_skew': float(completed.order_amount.skew()), 'q1': float(q1), 'q3': float(q3),
        'iqr': float(iqr), 'lower_fence': float(lower), 'upper_fence': float(upper),
        'outliers_below': int((completed.order_amount < lower).sum()), 'outliers_above': int((completed.order_amount > upper).sum()),
        'correlation_matrix': correlations.round(6).to_dict(), 'largest_abs_correlation_pair': list(largest_pair),
        'largest_abs_correlation_value': float(corr_pairs.loc[largest_pair]),
        'pivot_grand_total': float(pivot.loc['All','All']), 'city_stats': city_stats.round(2).to_dict(orient='records'),
    }
    # Core exact checkpoints and validation result.
    check = {
        'raw_orders': len(orders_raw)==13084, 'exact_dupes': removed_exact==119,
        'pending_removed': not orders.status.eq('pending').any(), 'one_order_per_id': len(orders)==12309,
        'completed_cancelled': int((orders.status=='completed').sum())==11110 and int((orders.status=='cancelled').sum())==1199,
        'completed_amount_filled': int(orders.order_amount.isna().sum())==0,
        'completed_delivery_filled': int(orders.loc[orders.status.eq('completed'),'delivery_minutes'].isna().sum())==0,
        'cancelled_delivery_missing': int(orders.loc[orders.status.eq('cancelled'),'delivery_minutes'].isna().sum())==1199,
        'completed_revenue': round(float(orders.loc[orders.status.eq('completed'),'order_amount'].sum()),2)==2998668.80,
        'six_cities': customers.city.nunique()==6, 'valid_age': customers.age.between(18,60).all(),
    }
    assert all(check.values()), {k:v for k,v in check.items() if not v}
    # SQL reference counts and totals
    sql_checks = {
        'Q1_customers': len(sql_results['Q1'])==30,
        'Q2_rows': len(sql_results['Q2'])==30,
        'Q2_revenue': round(float(sql_results['Q2'].revenue_inr.sum()),2)==2998668.80,
        'Q2_largest_cell': round(float(sql_results['Q2'].revenue_inr.max()),2)==233909.45,
        'Q3_products': len(sql_results['Q3'])==11,
        'Q4_customers': len(sql_results['Q4'])==25,
        'Q5_customers': len(sql_results['Q5'])==550,
        'Q7_days': len(sql_results['Q7'])==183,
    }
    assert all(sql_checks.values()), {k:v for k,v in sql_checks.items() if not v}
    report = {
        'audit': audit, 'cleaning': {'exact_duplicates_removed':removed_exact,'older_order_versions_removed':removed_order_versions,
            'unparseable_or_missing_order_amounts_filled':amount_missing,
            'negative_delivery_times_set_missing':int((delivery_num<0).sum()),
            'completed_delivery_times_imputed':completed_imputation_count,
            'cities':customers.city.value_counts().to_dict(),'genders':customers.gender.value_counts().to_dict()},
        'validation':check, 'sql_validation':sql_checks,
        'sql_metrics': {k:{'rows':len(v), 'columns':list(v.columns)} for k,v in sql_results.items()},
        'q2_largest_cell': sql_results['Q2'].sort_values('revenue_inr',ascending=False).head(1).to_dict(orient='records')[0],
        'q5_average_spend': float(sql_results['Q5'].avg_spend.iloc[0]),
        'q6_top_per_city': sql_results['Q6'].sort_values(['city','spend_rank']).groupby('city').head(1)[['city','customer_id','total_spend']].to_dict(orient='records'),
        'q6_rank_vs_row_number_different': int((sql_results['Q6'].spend_rank != sql_results['Q6'].row_num).sum()),
        'q7_last_cumulative': float(sql_results['Q7'].cumulative_revenue.iloc[-1]),
        'eda':stats,
    }
    (OUT/'part_a_report.json').write_text(json.dumps(report, indent=2, default=str), encoding='utf-8')
    print('ALL CHECKPOINTS PASSED')
    return report

if __name__ == '__main__':
    run()
