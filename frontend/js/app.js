// Financial Clarity - Web App Frontend State & Logic

const state = {
  activeTab: 'dashboard',
  activeFilter: 'all',
  activeTypeFilter: 'ALL', // 'ALL', 'DEBIT', 'CREDIT'
  searchQuery: '',
  selectedRange: 'month',
  selectedMonth: 'current',
  tags: [],
  rules: [],
  transactions: [],
  dashboardStats: null,
  isDarkMode: localStorage.getItem('fc_theme') === 'dark'
};

// --- INITIALIZATION ---

document.addEventListener('DOMContentLoaded', async () => {
  initTheme();
  setupEventListeners();
  await loadAllData();
});

function initTheme() {
  const html = document.documentElement;
  const icon = document.getElementById('theme-icon');
  if (state.isDarkMode) {
    html.classList.add('dark');
    if (icon) icon.textContent = 'light_mode';
  } else {
    html.classList.remove('dark');
    if (icon) icon.textContent = 'dark_mode';
  }
}

function toggleTheme() {
  state.isDarkMode = !state.isDarkMode;
  localStorage.setItem('fc_theme', state.isDarkMode ? 'dark' : 'light');
  initTheme();
}

function getRangeTimestamps() {
  if (state.selectedMonth === 'all') {
    return { startTs: null, endTs: null };
  }

  // Anchor to the latest transaction in the DB so the range window is relevant
  let anchorMs = Date.now();
  if (state.transactions && state.transactions.length > 0) {
    const maxTxMs = Math.max(...state.transactions.map(t => t.timestamp || 0));
    if (maxTxMs > 0) anchorMs = maxTxMs;
  }

  const anchorDate = new Date(anchorMs);
  let startMs = null;

  if (state.selectedRange === 'week') {
    const d = new Date(anchorDate);
    d.setDate(d.getDate() - 6);
    d.setHours(0, 0, 0, 0);
    startMs = d.getTime();
  } else if (state.selectedRange === 'month') {
    const d = new Date(anchorDate.getFullYear(), anchorDate.getMonth(), 1, 0, 0, 0);
    startMs = d.getTime();
  } else if (state.selectedRange === 'year') {
    const d = new Date(anchorDate.getFullYear(), 0, 1, 0, 0, 0);
    startMs = d.getTime();
  }

  return { startTs: startMs, endTs: null };
}

async function refreshDashboardStats() {
  try {
    const { startTs, endTs } = getRangeTimestamps();
    state.dashboardStats = await ApiClient.getDashboardStats(startTs, endTs);
    renderDashboard();
  } catch (err) {
    console.error('Failed to refresh stats:', err);
  }
}

async function loadAllData() {
  try {
    // First fetch transactions and metadata (unfiltered)
    const [tags, rules, txs] = await Promise.all([
      ApiClient.getTags(),
      ApiClient.getRules(),
      ApiClient.getTransactions()
    ]);

    state.tags = tags;
    state.rules = rules;
    state.transactions = txs;

    // Now compute range timestamps using actual transaction data
    const { startTs, endTs } = getRangeTimestamps();
    state.dashboardStats = await ApiClient.getDashboardStats(startTs, endTs);

    populateTagSelectDropdowns();
    renderDashboard();
    renderHistory();
    renderTags();
    renderRules();
  } catch (err) {
    console.error('Failed to load data:', err);
    showToast('Failed to connect to backend server. Make sure FastAPI server is running.', true);
  }
}

// --- EVENT LISTENERS & ROUTING ---

function setupEventListeners() {
  // Navigation Tabs
  document.querySelectorAll('.nav-tab').forEach(tab => {
    tab.addEventListener('click', (e) => {
      const targetTab = e.currentTarget.getAttribute('data-tab');
      switchTab(targetTab);
    });
  });

  // Theme Toggle Button
  document.getElementById('btn-theme-toggle')?.addEventListener('click', toggleTheme);

  // Clear Data Button
  document.getElementById('btn-seed')?.addEventListener('click', async () => {
    if (confirm('Are you sure you want to clear all transactions, tags, and rules?')) {
      await ApiClient.seedDemoData();
      await loadAllData();
      showToast('All data cleared successfully!');
    }
  });

  // FAB Add Transaction
  document.getElementById('fab-add-tx')?.addEventListener('click', () => {
    openTransactionModal();
  });

  // View All Transactions Button
  document.getElementById('btn-view-all-tx')?.addEventListener('click', () => {
    switchTab('history');
  });

  // Review Untagged Banner Button
  document.getElementById('btn-review-untagged')?.addEventListener('click', () => {
    switchTab('history');
    setHistoryFilter('untagged');
  });

  // Search input in History
  const searchInput = document.getElementById('input-search-tx');
  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      state.searchQuery = e.target.value.trim().toLowerCase();
      renderHistory();
    });
  }

  // Add Tag & Add Rule Buttons
  document.getElementById('btn-open-add-tag')?.addEventListener('click', () => openTagModal());
  document.getElementById('btn-open-add-rule')?.addEventListener('click', () => openRuleModal());

  // Apply Rules Button
  document.getElementById('btn-apply-all-rules')?.addEventListener('click', async () => {
    const res = await ApiClient.applyAllRules();
    showToast(res.message || 'Auto-tag rules applied!');
    await loadAllData();
  });

  // Range Toggle Buttons (Week, Month, Year)
  document.querySelectorAll('.range-btn').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      document.querySelectorAll('.range-btn').forEach(b => {
        b.classList.remove('active', 'bg-primary', 'text-white', 'shadow-sm');
        b.classList.add('text-on-surface-variant', 'dark:text-gray-400');
      });
      const target = e.currentTarget;
      target.classList.add('active', 'bg-primary', 'text-white', 'shadow-sm');
      target.classList.remove('text-on-surface-variant', 'dark:text-gray-400');

      state.selectedRange = target.getAttribute('data-range');
      await refreshDashboardStats();
    });
  });

  // Select Month / Filter Dropdown
  const selectMonth = document.getElementById('select-month');
  if (selectMonth) {
    selectMonth.addEventListener('change', async (e) => {
      state.selectedMonth = e.target.value;
      await refreshDashboardStats();
    });
  }

  // Credit / Debit Type Filter Buttons
  document.querySelectorAll('.tx-type-filter-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      document.querySelectorAll('.tx-type-filter-btn').forEach(b => {
        b.classList.remove('active', 'bg-primary', 'text-white', 'shadow-xs');
      });
      const target = e.currentTarget;
      target.classList.add('active', 'bg-primary', 'text-white', 'shadow-xs');
      state.activeTypeFilter = target.getAttribute('data-type') || 'ALL';
      renderHistory();
    });
  });

  // Modal Closers
  document.querySelectorAll('.btn-close-modal, #modal-backdrop').forEach(el => {
    el.addEventListener('click', (e) => {
      if (e.target === el || el.classList.contains('btn-close-modal')) {
        closeModals();
      }
    });
  });

  // Form Submissions
  document.getElementById('form-transaction')?.addEventListener('submit', handleTransactionSubmit);
  document.getElementById('form-tag')?.addEventListener('submit', handleTagSubmit);
  document.getElementById('form-rule')?.addEventListener('submit', handleRuleSubmit);

  // Sync Color Picker & Text Input for Tag Modal
  const colorPicker = document.getElementById('tag-color-picker');
  const colorText = document.getElementById('tag-color');
  if (colorPicker && colorText) {
    colorPicker.addEventListener('input', (e) => colorText.value = e.target.value);
    colorText.addEventListener('input', (e) => colorPicker.value = e.target.value);
  }

  // Setup Drag & Drop PDF upload handlers
  setupPDFUploadHandlers();
}

