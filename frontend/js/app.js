(() => {
  const loaders = { overview: loadOverview, customers: loadCustomers, assistant: () => {}, monitoring: loadMonitoring };
  const nav = document.querySelectorAll('.nav-link');
  let loaded = new Set();
  function showPage(name) {
    document.querySelectorAll('.page').forEach(p => p.classList.toggle('active', p.id === `page-${name}`));
    nav.forEach(button => button.classList.toggle('active', button.dataset.page === name));
    if (loaders[name] && !loaded.has(name)) { loaders[name](); loaded.add(name); }
  }
  nav.forEach(button => button.addEventListener('click', () => showPage(button.dataset.page)));
  window.showError = (message) => { const el = document.getElementById('globalError'); el.textContent = message; el.hidden = false; };
  API.get('/api/health').then(() => { document.getElementById('connectionStatus').textContent = 'Backend connected'; showPage('overview'); })
    .catch(error => { document.getElementById('connectionStatus').textContent = 'Backend unavailable'; showError(`Backend unavailable. Start the local API server and refresh. ${error.message}`); });
})();
