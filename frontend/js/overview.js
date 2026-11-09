(() => {
  const fmt = (n) => Number(n).toLocaleString('en-IN', { maximumFractionDigits: 2 });
  function card(label, value, icon, hint = '') {
    return `<article class="kpi-card"><div class="kpi-top"><span>${label}</span><span class="kpi-icon">${icon}</span></div><div class="kpi-value">${value}</div>${hint ? `<div class="kpi-hint">${hint}</div>` : ''}</article>`;
  }
  async function loadOverview() {
    try {
      const d = await API.get('/api/overview'); const k = d.kpis;
      document.getElementById('overviewKpis').innerHTML = [
        card('Total Customers', fmt(k.total_customers), '◉'),
        card('Total Products', fmt(k.total_products), '▦'),
        card('Total Orders', fmt(k.total_orders), '▤'),
        card('Completed Orders', fmt(k.completed_orders), '✓'),
        card('Cancelled Orders', fmt(k.cancelled_orders), '×'),
        card('Total Revenue', `₹${fmt(k.total_revenue_inr)}`, '₹', 'Completed orders'),
        card('Average Order Value', `₹${fmt(k.average_order_value_inr)}`, '↗'),
        card('Support Tickets', fmt(k.total_support_tickets), '✉')
      ].join('');
      Charts.drawBarChart('revenueByCity', d.revenue_by_city, 'Revenue by City (INR)', 'City', 'Revenue (INR)');
      Charts.drawPieChart('statusPie', d.order_status, 'Final order status distribution');
      Charts.drawBarChart('revenueCategory', d.revenue_by_category, 'Revenue by Product Category (INR)', 'Category', 'Revenue (INR)');
      Charts.drawLineChart('dailyTrend', d.daily_revenue, 'Daily Revenue Trend (INR)', 'Date', 'Revenue (INR)');
      Charts.drawPieChart('segmentPie', d.segment_distribution, 'Customer segment distribution');
      Charts.drawBarChart('orderVolume', d.order_volume_by_city, 'Order Volume by City', 'City', 'Orders');
    } catch (error) { showError(`Could not load Executive Overview: ${error.message}`); }
  }
  window.loadOverview = loadOverview;
})();