function switchTab(tabName) {
  state.activeTab = tabName;
  document.querySelectorAll('.tab-view').forEach(view => view.classList.add('hidden'));
  document.querySelectorAll('.nav-tab').forEach(t => {
    const isTarget = t.getAttribute('data-tab') === tabName;
    if (isTarget) {
      t.classList.add('active', 'text-primary', 'dark:text-[#667EEA]');
      t.classList.remove('text-on-surface-variant', 'dark:text-gray-400');
    } else {
      t.classList.remove('active', 'text-primary', 'dark:text-[#667EEA]');
      t.classList.add('text-on-surface-variant', 'dark:text-gray-400');
    }
  });

  const targetView = document.getElementById(`view-${tabName}`);
  if (targetView) targetView.classList.remove('hidden');

  window.scrollTo({ top: 0, behavior: 'smooth' });
}


// --- DASHBOARD RENDERER ---

function renderDashboard() {
  const stats = state.dashboardStats;
  if (!stats) return;

  // 1. Total Spent Card
  const totalSpentEl = document.getElementById('dash-total-spent');
  if (totalSpentEl) totalSpentEl.textContent = formatCurrency(stats.total_expenditure);

  // 2. Top Expense Card
  const topNameEl = document.getElementById('dash-top-name');
  const topAmountEl = document.getElementById('dash-top-amount');
  if (stats.top_expenditure) {
    if (topNameEl) topNameEl.textContent = stats.top_expenditure.account_name || 'Expense';
    if (topAmountEl) topAmountEl.textContent = formatCurrency(stats.top_expenditure.amount);
  } else {
    if (topNameEl) topNameEl.textContent = 'None';
    if (topAmountEl) topAmountEl.textContent = '₹0.00';
  }

  // 3. Untagged Banner
  const banner = document.getElementById('untagged-banner');
  const bannerText = document.getElementById('untagged-banner-text');
  if (stats.untagged_count > 0) {
    if (banner) banner.classList.remove('hidden');
    if (bannerText) bannerText.textContent = `You have ${stats.untagged_count} expense${stats.untagged_count > 1 ? 's' : ''} without categories.`;
  } else {
    if (banner) banner.classList.add('hidden');
  }

  // 4. Donut Chart & Category Grid
  renderDonutChart(stats.tag_totals, stats.total_expenditure);
  renderCategoryGrid(stats.tag_totals);

  // 5. Daily Trend Chart
  renderDailyTrend(stats.daily_trend);

  // 6. Recent Operations List
  renderRecentOperations();
}

function renderDonutChart(tagTotals, totalExpenditure) {
  const svg = document.getElementById('donut-svg');
  if (!svg) return;

  // Preserve background circle
  svg.innerHTML = '<circle class="stroke-surface-container dark:stroke-white/10" cx="50" cy="50" r="42" fill="none" stroke-width="14"></circle>';

  const centerLabel = document.getElementById('center-label');
  const centerValue = document.getElementById('center-value');
  const defaultLabel = "Total Expenditure";
  const defaultValue = formatCurrency(totalExpenditure);

  if (centerLabel) centerLabel.textContent = defaultLabel;
  if (centerValue) centerValue.textContent = defaultValue;

  if (!tagTotals || tagTotals.length === 0 || totalExpenditure === 0) {
    return;
  }

  const circumference = 2 * Math.PI * 42; // ~263.89
  let currentOffset = 0;

  tagTotals.forEach((item) => {
    const strokeDash = (item.total_amount / totalExpenditure) * circumference;
    const strokeGap = circumference - strokeDash;

    const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    circle.setAttribute('class', 'donut-segment');
    circle.setAttribute('cx', '50');
    circle.setAttribute('cy', '50');
    circle.setAttribute('r', '42');
    circle.setAttribute('stroke', item.tag_color || '#95A5A6');
    circle.setAttribute('stroke-dasharray', `${strokeDash.toFixed(1)} ${strokeGap.toFixed(1)}`);
    circle.setAttribute('style', `stroke-dashoffset: -${currentOffset.toFixed(1)};`);

    circle.setAttribute('data-category', `${item.tag_emoji} ${item.tag_name}`);
    circle.setAttribute('data-amount', formatCurrency(item.total_amount));

    circle.addEventListener('mouseenter', () => {
      if (centerLabel) centerLabel.textContent = `${item.tag_emoji} ${item.tag_name}`;
      if (centerValue) centerValue.textContent = formatCurrency(item.total_amount);
    });

    circle.addEventListener('mouseleave', () => {
      if (centerLabel) centerLabel.textContent = defaultLabel;
      if (centerValue) centerValue.textContent = defaultValue;
    });

    svg.appendChild(circle);
    currentOffset += strokeDash;
  });
}

