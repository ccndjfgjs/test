const state = { page: 1, pageSize: 12, total: 0, currentView: 'overview', products: [] };
const issueLabels = { cooling_noise: ['Шум охлаждения', '◖'], overheating: ['Перегрев', '♨'], battery_life: ['Автономность', '▰'], display: ['Экран', '▣'], reliability: ['Надёжность', '⌁'], performance: ['Производительность', '↗'] };
const categoryIcons = { 'Graphics cards': ['gpu', '▦'], Laptops: ['laptop', '▱'], Smartphones: ['phone', '▯'], Audio: ['audio', '♫'], Gaming: ['gaming', '⌑'] };
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
let toastTimer;
let jobsPollTimer;

function escapeHtml(value) { return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function safeExternalUrl(value) {
  try {
    const url = new URL(String(value));
    if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password) return '';
    return escapeHtml(url.href);
  } catch { return ''; }
}
function formatMoney(amount, currency = 'EUR') {
  if (amount == null) return '—';
  try { return new Intl.NumberFormat('nl-NL', { style: 'currency', currency, maximumFractionDigits: 2 }).format(Number(amount)); }
  catch { return `${Number(amount).toFixed(2)} ${currency}`; }
}
function formatDate(value) {
  if (!value) return '—';
  return new Intl.DateTimeFormat('ru-RU', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }).format(new Date(value));
}
function renderPriceHistory(history, currency) {
  const points = history.filter(point => point.currency === currency);
  if (points.length < 2) return `<section class="history-card"><div><span class="section-index">ИСТОРИЯ ЦЕН</span><p class="history-empty">Пока недостаточно снимков для графика (${points.length}).</p></div></section>`;
  const values = points.map(point => Number(point.price));
  const min = Math.min(...values), max = Math.max(...values), range = max - min || 1;
  const coords = values.map((value, index) => ({ x: 12 + index * (576 / (values.length - 1)), y: 78 - ((value - min) / range) * 55 }));
  const line = coords.map(point => `${point.x},${point.y}`).join(' ');
  const fill = `12,91 ${line} 588,91`;
  return `<section class="history-card"><div class="history-heading"><div><span class="section-index">ИСТОРИЯ ЦЕН · ${points.length} СНИМКА</span><div class="history-range">${formatMoney(min,currency)} <span>—</span> ${formatMoney(max,currency)}</div></div><span class="tiny-note">${escapeHtml(points[0].region)} → ${escapeHtml(points.at(-1).region)}</span></div>
    <svg class="history-chart" viewBox="0 0 600 105" role="img" aria-label="Изменение цены от ${escapeHtml(formatMoney(min,currency))} до ${escapeHtml(formatMoney(max,currency))}"><defs><linearGradient id="history-fill" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stop-color="#74d8ca" stop-opacity=".32"/><stop offset="100%" stop-color="#74d8ca" stop-opacity="0"/></linearGradient></defs><path d="M${fill.replaceAll(' ', ' L')} L588,91 L12,91 Z" fill="url(#history-fill)"/><polyline points="${line}" fill="none" stroke="#3cb9a8" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>${coords.map(point => `<circle cx="${point.x}" cy="${point.y}" r="3" fill="#fff" stroke="#36a896" stroke-width="2"/>`).join('')}</svg>
    <div class="history-legend"><span>${escapeHtml(formatDate(points[0].captured_at))}</span><span>${escapeHtml(formatDate(points.at(-1).captured_at))}</span></div></section>`;
}
function showToast(message) {
  const toast = $('#toast'); toast.textContent = message; toast.classList.add('show');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => toast.classList.remove('show'), 3600);
}
async function api(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  const response = await fetch(path, { ...options, headers });
  if (!response.ok) {
    let detail = `Ошибка ${response.status}`;
    try { const body = await response.json(); detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail || body); } catch {}
    throw new Error(detail);
  }
  return response.status === 204 ? null : response.json();
}
function viewName(view) { return ({ overview: 'Обзор', catalog: 'Каталог', community: 'Сообщество', sources: 'Источники' })[view] || 'Обзор'; }
function setView(view) {
  state.currentView = view;
  $$('.nav-item').forEach(button => { const active = button.dataset.view === view; button.classList.toggle('active', active); if (active) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current'); });
  $$('.view-panel').forEach(panel => { const active = panel.id === `view-${view}`; panel.classList.toggle('active', active); panel.hidden = !active; });
  $('#breadcrumb-current').textContent = viewName(view);
  if (view === 'catalog') loadProducts();
  if (view === 'community') loadCommunity();
  if (view === 'sources') { loadSources(); loadJobs(); }
  window.scrollTo({ top: 0, behavior: 'smooth' });
}
function categoryIcon(category) { return categoryIcons[category] || ['laptop', '◇']; }
function productIcon(category) { const [kind, glyph] = categoryIcon(category); return `<span class="device-icon ${kind}" aria-hidden="true">${glyph}</span>`; }
function issueTitle(tag) { return issueLabels[tag]?.[0] || tag.replaceAll('_', ' '); }
function issueGlyph(tag) { return issueLabels[tag]?.[1] || '✳'; }

async function loadDashboard() {
  try {
    const [dashboard, productData, categories] = await Promise.all([
      api('/api/dashboard'), api('/api/products?page_size=5&sort=price_asc'), api('/api/catalog/categories')
    ]);
    $('#metric-products').textContent = dashboard.metrics.products.toLocaleString('ru-RU');
    $('#metric-offers').textContent = dashboard.metrics.offers.toLocaleString('ru-RU');
    $('#metric-sources').textContent = dashboard.metrics.sources.toLocaleString('ru-RU');
    $('#metric-reviews').textContent = dashboard.metrics.reviews.toLocaleString('ru-RU');
    $('#market-count').textContent = `${dashboard.metrics.regions} региона`;
    $('#review-base').textContent = dashboard.metrics.reviews.toLocaleString('ru-RU');
    $('#current-date').textContent = new Intl.DateTimeFormat('ru-RU', { day: '2-digit', month: 'short', year: 'numeric' }).format(new Date());
    $('#last-updated').textContent = `обновлено ${new Intl.DateTimeFormat('ru-RU', { hour: '2-digit', minute: '2-digit' }).format(new Date())}`;
    fillCategories(categories);
    renderOverviewProducts(productData.items);
    renderOverviewIssues(dashboard.top_issues, dashboard.metrics.reviews);
  } catch (error) {
    $('#overview-products').innerHTML = `<tr><td colspan="5" class="loading-cell">Не удалось загрузить каталог: ${escapeHtml(error.message)}</td></tr>`;
    showToast(`Не удалось подключиться к API: ${error.message}`);
  }
}
function fillCategories(categories) {
  ['overview-category', 'catalog-category'].forEach(id => {
    const select = document.getElementById(id); if (!select) return;
    const first = select.options[0].outerHTML;
    const selected = select.value;
    select.innerHTML = first + categories.map(category => `<option value="${escapeHtml(category)}">${escapeHtml(category)}</option>`).join('');
    if (categories.includes(selected)) select.value = selected;
  });
}
function renderOverviewProducts(products) {
  state.products = products;
  $('#catalog-count').textContent = `${products.length} из каталога`;
  if (!products.length) { $('#overview-products').innerHTML = '<tr><td colspan="5" class="loading-cell">Ничего не найдено</td></tr>'; return; }
  $('#overview-products').innerHTML = products.map(product => `<tr>
    <td><div class="product-cell">${productIcon(product.category)}<div><strong>${escapeHtml(product.name)}</strong><small>${escapeHtml(product.brand || 'Бренд не указан')} · ${escapeHtml(product.model || '')}</small></div></div></td>
    <td><span class="category-tag">${escapeHtml(product.category)}</span></td>
    <td><span class="offer-count">${product.offer_count} ${product.offer_count === 1 ? 'листинг' : 'листинга'}</span></td>
    <td class="price-cell">${formatMoney(product.min_price, product.currency)}</td>
    <td><button class="open-product" data-product-id="${product.id}" aria-label="Открыть ${escapeHtml(product.name)}">↗</button></td>
  </tr>`).join('');
  $$('#overview-products [data-product-id]').forEach(button => button.addEventListener('click', () => openProduct(button.dataset.productId)));
}
function renderOverviewIssues(issues, totalReviews) {
  const root = $('#overview-issues');
  if (!issues?.length) { root.innerHTML = '<div class="empty-state compact">Пока нет отмеченных технических тем.</div>'; return; }
  const max = Math.max(...issues.map(issue => issue.mentions), 1);
  root.innerHTML = issues.slice(0, 4).map(issue => `<div class="issue-item">
    <span class="issue-symbol" aria-hidden="true">${issueGlyph(issue.tag)}</span><div><span class="issue-name">${escapeHtml(issueTitle(issue.tag))}</span><span class="issue-detail">${issue.negative} негативных сигналов из ${issue.mentions}</span><div class="issue-meter"><span style="width:${Math.max(6, issue.mentions / max * 100)}%"></span></div></div><span class="issue-count">${issue.mentions}</span>
  </div>`).join('');
  $('#review-base').textContent = Number(totalReviews || 0).toLocaleString('ru-RU');
}
function catalogFilters() {
  return new URLSearchParams({
    page: String(state.page), page_size: String(state.pageSize), sort: $('#catalog-sort').value,
    ...( $('#catalog-search').value.trim() ? { q: $('#catalog-search').value.trim() } : {} ),
    ...( $('#catalog-category').value ? { category: $('#catalog-category').value } : {} ),
    ...( $('#catalog-region').value ? { region: $('#catalog-region').value } : {} ),
    ...( $('#catalog-condition').value ? { condition: $('#catalog-condition').value } : {} ),
  });
}
async function loadProducts() {
  const isOverview = state.currentView === 'overview';
  if (isOverview) {
    const params = new URLSearchParams({ page_size: '5', sort: 'price_asc' });
    const query = $('#overview-search').value.trim(); const category = $('#overview-category').value;
    if (query) params.set('q', query); if (category) params.set('category', category);
    const data = await api(`/api/products?${params}`); renderOverviewProducts(data.items); return;
  }
  const grid = $('#catalog-grid'); grid.innerHTML = '<div class="empty-state">Загружаем товары…</div>';
  try {
    const data = await api(`/api/products?${catalogFilters()}`);
    state.total = data.total;
    $('#catalog-result-count').textContent = `${data.total} моделей в каталоге`;
    $('#page-label').textContent = `Страница ${data.page} · ${data.items.length} показано`;
    $('#prev-page').disabled = data.page <= 1;
    $('#next-page').disabled = data.page * data.page_size >= data.total;
    grid.innerHTML = data.items.length ? data.items.map(product => `<article class="catalog-card">
      <div class="catalog-card-top">${productIcon(product.category)}<span class="condition-pill">${product.offer_count ? `${product.offer_count} ПРЕДЛ.` : 'НЕТ В НАЛИЧИИ'}</span></div>
      <h3>${escapeHtml(product.name)}</h3><div class="product-brand">${escapeHtml(product.brand || 'Бренд не указан')} · ${escapeHtml(product.category)}</div>
      <div class="catalog-card-bottom"><div class="catalog-price"><small>ЛУЧШАЯ ЦЕНА</small><strong>${formatMoney(product.min_price, product.currency)}</strong></div><span class="catalog-offers">${product.review_count} отзывов</span></div>
      <button class="card-open" data-product-id="${product.id}">Открыть сравнение <span aria-hidden="true">→</span></button>
    </article>`).join('') : '<div class="empty-state">По этим фильтрам ничего не найдено. Попробуйте изменить запрос.</div>';
    $$('#catalog-grid [data-product-id]').forEach(button => button.addEventListener('click', () => openProduct(button.dataset.productId)));
  } catch (error) { grid.innerHTML = `<div class="empty-state">Ошибка загрузки: ${escapeHtml(error.message)}</div>`; }
}
async function openProduct(id) {
  const modal = $('#product-modal'); const content = $('#product-detail-content');
  content.innerHTML = '<div class="loading-cell">Загружаем карточку…</div>'; modal.showModal();
  try {
    const [detail, history, insights] = await Promise.all([api(`/api/products/${id}`), api(`/api/products/${id}/history`), api(`/api/products/${id}/insights`)]);
    const product = detail.product;
    content.innerHTML = `<div class="detail-brand">${escapeHtml(product.brand || 'БЕЗ БРЕНДА')} · ${escapeHtml(product.category)}</div>
      <h2 class="detail-title" id="product-modal-title">${escapeHtml(product.name)}</h2>
      <div class="detail-price">${formatMoney(product.min_price, product.currency)} <small style="font:9px var(--font);color:#879395">минимальная цена · ${product.offer_count} предлож.</small></div>
      <p class="modal-copy">${escapeHtml(product.description || 'Карточка нормализована по бренду и модели.')}</p>
      ${renderPriceHistory(history, product.currency)}
      ${product.specifications && Object.keys(product.specifications).length ? `<div class="spec-row">${Object.entries(product.specifications).map(([key,value]) => `<span class="category-tag">${escapeHtml(key)}: ${escapeHtml(value)}</span>`).join(' ')}</div>` : ''}
      <h3 class="detail-heading">Предложения по рынкам</h3>
      ${detail.offers.length ? detail.offers.map(offer => `<div class="detail-offer"><div><strong>${escapeHtml(offer.source)}</strong><small>${escapeHtml(offer.region)} · ${escapeHtml(offer.condition)} · ${offer.availability ? 'в наличии' : 'нет в наличии'}${offer.shipping_price ? ` · доставка ${formatMoney(offer.shipping_price, offer.currency)}` : ''}</small></div><span>${safeExternalUrl(offer.url) ? `<a href="${safeExternalUrl(offer.url)}" target="_blank" rel="noopener noreferrer">Открыть ↗</a>` : '—'}</span><strong>${formatMoney(offer.total_price ?? offer.price, offer.currency)}</strong></div>`).join('') : '<p class="modal-copy">Пока нет предложений.</p>'}
      <h3 class="detail-heading">Сигналы отзывов ${insights.review_count ? `(${insights.review_count})` : ''}</h3>
      ${insights.issues.length ? insights.issues.map(issue => `<p class="modal-copy"><b>${escapeHtml(issueTitle(issue.tag))}</b> · ${issue.mentions} упоминаний (${issue.negative} негативных)<br>${(issue.examples || []).slice(0,1).map(example => `<span>«${escapeHtml(example)}»</span>`).join('')}</p>`).join('') : '<p class="modal-copy">Пока нет отмеченных сигналов.</p>'}
      ${detail.reviews.length ? detail.reviews.slice(0,3).map(review => `<blockquote class="detail-review">“${escapeHtml(review.content)}”<small>${escapeHtml(review.source)} · ${review.sentiment}</small></blockquote>`).join('') : ''}
      <div class="tiny-note">ИСТОРИЯ ЦЕН: ${history.length} снимков · Сигналы извлекаются прозрачными правилами.</div>`;
  } catch (error) { content.innerHTML = `<div class="empty-state">Не удалось открыть товар: ${escapeHtml(error.message)}</div>`; }
}
async function loadCommunity() {
  try {
    const data = await api('/api/insights');
    const negative = data.sentiment?.negative || 0;
    $('#community-summary').innerHTML = `<article class="summary-card"><span>ОБРАБОТАНО ОТЗЫВОВ</span><strong>${data.review_count}<small>в базе</small></strong></article><article class="summary-card"><span>ТЕХНИЧЕСКИХ ТЕМ</span><strong>${data.issues.length}<small>категорий</small></strong></article><article class="summary-card"><span>НЕГАТИВНЫХ СИГНАЛОВ</span><strong>${negative}<small>требуют проверки</small></strong></article>`;
    const root = $('#community-issues');
    root.innerHTML = data.issues.length ? data.issues.map(issue => `<article class="community-issue"><div class="community-issue-head"><h3>${issueGlyph(issue.tag)} &nbsp;${escapeHtml(issueTitle(issue.tag))}</h3><span class="issue-count">${issue.mentions} упомин.</span></div><p>${issue.negative} из ${issue.mentions} упоминаний помечены как негативные по правилам тональности. Проверьте первоисточники перед выводами.</p>${(issue.examples || []).slice(0,1).map(example => `<blockquote>«${escapeHtml(example)}»</blockquote>`).join('')}</article>`).join('') : '<div class="empty-state">Пока нет данных сообщества. Отзывы можно загрузить через POST /api/reviews/batch.</div>';
  } catch (error) { $('#community-issues').innerHTML = `<div class="empty-state">Не удалось загрузить сигналы: ${escapeHtml(error.message)}</div>`; }
}
async function loadSources() {
  const root = $('#source-list');
  try {
    const sources = await api('/api/sources');
    root.innerHTML = sources.length ? sources.map(source => `<div class="source-row"><span class="source-mark" aria-hidden="true">⌁</span><div><strong>${escapeHtml(source.name)}</strong><small>${escapeHtml(source.mode)}</small></div><span class="source-stat">${source.offer_count} предлож.</span><span class="source-status">${source.regions} региона</span></div>`).join('') : '<div class="empty-state">Источников пока нет. Импортируйте первую разрешённую выгрузку.</div>';
  } catch (error) { root.innerHTML = `<div class="empty-state">Не удалось загрузить источники: ${escapeHtml(error.message)}</div>`; }
}
async function loadJobs() {
  clearTimeout(jobsPollTimer);
  const root = $('#jobs-table');
  try {
    const jobs = await api('/api/ingestion/jobs?limit=12');
    root.innerHTML = jobs.length ? jobs.map(job => `<tr><td>${escapeHtml(job.source)}</td><td><span class="status-badge ${escapeHtml(job.status)}"><i class="pulse-dot"></i>${escapeHtml(statusLabel(job.status))}</span></td><td>${job.processed_count} / ${job.total_count || '…'}</td><td>${formatDate(job.created_at)}</td><td title="${escapeHtml(job.error_message || '')}">${escapeHtml(job.error_message || '—')}</td></tr>`).join('') : '<tr><td colspan="5" class="loading-cell">Задач пока нет</td></tr>';
    if (jobs.some(job => job.status === 'queued' || job.status === 'running')) jobsPollTimer = setTimeout(loadJobs, 2200);
  } catch (error) { root.innerHTML = `<tr><td colspan="5" class="loading-cell">Ошибка: ${escapeHtml(error.message)}</td></tr>`; }
}
function statusLabel(status) { return ({ queued: 'в очереди', running: 'в работе', succeeded: 'готово', failed: 'ошибка' })[status] || status; }
function openImport() { $('#import-message').textContent = ''; $('#import-message').classList.remove('error'); $('#import-modal').showModal(); }
async function submitImport() {
  const message = $('#import-message'); message.textContent = ''; message.classList.remove('error');
  try {
    const source = $('#source-name').value.trim();
    if (!source) throw new Error('Укажите имя источника.');
    const feedUrl = $('#feed-url').value.trim();
    const apiKey = $('#api-key').value.trim();
    const headers = apiKey ? { 'X-Ingestion-Key': apiKey } : {};
    let result;
    if (feedUrl) {
      result = await api('/api/ingestion/feed-jobs', {
        method: 'POST', headers, body: JSON.stringify({ source, feed_url: feedUrl })
      });
    } else {
      const file = $('#import-file').files[0];
      const raw = file ? await file.text() : $('#import-json').value.trim();
      if (!raw) throw new Error('Выберите JSON-фид, файл или вставьте JSON.');
      const data = JSON.parse(raw);
      const records = Array.isArray(data) ? data : data.records;
      if (!Array.isArray(records) || !records.length) throw new Error('Нужен непустой массив records.');
      result = await api('/api/ingestion/jobs', {
        method: 'POST', headers, body: JSON.stringify({ source, records })
      });
    }
    message.textContent = `Задача ${result.id.slice(0, 8)} создана${result.total_count ? `: ${result.total_count} записей` : ''}.`;
    $('#import-json').value = ''; $('#import-file').value = ''; $('#feed-url').value = '';
    showToast(`Импорт поставлен в очередь${result.total_count ? ` · ${result.total_count} записей` : ''}`);
    setTimeout(() => { loadDashboard(); loadJobs(); }, 500);
    setTimeout(() => { if ($('#import-modal').open) $('#import-modal').close(); }, 1400);
  } catch (error) {
    message.textContent = error instanceof SyntaxError ? 'Некорректный JSON — проверьте формат.' : error.message;
    message.classList.add('error');
  }
}
function wireEvents() {
  $$('.nav-item').forEach(button => button.addEventListener('click', () => setView(button.dataset.view)));
  $$('[data-go-view]').forEach(button => button.addEventListener('click', () => setView(button.dataset.goView)));
  $('#overview-search').addEventListener('input', debounce(loadProducts, 250));
  $('#overview-category').addEventListener('change', loadProducts);
  ['catalog-search'].forEach(id => document.getElementById(id).addEventListener('input', debounce(() => { state.page = 1; loadProducts(); }, 250)));
  ['catalog-category','catalog-region','catalog-condition','catalog-sort'].forEach(id => document.getElementById(id).addEventListener('change', () => { state.page = 1; loadProducts(); }));
  $('#prev-page').addEventListener('click', () => { if (state.page > 1) { state.page--; loadProducts(); } });
  $('#next-page').addEventListener('click', () => { if (state.page * state.pageSize < state.total) { state.page++; loadProducts(); } });
  $('#open-import').addEventListener('click', openImport); $('#open-import-secondary').addEventListener('click', openImport);
  $('#cancel-import').addEventListener('click', () => $('#import-modal').close());
  $('#submit-import').addEventListener('click', submitImport);
  $('#refresh-jobs').addEventListener('click', loadJobs);
  $('#download-example').addEventListener('click', () => {
    const content = JSON.stringify({ source: 'authorized_partner_feed', records: [{ name: 'Laptop 14-inch', brand: 'Example', model: 'E14 Gen 1', category: 'Laptops', region: 'Netherlands', condition: 'new', price: '899.00', currency: 'EUR', external_id: 'partner-item-123', availability: true }] }, null, 2);
    const link = Object.assign(document.createElement('a'), { href: URL.createObjectURL(new Blob([content], { type: 'application/json' })), download: 'speciq-import-example.json' }); link.click(); URL.revokeObjectURL(link.href);
  });
  $('#import-file').addEventListener('change', async event => { if (event.target.files[0]) $('#import-json').value = await event.target.files[0].text(); });
  $('#contrast-button').addEventListener('click', event => { const active = document.body.classList.toggle('high-contrast'); event.currentTarget.setAttribute('aria-pressed', String(active)); $('#accessibility-status').textContent = active ? 'Режим повышенной контрастности включён' : 'Режим повышенной контрастности выключен'; });
  $('#font-button').addEventListener('click', event => { const active = document.body.classList.toggle('large-type'); event.currentTarget.setAttribute('aria-pressed', String(active)); $('#accessibility-status').textContent = active ? 'Увеличенный размер текста включён' : 'Стандартный размер текста'; });
  $('#speak-button').addEventListener('click', event => {
    if (!('speechSynthesis' in window)) { showToast('В этом браузере недоступно озвучивание.'); return; }
    if (speechSynthesis.speaking) { speechSynthesis.cancel(); event.currentTarget.setAttribute('aria-pressed', 'false'); $('#accessibility-status').textContent = 'Озвучивание остановлено'; return; }
    const active = document.querySelector('.view-panel.active');
    const text = active?.innerText?.replace(/\s+/g, ' ').slice(0, 2600) || document.title;
    const utterance = new SpeechSynthesisUtterance(text); utterance.lang = 'ru-RU'; utterance.rate = 1;
    utterance.onend = () => event.currentTarget.setAttribute('aria-pressed', 'false');
    speechSynthesis.cancel(); speechSynthesis.speak(utterance); event.currentTarget.setAttribute('aria-pressed', 'true');
    $('#accessibility-status').textContent = 'Начато озвучивание активного раздела';
  });
  document.addEventListener('keydown', event => {
    if (event.key === '/' && !['INPUT','TEXTAREA'].includes(document.activeElement.tagName)) { event.preventDefault(); (state.currentView === 'catalog' ? $('#catalog-search') : $('#overview-search')).focus(); }
    if (event.key === 'Escape' && 'speechSynthesis' in window && window.speechSynthesis.speaking) window.speechSynthesis.cancel();
  });
}
function debounce(fn, wait) { let timeout; return (...args) => { clearTimeout(timeout); timeout = setTimeout(() => fn(...args), wait); }; }

wireEvents();
loadDashboard();
