(() => {
  let records = [];
  const money = (n) => Number(n).toLocaleString('en-IN', { maximumFractionDigits: 2 });
  function card(label, value, icon) { return `<article class="kpi-card"><div class="kpi-top"><span>${label}</span><span class="kpi-icon">${icon}</span></div><div class="kpi-value">${value}</div></article>`; }
  function renderTable() {
    const query = document.getElementById('customerSearch').value.trim().toLowerCase();
    const city = document.getElementById('cityFilter').value;
    const segment = document.getElementById('segmentFilter').value;
    const filtered = records.filter(r => (!query || `${r.customer_id} ${r.city}`.toLowerCase().includes(query)) && (!city || r.city === city) && (!segment || r.segment_name === segment));
    const body = document.getElementById('customerTableBody');
    body.innerHTML = '';
    filtered.slice(0, 150).forEach(r => {
      const tr = document.createElement('tr');
      const values = [r.customer_id, r.city, r.segment_name, `${r.recency} days`, r.frequency, `₹${money(r.monetary)}`];
      values.forEach((value) => { const td = document.createElement('td'); td.textContent = value ?? '—'; tr.append(td); });
      const premium = document.createElement('td'); premium.innerHTML = r.is_premium ? '<span class="premium-pill">PREMIUM</span>' : '<span class="standard-pill">Standard</span>'; tr.append(premium);
      const risk = document.createElement('td'); risk.textContent = r.lapse_probability == null ? '—' : `${(Number(r.lapse_probability) * 100).toFixed(1)}%`; tr.append(risk);
      body.append(tr);
    });
    if (!filtered.length) body.innerHTML = '<tr><td colspan="8">No customers match these filters.</td></tr>';
    document.getElementById('customerTableCount').textContent = `Showing ${Math.min(filtered.length, 150)} of ${filtered.length.toLocaleString('en-IN')} filtered customers`;
  }
  async function loadCustomers() {
    try {
      const d = await API.get('/api/customers'); records = d.customers || [];
      const k = d.kpis;
      document.getElementById('customerKpis').innerHTML = [
        card('Customers with Completed Orders', money(k.customers_with_completed_orders), '◉'),
        card('Customer Segments', money(k.segment_count), '▦'),
        card('Premium Customers', money(k.premium_customers), '✦'),
        card('Average Frequency', money(k.average_frequency), '↻'),
        card('Average Monetary Value', `₹${money(k.average_monetary_inr)}`, '₹'),
        card('Average Recency', `${money(k.average_recency_days)} days`, '◷')
      ].join('');
      Charts.drawBarChart('segmentDistribution', d.segment_distribution.map(x => ({ label: x.label, value: x.value, detail: `${x.label}: ${x.value} customers (${x.pct}%)` })), 'Customer Count by Segment', 'Segment', 'Customers');
      Charts.drawBarChart('monetaryBySegment', d.average_monetary_by_segment, 'Average Monetary Value by Segment (INR)', 'Segment', 'INR');
      Charts.drawScatterPlot('recencyMonetary', d.recency_monetary_scatter, 'Recency vs Monetary Value', 'Recency (days)', 'Monetary (INR)');
      Charts.drawScatterPlot('frequencyMonetary', d.frequency_monetary_scatter, 'Frequency vs Monetary Value', 'Frequency (orders)', 'Monetary (INR)');
      Charts.drawBarChart('customerCity', d.customer_count_by_city, 'Customer Count by City', 'City', 'Customers');
      Charts.drawHorizontalBar('highRisk', d.top_risk, 'Top 10 High-Risk Customers', '%');
      const citySelect = document.getElementById('cityFilter');
      citySelect.innerHTML = '<option value="">All cities</option>' + [...new Set(records.map(r => r.city))].sort().map(x => `<option>${x}</option>`).join('');
      const segSelect = document.getElementById('segmentFilter');
      segSelect.innerHTML = '<option value="">All segments</option>' + [...new Set(records.map(r => r.segment_name))].sort().map(x => `<option>${x}</option>`).join('');
      renderTable();
    } catch (error) { showError(`Could not load Customer Intelligence: ${error.message}`); }
  }
  document.addEventListener('DOMContentLoaded', () => {
    ['customerSearch','cityFilter','segmentFilter'].forEach(id => document.getElementById(id)?.addEventListener(id === 'customerSearch' ? 'input' : 'change', renderTable));
  });
  window.loadCustomers = loadCustomers;
})();