function renderCategoryGrid(tagTotals) {
  const container = document.getElementById('dash-category-grid');
  if (!container) return;

  if (!tagTotals || tagTotals.length === 0) {
    container.innerHTML = '<p class="text-xs text-on-surface-variant dark:text-gray-400 col-span-2 text-center py-2">No category data yet.</p>';
    return;
  }

  container.innerHTML = tagTotals.map(item => `
    <div class="bg-surface-container-low dark:bg-[#16213E] p-3.5 rounded-2xl flex flex-col justify-between h-24 border border-surface-container dark:border-white/5 shadow-xs">
      <div class="flex justify-between items-center">
        <span class="font-bold text-sm text-on-surface dark:text-white">${formatCurrency(item.total_amount)}</span>
        <span class="text-xs font-semibold px-2 py-0.5 rounded-full bg-surface-container dark:bg-white/10 text-on-surface-variant dark:text-gray-300">${item.percentage}%</span>
      </div>
      <div class="flex items-center gap-2">
        <div class="w-7 h-7 rounded-full flex items-center justify-center text-xs text-white" style="background-color: ${item.tag_color}">
          ${item.tag_emoji}
        </div>
        <span class="text-xs font-medium text-on-surface dark:text-gray-200 truncate">${item.tag_name}</span>
      </div>
    </div>
  `).join('');
}

function renderDailyTrend(dailyTrend) {
  const barsContainer = document.getElementById('trend-bars-container');
  const labelsContainer = document.getElementById('trend-labels-container');
  if (!barsContainer || !labelsContainer) return;

  if (!dailyTrend || dailyTrend.length === 0) {
    barsContainer.innerHTML = '<p class="text-xs text-on-surface-variant dark:text-gray-400 text-center w-full py-4">No spending trend data.</p>';
    labelsContainer.innerHTML = '';
    return;
  }

  barsContainer.innerHTML = dailyTrend.map(day => {
    const heightPct = Math.max(day.percentage, 10);
    return `
      <div class="flex-1 bg-surface-container-high dark:bg-white/10 hover:bg-primary dark:hover:bg-[#667EEA] rounded-t-lg transition-all cursor-pointer group relative" style="height: ${heightPct}%">
        <div class="absolute -top-8 left-1/2 -translate-x-1/2 bg-on-surface dark:bg-white text-white dark:text-black text-[10px] font-bold py-1 px-2 rounded opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap shadow-md z-10">
          ${formatCurrency(day.total_amount)}
        </div>
      </div>
    `;
  }).join('');

  labelsContainer.innerHTML = dailyTrend.map(day => `
    <span class="flex-1 text-center">${day.day_label}</span>
  `).join('');
}

function attachTransactionItemListeners(container) {
  if (!container) return;

  container.querySelectorAll('.btn-delete-tx').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      e.preventDefault();
      const id = parseInt(btn.getAttribute('data-id'), 10);
      if (id && confirm('Delete this transaction?')) {
        try {
          await ApiClient.deleteTransaction(id);
          showToast('Transaction deleted');
          await loadAllData();
        } catch (err) {
          console.error('Delete transaction failed:', err);
          showToast(err.message || 'Failed to delete transaction', true);
        }
      }
    });
  });

  container.querySelectorAll('.btn-copy-vendor').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      e.preventDefault();
      const vendor = decodeURIComponent(btn.getAttribute('data-vendor') || '');
      if (vendor) {
        navigator.clipboard.writeText(vendor).then(() => {
          showToast(`Copied "${vendor}"`);
        }).catch(err => {
          console.error('Clipboard copy error:', err);
          showToast('Failed to copy vendor name', true);
        });
      }
    });
  });

  container.querySelectorAll('.btn-tag-selector').forEach(select => {
    select.addEventListener('change', async (e) => {
      const id = parseInt(select.getAttribute('data-id'), 10);
      const tagId = select.value ? parseInt(select.value, 10) : null;
      try {
        await ApiClient.updateTransactionTag(id, tagId);
        showToast('Transaction tag updated');
        await loadAllData();
      } catch (err) {
        console.error('Update tag failed:', err);
        showToast(err.message || 'Failed to update tag', true);
      }
    });
  });
}

function renderRecentOperations() {
  const container = document.getElementById('dash-recent-list');
  if (!container) return;

  const recent = state.transactions.slice(0, 5);

  if (recent.length === 0) {
    container.innerHTML = '<p class="text-xs text-on-surface-variant dark:text-gray-400 text-center py-4">No recent transactions.</p>';
    return;
  }

  container.innerHTML = recent.map(tx => renderTransactionItemHtml(tx)).join('');
  attachTransactionItemListeners(container);
}


// --- HISTORY / TRANSACTIONS RENDERER ---

