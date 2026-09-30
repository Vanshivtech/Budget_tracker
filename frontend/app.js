/* ================================================================
   ABT — AI Budget Tracker  |  App Logic
   Pure vanilla JS. No build step. No dependencies.
   ================================================================ */

(function () {
  'use strict';

  // ---------- State ----------
  let authToken = null;
  let currentUser = null;
  let currentView = 'chat';
  let isSending = false;
  let userNearBottom = true;

  // ---------- DOM refs ----------
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  const authScreen = $('#auth-screen');
  const appScreen = $('#app-screen');
  const authForm = $('#auth-form');
  const authTitle = $('#auth-title');
  const authSubtitle = $('#auth-subtitle');
  const authError = $('#auth-error');
  const authEmail = $('#auth-email');
  const authPassword = $('#auth-password');
  const authSubmitBtn = $('#auth-submit-btn');
  const authSwitchText = $('#auth-switch-text');
  const authSwitchBtn = $('#auth-switch-btn');

  const sidebar = $('#sidebar');
  const sidebarOverlay = $('#sidebar-overlay');
  const mobileMenuBtn = $('#mobile-menu-btn');
  const logoutBtn = $('#logout-btn');
  const userAvatarEl = $('#user-avatar');
  const userEmailEl = $('#user-email');

  const messageList = $('#message-list');
  const messageListInner = $('#message-list-inner');
  const chatWelcome = $('#chat-welcome');
  const typingIndicator = $('#typing-indicator');
  const composerInput = $('#composer-input');
  const composerSend = $('#composer-send');
  const jumpLatest = $('#jump-latest');

  const dashboardContent = $('#dashboard-content');
  const dashboardLoader = $('#dashboard-loader');
  const udharContent = $('#udhar-content');
  const udharLoader = $('#udhar-loader');
  const insightsContent = $('#insights-content');
  const insightsLoader = $('#insights-loader');

  // Onboarding DOM refs
  const onboardingScreen = $('#onboarding-screen');
  const obStepLabel = $('#onboarding-step-label');
  const obIncomeInput = $('#ob-income-input');
  const obCategoriesContainer = $('#ob-categories');
  const obTotalAmount = $('#ob-total-amount');
  const obRemaining = $('#ob-remaining');
  const obReviewList = $('#ob-review-list');
  const obReviewSummary = $('#ob-review-summary');
  const obBackBtn = $('#ob-back');
  const obSkipBtn = $('#ob-skip');
  const obNextBtn = $('#ob-next');
  const redoOnboardingBtn = $('#redo-onboarding-btn');

  // Onboarding state
  let currentObStep = 1;
  let obLiving = 'alone';
  let obIncome = null;
  let obCategoryState = {};
  let obDefaultsFetched = false;
  let obLastFetchedSituation = null;
  let obLastFetchedIncome = null;

  let isLoginMode = true;

  // ---------- Helpers ----------

  function api(path, options = {}) {
    const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
    if (authToken) headers['Authorization'] = 'Bearer ' + authToken;
    return fetch(path, { ...options, headers }).then(async (res) => {
      if (res.status === 401) {
        doLogout();
        throw new Error('Session expired');
      }
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Request failed');
      return data;
    });
  }

  function showToast(msg, type = 'info') {
    const container = $('#toast-container');
    const el = document.createElement('div');
    el.className = 'toast ' + type;
    el.textContent = msg;
    container.appendChild(el);
    setTimeout(() => {
      el.style.animation = 'toastOut 300ms ease forwards';
      setTimeout(() => el.remove(), 300);
    }, 3500);
  }

  // ---------- Theme Management ----------
  function getPreferredTheme() {
    const saved = localStorage.getItem('abt_theme');
    if (saved) return saved;
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches
      ? 'light'
      : 'dark';
  }

  function applyTheme(theme, save = true) {
    document.documentElement.setAttribute('data-theme', theme);
    const meta = $('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', theme === 'light' ? '#F4F6F8' : '#0B0D11');
    if (save) {
      try {
        localStorage.setItem('abt_theme', theme);
      } catch (e) {}
    }
  }

  function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme') || getPreferredTheme();
    const next = current === 'light' ? 'dark' : 'light';
    applyTheme(next, true);
  }

  function initTheme() {
    const initial = getPreferredTheme();
    applyTheme(initial, false);

    ['#theme-toggle', '#theme-toggle-mobile', '#theme-toggle-auth'].forEach((sel) => {
      const btn = $(sel);
      if (btn) {
        btn.addEventListener('click', (e) => {
          e.preventDefault();
          toggleTheme();
        });
      }
    });

    if (window.matchMedia) {
      window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', (e) => {
        if (!localStorage.getItem('abt_theme')) {
          applyTheme(e.matches ? 'light' : 'dark', false);
        }
      });
    }
  }

  initTheme();

  function formatCurrency(n) {
    if (n == null || isNaN(n)) return '--';
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(n);
  }

  function formatDate(dateStr) {
    if (!dateStr) return '';
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
  }

  function formatTime(dateStr) {
    if (!dateStr) return '';
    const d = new Date(dateStr);
    return d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true });
  }

  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  // ---------- Auth ----------

  function toggleAuthMode() {
    isLoginMode = !isLoginMode;
    authTitle.textContent = isLoginMode ? 'Welcome back' : 'Create account';
    authSubtitle.textContent = isLoginMode ? 'Sign in to your account' : 'Get started with ABT';
    authSubmitBtn.textContent = isLoginMode ? 'Sign in' : 'Create account';
    authSwitchText.textContent = isLoginMode ? "Don't have an account?" : 'Already have an account?';
    authSwitchBtn.textContent = isLoginMode ? 'Create account' : 'Sign in';
    authError.classList.remove('visible');
    authError.textContent = '';
    authPassword.autocomplete = isLoginMode ? 'current-password' : 'new-password';
  }

  authSwitchBtn.addEventListener('click', toggleAuthMode);

  authForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const email = authEmail.value.trim();
    const password = authPassword.value;

    if (!email || !password) return;

    authSubmitBtn.disabled = true;
    authSubmitBtn.textContent = isLoginMode ? 'Signing in...' : 'Creating account...';
    authError.classList.remove('visible');

    try {
      const endpoint = isLoginMode ? '/api/login' : '/api/signup';
      const data = await api(endpoint, {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      });

      authToken = data.token;
      currentUser = data.user;
      sessionStorage.setItem('abt_token', authToken);
      sessionStorage.setItem('abt_user', JSON.stringify(currentUser));

      await checkOnboardingAndProceed();
    } catch (err) {
      authError.textContent = err.message;
      authError.classList.add('visible');
    } finally {
      authSubmitBtn.disabled = false;
      authSubmitBtn.textContent = isLoginMode ? 'Sign in' : 'Create account';
    }
  });

  function doLogout() {
    authToken = null;
    currentUser = null;
    sessionStorage.removeItem('abt_token');
    sessionStorage.removeItem('abt_user');
    sessionStorage.removeItem('abt_onboarding_skipped');
    hideOnboarding();
    authScreen.style.display = '';
    appScreen.classList.remove('active');
    // Reset state
    messageListInner.querySelectorAll('.msg').forEach((m) => m.remove());
    chatWelcome.style.display = '';
    authEmail.value = '';
    authPassword.value = '';
  }

  logoutBtn.addEventListener('click', doLogout);

  // ---------- Session restore & Onboarding check ----------

  async function tryRestore() {
    const token = sessionStorage.getItem('abt_token');
    const user = sessionStorage.getItem('abt_user');
    if (token && user) {
      authToken = token;
      currentUser = JSON.parse(user);
      await checkOnboardingAndProceed();
    }
  }

  async function checkOnboardingAndProceed() {
    try {
      const skipped = sessionStorage.getItem('abt_onboarding_skipped');
      if (skipped) {
        showApp();
        return;
      }
      const st = await api('/api/onboarding/status');
      if (st && !st.completed) {
        showOnboarding(1);
      } else {
        showApp();
      }
    } catch (err) {
      console.warn('Could not check onboarding status:', err);
      showApp();
    }
  }

  function showApp() {
    authScreen.style.display = 'none';
    hideOnboarding();
    appScreen.classList.add('active');
    updateUserUI();
    loadChatHistory();
    loadGlanceData();
    switchView('chat');
  }

  function updateUserUI() {
    if (!currentUser) return;
    const email = currentUser.email || '';
    userEmailEl.textContent = email;
    userAvatarEl.textContent = email.charAt(0).toUpperCase();
  }

  // ---------- Navigation ----------

  function switchView(view) {
    currentView = view;

    // Update nav items (sidebar)
    $$('.nav-item').forEach((n) => {
      n.classList.toggle('active', n.dataset.view === view);
    });

    // Update tabs (mobile)
    $$('.tab-item').forEach((t) => {
      t.classList.toggle('active', t.dataset.view === view);
    });

    // Show correct panel
    $$('.view-panel').forEach((p) => {
      p.classList.toggle('active', p.id === 'view-' + view);
    });

    // Close mobile sidebar
    closeSidebar();

    // Load data for the view
    if (view === 'dashboard') loadDashboard();
    if (view === 'udhar') loadUdhar();
    if (view === 'insights') loadInsights();
  }

  // Nav click handlers
  $$('.nav-item').forEach((n) => {
    n.addEventListener('click', () => switchView(n.dataset.view));
  });
  $$('.tab-item').forEach((t) => {
    t.addEventListener('click', () => switchView(t.dataset.view));
  });

  // Mobile sidebar
  function openSidebar() {
    sidebar.classList.add('open');
    sidebarOverlay.classList.add('visible');
  }

  function closeSidebar() {
    sidebar.classList.remove('open');
    sidebarOverlay.classList.remove('visible');
  }

  mobileMenuBtn.addEventListener('click', openSidebar);
  sidebarOverlay.addEventListener('click', closeSidebar);

  // ---------- Chat ----------

  // Auto-grow textarea
  composerInput.addEventListener('input', () => {
    composerInput.style.height = 'auto';
    composerInput.style.height = Math.min(composerInput.scrollHeight, 150) + 'px';
    composerSend.classList.toggle('ready', composerInput.value.trim().length > 0);
    composerSend.disabled = composerInput.value.trim().length === 0;
  });

  // Send on Enter (Shift+Enter for newline)
  composerInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  composerSend.addEventListener('click', sendMessage);

  // Suggestion chips
  $$('.chip').forEach((chip) => {
    chip.addEventListener('click', () => {
      composerInput.value = chip.dataset.msg;
      composerInput.dispatchEvent(new Event('input'));
      sendMessage();
    });
  });

  async function sendMessage() {
    const text = composerInput.value.trim();
    if (!text || isSending) return;

    isSending = true;

    // Hide welcome
    chatWelcome.style.display = 'none';

    // Add user message
    appendMessage('user', text);

    // Clear input
    composerInput.value = '';
    composerInput.style.height = 'auto';
    composerSend.classList.remove('ready');
    composerSend.disabled = true;

    // Show typing
    typingIndicator.classList.add('visible');
    scrollToBottom();

    try {
      const data = await api('/api/chat', {
        method: 'POST',
        body: JSON.stringify({ message: text, session_id: 'default' }),
      });

      typingIndicator.classList.remove('visible');
      appendMessage('assistant', data.reply);
    } catch (err) {
      typingIndicator.classList.remove('visible');
      appendMessage('assistant', 'Something went wrong. Please try again.');
      showToast(err.message, 'error');
    } finally {
      isSending = false;
    }
  }

  function appendMessage(role, content, timestamp) {
    const msgEl = document.createElement('div');
    msgEl.className = 'msg ' + role;

    const contentEl = document.createElement('div');
    contentEl.className = 'msg-content';
    // Render text with line breaks
    contentEl.innerHTML = formatMessageContent(content);
    msgEl.appendChild(contentEl);

    if (timestamp) {
      const timeEl = document.createElement('div');
      timeEl.className = 'msg-time';
      timeEl.textContent = formatTime(timestamp);
      msgEl.appendChild(timeEl);
    }

    // Insert before typing indicator
    if (typingIndicator && typingIndicator.parentNode === messageListInner) {
      messageListInner.insertBefore(msgEl, typingIndicator);
    } else {
      messageListInner.appendChild(msgEl);
    }
    scrollToBottom();
  }

  function formatMessageContent(text) {
    if (!text) return '';
    // Escape HTML, then convert newlines to <br>
    let html = escapeHtml(text);
    html = html.replace(/\n/g, '<br>');
    // Bold: **text**
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    return html;
  }

  // Scroll management
  messageList.addEventListener('scroll', () => {
    const threshold = 100;
    const isNear =
      messageList.scrollHeight - messageList.scrollTop - messageList.clientHeight < threshold;
    userNearBottom = isNear;
    jumpLatest.classList.toggle('visible', !isNear);
  });

  jumpLatest.addEventListener('click', () => {
    scrollToBottom(true);
    jumpLatest.classList.remove('visible');
  });

  function scrollToBottom(force) {
    if (force || userNearBottom) {
      requestAnimationFrame(() => {
        messageList.scrollTop = messageList.scrollHeight;
      });
    }
  }

  // Load chat history
  async function loadChatHistory() {
    try {
      const data = await api('/api/chat/history');
      if (data.messages && data.messages.length > 0) {
        chatWelcome.style.display = 'none';
        // Clear existing messages
        messageListInner.querySelectorAll('.msg').forEach((m) => m.remove());
        data.messages.forEach((m) => {
          appendMessage(m.role, m.content, m.created_at);
        });
      }
    } catch (err) {
      // Silent fail — first use
    }
  }

  // Load glance data for welcome card
  async function loadGlanceData() {
    try {
      const [snapshot, streak, goals] = await Promise.all([
        api('/api/snapshot').catch(() => null),
        api('/api/streak').catch(() => null),
        api('/api/goals').catch(() => null),
      ]);

      if (snapshot) {
        const safeSpend = snapshot.safe_to_spend_daily;
        const savingsRate = snapshot.savings_rate_pct;
        $('#glance-safe').textContent = safeSpend != null ? formatCurrency(safeSpend) : '--';
        $('#glance-savings').textContent =
          savingsRate != null ? savingsRate.toFixed(0) + '%' : '--';
      }

      if (streak) {
        const days = streak.current_streak || 0;
        $('#glance-streak').textContent = days + ' day streak';
      }

      if (goals && goals.goals && goals.goals.length > 0) {
        const top = goals.goals[0];
        const pct = top.target_amount > 0
          ? Math.round((top.saved_amount / top.target_amount) * 100)
          : 0;
        $('#glance-goal').textContent = pct + '%';
      }
    } catch (err) {
      // Silent
    }
  }

  // ---------- Dashboard ----------

  async function loadDashboard() {
    dashboardLoader.style.display = '';
    dashboardContent.style.display = 'none';

    try {
      const [summary, dashboard, snapshot, insightsData, healthScore, recurringData, remindersData, rolloverData] = await Promise.all([
        api('/api/summary'),
        api('/api/dashboard'),
        api('/api/snapshot').catch(() => null),
        api('/api/insights').catch(() => null),
        api('/api/health-score').catch(() => null),
        api('/api/recurring').catch(() => ({ recurring: [] })),
        api('/api/recurring/reminders').catch(() => ({ reminders: [] })),
        api('/api/budgets/rollover').catch(() => ({ budgets: {} })),
      ]);

      renderDashboard(summary, dashboard, snapshot, insightsData, healthScore, recurringData, remindersData, rolloverData);
    } catch (err) {
      console.error('loadDashboard error:', err);
      dashboardContent.innerHTML =
        '<div class="empty-state"><p>Could not load dashboard data.</p></div>';
      dashboardContent.style.display = '';
    } finally {
      dashboardLoader.style.display = 'none';
    }
  }

  function animateNumber(el, target, formatFn) {
    if (!el || isNaN(target)) return;
    const start = 0;
    const duration = 450;
    const startTime = performance.now();

    function tick(now) {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const ease = 1 - Math.pow(1 - progress, 3);
      const current = Math.round(start + (target - start) * ease);
      el.textContent = formatFn(current);
      if (progress < 1) {
        requestAnimationFrame(tick);
      } else {
        el.textContent = formatFn(target);
      }
    }
    requestAnimationFrame(tick);
  }

  function renderDashboard(summary, dashboard, snapshot, insightsData, healthScore, recurringData, remindersData, rolloverData) {
    const totalSpent = summary.total_spent || dashboard.total_spent || 0;
    const totalBudget = summary.total_budget || dashboard.total_budget || 0;
    const txnCount = (summary.recent_transactions || []).length;
    const recentTxns = summary.recent_transactions || [];

    // Parse categories from either summary or dashboard format
    const rawCategories = summary.categories || dashboard.categories || summary.category_breakdown || [];
    const rolloverMap = (rolloverData && rolloverData.budgets) || {};

    const categoryBreakdown = rawCategories
      .map((c) => ({
        category: c.category || '',
        total: typeof c.spent === 'number' ? c.spent : (typeof c.total === 'number' ? c.total : 0),
        budget: typeof c.budget === 'number' ? c.budget : 0,
        base_budget: typeof c.base_budget === 'number' ? c.base_budget : (typeof c.budget === 'number' ? c.budget : 0),
        rollover_enabled: typeof c.rollover_enabled === 'boolean' ? c.rollover_enabled : !!(rolloverMap[c.category?.toLowerCase()]?.rollover_enabled),
        carried_amount: typeof c.carried_amount === 'number' ? c.carried_amount : (rolloverMap[c.category?.toLowerCase()]?.carried_amount || 0),
      }))
      .filter((c) => c.total > 0 || c.budget > 0)
      .sort((a, b) => b.total - a.total);

    // Build budgets map
    const budgets = {};
    rawCategories.forEach((c) => {
      if (c.category && typeof c.budget === 'number' && c.budget > 0) {
        budgets[c.category.toLowerCase()] = c.budget;
      }
    });

    // Parse daily spend
    const rawDaily = dashboard.daily_spend || [];
    const dailySpend = rawDaily.map((d) => ({
      date: d.day || d.date || '',
      total: typeof d.total === 'number' ? d.total : (typeof d.amount === 'number' ? d.amount : 0),
    }));

    // Calculations for top stat cards
    const budgetRemaining = Math.max(0, totalBudget - totalSpent);
    const budgetPctLeft = totalBudget > 0 ? Math.round(((totalBudget - totalSpent) / totalBudget) * 100) : 0;

    let savingsThisMonth = 0;
    let savingsRate = 0;
    if (snapshot && snapshot.monthly_income && snapshot.monthly_income > 0) {
      savingsThisMonth = Math.max(0, snapshot.monthly_income - totalSpent);
      savingsRate = Math.round((savingsThisMonth / snapshot.monthly_income) * 100);
    } else if (budgets['emergency fund'] || budgets['sip / investments']) {
      savingsThisMonth = (budgets['emergency fund'] || 0) + (budgets['sip / investments'] || 0);
      savingsRate = 0;
    }

    // Potential savings
    const discCats = ['eating out', 'shopping', 'entertainment', 'personal care', 'miscellaneous', 'food'];
    const discSpend = categoryBreakdown
      .filter((c) => discCats.includes(c.category.toLowerCase()))
      .reduce((sum, c) => sum + (c.total || 0), 0);

    let potentialSavings = 0;
    let potentialSub = 'Identified opportunities';
    if (discSpend > 0) {
      potentialSavings = Math.round(discSpend * 0.15);
      potentialSub = '15% trim on discretionary';
    } else {
      const overruns = categoryBreakdown
        .filter((c) => budgets[c.category.toLowerCase()] && c.total > budgets[c.category.toLowerCase()])
        .reduce((sum, c) => sum + (c.total - budgets[c.category.toLowerCase()]), 0);
      if (overruns > 0) {
        potentialSavings = Math.round(overruns);
        potentialSub = 'From budget overruns';
      } else if (budgetRemaining > 0) {
        potentialSavings = Math.round(budgetRemaining * 0.15);
        potentialSub = 'From unspent budget buffer';
      } else {
        potentialSavings = 0;
        potentialSub = 'Track expenses to unlock';
      }
    }

    // AI Insight determination from actual data
    let insightTitle = 'FINANCIAL HABIT SUMMARY';
    let insightText = '';
    let insightPrompt = '';

    if (categoryBreakdown.length > 0) {
      const top = categoryBreakdown[0];
      const pct = totalSpent > 0 ? Math.round((top.total / totalSpent) * 100) : 0;
      const topLimit = budgets[top.category.toLowerCase()] || 0;
      if (topLimit > 0 && top.total > topLimit) {
        insightTitle = `OVER-BUDGET: ${top.category.toUpperCase()}`;
        insightText = `You spent ${formatCurrency(top.total)} on ${top.category}, which is ${formatCurrency(top.total - topLimit)} over your ${formatCurrency(topLimit)} monthly budget.`;
        insightPrompt = `How can I reduce my ${top.category} expenses this month?`;
      } else {
        insightTitle = `${top.category.toUpperCase()} IS YOUR LARGEST OUTFLOW`;
        insightText = `Spending on ${top.category} accounts for ${pct}% of your total outflow this month (${formatCurrency(top.total)} across logged expenses).`;
        insightPrompt = `Analyze my spending on ${top.category} and suggest ways to optimize it.`;
      }
    } else if (insightsData && insightsData.insights && insightsData.insights.length > 0) {
      const ins = insightsData.insights[0];
      insightTitle = (ins.title || 'SPENDING PATTERN IDENTIFIED').toUpperCase();
      insightText = ins.body || ins.text || `Top category spend is ${formatCurrency(ins.value || 0)}.`;
      insightPrompt = `Tell me more about: ${ins.title}`;
    } else {
      insightTitle = 'PROACTIVE SPENDING HABITS';
      insightText = 'Log your daily expenses in chat or adjust category limits to receive automated insights and habit recommendations.';
      insightPrompt = 'Help me plan my budget for this month';
    }

    let html = '';

    // 0. Bill Reminder Banner (if any bills due in <= 2 days)
    if (remindersData && remindersData.reminders && remindersData.reminders.length > 0) {
      const r = remindersData.reminders[0];
      const dueStr = r.days_until_due === 0 ? 'due today' : (r.days_until_due === 1 ? 'due tomorrow' : 'due in 2 days');
      html += `
        <div class="bill-reminder-banner">
          <div class="bill-reminder-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>
              <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
            </svg>
          </div>
          <div class="bill-reminder-info">
            <strong>Upcoming Bill:</strong> ${escapeHtml(r.name)} (${formatCurrency(r.amount)}) is ${dueStr} (${formatDate(r.next_due_date)}).
          </div>
          <button class="bill-reminder-action" id="banner-view-bills-btn">View Bills</button>
        </div>
      `;
    }

    // 1. Dashboard Header
    html += `
      <div class="dashboard-header">
        <div class="dashboard-header-text">
          <h1>Dashboard</h1>
          <p>Personal financial health and monthly expense breakdown</p>
        </div>
        <div class="dashboard-header-actions">
          <button class="btn-export-statement" id="btn-open-export">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:14px;height:14px;">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="7 10 12 15 17 10"/>
              <line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
            Export Statement
          </button>
          <div class="dashboard-period-badge">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
              <line x1="16" y1="2" x2="16" y2="6"/>
              <line x1="8" y1="2" x2="8" y2="6"/>
              <line x1="3" y1="10" x2="21" y2="10"/>
            </svg>
            <span>This Month</span>
          </div>
        </div>
      </div>
    `;

    // 2. 4 Top Stat Cards
    html += '<div class="stat-cards-row">';

    // Card 1: This Month's Spending
    html += `
      <div class="stat-card">
        <div class="stat-card-header">
          <span class="stat-card-label">This Month's Spending</span>
          <div class="stat-card-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="1" y="4" width="22" height="16" rx="2" ry="2"/>
              <line x1="1" y1="10" x2="23" y2="10"/>
            </svg>
          </div>
        </div>
        <div class="stat-card-value" id="stat-val-spent">${formatCurrency(totalSpent)}</div>
        <div class="stat-card-sub">
          <span class="stat-pill neutral">${txnCount} entries</span>
          <span>across all categories</span>
        </div>
      </div>
    `;

    // Card 2: Budget Remaining
    const budgetStatusClass = totalBudget <= 0 ? 'neutral' : (totalSpent > totalBudget ? 'danger' : budgetPctLeft < 20 ? 'warning' : 'success');
    const budgetBadgeText = totalBudget > 0 ? (totalSpent > totalBudget ? 'Over budget' : `${budgetPctLeft}% left`) : 'No budget';
    html += `
      <div class="stat-card">
        <div class="stat-card-header">
          <span class="stat-card-label">Budget Remaining</span>
          <div class="stat-card-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
            </svg>
          </div>
        </div>
        <div class="stat-card-value" id="stat-val-budget">${formatCurrency(budgetRemaining)}</div>
        <div class="stat-card-sub">
          <span class="stat-pill ${budgetStatusClass}">${budgetBadgeText}</span>
          <span>of ${formatCurrency(totalBudget)} total</span>
        </div>
      </div>
    `;

    // Card 3: Savings This Month
    const savingsSubText = snapshot && snapshot.monthly_income > 0 ? `${savingsRate}% savings rate` : 'Planned monthly allocation';
    html += `
      <div class="stat-card">
        <div class="stat-card-header">
          <span class="stat-card-label">Savings This Month</span>
          <div class="stat-card-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="12" y1="1" x2="12" y2="23"/>
              <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>
            </svg>
          </div>
        </div>
        <div class="stat-card-value" id="stat-val-savings">${formatCurrency(savingsThisMonth)}</div>
        <div class="stat-card-sub">
          <span class="stat-pill success">${savingsSubText}</span>
        </div>
      </div>
    `;

    // Card 4: Potential Savings
    html += `
      <div class="stat-card">
        <div class="stat-card-header">
          <span class="stat-card-label">Potential Savings</span>
          <div class="stat-card-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
            </svg>
          </div>
        </div>
        <div class="stat-card-value" id="stat-val-potential">${formatCurrency(potentialSavings)}</div>
        <div class="stat-card-sub">
          <span class="stat-pill neutral">${potentialSub}</span>
        </div>
      </div>
    `;

    html += '</div>'; // close stat-cards-row

    // 3. Financial Health Score Card
    if (healthScore && typeof healthScore.score === 'number') {
      const tierClass = healthScore.tier === 'Excellent' ? 'excellent' : (healthScore.tier === 'Good' ? 'good' : (healthScore.tier === 'Fair' ? 'fair' : 'attention'));
      const partialBadge = healthScore.is_partial ? '<span class="partial-score-badge">Partial</span>' : '';

      let factorsHtml = '';
      (healthScore.factors || []).forEach((f) => {
        const factorPct = Math.max(5, Math.min(100, f.score));
        factorsHtml += `
          <div class="health-factor-item">
            <div class="health-factor-top">
              <span class="health-factor-name">${escapeHtml(f.name)}</span>
              <span class="health-factor-metric">${escapeHtml(f.raw_metric || '')} <strong class="health-factor-score">${f.score}/100</strong></span>
            </div>
            <div class="health-factor-bar-bg">
              <div class="health-factor-bar-fill ${tierClass}" style="width: ${factorPct}%;"></div>
            </div>
            <div class="health-factor-desc">${escapeHtml(f.description || '')}</div>
          </div>
        `;
      });

      const topTip = (healthScore.tips && healthScore.tips.length > 0) ? healthScore.tips[0] : '';

      html += `
        <div class="health-score-card">
          <div class="health-score-header">
            <div class="health-score-left">
              <div class="health-score-gauge-wrap">
                <div class="health-score-number">${healthScore.score}</div>
                <div class="health-score-max">/100</div>
              </div>
              <div class="health-score-meta">
                <div class="health-tier-badge ${tierClass}">${escapeHtml(healthScore.tier)} ${partialBadge}</div>
                <h3>Financial Health Score</h3>
                <p>Deterministic composite based on your savings, budget adherence, and logging habits</p>
              </div>
            </div>
          </div>
          <div class="health-factors-grid">
            ${factorsHtml}
          </div>
          ${topTip ? `
            <div class="health-score-tip">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:16px;height:16px;flex-shrink:0;">
                <circle cx="12" cy="12" r="10"/>
                <line x1="12" y1="16" x2="12" y2="12"/>
                <line x1="12" y1="8" x2="12.01" y2="8"/>
              </svg>
              <span>${escapeHtml(topTip)}</span>
            </div>
          ` : ''}
        </div>
      `;
    }

    // 4. AI Insight Callout Card
    html += `
      <div class="insight-callout-card">
        <div class="insight-callout-left">
          <div class="insight-pill">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10"/>
              <line x1="12" y1="16" x2="12" y2="12"/>
              <line x1="12" y1="8" x2="12.01" y2="8"/>
            </svg>
            AI Financial Insight
          </div>
          <div class="insight-callout-title">${escapeHtml(insightTitle)}</div>
          <div class="insight-callout-body">${escapeHtml(insightText)}</div>
        </div>
        <button class="insight-action-btn" id="insight-action-btn" data-prompt="${escapeHtml(insightPrompt)}">
          Ask ABT
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="9 18 15 12 9 6"/>
          </svg>
        </button>
      </div>
    `;

    // 5. Charts Row: Spending Trend & Category Donut
    html += '<div class="charts-row">';

    // Left Chart: Spending Trend
    html += `
      <div class="chart-card">
        <div class="chart-header">
          <div class="chart-title-wrap">
            <h3>Spending Trend</h3>
            <span>Daily expenses over the last 7 days</span>
          </div>
        </div>
        <div class="chart-body">
          ${renderTrendLineChart(dailySpend.slice(-7))}
        </div>
      </div>
    `;

    // Right Chart: Category Breakdown Donut Chart
    html += `
      <div class="chart-card">
        <div class="chart-header">
          <div class="chart-title-wrap">
            <h3>Category Breakdown</h3>
            <span>Distribution across budgets</span>
          </div>
        </div>
        <div class="chart-body">
          ${renderDonutChart(categoryBreakdown, totalSpent)}
        </div>
      </div>
    `;

    html += '</div>'; // close charts-row

    // 6. Budgets & Rollovers Section
    if (categoryBreakdown.length > 0) {
      html += `
        <div class="budgets-rollover-card">
          <div class="chart-header" style="margin-bottom: 12px;">
            <div class="chart-title-wrap">
              <h3>Category Budgets & Rollovers</h3>
              <span>Toggle rollover to carry unspent amounts into next month</span>
            </div>
          </div>
          <div class="budgets-rollover-list">
      `;

      categoryBreakdown.forEach((c) => {
        const spent = c.total;
        const effBudget = c.budget;
        const carried = c.carried_amount || 0;
        const isRollover = c.rollover_enabled;
        const rem = effBudget > 0 ? effBudget - spent : 0;
        const remText = effBudget > 0 ? (rem >= 0 ? `${formatCurrency(rem)} left` : `${formatCurrency(Math.abs(rem))} over`) : 'No limit';
        const remColor = effBudget > 0 && rem < 0 ? '#F87171' : 'var(--text-secondary)';

        html += `
          <div class="category-budget-row">
            <div class="cat-b-name-wrap">
              <span class="cat-b-name">${escapeHtml(c.category)}</span>
              ${carried > 0 ? `<span class="rollover-indicator-pill">+${formatCurrency(carried)} rolled over from last month</span>` : ''}
            </div>
            <div class="cat-b-amounts">
              <div>
                <span class="cat-b-spent">${formatCurrency(spent)}</span>
                <span class="cat-b-limit"> / ${effBudget > 0 ? formatCurrency(effBudget) : 'No limit'}</span>
                <div style="font-size:0.75rem; color:${remColor}; text-align:right;">${remText}</div>
              </div>
              <label class="rollover-switch-label" title="Roll over unspent budget to next month">
                <input type="checkbox" class="rollover-toggle-cb" data-category="${escapeHtml(c.category)}" ${isRollover ? 'checked' : ''}>
                <span class="rollover-slider"></span>
                <span class="rollover-switch-text">${isRollover ? 'Rollover' : 'Off'}</span>
              </label>
            </div>
          </div>
        `;
      });

      html += '</div></div>'; // close budgets-rollover-card
    }

    // 7. Recurring Bills & Subscriptions Section
    const recurringList = (recurringData && recurringData.recurring) || [];
    html += `
      <div class="dashboard-recurring-card" id="recurring-bills-section">
        <div class="chart-header">
          <div class="chart-title-wrap">
            <h3>Recurring Bills & Subscriptions</h3>
            <span>Fixed payments with automatic due date tracking</span>
          </div>
          <button class="btn-secondary" id="btn-add-recurring-trigger" style="display:inline-flex;align-items:center;gap:6px;font-size:var(--font-size-xs);padding:6px 12px;">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:14px;height:14px;">
              <line x1="12" y1="5" x2="12" y2="19"/>
              <line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            Add Bill
          </button>
        </div>
        <div class="recurring-list-wrap">
    `;

    if (recurringList.length > 0) {
      html += '<div class="recurring-items-grid">';
      recurringList.forEach((r) => {
        const isInactive = !r.active;
        html += `
          <div class="recurring-item ${isInactive ? 'inactive' : ''}">
            <div class="rec-info">
              <div class="rec-name-row">
                <strong class="rec-name">${escapeHtml(r.name)}</strong>
                <span class="rec-freq-pill">${escapeHtml(r.frequency)}</span>
              </div>
              <div class="rec-due-row">
                <span class="rec-due-date">Due: ${formatDate(r.next_due_date)}</span>
                ${r.active ? '<span class="rec-active-pill">Active</span>' : '<span class="rec-inactive-pill">Paused</span>'}
              </div>
            </div>
            <div class="rec-amount-action">
              <div class="rec-amount">${formatCurrency(r.amount)}</div>
              ${r.active ? `<button class="btn-deactivate-rec" data-rec-id="${r.id}">Deactivate</button>` : ''}
            </div>
          </div>
        `;
      });
      html += '</div>';
    } else {
      html += `
        <div class="empty-state" style="padding: 24px 0;">
          <p>No recurring bills tracked. Add rent, electricity, or subscriptions to receive automated bill reminders.</p>
        </div>
      `;
    }
    html += '</div></div>'; // close recurring card

    // 8. Recent Transactions Section
    html += `
      <div class="dashboard-txn-card">
        <div class="chart-header" style="margin-bottom: 0;">
          <div class="chart-title-wrap">
            <h3>Recent Transactions</h3>
            <span>Latest activity this month</span>
          </div>
        </div>
        <div class="txn-table-wrap">
    `;

    if (recentTxns.length > 0) {
      html += '<table class="txn-table"><thead><tr>';
      html += '<th>Date</th><th>Category</th><th>Note / Description</th><th style="text-align:right;">Amount</th>';
      html += '</tr></thead><tbody>';
      recentTxns.forEach((t) => {
        html += `<tr>
          <td class="txn-date">${formatDate(t.date)}</td>
          <td><span class="txn-category">${escapeHtml(t.category)}</span></td>
          <td style="color:var(--text-secondary);">${escapeHtml(t.note || 'Expense')}</td>
          <td class="txn-amount">${formatCurrency(t.amount)}</td>
        </tr>`;
      });
      html += '</tbody></table>';
    } else {
      html += `
        <div class="empty-state" style="padding: 36px 0;">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:36px;height:36px;opacity:0.25;margin-bottom:8px;">
            <rect x="2" y="4" width="20" height="16" rx="2"/>
            <line x1="6" y1="12" x2="18" y2="12"/>
          </svg>
          <p>No transactions recorded this month. Message ABT in chat to log an expense.</p>
        </div>
      `;
    }

    html += '</div></div>'; // close txn-table-wrap & dashboard-txn-card

    dashboardContent.innerHTML = html;
    dashboardContent.style.display = '';

    // Animate stat numbers smoothly
    animateNumber($('#stat-val-spent'), totalSpent, formatCurrency);
    animateNumber($('#stat-val-budget'), budgetRemaining, formatCurrency);
    animateNumber($('#stat-val-savings'), savingsThisMonth, formatCurrency);
    animateNumber($('#stat-val-potential'), potentialSavings, formatCurrency);

    // Wire up AI Insight action button
    const insightBtn = $('#insight-action-btn');
    if (insightBtn) {
      insightBtn.addEventListener('click', () => {
        const prompt = insightBtn.getAttribute('data-prompt');
        if (prompt && composerInput) {
          composerInput.value = prompt;
          switchView('chat');
          composerInput.focus();
        }
      });
    }

    // Wire up Export button
    const exportBtn = $('#btn-open-export');
    if (exportBtn) {
      exportBtn.addEventListener('click', () => {
        const modal = $('#modal-export');
        if (modal) {
          const monthInput = $('#export-month');
          if (monthInput && !monthInput.value) {
            monthInput.value = new Date().toISOString().slice(0, 7);
          }
          modal.style.display = 'flex';
        }
      });
    }

    // Wire up View Bills button on banner
    const viewBillsBtn = $('#banner-view-bills-btn');
    if (viewBillsBtn) {
      viewBillsBtn.addEventListener('click', () => {
        const sec = document.getElementById('recurring-bills-section');
        if (sec) sec.scrollIntoView({ behavior: 'smooth' });
      });
    }

    // Wire up Add Recurring Bill button
    const addRecBtn = $('#btn-add-recurring-trigger');
    if (addRecBtn) {
      addRecBtn.addEventListener('click', () => {
        const modal = $('#modal-recurring');
        if (modal) {
          const dInput = $('#rec-date');
          if (dInput && !dInput.value) {
            dInput.value = new Date().toISOString().slice(0, 10);
          }
          modal.style.display = 'flex';
        }
      });
    }

    // Wire up Deactivate Recurring Bill buttons
    $$('.btn-deactivate-rec').forEach((btn) => {
      btn.addEventListener('click', async (e) => {
        const id = e.target.getAttribute('data-rec-id');
        if (!id) return;
        try {
          await api(`/api/recurring/${id}/deactivate`, { method: 'POST' });
          showToast('Recurring bill deactivated', 'success');
          loadDashboard();
        } catch (err) {
          showToast(err.message || 'Failed to deactivate bill', 'error');
        }
      });
    });

    // Wire up Rollover toggles
    $$('.rollover-toggle-cb').forEach((cb) => {
      cb.addEventListener('change', async (e) => {
        const cat = e.target.getAttribute('data-category');
        const enabled = e.target.checked;
        const textSpan = e.target.parentElement.querySelector('.rollover-switch-text');
        if (textSpan) {
          textSpan.textContent = enabled ? 'Rollover' : 'Off';
        }
        try {
          await api('/api/budgets/rollover/toggle', {
            method: 'POST',
            body: JSON.stringify({ category: cat, enabled }),
          });
          showToast(`Budget rollover for ${cat} ${enabled ? 'enabled' : 'disabled'}`, 'success');
        } catch (err) {
          e.target.checked = !enabled;
          if (textSpan) textSpan.textContent = !enabled ? 'Rollover' : 'Off';
          showToast(err.message || 'Failed to update rollover', 'error');
        }
      });
    });
  }

  // SVG Donut Chart Renderer
  function renderDonutChart(data, totalSpent) {
    if (!data || data.length === 0 || totalSpent <= 0) {
      return `
        <div class="empty-state" style="padding: 32px 0;">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:36px;height:36px;opacity:0.25;margin-bottom:8px;">
            <circle cx="12" cy="12" r="10"/>
            <path d="M12 6v6l4 2"/>
          </svg>
          <p>No category spending recorded yet.</p>
        </div>
      `;
    }

    const colors = [
      '#10B981', '#38BDF8', '#818CF8', '#F59E0B', '#EC4899',
      '#64748B', '#14B8A6', '#A855F7', '#F97316', '#06B6D4'
    ];

    const size = 180;
    const center = size / 2; // 90
    const radius = 62;
    const circumference = 2 * Math.PI * radius; // ~389.55

    let currentOffset = 0;
    let circlesHtml = '';
    let legendHtml = '<div class="donut-legend">';

    data.forEach((cat, idx) => {
      const color = colors[idx % colors.length];
      const pct = (cat.total / totalSpent) * 100;
      const dashLength = (cat.total / totalSpent) * circumference;
      const dashSpace = circumference - dashLength;

      circlesHtml += `
        <circle class="donut-segment"
          cx="${center}" cy="${center}" r="${radius}"
          stroke="${color}"
          stroke-dasharray="${dashLength.toFixed(2)} ${dashSpace.toFixed(2)}"
          stroke-dashoffset="${(-currentOffset).toFixed(2)}"
        ><title>${escapeHtml(cat.category)}: ${formatCurrency(cat.total)} (${pct.toFixed(0)}%)</title></circle>
      `;

      currentOffset += dashLength;

      legendHtml += `
        <div class="donut-legend-item">
          <div class="donut-legend-left">
            <div class="donut-legend-dot" style="background:${color};"></div>
            <span class="donut-legend-name" title="${escapeHtml(cat.category)}">${escapeHtml(cat.category)}</span>
          </div>
          <span class="donut-legend-amount">${pct.toFixed(0)}%</span>
        </div>
      `;
    });

    legendHtml += '</div>';

    return `
      <div class="donut-chart-wrap">
        <svg class="donut-svg" viewBox="0 0 ${size} ${size}">
          <circle class="donut-circle-bg" cx="${center}" cy="${center}" r="${radius}"></circle>
          ${circlesHtml}
          <g class="donut-center-group" style="transform: rotate(90deg); transform-origin: ${center}px ${center}px;">
            <text class="donut-center-label" x="${center}" y="${center - 6}" text-anchor="middle">TOTAL SPENT</text>
            <text class="donut-center-value" x="${center}" y="${center + 14}" text-anchor="middle">${formatCurrency(totalSpent)}</text>
          </g>
        </svg>
        ${legendHtml}
      </div>
    `;
  }

  // SVG Trend Line Chart Renderer
  function renderTrendLineChart(data) {
    if (!data || data.length === 0) {
      return `
        <div class="empty-state" style="padding: 32px 0;">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:36px;height:36px;opacity:0.25;margin-bottom:8px;">
            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
          </svg>
          <p>No daily expense data yet for this period.</p>
        </div>
      `;
    }

    // Generate last 7 days series so the 7-day trend chart shows a complete, smooth curve
    const last7Days = [];
    const today = new Date();
    for (let offset = 6; offset >= 0; offset--) {
      const d = new Date(today);
      d.setDate(d.getDate() - offset);
      const iso = d.toISOString().split('T')[0];
      const matched = data.find((item) => (item.date || item.day) === iso);
      last7Days.push({
        date: iso,
        total: matched ? (matched.total || matched.amount || 0) : 0,
      });
    }
    const chartData = last7Days;

    const w = 480, h = 180, padL = 40, padR = 16, padT = 20, padB = 30;
    const chartW = w - padL - padR;
    const chartH = h - padT - padB;

    const maxVal = Math.max(...chartData.map((d) => d.total || d.amount || 0), 100);
    const stepX = chartData.length > 1 ? chartW / (chartData.length - 1) : chartW / 2;

    let points = '';
    let areaPoints = '';
    let pointsHtml = '';

    chartData.forEach((d, i) => {
      const val = d.total || d.amount || 0;
      const x = padL + (chartData.length > 1 ? i * stepX : chartW / 2);
      const y = padT + chartH - (val / maxVal) * chartH;

      if (i === 0) {
        points += `M${x.toFixed(1)},${y.toFixed(1)}`;
        areaPoints += `M${x.toFixed(1)},${(padT + chartH).toFixed(1)} L${x.toFixed(1)},${y.toFixed(1)}`;
      } else {
        points += ` L${x.toFixed(1)},${y.toFixed(1)}`;
        areaPoints += ` L${x.toFixed(1)},${y.toFixed(1)}`;
      }

      const dateStr = d.date ? formatDate(d.date) : `Day ${i + 1}`;
      pointsHtml += `
        <circle class="trend-point" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="4">
          <title>${dateStr}: ${formatCurrency(val)}</title>
        </circle>
        <text class="trend-axis-text" x="${x.toFixed(1)}" y="${h - 8}" font-size="10" text-anchor="middle" font-family="Inter,sans-serif">${dateStr}</text>
      `;
    });

    const lastX = padL + (chartData.length > 1 ? (chartData.length - 1) * stepX : chartW / 2);
    areaPoints += ` L${lastX.toFixed(1)},${(padT + chartH).toFixed(1)} Z`;

    // Grid lines
    let gridHtml = '';
    for (let i = 0; i <= 3; i++) {
      const y = padT + (chartH * i) / 3;
      const gridVal = Math.round(maxVal - (maxVal * i) / 3);
      gridHtml += `
        <line class="trend-grid-line" x1="${padL}" y1="${y}" x2="${w - padR}" y2="${y}" stroke-width="1" stroke-dasharray="3 3"/>
        <text class="trend-axis-text" x="${padL - 8}" y="${y + 3}" font-size="9" text-anchor="end" font-family="Inter,sans-serif">${Math.round(gridVal)}</text>
      `;
    }

    return `
      <svg class="trend-svg" viewBox="0 0 ${w} ${h}" preserveAspectRatio="xMidYMid meet">
        <defs>
          <linearGradient id="trend-area-grad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#10B981" stop-opacity="0.18" />
            <stop offset="100%" stop-color="#10B981" stop-opacity="0.0" />
          </linearGradient>
        </defs>
        ${gridHtml}
        <path d="${areaPoints}" fill="url(#trend-area-grad)" />
        <path class="chart-trend-line" d="${points}" />
        ${pointsHtml}
      </svg>
    `;
  }

  // ---------- Udhar ----------

  async function loadUdhar() {
    udharLoader.style.display = '';
    udharContent.style.display = 'none';

    try {
      const data = await api('/api/udhar');
      renderUdhar(data);
    } catch (err) {
      udharContent.innerHTML =
        '<div class="empty-state"><p>Could not load udhar data.</p></div>';
      udharContent.style.display = '';
    } finally {
      udharLoader.style.display = 'none';
    }
  }

  function renderUdhar(data) {
    const totalLent = data.total_lent || 0;
    const totalBorrowed = data.total_borrowed || 0;
    const net = typeof data.net === 'number' ? data.net : (totalLent - totalBorrowed);
    const persons = data.persons || data.people || [];

    let html = '';

    // Summary cards
    html += '<div class="udhar-summary-cards">';
    html += `<div class="udhar-card">
      <div class="card-label">Total Lent</div>
      <div class="card-value lent-color">${formatCurrency(totalLent)}</div>
      <div style="font-size:0.72rem;color:var(--text-tertiary);margin-top:2px;">Friends owe you</div>
    </div>`;
    html += `<div class="udhar-card">
      <div class="card-label">Total Borrowed</div>
      <div class="card-value borrowed-color">${formatCurrency(totalBorrowed)}</div>
      <div style="font-size:0.72rem;color:var(--text-tertiary);margin-top:2px;">You owe friends</div>
    </div>`;
    html += `<div class="udhar-card">
      <div class="card-label">Net Balance</div>
      <div class="card-value ${net > 0 ? 'lent-color' : (net < 0 ? 'borrowed-color' : '')}">${formatCurrency(net)}</div>
      <div style="font-size:0.72rem;color:var(--text-tertiary);margin-top:2px;">${net > 0 ? 'Net receivable' : (net < 0 ? 'Net payable' : 'All clear')}</div>
    </div>`;
    html += '</div>';

    // People list
    if (persons.length > 0) {
      html += '<div class="udhar-people-list">';
      persons.forEach((p) => {
        const name = p.name || p.person_name || 'Friend';
        const pNet = typeof p.net === 'number' ? p.net : ((p.kind === 'lent' ? 1 : -1) * (p.amount || 0));
        const hasSplit = p.is_split || (p.history && p.history.some((h) => h.is_split));

        let statusText = 'Settled up';
        let colorClass = '';
        if (pNet > 0) {
          statusText = `Owes you ${formatCurrency(pNet)}`;
          colorClass = 'lent-color';
        } else if (pNet < 0) {
          statusText = `You owe ${formatCurrency(Math.abs(pNet))}`;
          colorClass = 'borrowed-color';
        }

        let detailLine = '';
        if (p.history && p.history.length > 0) {
          const lastEntry = p.history[p.history.length - 1];
          const dateStr = lastEntry.entry_date ? formatDate(lastEntry.entry_date) : '';
          const noteStr = lastEntry.note ? escapeHtml(lastEntry.note) : (lastEntry.kind === 'lent' ? 'Lent' : 'Borrowed');
          detailLine = dateStr ? `${noteStr} · ${dateStr}` : noteStr;
        } else if (p.note) {
          detailLine = escapeHtml(p.note);
        }

        html += `<div class="udhar-person">
          <div class="udhar-person-info">
            <div class="udhar-name-row">
              <span class="udhar-person-name">${escapeHtml(name)}</span>
              ${hasSplit ? '<span class="split-badge">Split</span>' : ''}
            </div>
            <span class="udhar-person-detail">${detailLine || statusText}</span>
          </div>
          <div style="text-align:right;">
            <span class="udhar-person-amount ${colorClass}">${formatCurrency(Math.abs(pNet))}</span>
            <div style="font-size:0.72rem;color:var(--text-tertiary);">${pNet > 0 ? 'Owes you' : (pNet < 0 ? 'You owe' : 'Settled')}</div>
          </div>
        </div>`;
      });
      html += '</div>';
    } else {
      html += '<div class="empty-state"><p>No shared balances or debts yet. Ask ABT in chat about money you lent or borrowed, or tap "Split Expense".</p></div>';
    }

    udharContent.innerHTML = html;
    udharContent.style.display = '';
  }

  // ---------- Insights ----------

  async function loadInsights() {
    insightsLoader.style.display = '';
    insightsContent.style.display = 'none';

    try {
      const [insightsData, recapData] = await Promise.all([
        api('/api/insights').catch(() => ({ insights: [] })),
        api('/api/recap').catch(() => null),
      ]);

      renderInsights(insightsData.insights || [], recapData);
    } catch (err) {
      insightsContent.innerHTML =
        '<div class="empty-state"><p>Could not load insights.</p></div>';
      insightsContent.style.display = '';
    } finally {
      insightsLoader.style.display = 'none';
    }
  }

  function renderInsights(insights, recap) {
    let html = '';

    // Weekly recap card
    if (recap) {
      let topCat = '--';
      if (recap.top_category) {
        if (typeof recap.top_category === 'string') {
          topCat = recap.top_category;
        } else if (recap.top_category.category) {
          const catName = recap.top_category.category.charAt(0).toUpperCase() + recap.top_category.category.slice(1);
          topCat = recap.top_category.total ? `${catName} (${formatCurrency(recap.top_category.total)})` : catName;
        }
      }
      html += '<div class="recap-card"><h3>Weekly Recap</h3>';
      html += '<div class="recap-stats">';
      html += recapStatHTML('Spent (7d)', formatCurrency(recap.total_spent));
      html += recapStatHTML('Income (7d)', formatCurrency(recap.week_income));
      html += recapStatHTML('Top Category', topCat);
      html += recapStatHTML('Streak', (recap.logging_streak || 0) + ' days');
      html += '</div>';
      if (recap.narration) {
        html += `<p class="recap-narration" style="margin-top: 14px; font-size: var(--font-size-sm); color: var(--text-secondary); line-height: 1.5;">${escapeHtml(recap.narration)}</p>`;
      }
      html += '</div>';
    }

    // Insight cards
    if (insights.length > 0) {
      html += '<div class="insight-cards">';
      insights.forEach((ins) => {
        html += `<div class="insight-card">
          <div class="insight-title">${escapeHtml(ins.title || 'Insight')}</div>
          <div class="insight-body">${escapeHtml(ins.body || ins.text || '')}</div>
        </div>`;
      });
      html += '</div>';
    } else if (!recap) {
      html += '<div class="empty-state"><p>Not enough data for insights yet. Keep logging your expenses.</p></div>';
    }

    insightsContent.innerHTML = html;
    insightsContent.style.display = '';
  }

  function recapStatHTML(label, value) {
    return `<div class="recap-stat">
      <label>${escapeHtml(label)}</label>
      <span class="value">${escapeHtml(String(value))}</span>
    </div>`;
  }

  // ---------- Onboarding Wizard ----------

  const ONBOARDING_CATEGORIES = [
    { key: 'rent', label: 'Rent', group: 'needs' },
    { key: 'groceries', label: 'Groceries / daily needs', group: 'needs' },
    { key: 'eating out', label: 'Eating out / food delivery', group: 'wants' },
    { key: 'travel', label: 'Travel / commute', group: 'wants' },
    { key: 'utilities', label: 'Utilities (bills, wifi, recharge)', group: 'needs' },
    { key: 'personal care', label: 'Personal care', group: 'wants' },
    { key: 'entertainment', label: 'Entertainment / subscriptions', group: 'wants' },
    { key: 'shopping', label: 'Shopping', group: 'wants' },
    { key: 'health', label: 'Health / medical', group: 'needs' },
    { key: 'emergency fund', label: 'Emergency fund (savings)', group: 'savings' },
    { key: 'sip / investments', label: 'SIP / investments (savings)', group: 'savings' },
    { key: 'miscellaneous', label: 'Miscellaneous', group: 'wants' },
  ];

  function showOnboarding(startStep = 1) {
    authScreen.style.display = 'none';
    appScreen.classList.remove('active');
    onboardingScreen.style.display = 'flex';

    // Match radio selection with current living situation
    const currentRadio = $(`input[name="living"][value="${obLiving}"]`);
    if (currentRadio) {
      currentRadio.checked = true;
    } else {
      const defaultRadio = $('input[name="living"][value="alone"]');
      if (defaultRadio) {
        defaultRadio.checked = true;
        obLiving = 'alone';
      }
    }

    goToStep(startStep);
  }

  function hideOnboarding() {
    onboardingScreen.style.display = 'none';
  }

  async function goToStep(step) {
    currentObStep = step;

    // Progress label
    if (obStepLabel) obStepLabel.textContent = `Step ${step} of 4`;

    // Progress step circles
    $$('.progress-step').forEach((el) => {
      const s = parseInt(el.getAttribute('data-step'), 10);
      el.classList.remove('active', 'completed');
      if (s === step) el.classList.add('active');
      else if (s < step) el.classList.add('completed');
    });

    // Progress lines
    $$('.progress-line').forEach((el, idx) => {
      if (idx + 1 < step) el.classList.add('completed');
      else el.classList.remove('completed');
    });

    // Step views
    $$('.onboarding-step').forEach((el) => el.classList.remove('active'));
    const activeStepEl = $(`#ob-step-${step}`);
    if (activeStepEl) activeStepEl.classList.add('active');

    // Navigation buttons state
    if (obBackBtn) obBackBtn.style.visibility = step === 1 ? 'hidden' : 'visible';
    if (obNextBtn) {
      obNextBtn.textContent = step === 4 ? 'Save my budgets' : 'Next';
      obNextBtn.disabled = false;
    }

    if (step === 3) {
      await loadCategoryDefaults();
    } else if (step === 4) {
      renderReviewStep();
    }
  }

  async function loadCategoryDefaults() {
    if (obDefaultsFetched && obLastFetchedSituation === obLiving && obLastFetchedIncome === obIncome) {
      return;
    }

    try {
      let url = `/api/onboarding/defaults?living_situation=${encodeURIComponent(obLiving || 'alone')}`;
      if (obIncome && obIncome > 0) {
        url += `&income=${encodeURIComponent(obIncome)}`;
      }
      const data = await api(url);
      const defaults = data.defaults || {};

      obDefaultsFetched = true;
      obLastFetchedSituation = obLiving;
      obLastFetchedIncome = obIncome;

      ONBOARDING_CATEGORIES.forEach((cat) => {
        const isFamilyRent = (obLiving === 'family' && cat.key === 'rent');
        const defaultAmount = defaults[cat.key] != null ? defaults[cat.key] : 0;
        const existing = obCategoryState[cat.key];
        obCategoryState[cat.key] = {
          enabled: isFamilyRent ? false : (existing != null ? existing.enabled : true),
          amount: existing != null ? existing.amount : defaultAmount,
        };
      });

      renderCategoriesList();
    } catch (err) {
      console.error('Failed to load defaults:', err);
      showToast('Failed to load suggested budgets', 'error');
    }
  }

  function renderCategoriesList() {
    let html = '';
    ONBOARDING_CATEGORIES.forEach((cat) => {
      const isFamilyRent = (obLiving === 'family' && cat.key === 'rent');
      const st = obCategoryState[cat.key] || { enabled: true, amount: 0 };
      html += `
        <div class="ob-cat-row ${st.enabled ? '' : 'disabled'}" data-key="${escapeHtml(cat.key)}" style="${isFamilyRent ? 'display:none;' : ''}">
          <div class="ob-cat-left">
            <label class="ob-switch">
              <input type="checkbox" class="ob-cat-toggle" data-key="${escapeHtml(cat.key)}" ${st.enabled ? 'checked' : ''}>
              <span class="ob-slider"></span>
            </label>
            <span class="ob-cat-name">${escapeHtml(cat.label)}</span>
          </div>
          <div class="ob-cat-right">
            <div class="ob-cat-input-wrap">
              <span>Rs</span>
              <input type="number" class="ob-cat-input" data-key="${escapeHtml(cat.key)}" value="${st.amount}" min="0" step="100">
            </div>
          </div>
        </div>
      `;
    });
    obCategoriesContainer.innerHTML = html;

    obCategoriesContainer.querySelectorAll('.ob-cat-toggle').forEach((toggle) => {
      toggle.addEventListener('change', (e) => {
        const key = e.target.getAttribute('data-key');
        const row = e.target.closest('.ob-cat-row');
        if (obCategoryState[key]) {
          obCategoryState[key].enabled = e.target.checked;
        }
        if (row) {
          row.classList.toggle('disabled', !e.target.checked);
        }
        updateTotalBar();
      });
    });

    obCategoriesContainer.querySelectorAll('.ob-cat-input').forEach((input) => {
      input.addEventListener('input', (e) => {
        const key = e.target.getAttribute('data-key');
        const val = parseFloat(e.target.value);
        if (obCategoryState[key]) {
          obCategoryState[key].amount = (!isNaN(val) && val >= 0) ? val : 0;
        }
        updateTotalBar();
      });
    });

    updateTotalBar();
  }

  function updateTotalBar() {
    let total = 0;
    let savingsTotal = 0;
    ONBOARDING_CATEGORIES.forEach((cat) => {
      const isFamilyRent = (obLiving === 'family' && cat.key === 'rent');
      if (isFamilyRent) return;
      const st = obCategoryState[cat.key];
      if (st && st.enabled) {
        total += st.amount;
        if (cat.group === 'savings') {
          savingsTotal += st.amount;
        }
      }
    });

    obTotalAmount.textContent = formatCurrency(total);

    if (obIncome && obIncome > 0) {
      const leftover = obIncome - total;
      const savingsRate = Math.round((savingsTotal / obIncome) * 100);
      if (leftover >= 0) {
        obRemaining.className = 'ob-remaining surplus';
        obRemaining.textContent = `Leftover: ${formatCurrency(leftover)} (${savingsRate}% savings)`;
      } else {
        obRemaining.className = 'ob-remaining deficit';
        obRemaining.textContent = `Over budget by ${formatCurrency(Math.abs(leftover))}`;
      }
    } else {
      const activeCount = Object.values(obCategoryState).filter((s) => s.enabled).length;
      obRemaining.className = 'ob-remaining neutral';
      obRemaining.textContent = `${activeCount} categories active`;
    }
  }

  function renderReviewStep() {
    let total = 0;
    let needsTotal = 0;
    let wantsTotal = 0;
    let savingsTotal = 0;
    let listHtml = '';

    ONBOARDING_CATEGORIES.forEach((cat) => {
      const isFamilyRent = (obLiving === 'family' && cat.key === 'rent');
      if (isFamilyRent) return;
      const st = obCategoryState[cat.key];
      if (st && st.enabled && st.amount > 0) {
        total += st.amount;
        if (cat.group === 'needs') needsTotal += st.amount;
        else if (cat.group === 'wants') wantsTotal += st.amount;
        else if (cat.group === 'savings') savingsTotal += st.amount;

        listHtml += `
          <div class="ob-review-row">
            <span class="name">${escapeHtml(cat.label)}</span>
            <span class="val">${formatCurrency(st.amount)}</span>
          </div>
        `;
      }
    });

    if (!listHtml) {
      listHtml = '<div style="padding: 12px; color: var(--text-tertiary); text-align: center;">No categories enabled.</div>';
    }
    obReviewList.innerHTML = listHtml;

    let summaryHtml = `
      <div class="ob-summary-metric">
        <span class="label">Total Monthly Budget</span>
        <span class="val">${formatCurrency(total)}</span>
      </div>
    `;

    if (obIncome && obIncome > 0) {
      const leftover = obIncome - total;
      const savingsRate = Math.round((savingsTotal / obIncome) * 100);
      summaryHtml += `
        <div class="ob-summary-metric">
          <span class="label">Monthly Income</span>
          <span class="val">${formatCurrency(obIncome)}</span>
        </div>
        <div class="ob-summary-metric">
          <span class="label">Implied Savings Rate</span>
          <span class="val" style="color: ${savingsRate >= 20 ? 'var(--success)' : 'var(--text-primary)'};">${savingsRate}%</span>
        </div>
        <div class="ob-summary-metric">
          <span class="label">Leftover / Surplus</span>
          <span class="val" style="color: ${leftover >= 0 ? 'var(--success)' : 'var(--danger)'};">${formatCurrency(leftover)}</span>
        </div>
      `;
    }

    summaryHtml += `
      <div class="ob-summary-divider"></div>
      <div class="ob-summary-breakdown">
        <div class="ob-breakdown-box">
          <div class="box-label">Needs</div>
          <div class="box-val">${formatCurrency(needsTotal)}</div>
        </div>
        <div class="ob-breakdown-box">
          <div class="box-label">Wants</div>
          <div class="box-val">${formatCurrency(wantsTotal)}</div>
        </div>
        <div class="ob-breakdown-box">
          <div class="box-label">Savings</div>
          <div class="box-val">${formatCurrency(savingsTotal)}</div>
        </div>
      </div>
    `;

    obReviewSummary.innerHTML = summaryHtml;
  }

  async function saveOnboardingBudgets() {
    obNextBtn.disabled = true;
    obNextBtn.textContent = 'Saving...';
    try {
      const categoriesPayload = ONBOARDING_CATEGORIES.map((cat) => {
        const isFamilyRent = (obLiving === 'family' && cat.key === 'rent');
        const st = obCategoryState[cat.key] || { enabled: false, amount: 0 };
        return {
          name: cat.key,
          amount: isFamilyRent ? 0 : st.amount,
          enabled: isFamilyRent ? false : (st.enabled && st.amount > 0),
        };
      });

      await api('/api/onboarding/complete', {
        method: 'POST',
        body: JSON.stringify({
          living_situation: obLiving || 'alone',
          monthly_income: obIncome || null,
          categories: categoriesPayload,
        }),
      });

      sessionStorage.removeItem('abt_onboarding_skipped');
      showToast('Budgets saved successfully! Welcome to ABT.', 'success');
      showApp();
    } catch (err) {
      showToast(err.message || 'Failed to save budgets', 'error');
    } finally {
      obNextBtn.disabled = false;
      obNextBtn.textContent = 'Save my budgets';
    }
  }

  // Onboarding listeners
  if (obNextBtn) {
    obNextBtn.addEventListener('click', async () => {
      if (currentObStep === 1) {
        const sel = $('input[name="living"]:checked');
        if (!sel) {
          showToast('Please select your living situation', 'error');
          return;
        }
        obLiving = sel.value;
        goToStep(2);
      } else if (currentObStep === 2) {
        const val = parseFloat(obIncomeInput.value);
        obIncome = (!isNaN(val) && val > 0) ? val : null;
        goToStep(3);
      } else if (currentObStep === 3) {
        goToStep(4);
      } else if (currentObStep === 4) {
        await saveOnboardingBudgets();
      }
    });
  }

  if (obBackBtn) {
    obBackBtn.addEventListener('click', () => {
      if (currentObStep > 1) {
        goToStep(currentObStep - 1);
      }
    });
  }

  if (obSkipBtn) {
    obSkipBtn.addEventListener('click', () => {
      sessionStorage.setItem('abt_onboarding_skipped', '1');
      showApp();
    });
  }

  if (redoOnboardingBtn) {
    redoOnboardingBtn.addEventListener('click', () => {
      closeSidebar();
      sessionStorage.removeItem('abt_onboarding_skipped');
      showOnboarding(1);
    });
  }

  $$('input[name="living"]').forEach((radio) => {
    radio.addEventListener('change', (e) => {
      obLiving = e.target.value;
      if (obLastFetchedSituation !== obLiving) {
        obDefaultsFetched = false;
      }
    });
  });

  if (obIncomeInput) {
    obIncomeInput.addEventListener('input', (e) => {
      const val = parseFloat(e.target.value);
      obIncome = (!isNaN(val) && val > 0) ? val : null;
      if (obLastFetchedIncome !== obIncome) {
        obDefaultsFetched = false;
      }
    });
  }

  // ---------- Modals & Tier 1 Feature Handlers ----------

  function openModal(id) {
    const m = $(id);
    if (m) m.style.display = 'flex';
  }

  function closeModal(id) {
    const m = $(id);
    if (m) m.style.display = 'none';
  }

  // Backdrop click & Escape key to close modals
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      $$('.modal-overlay').forEach((m) => {
        m.style.display = 'none';
      });
    }
  });

  $$('.modal-overlay').forEach((modal) => {
    modal.addEventListener('click', (e) => {
      if (e.target === modal) {
        modal.style.display = 'none';
      }
    });
  });

  // Export Modal Handlers
  const exportCloseBtn = $('#export-modal-close');
  const exportCancelBtn = $('#export-cancel-btn');
  const exportDownloadBtn = $('#export-download-btn');
  const optFmtPdf = $('#opt-fmt-pdf');
  const optFmtXlsx = $('#opt-fmt-xlsx');

  if (exportCloseBtn) exportCloseBtn.addEventListener('click', () => closeModal('#modal-export'));
  if (exportCancelBtn) exportCancelBtn.addEventListener('click', () => closeModal('#modal-export'));

  if (optFmtPdf) {
    optFmtPdf.addEventListener('click', () => {
      const radio = optFmtPdf.querySelector('input[type="radio"]');
      if (radio) radio.checked = true;
      optFmtPdf.classList.add('active');
      if (optFmtXlsx) optFmtXlsx.classList.remove('active');
    });
  }

  if (optFmtXlsx) {
    optFmtXlsx.addEventListener('click', () => {
      const radio = optFmtXlsx.querySelector('input[type="radio"]');
      if (radio) radio.checked = true;
      optFmtXlsx.classList.add('active');
      if (optFmtPdf) optFmtPdf.classList.remove('active');
    });
  }

  if (exportDownloadBtn) {
    exportDownloadBtn.addEventListener('click', async () => {
      const monthInput = $('#export-month');
      const month = monthInput?.value || new Date().toISOString().slice(0, 7);
      const fmtRadio = $('input[name="export_format"]:checked');
      const format = fmtRadio ? fmtRadio.value : 'pdf';

      exportDownloadBtn.disabled = true;
      const originalHtml = exportDownloadBtn.innerHTML;
      exportDownloadBtn.innerHTML = 'Generating...';

      try {
        const res = await fetch(`/api/export/monthly?month=${encodeURIComponent(month)}&format=${format}`, {
          headers: {
            'Authorization': 'Bearer ' + authToken,
          },
        });

        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          throw new Error(errData.detail || 'Failed to generate statement export');
        }

        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;
        const filename = format === 'xlsx' ? `statement_${month}.xlsx` : `statement_${month}.pdf`;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        a.remove();

        showToast(`Downloaded ${format.toUpperCase()} statement for ${month}`, 'success');
        closeModal('#modal-export');
      } catch (err) {
        showToast(err.message || 'Export download failed', 'error');
      } finally {
        exportDownloadBtn.disabled = false;
        exportDownloadBtn.innerHTML = originalHtml;
      }
    });
  }

  // Recurring Bill Modal Handlers
  const recCloseBtn = $('#recurring-modal-close');
  const recCancelBtn = $('#recurring-cancel-btn');
  const recSaveBtn = $('#recurring-save-btn');

  if (recCloseBtn) recCloseBtn.addEventListener('click', () => closeModal('#modal-recurring'));
  if (recCancelBtn) recCancelBtn.addEventListener('click', () => closeModal('#modal-recurring'));

  if (recSaveBtn) {
    recSaveBtn.addEventListener('click', async () => {
      const name = $('#rec-name')?.value?.trim();
      const amount = parseFloat($('#rec-amount')?.value);
      const frequency = $('#rec-frequency')?.value || 'monthly';
      const category = $('#rec-category')?.value || 'other';
      const startDate = $('#rec-date')?.value || null;

      if (!name) {
        showToast('Please enter a bill or subscription name', 'error');
        return;
      }
      if (isNaN(amount) || amount <= 0) {
        showToast('Please enter a valid amount', 'error');
        return;
      }

      recSaveBtn.disabled = true;
      recSaveBtn.textContent = 'Saving...';

      try {
        await api('/api/recurring', {
          method: 'POST',
          body: JSON.stringify({
            name,
            amount,
            category,
            frequency,
            start_date: startDate,
          }),
        });

        showToast(`Added recurring bill "${name}"`, 'success');
        closeModal('#modal-recurring');
        $('#rec-name').value = '';
        $('#rec-amount').value = '';
        loadDashboard();
      } catch (err) {
        showToast(err.message || 'Failed to save recurring bill', 'error');
      } finally {
        recSaveBtn.disabled = false;
        recSaveBtn.textContent = 'Save Recurring Bill';
      }
    });
  }

  // Split Expense Modal Handlers
  const splitTriggerBtn = $('#btn-split-trigger');
  const splitCloseBtn = $('#split-modal-close');
  const splitCancelBtn = $('#split-cancel-btn');
  const splitConfirmBtn = $('#split-confirm-btn');
  const splitAmtInput = $('#split-amount');
  const splitPartsInput = $('#split-participants');

  if (splitTriggerBtn) {
    splitTriggerBtn.addEventListener('click', () => {
      openModal('#modal-split');
      updateSplitPreview();
    });
  }

  if (splitCloseBtn) splitCloseBtn.addEventListener('click', () => closeModal('#modal-split'));
  if (splitCancelBtn) splitCancelBtn.addEventListener('click', () => closeModal('#modal-split'));

  function updateSplitPreview() {
    const amountVal = parseFloat($('#split-amount')?.value);
    const participantsVal = $('#split-participants')?.value || '';
    const names = participantsVal.split(',').map((s) => s.trim()).filter(Boolean);
    const previewBox = $('#split-calc-preview');
    const userShareEl = $('#preview-user-share');
    const friendsShareEl = $('#preview-friends-share');

    if (!isNaN(amountVal) && amountVal > 0 && names.length > 0) {
      const totalPeople = names.length + 1;
      const userShare = Math.round((amountVal / totalPeople) * 100) / 100;
      const friendsShare = Math.round((amountVal - userShare) * 100) / 100;
      const perFriend = Math.round((friendsShare / names.length) * 100) / 100;

      if (userShareEl) userShareEl.textContent = formatCurrency(userShare);
      if (friendsShareEl) friendsShareEl.textContent = `${formatCurrency(friendsShare)} (${names.length} friend${names.length > 1 ? 's' : ''} @ ${formatCurrency(perFriend)} each)`;
      if (previewBox) previewBox.style.display = 'flex';
    } else {
      if (previewBox) previewBox.style.display = 'none';
    }
  }

  if (splitAmtInput) splitAmtInput.addEventListener('input', updateSplitPreview);
  if (splitPartsInput) splitPartsInput.addEventListener('input', updateSplitPreview);

  if (splitConfirmBtn) {
    splitConfirmBtn.addEventListener('click', async () => {
      const amount = parseFloat($('#split-amount')?.value);
      const category = $('#split-category')?.value || 'food';
      const note = $('#split-note')?.value?.trim() || null;
      const participantsRaw = $('#split-participants')?.value || '';
      const participants = participantsRaw.split(',').map((s) => s.trim()).filter(Boolean);

      if (isNaN(amount) || amount <= 0) {
        showToast('Please enter a valid total amount', 'error');
        return;
      }
      if (participants.length === 0) {
        showToast('Please enter at least one friend to split with', 'error');
        return;
      }

      splitConfirmBtn.disabled = true;
      splitConfirmBtn.textContent = 'Recording...';

      try {
        const res = await api('/api/udhar/split', {
          method: 'POST',
          body: JSON.stringify({
            total_amount: amount,
            amount: amount,
            category,
            note,
            participants,
          }),
        });

        showToast(res.message || `Split expense of ${formatCurrency(amount)} recorded!`, 'success');
        closeModal('#modal-split');

        $('#split-amount').value = '';
        $('#split-note').value = '';
        $('#split-participants').value = '';
        if ($('#split-calc-preview')) $('#split-calc-preview').style.display = 'none';

        loadUdhar();
      } catch (err) {
        showToast(err.message || 'Failed to record split', 'error');
      } finally {
        splitConfirmBtn.disabled = false;
        splitConfirmBtn.textContent = 'Record & Split';
      }
    });
  }

  // ---------- PWA Service Worker ----------

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  }

  // ---------- Init ----------

  tryRestore();
})();
