(() => {
  const NS = 'http://www.w3.org/2000/svg';
  const palette = ['#f47b35', '#193a57', '#76a5a1', '#d5a84f', '#8d9cac', '#c87868', '#a4b6c5'];
  const node = (tag, attrs = {}, text = '') => {
    const el = document.createElementNS(NS, tag);
    Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, v));
    if (text !== '') el.textContent = text;
    return el;
  };
  function prepare(id, title) {
    const host = document.getElementById(id);
    if (!host) return null;
    host.innerHTML = '';
    const data = [];
    if (!data.length) {
      const svg = node('svg', { viewBox: '0 0 640 250', role: 'img', 'aria-label': title });
      svg.append(node('text', { x: 320, y: 125, 'text-anchor': 'middle', fill: '#98a5b0', 'font-size': 13 }, 'No data available'));
      host.append(svg); return null;
    }
    return host;
  }
  function shell(id, title, height = 250) {
    const host = document.getElementById(id);
    if (!host) return null;
    host.innerHTML = '';
    const svg = node('svg', { viewBox: `0 0 640 ${height}`, role: 'img', 'aria-label': title, preserveAspectRatio: 'xMidYMid meet' });
    svg.append(node('text', { x: 18, y: 21, fill: '#748391', 'font-size': 10, 'font-weight': 700 }, title));
    host.append(svg);
    return svg;
  }
  function empty(id, title) { const svg = shell(id, title); if (svg) svg.append(node('text', { x: 320, y: 135, 'text-anchor': 'middle', fill: '#98a5b0', 'font-size': 13 }, 'No data available')); }
  function drawBarChart(id, data, title, xLabel = '', yLabel = '') {
    if (!data?.length) return empty(id, title);
    const svg = shell(id, title); if (!svg) return;
    const w = 640, h = 250, left = 53, right = 18, top = 40, bottom = 55;
    const max = Math.max(1, ...data.map(d => Number(d.value) || 0));
    const plotH = h - top - bottom, plotW = w - left - right;
    for (let i = 0; i <= 4; i++) {
      const y = top + plotH * i / 4;
      svg.append(node('line', { x1: left, y1: y, x2: w - right, y2: y, stroke: '#edf1f4', 'stroke-width': 1 }));
      svg.append(node('text', { x: left - 8, y: y + 3, 'text-anchor': 'end', fill: '#98a5b0', 'font-size': 9 }, compact(max * (4 - i) / 4)));
    }
    const gap = 13, bw = Math.max(12, (plotW - gap * (data.length - 1)) / data.length);
    data.forEach((d, i) => {
      const val = Number(d.value) || 0, bh = val / max * (plotH - 7), x = left + i * (bw + gap), y = top + plotH - bh;
      const rect = node('rect', { x, y, width: bw, height: bh, rx: 4, fill: palette[i % palette.length] });
      rect.append(node('title', {}, d.detail || `${d.label}: ${formatNumber(val)}`)); svg.append(rect);
      if (data.length <= 8) svg.append(node('text', { x: x + bw / 2, y: Math.max(top + 9, y - 5), 'text-anchor': 'middle', fill: '#647586', 'font-size': 8 }, compact(val)));
      svg.append(node('text', { x: x + bw / 2, y: top + plotH + 16, 'text-anchor': 'middle', fill: '#667787', 'font-size': data.length > 7 ? 8 : 9 }, truncate(d.label, data.length > 7 ? 9 : 15)));
    });
    if (xLabel) svg.append(node('text', { x: left + plotW / 2, y: h - 8, 'text-anchor': 'middle', fill: '#8593a0', 'font-size': 9 }, xLabel));
    if (yLabel) svg.append(node('text', { x: 13, y: top + plotH / 2, transform: `rotate(-90 13 ${top + plotH / 2})`, 'text-anchor': 'middle', fill: '#8593a0', 'font-size': 9 }, yLabel));
  }
  function drawHorizontalBar(id, data, title, valueSuffix = '') {
    if (!data?.length) return empty(id, title);
    const svg = shell(id, title, Math.max(250, 44 + data.length * 20)); if (!svg) return;
    const h = Math.max(250, 44 + data.length * 20); svg.setAttribute('viewBox', `0 0 640 ${h}`);
    const max = Math.max(.01, ...data.map(d => Number(d.value) || 0));
    data.forEach((d, i) => {
      const y = 44 + i * 20, value = Number(d.value) || 0;
      svg.append(node('text', { x: 18, y: y + 11, fill: '#667787', 'font-size': 9 }, truncate(d.label, 18)));
      svg.append(node('rect', { x: 166, y: y + 2, width: 390, height: 10, rx: 5, fill: '#eef2f5' }));
      const bar = node('rect', { x: 166, y: y + 2, width: Math.max(1, 390 * value / max), height: 10, rx: 5, fill: palette[0] });
      bar.append(node('title', {}, `${d.label}: ${formatNumber(value)}${valueSuffix}`)); svg.append(bar);
      svg.append(node('text', { x: 565, y: y + 11, fill: '#516273', 'font-size': 9 }, `${formatNumber(value)}${valueSuffix}`));
    });
    svg.append(node('text', { x: 360, y: h - 5, 'text-anchor': 'middle', fill: '#8593a0', 'font-size': 9 }, 'Predicted lapse probability (%)'));
  }
  function drawPieChart(id, data, title) {
    const valid = (data || []).filter(d => Number(d.value) > 0);
    if (!valid.length) return empty(id, title);
    const svg = shell(id, title); if (!svg) return;
    const total = valid.reduce((s, d) => s + Number(d.value), 0); let angle = -Math.PI / 2;
    const cx = 205, cy = 137, r = 86;
    valid.forEach((d, i) => {
      const next = angle + Number(d.value) / total * Math.PI * 2;
      const x1 = cx + r * Math.cos(angle), y1 = cy + r * Math.sin(angle), x2 = cx + r * Math.cos(next), y2 = cy + r * Math.sin(next);
      const large = next - angle > Math.PI ? 1 : 0;
      const path = node('path', { d: `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2} Z`, fill: palette[i % palette.length], stroke: '#fff', 'stroke-width': 2 });
      path.append(node('title', {}, `${d.label}: ${formatNumber(d.value)} (${(d.value / total * 100).toFixed(1)}%)`)); svg.append(path); angle = next;
    });
    valid.forEach((d, i) => {
      const y = 83 + i * 27;
      svg.append(node('rect', { x: 365, y: y - 9, width: 9, height: 9, rx: 2, fill: palette[i % palette.length] }));
      svg.append(node('text', { x: 381, y, fill: '#627282', 'font-size': 10 }, truncate(d.label, 27)));
      svg.append(node('text', { x: 381, y: y + 12, fill: '#9aa5af', 'font-size': 9 }, `${formatNumber(d.value)} · ${(d.value / total * 100).toFixed(1)}%`));
    });
  }
  function drawLineChart(id, data, title, xLabel = '', yLabel = '') {
    if (!data?.length) return empty(id, title);
    const svg = shell(id, title); if (!svg) return;
    const w = 640, h = 250, left = 53, right = 18, top = 40, bottom = 47;
    const vals = data.map(d => Number(d.value) || 0), max = Math.max(1, ...vals), min = 0;
    const plotH = h - top - bottom, plotW = w - left - right;
    for (let i = 0; i <= 4; i++) {
      const y = top + plotH * i / 4;
      svg.append(node('line', { x1: left, y1: y, x2: w - right, y2: y, stroke: '#edf1f4' }));
      svg.append(node('text', { x: left - 8, y: y + 3, 'text-anchor': 'end', fill: '#98a5b0', 'font-size': 9 }, compact(max * (4 - i) / 4)));
    }
    const points = data.map((d, i) => [left + i * plotW / Math.max(1, data.length - 1), top + plotH - ((Number(d.value) || 0) - min) / (max - min || 1) * plotH]);
    const path = node('path', { d: points.map((p, i) => `${i ? 'L' : 'M'} ${p[0]} ${p[1]}`).join(' '), fill: 'none', stroke: palette[0], 'stroke-width': 2.3, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }); svg.append(path);
    points.forEach((p, i) => { const c = node('circle', { cx: p[0], cy: p[1], r: data.length > 80 ? 1.7 : 3, fill: palette[0] }); c.append(node('title', {}, `${data[i].label}: ${formatNumber(data[i].value)}`)); svg.append(c); });
    [0, Math.floor((data.length - 1) / 2), data.length - 1].forEach(i => { if (i >= 0) svg.append(node('text', { x: points[i][0], y: h - 22, 'text-anchor': 'middle', fill: '#82909d', 'font-size': 8 }, data[i].label)); });
    if (xLabel) svg.append(node('text', { x: 320, y: h - 5, 'text-anchor': 'middle', fill: '#8593a0', 'font-size': 9 }, xLabel));
    if (yLabel) svg.append(node('text', { x: 13, y: 145, transform: 'rotate(-90 13 145)', 'text-anchor': 'middle', fill: '#8593a0', 'font-size': 9 }, yLabel));
  }
  function drawScatterPlot(id, data, title, xLabel = '', yLabel = '') {
    if (!data?.length) return empty(id, title);
    const svg = shell(id, title); if (!svg) return;
    const w = 640, h = 250, left = 52, right = 18, top = 42, bottom = 48;
    const xs = data.map(d => Number(d.x)), ys = data.map(d => Number(d.y));
    const xmin = Math.min(0, ...xs), xmax = Math.max(1, ...xs), ymin = Math.min(0, ...ys), ymax = Math.max(1, ...ys);
    const plotW = w - left - right, plotH = h - top - bottom;
    for (let i = 0; i <= 4; i++) {
      const y = top + plotH * i / 4;
      svg.append(node('line', { x1: left, y1: y, x2: w - right, y2: y, stroke: '#edf1f4' }));
      svg.append(node('text', { x: left - 8, y: y + 3, 'text-anchor': 'end', fill: '#98a5b0', 'font-size': 8 }, compact(ymax * (4 - i) / 4)));
    }
    const groups = [...new Set(data.map(d => d.group || 'Customers'))];
    data.forEach(d => {
      const x = left + (Number(d.x) - xmin) / (xmax - xmin || 1) * plotW;
      const y = top + plotH - (Number(d.y) - ymin) / (ymax - ymin || 1) * plotH;
      const ci = groups.indexOf(d.group || 'Customers');
      const dot = node('circle', { cx: x, cy: y, r: 3, fill: palette[ci % palette.length], opacity: .65 });
      dot.append(node('title', {}, `${d.group || 'Customer'} · ${xLabel}: ${formatNumber(d.x)} · ${yLabel}: ${formatNumber(d.y)}`)); svg.append(dot);
    });
    groups.slice(0, 5).forEach((g, i) => { const x = 72 + i * 112; svg.append(node('circle', { cx: x, cy: h - 14, r: 4, fill: palette[i % palette.length] })); svg.append(node('text', { x: x + 8, y: h - 11, fill: '#82909d', 'font-size': 8 }, truncate(g, 15))); });
    if (xLabel) svg.append(node('text', { x: left + plotW / 2, y: h - 1, 'text-anchor': 'middle', fill: '#8593a0', 'font-size': 8 }, xLabel));
    if (yLabel) svg.append(node('text', { x: 12, y: top + plotH / 2, transform: `rotate(-90 12 ${top + plotH / 2})`, 'text-anchor': 'middle', fill: '#8593a0', 'font-size': 8 }, yLabel));
  }
  function formatNumber(n) { return Number(n).toLocaleString('en-IN', { maximumFractionDigits: 2 }); }
  function compact(n) { const v = Number(n); if (Math.abs(v) >= 1000000) return `${(v / 1000000).toFixed(1)}m`; if (Math.abs(v) >= 1000) return `${(v / 1000).toFixed(1)}k`; return v.toFixed(0); }
  function truncate(s, n) { s = String(s); return s.length > n ? `${s.slice(0, n - 1)}…` : s; }
  window.Charts = { drawBarChart, drawHorizontalBar, drawPieChart, drawLineChart, drawScatterPlot, formatNumber };
})();