function renderHistory() {
  const container = document.getElementById('history-list-container');
  if (!container) return;

  // Render Filter Pills
  renderHistoryFilterPills();

  // Apply filters
  let filtered = [...state.transactions];

  // Apply type filter (ALL, DEBIT, CREDIT)
  if (state.activeTypeFilter && state.activeTypeFilter !== 'ALL') {
    filtered = filtered.filter(t => t.type === state.activeTypeFilter);
  }

  // Apply tag filters
  if (state.activeFilter === 'untagged') {
    filtered = filtered.filter(t => !t.tag_id || !t.is_tagged);
  } else if (state.activeFilter !== 'all') {
    const tagId = parseInt(state.activeFilter, 10);
    filtered = filtered.filter(t => t.tag_id === tagId);
  }

  if (state.searchQuery) {
    filtered = filtered.filter(t => 
      (t.account_name && t.account_name.toLowerCase().includes(state.searchQuery)) ||
      (t.raw_message && t.raw_message.toLowerCase().includes(state.searchQuery)) ||
      (t.tag_name && t.tag_name.toLowerCase().includes(state.searchQuery))
    );
  }

  if (filtered.length === 0) {
    container.innerHTML = '<div class="text-center py-10"><span class="material-symbols-outlined text-4xl text-outline mb-2">search_off</span><p class="text-sm font-medium text-on-surface-variant dark:text-gray-400">No transactions match your filter.</p></div>';
    return;
  }

  // Group by Today, Yesterday, Earlier
  const todayMs = new Date().setHours(0, 0, 0, 0);
  const yesterdayMs = todayMs - (86400 * 1000);

  const groups = {
    TODAY: [],
    YESTERDAY: [],
    EARLIER: []
  };

  filtered.forEach(tx => {
    if (tx.timestamp >= todayMs) groups.TODAY.push(tx);
    else if (tx.timestamp >= yesterdayMs) groups.YESTERDAY.push(tx);
    else groups.EARLIER.push(tx);
  });

  let html = '';

  ['TODAY', 'YESTERDAY', 'EARLIER'].forEach(groupKey => {
    if (groups[groupKey].length > 0) {
      html += `
        <div class="space-y-2">
          <h3 class="text-xs font-bold text-outline dark:text-gray-400 uppercase tracking-wider px-1">${groupKey}</h3>
          <div class="space-y-2.5">
            ${groups[groupKey].map(tx => renderTransactionItemHtml(tx)).join('')}
          </div>
        </div>
      `;
    }
  });

  container.innerHTML = html;
  attachTransactionItemListeners(container);
}

function renderHistoryFilterPills() {
  const container = document.getElementById('history-filter-pills');
  if (!container) return;

  let html = `
    <button class="filter-pill ${state.activeFilter === 'all' ? 'active bg-primary text-white' : 'bg-surface-container-lowest dark:bg-[#1A1A2E] text-on-surface-variant dark:text-gray-300'} whitespace-nowrap px-4 py-1.5 rounded-full text-xs font-semibold border border-surface-container dark:border-white/10 transition-all" data-filter="all">All</button>
    <button class="filter-pill ${state.activeFilter === 'untagged' ? 'active bg-primary text-white' : 'bg-surface-container-lowest dark:bg-[#1A1A2E] text-on-surface-variant dark:text-gray-300'} whitespace-nowrap px-4 py-1.5 rounded-full text-xs font-semibold border border-surface-container dark:border-white/10 transition-all" data-filter="untagged">Untagged</button>
  `;

  state.tags.forEach(tag => {
    const isActive = state.activeFilter === String(tag.id);
    html += `
      <button class="filter-pill ${isActive ? 'active bg-primary text-white' : 'bg-surface-container-lowest dark:bg-[#1A1A2E] text-on-surface-variant dark:text-gray-300'} whitespace-nowrap px-4 py-1.5 rounded-full text-xs font-semibold border border-surface-container dark:border-white/10 transition-all" data-filter="${tag.id}">
        ${tag.emoji || ''} ${tag.name}
      </button>
    `;
  });

  container.innerHTML = html;

  container.querySelectorAll('.filter-pill').forEach(pill => {
    pill.addEventListener('click', (e) => {
      const filter = e.currentTarget.getAttribute('data-filter');
      setHistoryFilter(filter);
    });
  });
}

function setHistoryFilter(filterVal) {
  state.activeFilter = filterVal;
  renderHistory();
}

