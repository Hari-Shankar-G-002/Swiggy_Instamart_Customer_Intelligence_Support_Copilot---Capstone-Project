(() => {
  const fmt = n => Number(n ?? 0).toLocaleString('en-IN', { maximumFractionDigits: 3 });
  function metric(label, value) { return `<div class="metric-item"><span>${label}</span><strong>${value}</strong></div>`; }
  async function loadMonitoring() {
    try {
      const d = await API.get('/api/monitoring');
      document.getElementById('stageStatus').innerHTML = d.execution_status.map(s => {
        const passed = s.status === 'passed'; const failed = s.status === 'failed';
        return `<article class="stage-card"><strong>${s.label}</strong><span class="stage-state ${passed ? 'passed' : failed ? 'failed' : ''}">${s.status}</span></article>`;
      }).join('');
      document.getElementById('dataMetrics').innerHTML = [
        metric('Raw customers',fmt(d.data.raw_customers)),metric('Raw order rows',fmt(d.data.raw_orders)),
        metric('Clean orders',fmt(d.data.clean_orders)),metric('Duplicate/version rows removed',fmt(d.data.duplicates_removed)),
        metric('Completed orders',fmt(d.data.completed_orders)),metric('Cancelled orders',fmt(d.data.cancelled_orders)),
        metric('Data validation',d.data.validation_status),metric('SQL query checks',d.data.sql_status)
      ].join('');
      document.getElementById('mlMetrics').innerHTML = [
        metric('K-means segments',fmt(d.ml.segments)),metric('PCA variance explained',`${(d.ml.pca_explained_variance*100).toFixed(1)}%`),
        metric('Logistic Regression F1',fmt(d.ml.logistic_f1)),metric('Random Forest F1',fmt(d.ml.random_forest_f1)),
        metric('Baseline F1',fmt(d.ml.baseline_f1)),metric('Selected model',d.ml.selected_model),metric('High-risk Premium list',fmt(d.ml.high_risk_customers))
      ].join('');
      Charts.drawBarChart('modelF1',[
        {label:'Baseline',value:d.ml.baseline_f1},{label:'Logistic',value:d.ml.logistic_f1},{label:'Random Forest',value:d.ml.random_forest_f1}
      ],'Lapsed-class Test F1 Comparison','Model','F1 score');
      document.getElementById('supportMetrics').innerHTML = [
        metric('Total tickets',fmt(d.support.total_tickets)),metric('Successfully classified',fmt(d.support.successfully_classified)),
        metric('Invalid outputs',fmt(d.support.invalid_outputs)),metric('Empty tickets skipped',fmt(d.support.empty_skipped)),
        metric('Long tickets flagged',fmt(d.support.long_flagged)),metric('Human review',fmt(d.support.human_review)),
        metric('Security team',fmt(d.support.security_team)),metric('Premium desk',fmt(d.support.premium_desk))
      ].join('');
      Charts.drawPieChart('triageStatus',d.support.processing_status,'Ticket processing status');
      Charts.drawPieChart('triageClass',d.support.classification_status,'Ticket category / review status');
      document.getElementById('ragMetrics').innerHTML = [
        metric('Policy evaluation questions',fmt(d.rag_agent.policy_questions)),metric('Correct retrieval',`${d.rag_agent.correct_retrieval}/12`),
        metric('Grounded answers',`${d.rag_agent.grounded_answers}/12`),metric('Unanswerable handled',`${d.rag_agent.unanswerable_handled}/2`),
        metric('Refund scenarios',fmt(d.rag_agent.refund_scenarios)),metric('Escalations',fmt(d.rag_agent.escalations)),
        metric('Denied refunds',fmt(d.rag_agent.denied)),metric('Not found',fmt(d.rag_agent.not_found)),metric('Fallbacks',fmt(d.rag_agent.fallbacks))
      ].join('');
      Charts.drawPieChart('agentOutcomes',d.rag_agent.refund_outcomes,'Refund agent scenario outcomes');
    } catch (error) { showError(`Could not load Project Monitoring: ${error.message}`); }
  }
  window.loadMonitoring = loadMonitoring;
})();
