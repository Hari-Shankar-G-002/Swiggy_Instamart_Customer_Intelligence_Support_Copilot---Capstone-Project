"""Part B: RFM segmentation and leakage-aware customer lapse modelling."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.compose import ColumnTransformer
from sklearn.decomposition import PCA
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score,
                             precision_score, recall_score, silhouette_score)
from sklearn.model_selection import GridSearchCV, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.base import clone
from sklearn.utils import resample
import joblib

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data'/'clean'; OUT=ROOT/'outputs'
SNAPSHOT=pd.Timestamp('2025-10-01 00:00:00')
CUTOFF=pd.Timestamp('2025-09-01 00:00:00')


def _metrics(y_true, y_pred):
    return {'confusion_matrix': confusion_matrix(y_true,y_pred).tolist(),
            'precision':float(precision_score(y_true,y_pred,zero_division=0)),
            'recall':float(recall_score(y_true,y_pred,zero_division=0)),
            'f1':float(f1_score(y_true,y_pred,zero_division=0)),
            'accuracy':float(accuracy_score(y_true,y_pred))}


def run() -> dict:
    OUT.mkdir(parents=True,exist_ok=True)
    customers=pd.read_csv(DATA/'customers.csv',parse_dates=['signup_date'])
    orders=pd.read_csv(DATA/'orders.csv',parse_dates=['order_ts'])
    seg_orders=orders[orders.status.eq('completed')].copy()
    # RFM as-of 2025-10-01 for all customers with at least one completed order.
    rfm=(seg_orders.groupby('customer_id').agg(last_order_ts=('order_ts','max'),
          frequency=('order_id','nunique'), monetary=('order_amount','sum')).reset_index())
    rfm['recency']=(SNAPSHOT-rfm.last_order_ts).dt.days
    rfm=rfm[['customer_id','recency','frequency','monetary']]
    rfm_features=rfm[['recency','frequency','monetary']]
    rfm_scaler=StandardScaler()
    rfm_scaled=rfm_scaler.fit_transform(rfm_features)
    cluster_scores=[]
    for k in range(2,9):
        km=KMeans(n_clusters=k,n_init=10,random_state=42)
        labels=km.fit_predict(rfm_scaled)
        cluster_scores.append({'k':k,'inertia':float(km.inertia_),
                               'silhouette':float(silhouette_score(rfm_scaled,labels))})
    final_k=4
    kmeans=KMeans(n_clusters=final_k,n_init=10,random_state=42)
    segment_ids=kmeans.fit_predict(rfm_scaled)
    rfm['segment_id']=segment_ids
    profile=(rfm.groupby('segment_id').agg(size=('customer_id','count'),
        mean_recency=('recency','mean'),mean_frequency=('frequency','mean'),
        mean_monetary=('monetary','mean')).reset_index())
    premium_id=int(profile.sort_values('mean_monetary',ascending=False).iloc[0].segment_id)
    # Business labels reflect observed centroids; IDs remain arbitrary K-means labels.
    freq_id=int(profile.loc[profile.segment_id.ne(premium_id)].sort_values('mean_frequency',ascending=False).iloc[0].segment_id)
    stale_id=int(profile.loc[~profile.segment_id.isin([premium_id,freq_id])].sort_values('mean_recency',ascending=False).iloc[0].segment_id)
    labels={premium_id:('Premium Power Shoppers','Protect with early access and personalised high-value bundles'),
            freq_id:('Frequent Essentials','Use replenishment reminders and value packs')}
    remaining=[int(x) for x in profile.segment_id if int(x) not in labels]
    if remaining:
        labels[stale_id]=('At-Risk Occasionals','Trigger a reactivation offer and service check-in')
        for sid in remaining:
            if sid not in labels:
                labels[sid]=('Steady Value Shoppers','Encourage a second category with relevant cross-sell offers')
    rfm['segment_name']=rfm.segment_id.map({k:v[0] for k,v in labels.items()})
    rfm['is_premium']=rfm.segment_id.eq(premium_id)
    segment_profile=profile.copy()
    segment_profile['segment_name']=segment_profile.segment_id.map({k:v[0] for k,v in labels.items()})
    segment_profile['recommended_action']=segment_profile.segment_id.map({k:v[1] for k,v in labels.items()})
    pca=PCA(n_components=2,random_state=42).fit(rfm_scaled)
    rfm.to_csv(OUT/'customer_segments.csv',index=False)
    # Build a pre-cutoff feature table and September outcome label. Segment labels are not features.
    prior=orders[orders.order_ts<CUTOFF].copy()
    prior_completed=prior[prior.status.eq('completed')].copy()
    cohort_ids=prior_completed.customer_id.unique()
    cohort=customers[customers.customer_id.isin(cohort_ids)].copy()
    september=orders[(orders.order_ts>=CUTOFF)&(orders.order_ts<pd.Timestamp('2025-10-01'))&orders.status.eq('completed')]
    active_sept=set(september.customer_id.unique())
    cohort['lapsed']=(~cohort.customer_id.isin(active_sept)).astype(int)
    comp_agg=prior_completed.groupby('customer_id').agg(
        last_order=('order_ts','max'),frequency=('order_id','nunique'),monetary=('order_amount','sum'),
        avg_discount=('discount_pct','mean'),avg_delivery=('delivery_minutes','mean'))
    final_agg=prior.groupby('customer_id').agg(final_orders=('order_id','nunique'),cancelled_orders=('status',lambda x:int((x=='cancelled').sum())))
    fav=(prior_completed.merge(pd.read_csv(DATA/'products.csv')[['product_id','category']],on='product_id')
         .groupby('customer_id').category.agg(lambda x:x.mode().iloc[0]))
    features=cohort.set_index('customer_id').join(comp_agg).join(final_agg).join(fav.rename('favourite_category'))
    features['recency']=(CUTOFF-features.last_order).dt.days
    features['cancellation_rate']=features.cancelled_orders/features.final_orders
    features['tenure_days']=(CUTOFF-features.signup_date).dt.days
    features=features.reset_index()
    feature_cols=['recency','frequency','monetary','avg_discount','cancellation_rate','avg_delivery',
                  'favourite_category','city','age','gender','tenure_days']
    numeric_cols=['recency','frequency','monetary','avg_discount','cancellation_rate','avg_delivery','age','tenure_days']
    categorical_cols=['favourite_category','city','gender']
    X=features[feature_cols].copy(); y=features.lapsed.astype(int)
    # Features should be complete before any split/fit. These values are all derived only from pre-cutoff data.
    assert not X.isna().any().any(), X.isna().sum().to_dict()
    X_train,X_test,y_train,y_test,idx_train,idx_test=train_test_split(
        X,y,features.customer_id,test_size=.2,stratify=y,random_state=42)
    preprocessor=ColumnTransformer([
        ('numeric',StandardScaler(),numeric_cols),
        ('categorical',OneHotEncoder(drop='first',handle_unknown='ignore'),categorical_cols)
    ])
    log_pipe=Pipeline([('preprocess',preprocessor),('model',LogisticRegression(max_iter=1000))])
    log_grid=GridSearchCV(log_pipe,{'model__C':[.01,.1,1,10,100]},cv=5,scoring='f1',n_jobs=-1)
    log_grid.fit(X_train,y_train)
    rf_pipe=Pipeline([('preprocess',preprocessor),('model',RandomForestClassifier(n_estimators=100,random_state=42))])
    rf_grid=GridSearchCV(rf_pipe,{'model__max_depth':[3,5,8],'model__min_samples_leaf':[5,10,20]},cv=5,scoring='f1',n_jobs=-1)
    rf_grid.fit(X_train,y_train)
    log_pred=log_grid.predict(X_test); rf_pred=rf_grid.predict(X_test)
    log_metrics=_metrics(y_test,log_pred); rf_metrics=_metrics(y_test,rf_pred)
    baseline_pred=np.zeros(len(y_test),dtype=int)
    baseline_metrics=_metrics(y_test,baseline_pred)
    chosen_name='Random Forest' if rf_metrics['f1']>=log_metrics['f1'] else 'Logistic Regression'
    selected=rf_grid.best_estimator_ if chosen_name=='Random Forest' else log_grid.best_estimator_
    selected_test=rf_pred if chosen_name=='Random Forest' else log_pred
    # Training-only oversampling for the best logistic pipeline.
    train_aug=X_train.copy(); train_aug['__target__']=y_train.values
    class_counts=train_aug['__target__'].value_counts().to_dict()
    majority=int(max(class_counts.values()))
    minority_class=int(min(class_counts,key=class_counts.get))
    minority=train_aug[train_aug['__target__']==minority_class]
    extra=resample(minority,replace=True,n_samples=majority-len(minority),random_state=42)
    balanced=pd.concat([train_aug,extra],ignore_index=True)
    balanced_log=clone(log_grid.best_estimator_)
    balanced_log.fit(balanced[feature_cols],balanced['__target__'])
    balanced_pred=balanced_log.predict(X_test)
    oversample_metrics=_metrics(y_test,balanced_pred)
    # Feature importances and logistic coefficient interpretations.
    rf_model=rf_grid.best_estimator_.named_steps['model']
    rf_names=rf_grid.best_estimator_.named_steps['preprocess'].get_feature_names_out()
    importances=sorted(zip(rf_names,rf_model.feature_importances_),key=lambda z:z[1],reverse=True)[:5]
    log_model=log_grid.best_estimator_.named_steps['model']
    log_names=log_grid.best_estimator_.named_steps['preprocess'].get_feature_names_out()
    coefs=sorted(zip(log_names,log_model.coef_[0]),key=lambda z:abs(z[1]),reverse=True)[:3]
    # Persist chosen model and independently verify the reload produces identical predictions.
    model_path=OUT/'lapse_model.joblib'
    joblib.dump({'pipeline':selected,'feature_columns':feature_cols,'numeric_columns':numeric_cols,
                 'categorical_columns':categorical_cols,'selected_model':chosen_name},model_path)
    loaded=joblib.load(model_path)
    reload_pred=loaded['pipeline'].predict(X_test)
    assert np.array_equal(selected_test,reload_pred)
    # Scores for all eligible pre-cutoff cohort customers, plus the requested illustrative Premium test list.
    all_prob=selected.predict_proba(X)[:,1]
    scores=pd.DataFrame({'customer_id':features.customer_id,'lapse_probability':all_prob,'actually_lapsed':features.lapsed})
    scores.to_csv(OUT/'customer_lapse_scores.csv',index=False)
    premium_map=rfm.set_index('customer_id').is_premium
    test_result=pd.DataFrame({'customer_id':idx_test.values,'lapse_probability':selected.predict_proba(X_test)[:,1],
                              'actually_lapsed':y_test.values})
    test_result['is_premium']=test_result.customer_id.map(premium_map).fillna(False).astype(bool)
    retention=test_result[test_result.is_premium].sort_values('lapse_probability',ascending=False).head(10)
    retention[['customer_id','lapse_probability','actually_lapsed']].to_csv(OUT/'retention_list.csv',index=False)
    report={
      'rfm':{'customers':len(rfm),'recency_median':float(rfm.recency.median()),'recency_min':int(rfm.recency.min()),
        'recency_max':int(rfm.recency.max()),'frequency_mean':float(rfm.frequency.mean()),'frequency_max':int(rfm.frequency.max()),
        'monetary_mean':float(rfm.monetary.mean()),'monetary_max':float(rfm.monetary.max())},
      'kmeans':cluster_scores,'chosen_k':final_k,'segment_profile':segment_profile.round(3).to_dict(orient='records'),
      'premium_segment_id':premium_id,'pca_explained_variance_ratio':pca.explained_variance_ratio_.tolist(),
      'lapse':{'cohort_size':len(features),'lapsed':int(y.sum()),'lapse_rate':float(y.mean()),
        'train_rows':len(X_train),'test_rows':len(X_test),'baseline':baseline_metrics,
        'logistic':{'best_params':log_grid.best_params_,'best_cv_f1':float(log_grid.best_score_),'test':log_metrics},
        'random_forest':{'best_params':rf_grid.best_params_,'best_cv_f1':float(rf_grid.best_score_),'test':rf_metrics},
        'selected_model':chosen_name,'selected_test_f1':_metrics(y_test,selected_test)['f1'],
        'training_scaler_frequency_mean':float(log_grid.best_estimator_.named_steps['preprocess'].named_transformers_['numeric'].mean_[numeric_cols.index('frequency')]),
        'full_cohort_frequency_mean':float(X.frequency.mean()),'oversample_class_counts_before':{str(k):int(v) for k,v in class_counts.items()},
        'oversample_class_counts_after':{str(k):int(v) for k,v in balanced['__target__'].value_counts().to_dict().items()},
        'balanced_logistic_test':oversample_metrics,
        'rf_top_features':[{'feature':str(n),'importance':float(v)} for n,v in importances],
        'logistic_top_coefficients':[{'feature':str(n),'coefficient':float(v),'sign':'positive' if v>0 else 'negative'} for n,v in coefs],
        'reload_predictions_identical':bool(np.array_equal(selected_test,reload_pred)),
        'retention_rows':len(retention),'retention_true_lapsed':int(retention.actually_lapsed.sum()),
      }
    }
    (OUT/'part_b_report.json').write_text(json.dumps(report,indent=2,default=str),encoding='utf-8')
    return report

if __name__=='__main__':
    r=run(); print('Part B complete:',r['lapse']['selected_model'],'test F1=',round(r['lapse']['selected_test_f1'],3))