function renderTransactionItemHtml(tx) {
  const isCredit = tx.type === 'CREDIT';
  const amountStr = `${isCredit ? '+' : '-'} ${formatCurrency(tx.amount)}`;
  const amountColorClass = isCredit ? 'text-emerald-500 font-bold' : 'text-on-surface dark:text-white font-bold';

  const tagColor = tx.tag_color || '#95A5A6';
  const tagEmoji = tx.tag_emoji || '📦';

  const formattedDateTime = tx.timestamp 
    ? new Date(tx.timestamp).toLocaleString('en-IN', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        hour12: true
      })
    : '';

  const vendorName = tx.account_name || 'Unknown Account';

  return `
    <div class="bg-surface-container-lowest dark:bg-[#1A1A2E] p-4 rounded-2xl border border-surface-container dark:border-white/10 flex items-center justify-between shadow-xs transition-all hover:border-primary/30">
      <div class="flex items-center gap-3 overflow-hidden">
        <div class="w-11 h-11 rounded-2xl flex items-center justify-center font-bold text-white shrink-0 shadow-xs" style="background-color: ${tagColor}">
          <span class="text-base">${tagEmoji}</span>
        </div>
        <div class="truncate">
          <div class="flex items-center gap-1.5 truncate">
            <h4 class="font-bold text-sm text-on-surface dark:text-white leading-tight truncate">${vendorName}</h4>
            <button class="btn-copy-vendor text-gray-400 hover:text-primary transition-colors p-0.5 rounded shrink-0" data-vendor="${encodeURIComponent(vendorName)}" title="Copy vendor name">
              <span class="material-symbols-outlined text-[15px]">content_copy</span>
            </button>
          </div>
          <p class="text-xs text-on-surface-variant dark:text-gray-400 truncate mt-0.5">${tx.raw_message || 'Transaction'}</p>
          ${formattedDateTime ? `
            <p class="text-[11px] font-semibold text-primary dark:text-[#667EEA] mt-1 flex items-center gap-1">
              <span class="material-symbols-outlined text-[13px] opacity-80">schedule</span>
              <span>${formattedDateTime}</span>
            </p>
          ` : ''}
        </div>
      </div>

      <div class="flex flex-col items-end gap-1.5 shrink-0 ml-3">
        <span class="text-sm ${amountColorClass}">${amountStr}</span>
        
        <div class="flex items-center gap-1">
          <!-- Tag Selector Dropdown -->
          <select class="btn-tag-selector text-[11px] font-semibold bg-surface-container-low dark:bg-[#16213E] text-on-surface dark:text-gray-200 px-2 py-0.5 rounded-lg border border-surface-container dark:border-white/10 focus:outline-none cursor-pointer" data-id="${tx.id}">
            <option value="" ${!tx.tag_id ? 'selected' : ''}>🏷️ Untagged</option>
            ${state.tags.map(t => `<option value="${t.id}" ${tx.tag_id === t.id ? 'selected' : ''}>${t.emoji || ''} ${t.name}</option>`).join('')}
          </select>

          <!-- Delete Action -->
          <button class="btn-delete-tx text-gray-400 hover:text-rose-500 p-1 rounded-lg transition-colors" data-id="${tx.id}" title="Delete Transaction">
            <span class="material-symbols-outlined text-base">delete</span>
          </button>
        </div>
      </div>
    </div>
  `;
}


// --- TAGS RENDERER ---

function renderTags() {
  const container = document.getElementById('tags-grid-container');
  if (!container) return;

  if (!state.tags || state.tags.length === 0) {
    container.innerHTML = '<p class="text-xs text-on-surface-variant dark:text-gray-400 col-span-2 text-center py-6">No tags created yet.</p>';
    return;
  }

  container.innerHTML = state.tags.map(tag => {
    // Count transactions with this tag
    const txCount = state.transactions.filter(t => t.tag_id === tag.id).length;

    return `
      <div class="bg-surface-container-lowest dark:bg-[#1A1A2E] p-4 rounded-3xl border border-surface-container dark:border-white/10 shadow-xs flex flex-col justify-between space-y-3 relative overflow-hidden group">
        <div class="flex justify-between items-start">
          <div class="w-10 h-10 rounded-2xl flex items-center justify-center text-lg shadow-xs" style="background-color: ${tag.color_hex}20; color: ${tag.color_hex}">
            ${tag.emoji || '🏷️'}
          </div>
          <div class="flex items-center gap-1 opacity-80 group-hover:opacity-100 transition-opacity">
            <button class="btn-edit-tag text-gray-400 hover:text-primary p-1 rounded-lg" data-id="${tag.id}">
              <span class="material-symbols-outlined text-base">edit</span>
            </button>
            <button class="btn-delete-tag text-gray-400 hover:text-rose-500 p-1 rounded-lg" data-id="${tag.id}">
              <span class="material-symbols-outlined text-base">delete</span>
            </button>
          </div>
        </div>

        <div>
          <h3 class="font-bold text-sm text-on-surface dark:text-white leading-tight">${tag.name}</h3>
          <p class="text-xs text-on-surface-variant dark:text-gray-400 mt-0.5">${txCount} transaction${txCount !== 1 ? 's' : ''}</p>
        </div>

        <div class="flex items-center gap-2">
          <span class="w-3 h-3 rounded-full shadow-xs" style="background-color: ${tag.color_hex}"></span>
          <span class="text-[11px] font-mono text-outline uppercase">${tag.color_hex}</span>
        </div>
      </div>
    `;
  }).join('');

  // Event handlers for edit and delete
  container.querySelectorAll('.btn-edit-tag').forEach(btn => {
    btn.addEventListener('click', () => {
      const id = parseInt(btn.getAttribute('data-id'), 10);
      const tag = state.tags.find(t => t.id === id);
      if (tag) openTagModal(tag);
    });
  });

  container.querySelectorAll('.btn-delete-tag').forEach(btn => {
    btn.addEventListener('click', async () => {
      const id = parseInt(btn.getAttribute('data-id'), 10);
      if (confirm('Delete this tag? Associated transactions will become untagged.')) {
        await ApiClient.deleteTag(id);
        showToast('Tag deleted');
        await loadAllData();
      }
    });
  });
}


// --- RULES RENDERER ---

function renderRules() {
  const container = document.getElementById('rules-list-container');
  if (!container) return;

  if (!state.rules || state.rules.length === 0) {
    container.innerHTML = '<p class="text-xs text-on-surface-variant dark:text-gray-400 text-center py-6">No auto-tag rules configured yet.</p>';
    return;
  }

  container.innerHTML = state.rules.map(rule => {
    const isIgnore = rule.is_ignore_rule;
    const badgeBg = isIgnore ? 'bg-rose-500/20 text-rose-600 dark:text-rose-400' : '';
    const badgeStyle = isIgnore ? '' : `style="background-color: ${rule.tag_color || '#667EEA'}"`;

    return `
      <div class="bg-surface-container-lowest dark:bg-[#1A1A2E] p-4 rounded-2xl border border-surface-container dark:border-white/10 shadow-xs flex items-center justify-between">
        <div class="flex items-center gap-3">
          <div class="bg-primary/10 text-primary dark:text-[#667EEA] px-3 py-1.5 rounded-xl font-mono font-bold text-xs">
            "${rule.account_keyword}"
          </div>
          <span class="material-symbols-outlined text-outline text-base">arrow_forward</span>
          <div class="flex items-center gap-1.5 px-3 py-1 rounded-xl text-xs font-bold ${isIgnore ? badgeBg : 'text-white'}" ${badgeStyle}>
            <span>${isIgnore ? '🚫' : (rule.tag_emoji || '🏷️')}</span>
            <span>${isIgnore ? 'IGNORE TRANSACTIONS' : rule.tag_name}</span>
          </div>
        </div>

        <button class="btn-delete-rule text-gray-400 hover:text-rose-500 p-1.5 rounded-lg transition-colors" data-id="${rule.id}" title="Delete Rule">
          <span class="material-symbols-outlined text-lg">delete</span>
        </button>
      </div>
    `;
  }).join('');

  container.querySelectorAll('.btn-delete-rule').forEach(btn => {
    btn.addEventListener('click', async () => {
      const id = parseInt(btn.getAttribute('data-id'), 10);
      if (confirm('Delete this auto-tag rule?')) {
        await ApiClient.deleteRule(id);
        showToast('Rule deleted');
        await loadAllData();
      }
    });
  });
}


// --- MODAL CONTROLLERS & FORM SUBMISSIONS ---

function openTransactionModal(txToEdit = null) {
  const modal = document.getElementById('modal-transaction');
  const backdrop = document.getElementById('modal-backdrop');
  if (!modal || !backdrop) return;

  document.getElementById('modal-tx-title').textContent = txToEdit ? 'Edit Transaction' : 'Add New Transaction';
  document.getElementById('tx-edit-id').value = txToEdit ? txToEdit.id : '';
  document.getElementById('tx-amount').value = txToEdit ? txToEdit.amount : '';
  document.getElementById('tx-type').value = txToEdit ? txToEdit.type : 'DEBIT';
  document.getElementById('tx-account').value = txToEdit ? txToEdit.account_name : '';
  document.getElementById('tx-notes').value = txToEdit ? txToEdit.raw_message : '';

  populateTagSelectDropdowns();
  if (txToEdit) {
    document.getElementById('tx-tag').value = txToEdit.tag_id || '';
  }

  // Reset modal mode to Manual Entry by default
  switchTxModalMode('manual');
  openModal('modal-transaction');
}

function switchTxModalMode(mode) {
  const btnManual = document.getElementById('btn-mode-manual');
  const btnPDF = document.getElementById('btn-mode-pdf');
  const panelManual = document.getElementById('tx-panel-manual');
  const panelPDF = document.getElementById('tx-panel-pdf');

  if (!btnManual || !btnPDF || !panelManual || !panelPDF) return;

  if (mode === 'pdf') {
    btnPDF.className = 'flex-1 py-2 rounded-xl text-xs font-bold transition-all bg-primary text-white shadow-xs flex items-center justify-center gap-1.5';
    btnManual.className = 'flex-1 py-2 rounded-xl text-xs font-bold transition-all text-on-surface-variant dark:text-gray-400 hover:text-on-surface flex items-center justify-center gap-1.5';
    panelManual.classList.add('hidden');
    panelPDF.classList.remove('hidden');
  } else {
    btnManual.className = 'flex-1 py-2 rounded-xl text-xs font-bold transition-all bg-primary text-white shadow-xs flex items-center justify-center gap-1.5';
    btnPDF.className = 'flex-1 py-2 rounded-xl text-xs font-bold transition-all text-on-surface-variant dark:text-gray-400 hover:text-on-surface flex items-center justify-center gap-1.5';
    panelPDF.classList.add('hidden');
    panelManual.classList.remove('hidden');
  }
}

function openTagModal(tagToEdit = null) {
  document.getElementById('modal-tag-title').textContent = tagToEdit ? 'Edit Tag' : 'Add New Tag';
  document.getElementById('tag-edit-id').value = tagToEdit ? tagToEdit.id : '';
  document.getElementById('tag-name').value = tagToEdit ? tagToEdit.name : '';
  document.getElementById('tag-emoji').value = tagToEdit ? tagToEdit.emoji : '🏷️';
  document.getElementById('tag-color').value = tagToEdit ? tagToEdit.color_hex : '#667EEA';
  document.getElementById('tag-color-picker').value = tagToEdit ? tagToEdit.color_hex : '#667EEA';

  openModal('modal-tag');
}

function openRuleModal() {
  document.getElementById('rule-keyword').value = '';
  const radioTag = document.getElementById('rule-type-tag');
  const tagContainer = document.getElementById('rule-tag-container');
  if (radioTag) radioTag.checked = true;
  if (tagContainer) tagContainer.classList.remove('hidden');

  populateTagSelectDropdowns();
  openModal('modal-rule');
}

// Rule Type Radio Listeners
document.querySelectorAll('input[name="rule-type-radio"]').forEach(radio => {
  radio.addEventListener('change', (e) => {
    const tagContainer = document.getElementById('rule-tag-container');
    if (!tagContainer) return;
    if (e.target.value === 'IGNORE') {
      tagContainer.classList.add('hidden');
    } else {
      tagContainer.classList.remove('hidden');
    }
  });
});

let modalCloseTimeout = null;

function openModal(modalId) {
  const modal = document.getElementById(modalId);
  const backdrop = document.getElementById('modal-backdrop');
  if (!modal || !backdrop) return;

  if (modalCloseTimeout) {
    clearTimeout(modalCloseTimeout);
    modalCloseTimeout = null;
  }

  // Hide all other modal panels immediately
  document.querySelectorAll('#modal-transaction, #modal-tag, #modal-rule, #modal-pdf-preview').forEach(m => {
    if (m.id === modalId) {
      m.classList.remove('hidden');
    } else {
      m.classList.add('hidden');
    }
  });

  backdrop.classList.remove('hidden');
  setTimeout(() => backdrop.classList.remove('opacity-0'), 10);
}

function closeModals() {
  const backdrop = document.getElementById('modal-backdrop');
  if (!backdrop) return;

  if (modalCloseTimeout) {
    clearTimeout(modalCloseTimeout);
  }

  backdrop.classList.add('opacity-0');
  modalCloseTimeout = setTimeout(() => {
    backdrop.classList.add('hidden');
    document.querySelectorAll('#modal-transaction, #modal-tag, #modal-rule, #modal-pdf-preview').forEach(m => m.classList.add('hidden'));
    modalCloseTimeout = null;
  }, 200);
}

function populateTagSelectDropdowns() {
  const txTagSelect = document.getElementById('tx-tag');
  const ruleTagSelect = document.getElementById('rule-tag');

  const optionsHtml = state.tags.map(t => `<option value="${t.id}">${t.emoji || ''} ${t.name}</option>`).join('');

  if (txTagSelect) {
    txTagSelect.innerHTML = '<option value="">(Untagged)</option>' + optionsHtml;
  }
  if (ruleTagSelect) {
    ruleTagSelect.innerHTML = optionsHtml;
  }
}

async function handleTransactionSubmit(e) {
  e.preventDefault();
  const editId = document.getElementById('tx-edit-id').value;
  const amount = parseFloat(document.getElementById('tx-amount').value);
  const type = document.getElementById('tx-type').value;
  const account_name = document.getElementById('tx-account').value.trim();
  const raw_message = document.getElementById('tx-notes').value.trim();
  const tagVal = document.getElementById('tx-tag').value;
  const tag_id = tagVal ? parseInt(tagVal, 10) : null;

  const payload = { amount, type, account_name, raw_message, tag_id };

  if (editId) {
    await ApiClient.updateTransaction(parseInt(editId, 10), payload);
    showToast('Transaction updated!');
  } else {
    await ApiClient.createTransaction(payload);
    showToast('Transaction created!');
  }

  closeModals();
  await loadAllData();
}

async function handleTagSubmit(e) {
  e.preventDefault();
  const editId = document.getElementById('tag-edit-id').value;
  const name = document.getElementById('tag-name').value.trim();
  const emoji = document.getElementById('tag-emoji').value.trim() || '🏷️';
  const color_hex = document.getElementById('tag-color').value.trim() || '#667EEA';

  const payload = { name, emoji, color_hex };

  try {
    if (editId) {
      await ApiClient.updateTag(parseInt(editId, 10), payload);
      showToast('Tag updated!');
    } else {
      await ApiClient.createTag(payload);
      showToast('Tag created!');
    }
    closeModals();
    await loadAllData();
  } catch (err) {
    showToast(err.message, true);
  }
}

async function handleRuleSubmit(e) {
  e.preventDefault();
  const account_keyword = document.getElementById('rule-keyword').value.trim();
  const selectedRuleType = document.querySelector('input[name="rule-type-radio"]:checked')?.value || 'TAG';
  const is_ignore_rule = selectedRuleType === 'IGNORE';
  const tagVal = document.getElementById('rule-tag').value;
  const tag_id = (!is_ignore_rule && tagVal) ? parseInt(tagVal, 10) : null;

  try {
    await ApiClient.createRule({ account_keyword, tag_id, is_ignore_rule });
    showToast(is_ignore_rule ? 'Vendor ignore rule created & applied!' : 'Auto-tag rule created & applied!');
    closeModals();
    await loadAllData();
  } catch (err) {
    showToast(err.message, true);
  }
}


// --- UTILITIES ---

function formatCurrency(val) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 2
  }).format(val || 0);
}

function showToast(msg, isError = false) {
  const existing = document.getElementById('app-toast');
  if (existing) existing.remove();

  const toast = document.createElement('div');
  toast.id = 'app-toast';
  toast.className = `fixed top-16 right-4 z-50 px-4 py-2.5 rounded-2xl shadow-xl font-semibold text-xs text-white flex items-center gap-2 animate-fade-in ${
    isError ? 'bg-rose-600' : 'bg-emerald-600'
  }`;
  toast.innerHTML = `
    <span class="material-symbols-outlined text-base">${isError ? 'error' : 'check_circle'}</span>
    <span>${msg}</span>
  `;

  document.body.appendChild(toast);
  setTimeout(() => {
    toast.remove();
  }, 3500);
}


// --- GPAY PDF UPLOAD & PARSING HANDLERS ---

let parsedPDFItemsState = [];

function setupPDFUploadHandlers() {
  const dropzone = document.getElementById('pdf-dropzone');
  const fileInput = document.getElementById('pdf-file-input');

  if (!dropzone || !fileInput) return;

  // Mode Switcher Buttons inside Add Transaction Modal
  document.getElementById('btn-mode-manual')?.addEventListener('click', () => switchTxModalMode('manual'));
  document.getElementById('btn-mode-pdf')?.addEventListener('click', () => switchTxModalMode('pdf'));

  // File input change
  fileInput.addEventListener('change', (e) => {
    if (e.target.files && e.target.files[0]) {
      handlePDFFile(e.target.files[0]);
    }
  });

  // Drag & Drop events
  ['dragenter', 'dragover'].forEach(eventName => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.add('border-primary', 'bg-primary/10');
    }, false);
  });

  ['dragleave', 'drop'].forEach(eventName => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.remove('border-primary', 'bg-primary/10');
    }, false);
  });

  dropzone.addEventListener('drop', (e) => {
    const dt = e.dataTransfer;
    const files = dt.files;
    if (files && files[0]) {
      handlePDFFile(files[0]);
    }
  });

  // Confirm Import Button
  document.getElementById('pdf-btn-confirm-import')?.addEventListener('click', handleConfirmPDFImport);

  // Toggle All Checkbox Button
  document.getElementById('pdf-btn-toggle-all')?.addEventListener('click', () => {
    const checkboxes = document.querySelectorAll('.pdf-tx-checkbox');
    const allChecked = Array.from(checkboxes).every(cb => cb.checked);
    checkboxes.forEach(cb => cb.checked = !allChecked);
    updatePDFSelectedCount();
  });
}

async function handlePDFFile(file) {
  if (!file.name.toLowerCase().endsWith('.pdf')) {
    showToast('Please select a valid PDF document.', true);
    return;
  }

  const pwdInput = document.getElementById('pdf-password-input');
  const password = pwdInput ? pwdInput.value.trim() : '';

  showToast('Parsing GPay Statement PDF...');

  try {
    const res = await ApiClient.parsePDF(file, password);
    parsedPDFItemsState = res.transactions || [];

    renderPDFPreviewModal(res);
    openModal('modal-pdf-preview');
    showToast(`Parsed ${res.total_found} transaction(s)!`);
  } catch (err) {
    console.error('PDF Parse Error:', err);
    showToast(err.message || 'Failed to parse PDF statement.', true);
  }
}

function renderPDFPreviewModal(parseResult) {
  document.getElementById('pdf-stat-total').textContent = `Total: ${parseResult.total_found}`;
  document.getElementById('pdf-stat-new').textContent = `New: ${parseResult.new_count}`;
  document.getElementById('pdf-stat-dup').textContent = `Duplicates: ${parseResult.duplicate_count}`;

  const container = document.getElementById('pdf-preview-list');
  if (!container) return;

  const items = parseResult.transactions || [];

  if (items.length === 0) {
    container.innerHTML = '<p class="text-xs text-on-surface-variant dark:text-gray-400 text-center py-6">No transactions found in this statement.</p>';
    updatePDFSelectedCount();
    return;
  }

  container.innerHTML = items.map((item, idx) => {
    const dateFormatted = new Date(item.timestamp).toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });

    const isDup = item.is_duplicate;
    const isChecked = !isDup; // Duplicates unselected by default!

    return `
      <div class="p-3.5 rounded-2xl border ${
        isDup 
          ? 'bg-surface-container-low/50 dark:bg-[#16213E]/50 border-amber-500/30' 
          : 'bg-surface-container-lowest dark:bg-[#1A1A2E] border-surface-container dark:border-white/10 shadow-xs'
      } flex items-center justify-between gap-3">
        
        <div class="flex items-center gap-3 flex-1 min-w-0">
          <input type="checkbox" class="pdf-tx-checkbox w-4 h-4 rounded text-primary border-surface-container cursor-pointer" data-idx="${idx}" ${isChecked ? 'checked' : ''} onchange="updatePDFSelectedCount()" />
          
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2 flex-wrap">
              <span class="font-bold text-sm text-on-surface dark:text-white truncate">${item.account_name}</span>
              ${item.tag_name ? `
                <span class="text-[10px] font-bold px-2 py-0.5 rounded-full text-white flex items-center gap-1" style="background-color: ${item.tag_color || '#667EEA'}">
                  ${item.tag_emoji || '🏷️'} ${item.tag_name}
                </span>
              ` : ''}
              ${isDup ? `
                <span class="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
                  Duplicate (Already in DB)
                </span>
              ` : `
                <span class="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                  New
                </span>
              `}
            </div>
            <p class="text-[11px] text-on-surface-variant dark:text-gray-400 mt-0.5 truncate">${dateFormatted} • ${item.raw_message}</p>
          </div>
        </div>

        <div class="text-right">
          <span class="font-extrabold text-sm ${item.type === 'CREDIT' ? 'text-emerald-500' : 'text-on-surface dark:text-white'}">
            ${item.type === 'CREDIT' ? '+' : '-'}${formatCurrency(item.amount)}
          </span>
          <p class="text-[10px] font-semibold text-outline uppercase">${item.type}</p>
        </div>

      </div>
    `;
  }).join('');

  updatePDFSelectedCount();
}

function updatePDFSelectedCount() {
  const checkboxes = document.querySelectorAll('.pdf-tx-checkbox:checked');
  const countEl = document.getElementById('pdf-selected-count');
  if (countEl) {
    countEl.textContent = `${checkboxes.length} transaction(s) selected`;
  }
}

function togglePDFSelectAll() {
  const checkboxes = document.querySelectorAll('.pdf-tx-checkbox');
  const allChecked = Array.from(checkboxes).every(cb => cb.checked);
  checkboxes.forEach(cb => cb.checked = !allChecked);
  updatePDFSelectedCount();
}

async function handleConfirmPDFImport() {
  const checkboxes = document.querySelectorAll('.pdf-tx-checkbox:checked');
  if (checkboxes.length === 0) {
    showToast('Please select at least one transaction to import.', true);
    return;
  }

  const selectedPayloads = [];
  checkboxes.forEach(cb => {
    const idx = parseInt(cb.getAttribute('data-idx'), 10);
    const item = parsedPDFItemsState[idx];
    if (item) {
      selectedPayloads.push({
        amount: item.amount,
        type: item.type,
        account_name: item.account_name,
        raw_message: item.raw_message,
        timestamp: item.timestamp,
        tag_id: item.tag_id
      });
    }
  });

  try {
    const res = await ApiClient.confirmImport(selectedPayloads);
    showToast(res.message || 'Transactions imported successfully!');
    closeModals();
    await loadAllData();
    switchTab('history');
  } catch (err) {
    console.error('Import Confirm Error:', err);
    showToast(err.message || 'Failed to import selected transactions.', true);
  }
}

window.handleConfirmPDFImport = handleConfirmPDFImport;
window.togglePDFSelectAll = togglePDFSelectAll;
window.updatePDFSelectedCount = updatePDFSelectedCount;


