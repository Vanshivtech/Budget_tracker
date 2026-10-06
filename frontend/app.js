/* ================================================================
   SAARTH — Make money meaningful  |  App Logic
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
    const isFormData = options.body instanceof FormData;
    const headers = { ...(options.headers || {}) };
    if (!isFormData && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json';
    }
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

  // ---------- Floating Undo Toast Banner ----------
  let undoToastTimer = null;

  function showUndoToast(actionText) {
    const banner = $('#undo-toast-banner');
    const msgEl = $('#undo-toast-message');
    if (!banner || !msgEl) return;

    msgEl.textContent = actionText || 'Expense logged';
    banner.style.display = 'flex';
    banner.style.animation = 'undoToastIn 250ms cubic-bezier(0.16, 1, 0.3, 1) forwards';

    clearTimeout(undoToastTimer);
    undoToastTimer = setTimeout(() => {
      hideUndoToast();
    }, 10000);
  }

  function hideUndoToast() {
    const banner = $('#undo-toast-banner');
    if (!banner || banner.style.display === 'none') return;
    clearTimeout(undoToastTimer);
    banner.style.animation = 'undoToastOut 200ms ease forwards';
    setTimeout(() => {
      banner.style.display = 'none';
    }, 200);
  }

  function initUndoToast() {
    const btn = $('#undo-toast-btn');
    const closeBtn = $('#undo-toast-close');
    if (btn) {
      btn.addEventListener('click', async () => {
        hideUndoToast();
        try {
          const res = await api('/api/undo', { method: 'POST' });
          showToast(res.message || 'Action undone successfully', 'success');
          await refreshBudgetsAndDashboard();
          if (currentView === 'chat') loadChatHistory();
        } catch (err) {
          showToast(err.message || 'Failed to undo action', 'error');
        }
      });
    }
    if (closeBtn) {
      closeBtn.addEventListener('click', () => hideUndoToast());
    }
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
  initUndoToast();

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
    authTitle.textContent = isLoginMode ? 'Welcome back' : 'Create your account';
    authSubtitle.textContent = isLoginMode ? 'Sign in to your account' : 'Start your financial journey';
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

      checkMaintenanceStatus();

      if (currentUser && currentUser.force_password_reset) {
        showApp();
        switchView('settings');
        const pwdCard = document.getElementById('settings-change-password-card');
        if (pwdCard) {
          pwdCard.scrollIntoView({ behavior: 'smooth' });
          showChangePwdAlert('Password reset required: Please set a new password before continuing.', 'warning');
        }
        return;
      }

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
    const mb = document.getElementById('maintenance-banner');
    if (mb) mb.style.display = 'none';
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
    checkMaintenanceStatus();
    const token = sessionStorage.getItem('abt_token');
    const user = sessionStorage.getItem('abt_user');
    if (token && user) {
      authToken = token;
      currentUser = JSON.parse(user);
      if (currentUser && currentUser.force_password_reset) {
        showApp();
        switchView('settings');
        const pwdCard = document.getElementById('settings-change-password-card');
        if (pwdCard) {
          pwdCard.scrollIntoView({ behavior: 'smooth' });
          showChangePwdAlert('Password reset required: Please set a new password before continuing.', 'warning');
        }
        return;
      }
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
    loadUserIdentity();
    initMobileTooltips();
    loadAllCategories();
    loadChatHistory();
    loadGlanceData();
    checkMaintenanceStatus();
    switchView('chat');
  }

  window.setAuthSession = function(tok, usr) {
    authToken = tok;
    currentUser = usr;
    sessionStorage.setItem('abt_token', tok);
    sessionStorage.setItem('abt_user', JSON.stringify(usr));
    sessionStorage.setItem('abt_onboarding_skipped', '1');
    showApp();
  };

  function updateUserUI() {
    if (!currentUser) return;
    const name = currentUser.username || (currentUser.email ? currentUser.email.split('@')[0] : 'User');
    const email = currentUser.email || '';

    const nameEl = $('#user-display-name');
    if (nameEl) nameEl.textContent = name;

    const emailEl = $('#user-email');
    if (emailEl) {
      emailEl.textContent = email;
      emailEl.title = email;
    }

    const avatarEl = $('#user-avatar');
    if (avatarEl) {
      if (currentUser.avatar_url) {
        avatarEl.innerHTML = `<img src="${escapeHtml(currentUser.avatar_url)}" alt="${escapeHtml(name)}" class="avatar-photo-img">`;
      } else if (currentUser.avatar_id && typeof PRESET_AVATARS !== 'undefined') {
        const av = PRESET_AVATARS.find((a) => a.id === currentUser.avatar_id);
        if (av) avatarEl.innerHTML = av.svg;
        else avatarEl.textContent = name.charAt(0).toUpperCase();
      } else {
        avatarEl.textContent = name.charAt(0).toUpperCase();
      }
    }

    // Settings preview update
    const photoImg = $('#photo-preview-img');
    const photoPlaceholder = $('#photo-preview-placeholder');
    const removeBtn = $('#btn-remove-photo');
    if (photoImg && photoPlaceholder && removeBtn) {
      if (currentUser.avatar_url) {
        photoImg.src = currentUser.avatar_url;
        photoImg.style.display = 'block';
        photoPlaceholder.style.display = 'none';
        removeBtn.style.display = 'inline-block';
      } else {
        photoImg.src = '';
        photoImg.style.display = 'none';
        photoPlaceholder.style.display = 'block';
        removeBtn.style.display = 'none';
      }
    }
  }

  async function loadUserIdentity() {
    if (!authToken) return;
    try {
      const data = await api('/api/user/display');
      if (data && currentUser) {
        if (data.username) currentUser.username = data.username;
        if (data.avatar_id) currentUser.avatar_id = data.avatar_id;
        if (data.avatar_url !== undefined) currentUser.avatar_url = data.avatar_url;
        sessionStorage.setItem('abt_user', JSON.stringify(currentUser));
        updateUserUI();
      }
    } catch (e) {
      console.warn('Could not load user display:', e);
    }
  }

  function initMobileTooltips() {
    if (window._mobileTooltipsInit) return;
    window._mobileTooltipsInit = true;
    let touchTimer = null;
    let activeTouchEl = null;

    document.addEventListener('touchstart', (e) => {
      const target = e.target.closest('[data-tooltip]');
      if (!target) return;
      clearTimeout(touchTimer);
      activeTouchEl = target;
      touchTimer = setTimeout(() => {
        if (activeTouchEl) {
          activeTouchEl.classList.add('tooltip-active');
          setTimeout(() => {
            if (activeTouchEl) activeTouchEl.classList.remove('tooltip-active');
          }, 2500);
        }
      }, 450);
    }, { passive: true });

    document.addEventListener('touchend', () => {
      clearTimeout(touchTimer);
      if (activeTouchEl) {
        setTimeout(() => activeTouchEl?.classList.remove('tooltip-active'), 1500);
      }
    }, { passive: true });

    document.addEventListener('touchmove', () => {
      clearTimeout(touchTimer);
    }, { passive: true });
  }

  async function refreshBudgetsAndDashboard() {
    // Clear in-memory caches
    cachedTransactionsList = [];
    cachedUdharData = null;

    const promises = [
      loadDashboard(),
      api('/api/summary').catch(() => ({})),
      api('/api/budgets').catch(() => ({ budgets: [] })),
      api('/api/budgets/rollover').catch(() => ({ budgets: {} })),
    ];

    if (currentView === 'transactions') {
      promises.push(loadTransactionsView());
    }
    if (currentView === 'settings') {
      promises.push(loadSettings());
    }
    if (currentView === 'udhar') {
      promises.push(loadUdhar());
    }
    if (currentView === 'calendar') {
      promises.push(loadCalendar());
    }
    if (currentView === 'insights') {
      promises.push(loadInsights());
    }
    loadGlanceData();

    await Promise.all(promises);
  }

  // ---------- Navigation ----------

  function switchView(view) {
    console.log("NAV_SWITCH_VIEW:", view);
    updateUserUI();
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
    if (view === 'transactions') loadTransactionsView();
    if (view === 'dashboard') loadDashboard();
    if (view === 'calendar') loadCalendar();
    if (view === 'bills') loadBills();
    if (view === 'import') loadImport();
    if (view === 'udhar') loadUdhar();
    if (view === 'insights') loadInsights();
    if (view === 'settings') loadSettings();
  }
  window.switchView = switchView;

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

      if (data.reply && /(?:logged|recorded|added)\s+(?:rs\.?|₹|\d)/i.test(data.reply)) {
        showUndoToast('Expense logged');
        await refreshBudgetsAndDashboard();
      }
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
      messageList.scrollHeight - messageList.scrollTop - messageList.clientHeight <= threshold;
    userNearBottom = isNear;
    if (jumpLatest) {
      jumpLatest.style.display = !isNear ? 'block' : 'none';
      jumpLatest.classList.toggle('visible', !isNear);
    }
  });

  if (jumpLatest) {
    jumpLatest.addEventListener('click', () => {
      scrollToBottom(true);
      jumpLatest.style.display = 'none';
      jumpLatest.classList.remove('visible');
    });
  }

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

      const safeEl = $('#glance-safe');
      const savingsEl = $('#glance-savings');
      const streakEl = $('#glance-streak');
      const goalEl = $('#glance-goal');

      if (safeEl) {
        if (snapshot && snapshot.safe_to_spend_daily != null) {
          safeEl.textContent = formatCurrency(snapshot.safe_to_spend_daily);
          safeEl.classList.remove('glance-empty-prompt');
        } else {
          safeEl.innerHTML = '<span class="glance-empty-prompt">Add income to calculate</span>';
        }
      }

      if (savingsEl) {
        if (snapshot && snapshot.savings_rate_pct != null) {
          savingsEl.textContent = snapshot.savings_rate_pct.toFixed(0) + '%';
          savingsEl.classList.remove('glance-empty-prompt');
        } else {
          savingsEl.innerHTML = '<span class="glance-empty-prompt">Add income to calculate</span>';
        }
      }

      if (streakEl) {
        const days = streak ? (streak.current_streak || 0) : 0;
        if (days > 0) {
          streakEl.textContent = days + (days === 1 ? ' day streak' : ' days streak');
          streakEl.classList.remove('glance-empty-prompt');
        } else {
          streakEl.innerHTML = '<span class="glance-empty-prompt">Log today to start your streak</span>';
        }
      }

      if (goalEl) {
        if (goals && goals.goals && goals.goals.length > 0) {
          const top = goals.goals[0];
          const pct = top.target_amount > 0
            ? Math.round((top.saved_amount / top.target_amount) * 100)
            : 0;
          goalEl.textContent = pct + '%';
          goalEl.classList.remove('glance-empty-prompt');
        } else {
          goalEl.innerHTML = '<span class="glance-empty-prompt">Set a goal in Settings</span>';
        }
      }
    } catch (err) {
      // Silent
    }
  }

  // ---------- Dashboard ----------

  async function loadDashboard() {
    renderQuickAddBar('dashboard-quick-add-wrap');
    dashboardLoader.style.display = '';
    dashboardContent.style.display = 'none';

    try {
      // Tier 1: Fast SQL aggregates (< 500ms)
      const [summary, dashboard, snapshot, recurringData, remindersData, rolloverData] = await Promise.all([
        api('/api/summary'),
        api('/api/dashboard?tier=1'),
        api('/api/snapshot').catch(() => null),
        api('/api/recurring').catch(() => ({ recurring: [] })),
        api('/api/recurring/reminders').catch(() => ({ reminders: [] })),
        api('/api/budgets/rollover').catch(() => ({ budgets: {} })),
      ]);

      renderDashboard(summary, dashboard, snapshot, recurringData, remindersData, rolloverData);
      loadDashboardTier2(summary, dashboard);
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

  function renderDashboard(summary, dashboard, snapshot, recurringData, remindersData, rolloverData) {
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

    // 0b. Overspending Projections Alert Banner (Tier 2 placeholder)
    html += '<div id="dashboard-projections-container"></div>';

    // 1. Dashboard Header
    html += `
      <div class="dashboard-header">
        <div class="dashboard-header-text">
          <h1>Dashboard</h1>
          <p>Personal financial health and monthly expense breakdown</p>
        </div>
        <div class="dashboard-header-actions">
          <button class="btn-primary" id="btn-open-add-income" style="font-size:12px;padding:7px 14px;display:inline-flex;align-items:center;gap:6px;" data-tooltip="Record salary, freelance, or other income this month" data-tooltip-pos="bottom">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:13px;height:13px;"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            Add Income
          </button>
          <button class="btn-export-statement" id="btn-open-export" data-tooltip="Download your monthly transactions as PDF or Excel" data-tooltip-pos="bottom">
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

    // Card 4: Potential Savings (Tier 2 placeholder with subtle skeleton / spinner)
    html += `
      <div class="stat-card" id="stat-card-potential">
        <div class="stat-card-header">
          <span class="stat-card-label">Potential Savings</span>
          <div class="stat-card-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
            </svg>
          </div>
        </div>
        <div class="stat-card-value" id="stat-val-potential">
          <div class="skeleton-shimmer" style="height:26px;width:75px;border-radius:4px;display:inline-block;"></div>
        </div>
        <div class="stat-card-sub" id="stat-sub-potential">
          <div class="tier2-spinner-wrap"><div class="tier2-spinner"></div><span>Calculating...</span></div>
        </div>
      </div>
    `;

    html += '</div>'; // close stat-cards-row

    // 3. Financial Health Score Card (Tier 2 placeholder)
    html += `
      <div id="dashboard-health-score-container">
        <div class="health-score-card skeleton-card" style="padding:22px;border:1px dashed var(--border-subtle);background:var(--bg-card);border-radius:var(--radius-lg);margin-bottom:20px;">
          <div class="tier2-spinner-wrap" style="display:flex;align-items:center;gap:10px;color:var(--text-tertiary);font-size:13px;">
            <div class="tier2-spinner"></div>
            <span>Evaluating financial health score...</span>
          </div>
        </div>
      </div>
    `;

    // 4. AI Insight Callout Card (Tier 2 placeholder)
    html += `
      <div id="dashboard-insight-container">
        <div class="insight-callout-card skeleton-card" style="padding:20px;border:1px dashed var(--border-subtle);background:var(--bg-card);border-radius:var(--radius-lg);margin-bottom:20px;">
          <div class="tier2-spinner-wrap" style="display:flex;align-items:center;gap:10px;color:var(--text-tertiary);font-size:13px;">
            <div class="tier2-spinner"></div>
            <span>Synthesizing AI insights...</span>
          </div>
        </div>
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
      html += '<th>Date</th><th>Category</th><th>Note / Description</th><th style="text-align:right;">Amount</th><th style="width:36px;text-align:center;">Bill</th>';
      html += '</tr></thead><tbody>';
      recentTxns.forEach((t) => {
        html += `<tr>
          <td class="txn-date">${formatDate(t.date)}</td>
          <td><span class="txn-category">${escapeHtml(t.category)}</span></td>
          <td style="color:var(--text-secondary);">${escapeHtml(t.note || 'Expense')}</td>
          <td class="txn-amount">${formatCurrency(t.amount)}</td>
          <td style="text-align:center;">
            <button class="btn-add-bill-tx" data-tx-id="${t.id}" title="Attach bill/receipt" style="background:none;border:none;cursor:pointer;color:var(--text-tertiary);padding:4px;display:inline-flex;align-items:center;">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px;"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
            </button>
          </td>
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
          <p>No transactions recorded this month. Message SAARTH in chat to log an expense.</p>
        </div>
      `;
    }

    html += '</div></div>'; // close txn-table-wrap & dashboard-txn-card

    dashboardContent.innerHTML = html;
    dashboardContent.style.display = '';
    renderQuickAddBar('dashboard-quick-add-wrap');

    // Animate stat numbers smoothly
    animateNumber($('#stat-val-spent'), totalSpent, formatCurrency);
    animateNumber($('#stat-val-budget'), budgetRemaining, formatCurrency);
    animateNumber($('#stat-val-savings'), savingsThisMonth, formatCurrency);

    // Wire up Add Income button
    const addIncomeBtn = $('#btn-open-add-income');
    if (addIncomeBtn) {
      addIncomeBtn.addEventListener('click', () => {
        openIncomeModal();
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
          await refreshBudgetsAndDashboard();
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
          await refreshBudgetsAndDashboard();
        } catch (err) {
          e.target.checked = !enabled;
          if (textSpan) textSpan.textContent = !enabled ? 'Rollover' : 'Off';
          showToast(err.message || 'Failed to update rollover', 'error');
        }
      });
    });

    // Wire up Add Bill on transactions
    $$('.btn-add-bill-tx').forEach((btn) => {
      btn.addEventListener('click', () => {
        openAddBillModal(btn.dataset.txId);
      });
    });
  }

  // ---------- Tier 2 Dashboard Loader (Asynchronous computations) ----------
  async function loadDashboardTier2(summary, dashboard) {
    try {
      const tier2 = await api('/api/dashboard/tier2');

      // 1. Update Potential Savings Card
      const potVal = $('#stat-val-potential');
      const potSub = $('#stat-sub-potential');
      if (potVal && typeof tier2.potential_savings === 'number') {
        animateNumber(potVal, tier2.potential_savings, formatCurrency);
        if (potSub) {
          potSub.innerHTML = `<span class="stat-pill neutral">${escapeHtml(tier2.potential_savings_subtitle || 'Identified opportunities')}</span>`;
        }
      }

      // 2. Update Projections Banner
      const projContainer = $('#dashboard-projections-container');
      if (projContainer) {
        if (tier2.projections && tier2.projections.length > 0) {
          const topProj = tier2.projections[0];
          projContainer.innerHTML = `
            <div class="projection-alert-banner" style="margin-bottom:16px;background:rgba(239,68,68,0.08);border:1px solid rgba(239,68,68,0.25);border-radius:var(--radius-md);padding:12px 16px;display:flex;align-items:center;gap:12px;">
              <div style="color:var(--danger);flex-shrink:0;">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:20px;height:20px;">
                  <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
                  <line x1="12" y1="9" x2="12" y2="13"/>
                  <line x1="12" y1="17" x2="12.01" y2="17"/>
                </svg>
              </div>
              <div style="flex:1;font-size:13px;line-height:1.4;">
                <strong style="color:var(--danger);">Projected Overspending:</strong> ${escapeHtml(topProj.message)}
              </div>
            </div>
          `;
        } else {
          projContainer.innerHTML = '';
        }
      }

      // 3. Update Health Score Card
      const hsContainer = $('#dashboard-health-score-container');
      if (hsContainer && tier2.health_score && typeof tier2.health_score.score === 'number') {
        const hs = tier2.health_score;
        const tierClass = hs.tier === 'Excellent' ? 'excellent' : (hs.tier === 'Good' ? 'good' : (hs.tier === 'Fair' ? 'fair' : 'attention'));
        const partialBadge = hs.is_partial ? '<span class="partial-score-badge">Partial</span>' : '';

        let factorsHtml = '';
        (hs.factors || []).forEach((f) => {
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

        const topTip = (hs.tips && hs.tips.length > 0) ? hs.tips[0] : '';
        hsContainer.innerHTML = `
          <div class="health-score-card">
            <div class="health-score-header">
              <div class="health-score-left">
                <div class="health-score-gauge-wrap">
                  <div class="health-score-number">${hs.score}</div>
                  <div class="health-score-max">/100</div>
                </div>
                <div class="health-score-meta">
                  <div class="health-tier-badge ${tierClass}">${escapeHtml(hs.tier)} ${partialBadge}</div>
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

      // 4. Update AI Insight Card
      const insContainer = $('#dashboard-insight-container');
      if (insContainer && tier2.ai_insight) {
        const ins = tier2.ai_insight;
        insContainer.innerHTML = `
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
              <div class="insight-callout-title">${escapeHtml(ins.title || '')}</div>
              <div class="insight-callout-body">${escapeHtml(ins.text || '')}</div>
            </div>
            <button class="insight-action-btn" id="insight-action-btn" data-prompt="${escapeHtml(ins.prompt || '')}">
              Ask SAARTH
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="9 18 15 12 9 6"/>
              </svg>
            </button>
          </div>
        `;

        const newInsightBtn = $('#insight-action-btn');
        if (newInsightBtn) {
          newInsightBtn.addEventListener('click', () => {
            const prompt = newInsightBtn.getAttribute('data-prompt');
            if (prompt && composerInput) {
              composerInput.value = prompt;
              switchView('chat');
              composerInput.focus();
            }
          });
        }
      }
    } catch (err) {
      console.warn('Dashboard Tier 2 load error:', err);
    }
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

  let cachedUdharData = null;

  async function loadUdhar() {
    udharLoader.style.display = '';
    udharContent.style.display = 'none';

    try {
      const data = await api('/api/udhar');
      cachedUdharData = data;
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

    // Populate person datalist for autocomplete
    const dl = $('#udhar-person-datalist');
    if (dl) {
      dl.innerHTML = persons.map((p) => `<option value="${escapeHtml(p.name || p.person_name)}"></option>`).join('');
    }

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
            <div style="display:flex;gap:4px;justify-content:flex-end;margin-top:6px;">
              <button class="btn-secondary btn-sm btn-open-ledger" data-person-key="${escapeHtml(p.person_key || name.toLowerCase())}" data-tooltip="View detailed transaction history with this person" style="font-size:11px;padding:3px 8px;">Ledger</button>
              ${pNet > 0 ? `<button class="btn-secondary btn-sm btn-nudge-reminder" data-person-key="${escapeHtml(p.person_key || name.toLowerCase())}" data-tooltip="Generate a polite WhatsApp reminder message for this person" style="font-size:11px;padding:3px 8px;">Send reminder</button>` : ''}
            </div>
          </div>
        </div>`;
      });
      html += '</div>';
    } else {
      html += '<div class="empty-state"><p>No shared balances or debts yet. Ask SAARTH in chat about money you lent or borrowed, or tap "Split Expense".</p></div>';
    }

    udharContent.innerHTML = html;
    udharContent.style.display = '';

    // Attach Ledger button handlers
    udharContent.querySelectorAll('.btn-open-ledger').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const pKey = btn.dataset.personKey;
        const person = persons.find((x) => (x.person_key || (x.name || x.person_name || '').toLowerCase()) === pKey);
        if (person) openUdharLedgerModal(person);
      });
    });

    // Attach reminder click handlers
    udharContent.querySelectorAll('.btn-nudge-reminder').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        openUdharReminderModal(btn.dataset.personKey);
      });
    });
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
    const mb = document.getElementById('maintenance-banner');
    if (mb) mb.style.display = 'none';
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
              <span>₹</span>
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
      showToast('Budgets saved successfully! Welcome to SAARTH.', 'success');
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

  // ---------- Modals & Form State Management ----------
  const modalDirtyCheckers = new Map();

  function openModal(id, dirtyCheckFn = null) {
    const m = $(id);
    if (!m) return;
    m.style.display = 'flex';
    if (dirtyCheckFn) {
      modalDirtyCheckers.set(id, dirtyCheckFn);
    } else {
      modalDirtyCheckers.delete(id);
    }
  }

  function closeModal(id, force = false) {
    const m = $(id);
    if (!m || m.style.display === 'none') return;
    const dirtyFn = modalDirtyCheckers.get(id);
    if (!force && dirtyFn && dirtyFn()) {
      if (!confirm('You have unsaved changes. Are you sure you want to close?')) {
        return;
      }
    }
    m.style.display = 'none';
    modalDirtyCheckers.delete(id);
  }

  // Backdrop click & Escape key to close modals with dirty warning
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      $$('.modal-overlay').forEach((m) => {
        if (m.style.display === 'flex' || m.style.display === 'block') {
          closeModal('#' + m.id);
        }
      });
    }
  });

  $$('.modal-overlay').forEach((modal) => {
    modal.addEventListener('click', (e) => {
      if (e.target === modal) {
        closeModal('#' + modal.id);
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
        await refreshBudgetsAndDashboard();
      } catch (err) {
        showToast(err.message || 'Failed to record split', 'error');
      } finally {
        splitConfirmBtn.disabled = false;
        splitConfirmBtn.textContent = 'Record & Split';
      }
    });
  }

  // ================================================================
  // ---------- Cash-Flow Calendar View ----------
  // ================================================================

  let calendarCurrentMonth = new Date().toISOString().slice(0, 7);

  async function loadCalendar(month) {
    if (month) calendarCurrentMonth = month;
    const gridEl = $('#calendar-days-grid');
    const titleEl = $('#cal-month-title');
    const kpiBillsEl = $('#cal-kpi-bills');
    const kpiRecEl = $('#cal-kpi-receivable');
    const kpiPayEl = $('#cal-kpi-payable');
    const kpiBalEl = $('#cal-kpi-balance');
    const detailEl = $('#cal-day-detail');

    if (detailEl) detailEl.style.display = 'none';
    if (!gridEl) return;

    gridEl.innerHTML = '<div style="grid-column: 1 / -1; text-align:center; padding: 40px;"><div class="spinner"></div></div>';

    const [yStr, mStr] = calendarCurrentMonth.split('-');
    const dateObj = new Date(parseInt(yStr, 10), parseInt(mStr, 10) - 1, 1);
    const monthName = dateObj.toLocaleString('default', { month: 'long', year: 'numeric' });
    if (titleEl) titleEl.textContent = monthName;

    try {
      const data = await api(`/api/calendar?month=${encodeURIComponent(calendarCurrentMonth)}`);
      const kpis = data.kpis || {};

      if (kpiBillsEl) kpiBillsEl.textContent = formatCurrency(kpis.recurring_bills_total || 0);
      if (kpiRecEl) kpiRecEl.textContent = formatCurrency(kpis.udhar_receivable_total || 0);
      if (kpiPayEl) kpiPayEl.textContent = formatCurrency(kpis.udhar_payable_total || 0);
      if (kpiBalEl) {
        const netBal = kpis.running_balance_end || 0;
        kpiBalEl.textContent = formatCurrency(netBal);
        kpiBalEl.className = 'cal-kpi-val ' + (netBal >= 0 ? 'success' : 'danger');
      }

      const firstDayDow = dateObj.getDay();
      const days = data.days || [];
      const todayIso = new Date().toISOString().slice(0, 10);

      let gridHtml = '';
      for (let i = 0; i < firstDayDow; i++) {
        gridHtml += '<div class="cal-day-cell other-month"></div>';
      }

      days.forEach((dayData) => {
        const isToday = dayData.date === todayIso;
        const events = dayData.events || [];
        const hasBills = events.some((e) => e.type === 'bill');
        const hasRec = events.some((e) => e.type === 'udhar_due' && e.direction === 'receivable');
        const hasPay = events.some((e) => e.type === 'udhar_due' && e.direction === 'payable');
        const hasInc = events.some((e) => e.type === 'income');

        let pillsHtml = '';
        if (events.length > 0) {
          pillsHtml += '<div class="cal-events-wrap">';
          if (hasBills) pillsHtml += '<span class="cal-event-pill bill" title="Bills due">Bill</span>';
          if (hasRec) pillsHtml += '<span class="cal-event-pill rec" title="Udhar to collect">Receive</span>';
          if (hasPay) pillsHtml += '<span class="cal-event-pill pay" title="Udhar to pay">Pay</span>';
          if (hasInc) pillsHtml += '<span class="cal-event-pill inc" title="Expected Income">Income</span>';
          pillsHtml += '</div>';
        }

        let balSub = '';
        if (dayData.projected_balance != null) {
          const balVal = dayData.projected_balance;
          balSub = `<div class="cal-day-bal ${balVal < 0 ? 'danger' : ''}">${formatCurrency(balVal)}</div>`;
        }

        gridHtml += `
          <div class="cal-day-cell ${isToday ? 'today' : ''} ${events.length > 0 ? 'has-events' : ''}" data-date="${dayData.date}">
            <div class="cal-day-num">${dayData.day}</div>
            ${pillsHtml}
            ${balSub}
          </div>
        `;
      });

      gridEl.innerHTML = gridHtml;

      gridEl.querySelectorAll('.cal-day-cell[data-date]').forEach((cell) => {
        cell.addEventListener('click', () => {
          gridEl.querySelectorAll('.cal-day-cell').forEach((c) => c.classList.remove('selected'));
          cell.classList.add('selected');
          const dIso = cell.getAttribute('data-date');
          const matchedDay = days.find((d) => d.date === dIso);
          if (matchedDay) showCalendarDayDetail(matchedDay);
        });
      });

    } catch (err) {
      gridEl.innerHTML = `<div style="grid-column: 1 / -1; padding: 24px; text-align: center; color: var(--danger);">Failed to load calendar: ${escapeHtml(err.message)}</div>`;
    }
  }

  function showCalendarDayDetail(dayData) {
    const detailEl = $('#cal-day-detail');
    const titleEl = $('#cal-detail-title');
    const bodyEl = $('#cal-detail-body');
    if (!detailEl || !bodyEl) return;

    if (titleEl) titleEl.textContent = `Scheduled on ${formatDate(dayData.date)}`;

    let html = '';
    const events = dayData.events || [];

    if (events.length === 0) {
      html += '<p style="color:var(--text-tertiary);font-size:13px;">No bills, udhar due dates, or planned events for this day.</p>';
    } else {
      html += '<div class="cal-detail-events-list">';
      events.forEach((ev) => {
        let tagClass = 'neutral';
        let label = ev.name || ev.person || 'Event';
        let extra = '';

        if (ev.type === 'bill') {
          tagClass = 'danger';
          label = `Bill: ${ev.name}`;
          extra = `Category: ${ev.category || 'other'} · Recurring`;
        } else if (ev.type === 'udhar_due') {
          if (ev.direction === 'receivable') {
            tagClass = 'success';
            label = `${ev.person} owes you (Udhar)`;
            extra = 'Due to receive';
          } else {
            tagClass = 'danger';
            label = `You owe ${ev.person} (Udhar)`;
            extra = 'Due to pay';
          }
        } else if (ev.type === 'income') {
          tagClass = 'success';
          label = `Income: ${ev.name || 'Salary'}`;
          extra = 'Expected deposit';
        }

        html += `
          <div class="cal-detail-event-item">
            <div class="cal-detail-event-left">
              <span class="badge ${tagClass}" style="margin-bottom:4px;display:inline-block;">${escapeHtml(label)}</span>
              <div style="font-size:12px;color:var(--text-secondary);">${escapeHtml(extra)}</div>
            </div>
            <div class="cal-detail-event-amt ${tagClass === 'success' ? 'success-text' : 'danger-text'}">
              ${formatCurrency(ev.amount || 0)}
            </div>
          </div>
        `;
      });
      html += '</div>';
    }

    if (dayData.projected_balance != null) {
      html += `
        <div class="cal-detail-balance-row">
          <span>Projected Running Balance</span>
          <strong>${formatCurrency(dayData.projected_balance)}</strong>
        </div>
      `;
    }

    bodyEl.innerHTML = html;
    detailEl.style.display = 'block';
  }

  const calPrevBtn = $('#cal-prev-btn');
  const calNextBtn = $('#cal-next-btn');
  const calDetailClose = $('#cal-detail-close');

  if (calPrevBtn) {
    calPrevBtn.addEventListener('click', () => {
      const [y, m] = calendarCurrentMonth.split('-').map(Number);
      const d = new Date(y, m - 2, 1);
      calendarCurrentMonth = d.toISOString().slice(0, 7);
      loadCalendar();
    });
  }

  if (calNextBtn) {
    calNextBtn.addEventListener('click', () => {
      const [y, m] = calendarCurrentMonth.split('-').map(Number);
      const d = new Date(y, m, 1);
      calendarCurrentMonth = d.toISOString().slice(0, 7);
      loadCalendar();
    });
  }

  if (calDetailClose) {
    calDetailClose.addEventListener('click', () => {
      const detailEl = $('#cal-day-detail');
      if (detailEl) detailEl.style.display = 'none';
    });
  }

  // ================================================================
  // ---------- Bills & Receipts View ----------
  // ================================================================

  let cachedTransactionsList = [];

  async function loadBills() {
    const loader = $('#bills-loader');
    const content = $('#bills-content');
    const grid = $('#receipts-grid');
    if (!grid) return;

    if (loader) loader.style.display = '';
    if (content) content.style.display = 'none';

    try {
      const data = await api('/api/receipts');
      const receipts = data.receipts || [];

      if (receipts.length === 0) {
        grid.innerHTML = `
          <div class="empty-state" style="grid-column: 1 / -1; padding: 48px 0;">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:40px;height:40px;opacity:0.3;margin-bottom:12px;">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
            </svg>
            <p>No bills or receipts uploaded yet.</p>
            <button class="btn-primary btn-sm" id="btn-empty-upload-bill" style="margin-top:12px;">Upload First Bill</button>
          </div>
        `;
        const emptyBtn = $('#btn-empty-upload-bill');
        if (emptyBtn) emptyBtn.addEventListener('click', () => openAddBillModal());
      } else {
        let html = '';
        receipts.forEach((r) => {
          const isPdf = r.mime === 'application/pdf';
          const sizeKb = (r.size / 1024).toFixed(1);
          const txDesc = r.merchant || r.category || (r.amount ? `₹${r.amount}` : 'General Receipt');
          const txDate = r.transaction_date ? formatDate(r.transaction_date) : formatDate(r.created_at);

          html += `
            <div class="receipt-card" data-id="${r.id}">
              <div class="receipt-preview-thumb">
                ${isPdf ? `
                  <div class="receipt-pdf-placeholder">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                    <span>PDF Document</span>
                  </div>
                ` : `
                  <img src="${escapeHtml(r.signed_url)}" alt="Receipt thumbnail" loading="lazy">
                `}
              </div>
              <div class="receipt-info">
                <div class="receipt-linked-tx">${escapeHtml(txDesc)}</div>
                <div class="receipt-meta">${txDate} · ${sizeKb} KB</div>
              </div>
              <div class="receipt-actions">
                <button class="btn-secondary btn-sm btn-view-receipt" data-id="${r.id}">View</button>
                <button class="btn-secondary btn-sm danger-text btn-del-receipt" data-id="${r.id}">Delete</button>
              </div>
            </div>
          `;
        });
        grid.innerHTML = html;

        grid.querySelectorAll('.btn-view-receipt').forEach((btn) => {
          btn.addEventListener('click', () => {
            const rid = parseInt(btn.dataset.id, 10);
            const r = receipts.find((x) => x.id === rid);
            if (r) openReceiptPreviewModal(r);
          });
        });

        grid.querySelectorAll('.btn-del-receipt').forEach((btn) => {
          btn.addEventListener('click', async () => {
            const rid = parseInt(btn.dataset.id, 10);
            if (!confirm('Are you sure you want to delete this receipt?')) return;
            try {
              await api(`/api/receipts/${rid}`, { method: 'DELETE' });
              showToast('Receipt deleted', 'success');
              loadBills();
            } catch (err) {
              showToast(err.message || 'Failed to delete receipt', 'error');
            }
          });
        });
      }

      if (content) content.style.display = '';
    } catch (err) {
      if (grid) grid.innerHTML = `<div style="grid-column: 1 / -1; padding: 24px; text-align: center; color: var(--danger);">Failed to load receipts: ${escapeHtml(err.message)}</div>`;
      if (content) content.style.display = '';
    } finally {
      if (loader) loader.style.display = 'none';
    }
  }

  const uploadReceiptTrigger = $('#btn-upload-receipt-trigger');
  if (uploadReceiptTrigger) {
    uploadReceiptTrigger.addEventListener('click', () => openAddBillModal());
  }

  async function openAddBillModal(txId = null) {
    const modal = $('#modal-add-bill');
    const txSelect = $('#bill-transaction-select');
    const txInput = $('#bill-transaction-id');
    const fileInput = $('#bill-file-input');
    const previewWrap = $('#bill-file-preview');
    const previewImg = $('#bill-preview-img');
    const previewPdf = $('#bill-preview-pdf');

    if (fileInput) fileInput.value = '';
    if (previewWrap) previewWrap.style.display = 'none';
    if (previewImg) { previewImg.src = ''; previewImg.style.display = 'none'; }
    if (previewPdf) previewPdf.style.display = 'none';
    if (txInput) txInput.value = txId || '';

    if (txSelect) {
      try {
        const data = await api('/api/transactions?limit=30');
        cachedTransactionsList = data.transactions || [];
        let optHtml = '<option value="">General receipt (unlinked)</option>';
        cachedTransactionsList.forEach((t) => {
          const sel = (txId && String(t.id) === String(txId)) ? 'selected' : '';
          const label = `${formatDate(t.date)}: ${t.merchant || t.category} (${formatCurrency(t.amount)})`;
          optHtml += `<option value="${t.id}" ${sel}>${escapeHtml(label)}</option>`;
        });
        txSelect.innerHTML = optHtml;
      } catch (e) {
        // Fallback
      }
    }

    if (modal) modal.style.display = 'flex';
  }

  const addBillClose = $('#add-bill-modal-close');
  const addBillCancel = $('#add-bill-cancel-btn');
  const addBillUpload = $('#add-bill-upload-btn');
  const billFileInput = $('#bill-file-input');

  if (addBillClose) addBillClose.addEventListener('click', () => closeModal('#modal-add-bill'));
  if (addBillCancel) addBillCancel.addEventListener('click', () => closeModal('#modal-add-bill'));

  if (billFileInput) {
    billFileInput.addEventListener('change', () => {
      const file = billFileInput.files && billFileInput.files[0];
      const previewWrap = $('#bill-file-preview');
      const previewImg = $('#bill-preview-img');
      const previewPdf = $('#bill-preview-pdf');
      const pdfFilename = $('#bill-pdf-filename');

      if (!file) {
        if (previewWrap) previewWrap.style.display = 'none';
        return;
      }

      if (file.size > 5 * 1024 * 1024) {
        showToast('File exceeds 5 MB limit. Please select a smaller file.', 'error');
        billFileInput.value = '';
        if (previewWrap) previewWrap.style.display = 'none';
        return;
      }

      if (previewWrap) previewWrap.style.display = 'block';

      if (file.type.startsWith('image/')) {
        if (previewImg) {
          previewImg.src = URL.createObjectURL(file);
          previewImg.style.display = 'block';
        }
        if (previewPdf) previewPdf.style.display = 'none';
      } else if (file.type === 'application/pdf') {
        if (previewImg) previewImg.style.display = 'none';
        if (previewPdf) {
          previewPdf.style.display = 'block';
          if (pdfFilename) pdfFilename.textContent = file.name;
        }
      }
    });
  }

  if (addBillUpload) {
    addBillUpload.addEventListener('click', async () => {
      const file = billFileInput?.files && billFileInput.files[0];
      if (!file) {
        showToast('Please select a JPG, PNG, or PDF receipt file', 'error');
        return;
      }

      const txSelect = $('#bill-transaction-select');
      const txId = txSelect?.value || $('#bill-transaction-id')?.value || '';

      const formData = new FormData();
      formData.append('file', file);
      if (txId) formData.append('transaction_id', txId);

      addBillUpload.disabled = true;
      addBillUpload.textContent = 'Uploading...';

      try {
        const res = await fetch('/api/receipts/upload', {
          method: 'POST',
          headers: {
            'Authorization': 'Bearer ' + authToken,
          },
          body: formData,
        });

        const resData = await res.json();
        if (!res.ok) throw new Error(resData.detail || 'Upload failed');

        showToast('Receipt attached successfully!', 'success');
        closeModal('#modal-add-bill');
        loadBills();
      } catch (err) {
        showToast(err.message || 'Failed to upload receipt', 'error');
      } finally {
        addBillUpload.disabled = false;
        addBillUpload.textContent = 'Upload Receipt';
      }
    });
  }

  let activePreviewReceipt = null;

  function openReceiptPreviewModal(rec) {
    activePreviewReceipt = rec;
    const modal = $('#modal-receipt-preview');
    const titleEl = $('#receipt-preview-title');
    const mediaContainer = $('#receipt-media-container');
    const metaInfo = $('#receipt-meta-info');
    const openLink = $('#receipt-open-link');

    if (!modal) return;

    const txDesc = rec.merchant || rec.category || (rec.amount ? `₹${rec.amount}` : 'General Receipt');
    if (titleEl) titleEl.textContent = `Receipt: ${txDesc}`;

    if (openLink) openLink.href = rec.signed_url;

    if (mediaContainer) {
      if (rec.mime === 'application/pdf') {
        mediaContainer.innerHTML = `
          <div style="padding: 40px; text-align:center;">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:48px;height:48px;color:var(--accent);margin-bottom:12px;"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
            <div style="font-size:15px;font-weight:600;margin-bottom:8px;">PDF Attachment</div>
            <a href="${escapeHtml(rec.signed_url)}" target="_blank" class="btn-primary btn-sm" style="text-decoration:none;">Open PDF in New Tab</a>
          </div>
        `;
      } else {
        mediaContainer.innerHTML = `<img src="${escapeHtml(rec.signed_url)}" alt="Receipt Document" style="max-width:100%;max-height:450px;border-radius:var(--radius-sm);object-fit:contain;">`;
      }
    }

    if (metaInfo) {
      metaInfo.innerHTML = `
        <div><strong>Linked To:</strong> ${escapeHtml(txDesc)}</div>
        <div><strong>Uploaded:</strong> ${formatDate(rec.created_at)}</div>
        <div><strong>File Size:</strong> ${(rec.size / 1024).toFixed(1)} KB (${escapeHtml(rec.mime)})</div>
        <div style="font-size:11px;color:var(--text-tertiary);margin-top:4px;">Storage Path: ${escapeHtml(rec.path)}</div>
      `;
    }

    modal.style.display = 'flex';
  }

  const receiptPreviewClose = $('#receipt-preview-close');
  const receiptPreviewDone = $('#receipt-preview-done-btn');
  const receiptDeleteBtn = $('#receipt-delete-btn');

  if (receiptPreviewClose) receiptPreviewClose.addEventListener('click', () => closeModal('#modal-receipt-preview'));
  if (receiptPreviewDone) receiptPreviewDone.addEventListener('click', () => closeModal('#modal-receipt-preview'));

  if (receiptDeleteBtn) {
    receiptDeleteBtn.addEventListener('click', async () => {
      if (!activePreviewReceipt) return;
      if (!confirm('Are you sure you want to delete this receipt?')) return;

      try {
        await api(`/api/receipts/${activePreviewReceipt.id}`, { method: 'DELETE' });
        showToast('Receipt deleted', 'success');
        closeModal('#modal-receipt-preview');
        loadBills();
      } catch (err) {
        showToast(err.message || 'Failed to delete receipt', 'error');
      }
    });
  }

  // ================================================================
  // ---------- Statement & CSV Import View ----------
  // ================================================================

  let importMode = 'csv';
  let importChosenFile = null;
  let importParsedRows = [];

  function loadImport() {
    const csvTab = $('#tab-import-csv');
    const textTab = $('#tab-import-text');
    const csvPanel = $('#import-csv-panel');
    const textPanel = $('#import-text-panel');
    const previewCard = $('#import-preview-card');
    const inputCard = $('#import-input-card');

    if (previewCard) previewCard.style.display = 'none';
    if (inputCard) inputCard.style.display = 'block';

    if (csvTab && textTab && csvPanel && textPanel) {
      csvTab.onclick = () => {
        importMode = 'csv';
        csvTab.classList.add('active');
        textTab.classList.remove('active');
        csvPanel.style.display = 'block';
        textPanel.style.display = 'none';
      };

      textTab.onclick = () => {
        importMode = 'text';
        textTab.classList.add('active');
        csvTab.classList.remove('active');
        csvPanel.style.display = 'none';
        textPanel.style.display = 'block';
      };
    }

    const dropzone = $('#csv-dropzone');
    const fileInput = $('#csv-file-input');
    const fileNameBadge = $('#chosen-file-name');

    if (dropzone && fileInput) {
      dropzone.onclick = () => fileInput.click();

      fileInput.onchange = (e) => {
        const file = e.target.files && e.target.files[0];
        if (file) handleChosenCsv(file);
      };

      dropzone.ondragover = (e) => {
        e.preventDefault();
        dropzone.classList.add('drag-over');
      };

      dropzone.ondragleave = () => {
        dropzone.classList.remove('drag-over');
      };

      dropzone.ondrop = (e) => {
        e.preventDefault();
        dropzone.classList.remove('drag-over');
        const file = e.dataTransfer.files && e.dataTransfer.files[0];
        if (file) handleChosenCsv(file);
      };
    }

    function handleChosenCsv(file) {
      if (!file.name.toLowerCase().endsWith('.csv') && file.type !== 'text/csv') {
        showToast('Please select a valid CSV statement file', 'error');
        return;
      }
      if (file.size > 2 * 1024 * 1024) {
        showToast('File exceeds 2 MB limit', 'error');
        return;
      }
      importChosenFile = file;
      if (fileNameBadge) {
        fileNameBadge.textContent = `${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
        fileNameBadge.style.display = 'inline-block';
      }
    }
  }

  const parseStatementBtn = $('#btn-parse-statement');
  if (parseStatementBtn) {
    parseStatementBtn.addEventListener('click', async () => {
      let payload;
      let isForm = false;

      if (importMode === 'csv') {
        if (!importChosenFile) {
          showToast('Please select a CSV file first', 'error');
          return;
        }
        const fd = new FormData();
        fd.append('file', importChosenFile);
        payload = fd;
        isForm = true;
      } else {
        const text = $('#import-text-area')?.value?.trim();
        if (!text) {
          showToast('Please paste SMS or UPI transaction lines', 'error');
          return;
        }
        payload = JSON.stringify({ text });
        isForm = false;
      }

      parseStatementBtn.disabled = true;
      parseStatementBtn.textContent = 'Parsing & Categorizing...';

      try {
        const headers = { 'Authorization': 'Bearer ' + authToken };
        if (!isForm) headers['Content-Type'] = 'application/json';

        const res = await fetch('/api/import/preview', {
          method: 'POST',
          headers,
          body: payload,
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to parse statement');

        renderImportPreview(data);
      } catch (err) {
        showToast(err.message || 'Import parsing failed', 'error');
      } finally {
        parseStatementBtn.disabled = false;
        parseStatementBtn.textContent = 'Parse & Preview Statement';
      }
    });
  }

  function renderImportPreview(data) {
    const inputCard = $('#import-input-card');
    const previewCard = $('#import-preview-card');
    const pillsWrap = $('#import-stats-pills');
    const tbody = $('#import-tbody');
    const selectAll = $('#import-select-all');

    importParsedRows = data.rows || [];

    if (inputCard) inputCard.style.display = 'none';
    if (previewCard) previewCard.style.display = 'block';

    const sum = data.summary || {};
    if (pillsWrap) {
      pillsWrap.innerHTML = `
        <span class="stat-pill neutral">${sum.total_rows || 0} Total</span>
        <span class="stat-pill danger">${sum.expenses_count || 0} Expenses</span>
        <span class="stat-pill success">${sum.credits_count || 0} Credits / Inflows</span>
        ${sum.duplicates_count ? `<span class="stat-pill warning">${sum.duplicates_count} Potential Duplicates</span>` : ''}
        <span class="stat-pill info">${sum.rules_count || 0} Rule-matched</span>
        ${sum.llm_count ? `<span class="stat-pill info">${sum.llm_count} AI-categorized</span>` : ''}
      `;
    }

    const allCategories = ['food', 'groceries', 'travel', 'rent', 'bills', 'eating out', 'utilities', 'shopping', 'entertainment', 'health', 'personal care', 'emergency fund', 'sip / investments', 'miscellaneous', 'other'];

    let rowsHtml = '';
    importParsedRows.forEach((r, idx) => {
      const isCredit = r.is_credit;
      const isDup = r.is_duplicate;
      const rowClass = isDup ? 'table-row-duplicate' : (isCredit ? 'table-row-credit' : '');

      rowsHtml += `
        <tr class="${rowClass}" data-idx="${idx}">
          <td>
            <input type="checkbox" class="import-row-check" data-idx="${idx}" ${isDup ? '' : 'checked'}>
          </td>
          <td>${formatDate(r.date)}</td>
          <td>
            <strong>${escapeHtml(r.merchant || r.description)}</strong>
            <div style="font-size:11px;color:var(--text-tertiary);">${escapeHtml(r.description || '')}</div>
          </td>
          <td class="${isCredit ? 'success-text' : 'danger-text'}" style="font-weight:600;">
            ${isCredit ? '+' : '-'}${formatCurrency(r.amount)}
          </td>
          <td>
            <span class="badge ${isCredit ? 'success' : 'neutral'}">${isCredit ? 'Credit' : 'Debit'}</span>
          </td>
          <td>
            ${isCredit ? `
              <span style="font-size:12px;color:var(--text-secondary);">Income</span>
            ` : `
              <select class="form-input import-cat-select" data-idx="${idx}" style="padding:4px 8px;font-size:12px;height:auto;">
                ${allCategories.map((c) => `<option value="${c}" ${c.toLowerCase() === (r.category || '').toLowerCase() ? 'selected' : ''}>${c.charAt(0).toUpperCase() + c.slice(1)}</option>`).join('')}
              </select>
            `}
          </td>
          <td>
            ${isDup ? `
              <span class="badge warning" title="Similar transaction already logged">Potential Dup</span>
            ` : `
              <span class="badge neutral" style="font-size:10px;">${escapeHtml(r.categorized_by || 'auto')}</span>
            `}
          </td>
        </tr>
      `;
    });

    if (tbody) tbody.innerHTML = rowsHtml;

    tbody?.querySelectorAll('.import-cat-select').forEach((sel) => {
      sel.addEventListener('change', (e) => {
        const idx = parseInt(e.target.dataset.idx, 10);
        if (importParsedRows[idx]) {
          importParsedRows[idx].category = e.target.value;
        }
      });
    });

    if (selectAll) {
      selectAll.checked = true;
      selectAll.onchange = () => {
        const checked = selectAll.checked;
        tbody?.querySelectorAll('.import-row-check').forEach((chk) => {
          chk.checked = checked;
        });
      };
    }
  }

  const importCancelPreview = $('#import-cancel-preview');
  if (importCancelPreview) {
    importCancelPreview.addEventListener('click', () => {
      $('#import-preview-card').style.display = 'none';
      $('#import-input-card').style.display = 'block';
    });
  }

  const importConfirmSave = $('#import-confirm-save');
  if (importConfirmSave) {
    importConfirmSave.addEventListener('click', async () => {
      const selectedIndices = [];
      $$('.import-row-check:checked').forEach((chk) => {
        selectedIndices.push(parseInt(chk.dataset.idx, 10));
      });

      if (selectedIndices.length === 0) {
        showToast('Please select at least one transaction to import', 'error');
        return;
      }

      const rowsToImport = selectedIndices.map((i) => {
        const r = importParsedRows[i];
        return {
          date: r.date,
          amount: r.amount,
          category: r.category || 'other',
          note: r.description || r.merchant || '',
          merchant: r.merchant || '',
          is_credit: r.is_credit,
          import_credit: r.is_credit,
        };
      });

      importConfirmSave.disabled = true;
      importConfirmSave.textContent = 'Importing...';

      try {
        const res = await api('/api/import/confirm', {
          method: 'POST',
          body: JSON.stringify({ rows: rowsToImport }),
        });

        const totalImported = (res.imported_transactions || 0) + (res.imported_income || 0);
        showToast(`Successfully imported ${totalImported} entries (${res.imported_transactions} expenses, ${res.imported_income} income)!`, 'success');

        $('#import-preview-card').style.display = 'none';
        $('#import-input-card').style.display = 'block';
        if ($('#import-text-area')) $('#import-text-area').value = '';
        importChosenFile = null;
        if ($('#chosen-file-name')) $('#chosen-file-name').style.display = 'none';

        switchView('dashboard');
        await refreshBudgetsAndDashboard();
      } catch (err) {
        showToast(err.message || 'Import failed', 'error');
      } finally {
        importConfirmSave.disabled = false;
        importConfirmSave.textContent = 'Import Selected Entries';
      }
    });
  }

  // ================================================================
  // ---------- Settings View & Web Push ----------
  // ================================================================

  const PRESET_AVATARS = [
    { id: 1, name: 'Prism', svg: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>' },
    { id: 2, name: 'Shield', svg: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>' },
    { id: 3, name: 'Coin', svg: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v12M8 10h8"/></svg>' },
    { id: 4, name: 'Bolt', svg: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>' },
    { id: 5, name: 'Star', svg: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>' },
    { id: 6, name: 'Compass', svg: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"/></svg>' },
    { id: 7, name: 'Crown', svg: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 4l3 12h14l3-12-6 7-4-7-4 7-6-7zm3 16h14v2H5v-2z"/></svg>' },
    { id: 8, name: 'Anchor', svg: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="5" r="3"/><line x1="12" y1="22" x2="12" y2="8"/><path d="M5 12H2a10 10 0 0 0 20 0h-3"/></svg>' },
  ];

  function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; ++i) {
      outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
  }

  async function loadSettings() {
    try {
      const [displayData, categoriesData, recurringData, budgetsData, goalsData, profileData] = await Promise.all([
        api('/api/user/display').catch(() => ({})),
        api('/api/categories').catch(() => ({ categories: [], custom: [] })),
        api('/api/recurring').catch(() => ({ recurring: [] })),
        api('/api/budgets').catch(() => ({ budgets: [] })),
        api('/api/goals').catch(() => ({ goals: [] })),
        api('/api/profile').catch(() => ({})),
      ]);

      // 1. Email and Username
      const emailDisplay = $('#settings-email-display');
      const usernameInput = $('#settings-username-input');
      if (emailDisplay) emailDisplay.value = displayData.email || (currentUser && currentUser.email) || '';
      if (usernameInput) usernameInput.value = displayData.username || '';

      // 2. Avatar Grid
      const avatarGrid = $('#avatar-grid');
      const currentAvatarId = displayData.avatar_id || 1;
      if (avatarGrid) {
        avatarGrid.innerHTML = PRESET_AVATARS.map((av) => `
          <button type="button" class="avatar-option ${av.id === currentAvatarId ? 'active' : ''}" data-id="${av.id}" title="${escapeHtml(av.name)}">
            ${av.svg}
          </button>
        `).join('');

        avatarGrid.querySelectorAll('.avatar-option').forEach((btn) => {
          btn.addEventListener('click', async () => {
            const aid = parseInt(btn.dataset.id, 10);
            avatarGrid.querySelectorAll('.avatar-option').forEach((b) => b.classList.remove('active'));
            btn.classList.add('active');
            try {
              await api('/api/user/avatar', {
                method: 'PATCH',
                body: JSON.stringify({ avatar_id: aid }),
              });
              if (currentUser) {
                currentUser.avatar_id = aid;
                currentUser.avatar_url = null;
                sessionStorage.setItem('abt_user', JSON.stringify(currentUser));
              }
              showToast('Avatar updated', 'success');
              updateUserUI();
            } catch (err) {
              showToast(err.message || 'Failed to update avatar', 'error');
            }
          });
        });
      }

      // Custom photo upload & remove wiring
      const fileInput = $('#avatar-photo-file-input');
      const uploadTrigger = $('#btn-trigger-photo-upload');
      const removePhotoBtn = $('#btn-remove-photo');
      const uploadError = $('#photo-upload-error');

      if (uploadTrigger && !uploadTrigger._bound) {
        uploadTrigger._bound = true;
        uploadTrigger.addEventListener('click', () => {
          if (uploadError) uploadError.style.display = 'none';
          fileInput?.click();
        });
      }

      if (fileInput && !fileInput._bound) {
        fileInput._bound = true;
        fileInput.addEventListener('change', async (e) => {
          const file = e.target.files && e.target.files[0];
          if (!file) return;

          if (uploadError) uploadError.style.display = 'none';

          // Validate format by content type (JPG and PNG only, reject GIFs)
          const allowedTypes = ['image/jpeg', 'image/png', 'image/jpg'];
          if (!allowedTypes.includes(file.type.toLowerCase())) {
            const errMsg = 'Only JPG and PNG images are supported.';
            if (uploadError) {
              uploadError.textContent = errMsg;
              uploadError.style.display = 'block';
            }
            showToast(errMsg, 'error');
            fileInput.value = '';
            return;
          }

          // Validate max size 2 MB
          if (file.size > 2 * 1024 * 1024) {
            const errMsg = 'Photo size must be 2 MB or less.';
            if (uploadError) {
              uploadError.textContent = errMsg;
              uploadError.style.display = 'block';
            }
            showToast(errMsg, 'error');
            fileInput.value = '';
            return;
          }

          uploadTrigger.disabled = true;
          uploadTrigger.textContent = 'Uploading...';

          try {
            const formData = new FormData();
            formData.append('file', file);
            const res = await api('/api/user/avatar-upload', {
              method: 'POST',
              body: formData,
            });

            if (currentUser) {
              currentUser.avatar_url = res.avatar_url;
              sessionStorage.setItem('abt_user', JSON.stringify(currentUser));
            }
            updateUserUI();
            showToast('Profile photo updated successfully', 'success');
          } catch (err) {
            const errMsg = err.message || 'Failed to upload photo';
            if (uploadError) {
              uploadError.textContent = errMsg;
              uploadError.style.display = 'block';
            }
            showToast(errMsg, 'error');
          } finally {
            uploadTrigger.disabled = false;
            uploadTrigger.textContent = 'Upload Photo';
            fileInput.value = '';
          }
        });
      }

      if (removePhotoBtn && !removePhotoBtn._bound) {
        removePhotoBtn._bound = true;
        removePhotoBtn.addEventListener('click', async () => {
          removePhotoBtn.disabled = true;
          removePhotoBtn.textContent = 'Removing...';
          try {
            await api('/api/user/avatar-photo', { method: 'DELETE' });
            if (currentUser) {
              currentUser.avatar_url = null;
              sessionStorage.setItem('abt_user', JSON.stringify(currentUser));
            }
            updateUserUI();
            showToast('Profile photo removed', 'success');
          } catch (err) {
            showToast(err.message || 'Failed to remove photo', 'error');
          } finally {
            removePhotoBtn.disabled = false;
            removePhotoBtn.textContent = 'Remove photo';
          }
        });
      }

      // Sync display data to currentUser
      if (displayData && currentUser) {
        if (displayData.username) currentUser.username = displayData.username;
        if (displayData.avatar_id) currentUser.avatar_id = displayData.avatar_id;
        if (displayData.avatar_url !== undefined) currentUser.avatar_url = displayData.avatar_url;
        sessionStorage.setItem('abt_user', JSON.stringify(currentUser));
        updateUserUI();
      }

      // 3. Web Push State
      await checkAndUpdatePushState();

      // 4. Custom Categories
      renderSettingsCategories(categoriesData.custom || []);

      // 5. Budget Manager
      renderSettingsBudgets(budgetsData.budgets || [], categoriesData.categories || []);

      // 6. Savings Goals
      renderSettingsGoals(goalsData.goals || []);

      // 7. Recurring Bills List
      renderSettingsRecurring(recurringData.recurring || []);

      // 8. Financial Profile (Living Situation & Risk Comfort)
      const livingSelect = $('#profile-living-situation');
      const riskSelect = $('#profile-risk-comfort');
      const savedIndicator = $('#profile-saved-indicator');

      if (livingSelect && profileData && profileData.living_situation) {
        livingSelect.value = profileData.living_situation;
      }
      if (riskSelect && profileData && profileData.risk_comfort) {
        riskSelect.value = profileData.risk_comfort;
      }

      async function saveFinancialProfile() {
        const living = livingSelect?.value;
        const risk = riskSelect?.value;
        try {
          await api('/api/profile', {
            method: 'PATCH',
            body: JSON.stringify({
              living_situation: living,
              risk_comfort: risk,
            }),
          });
          if (savedIndicator) {
            savedIndicator.style.display = 'inline-block';
            setTimeout(() => {
              savedIndicator.style.display = 'none';
            }, 2500);
          }
        } catch (err) {
          showToast(err.message || 'Failed to update financial profile', 'error');
        }
      }

      if (livingSelect && !livingSelect._boundChange) {
        livingSelect._boundChange = true;
        livingSelect.addEventListener('change', saveFinancialProfile);
      }
      if (riskSelect && !riskSelect._boundChange) {
        riskSelect._boundChange = true;
        riskSelect.addEventListener('change', saveFinancialProfile);
      }

    } catch (err) {
      console.error('loadSettings error:', err);
    }
  }

  function updateUserAvatarHeader(avatarId) {
    if (currentUser) {
      currentUser.avatar_id = avatarId;
      currentUser.avatar_url = null;
      sessionStorage.setItem('abt_user', JSON.stringify(currentUser));
    }
    updateUserUI();
  }

  // Save username
  const saveUsernameBtn = $('#btn-save-username');
  if (saveUsernameBtn && !saveUsernameBtn._bound) {
    saveUsernameBtn._bound = true;
    saveUsernameBtn.addEventListener('click', async () => {
      const val = $('#settings-username-input')?.value?.trim();
      if (!val || val.length < 3 || val.length > 20) {
        showToast('Username must be 3-20 characters', 'error');
        return;
      }
      try {
        await api('/api/user/username', {
          method: 'PATCH',
          body: JSON.stringify({ username: val }),
        });
        if (currentUser) {
          currentUser.username = val;
          sessionStorage.setItem('abt_user', JSON.stringify(currentUser));
        }
        showToast('Username saved successfully', 'success');
        updateUserUI();
      } catch (err) {
        showToast(err.message || 'Failed to save username', 'error');
      }
    });
  }

  // ---------- Maintenance Status ----------
  async function checkMaintenanceStatus() {
    const mb = document.getElementById('maintenance-banner');
    if (!mb) return;
    const isOnboarding = onboardingScreen && onboardingScreen.style.display !== 'none';
    const isAuth = authScreen && authScreen.style.display !== 'none';
    if (!authToken || !currentUser || isAuth || isOnboarding) {
      mb.style.display = 'none';
      return;
    }
    try {
      const data = await api('/api/app-status');
      mb.style.display = (data && data.maintenance_mode) ? 'block' : 'none';
    } catch (e) {
      mb.style.display = 'none';
    }
  }

  // ---------- Change Password Handlers ----------
  const btnSubmitChangePwd = $('#btn-submit-change-password');
  const inputCurrPwd = $('#input-current-password');
  const inputNewPwd = $('#input-new-password');
  const inputConfirmPwd = $('#input-confirm-password');
  const alertChangePwd = $('#change-pwd-alert');
  const errNewPwdLen = $('#err-new-pwd-len');
  const errConfirmMismatch = $('#err-confirm-mismatch');

  function showChangePwdAlert(msg, type) {
    if (!alertChangePwd) return;
    alertChangePwd.style.display = 'block';
    alertChangePwd.textContent = msg;
    if (type === 'success') {
      alertChangePwd.style.background = 'rgba(16, 185, 129, 0.15)';
      alertChangePwd.style.color = '#34d399';
      alertChangePwd.style.border = '1px solid rgba(16, 185, 129, 0.3)';
    } else if (type === 'warning') {
      alertChangePwd.style.background = 'rgba(245, 158, 11, 0.15)';
      alertChangePwd.style.color = '#fbbf24';
      alertChangePwd.style.border = '1px solid rgba(245, 158, 11, 0.3)';
    } else {
      alertChangePwd.style.background = 'rgba(239, 68, 68, 0.15)';
      alertChangePwd.style.color = '#f87171';
      alertChangePwd.style.border = '1px solid rgba(239, 68, 68, 0.3)';
    }
  }

  function validateChangePwdInline() {
    let valid = true;
    const newP = inputNewPwd ? inputNewPwd.value : '';
    const confP = inputConfirmPwd ? inputConfirmPwd.value : '';

    if (newP.length > 0 && newP.length < 8) {
      if (errNewPwdLen) errNewPwdLen.style.display = 'block';
      valid = false;
    } else {
      if (errNewPwdLen) errNewPwdLen.style.display = 'none';
    }

    if (confP.length > 0 && newP !== confP) {
      if (errConfirmMismatch) errConfirmMismatch.style.display = 'block';
      valid = false;
    } else {
      if (errConfirmMismatch) errConfirmMismatch.style.display = 'none';
    }
    return valid;
  }

  if (inputNewPwd) inputNewPwd.addEventListener('input', validateChangePwdInline);
  if (inputConfirmPwd) inputConfirmPwd.addEventListener('input', validateChangePwdInline);

  if (btnSubmitChangePwd) {
    btnSubmitChangePwd.addEventListener('click', async () => {
      const curr = inputCurrPwd ? inputCurrPwd.value : '';
      const newP = inputNewPwd ? inputNewPwd.value : '';
      const conf = inputConfirmPwd ? inputConfirmPwd.value : '';

      if (!curr) {
        showChangePwdAlert('Current password is required', 'error');
        return;
      }
      if (newP.length < 8) {
        if (errNewPwdLen) errNewPwdLen.style.display = 'block';
        showChangePwdAlert('New password must be at least 8 characters long', 'error');
        return;
      }
      if (newP !== conf) {
        if (errConfirmMismatch) errConfirmMismatch.style.display = 'block';
        showChangePwdAlert('New passwords do not match', 'error');
        return;
      }
      if (newP === curr) {
        showChangePwdAlert('New password cannot be identical to current password', 'error');
        return;
      }

      btnSubmitChangePwd.disabled = true;
      btnSubmitChangePwd.textContent = 'Updating...';
      try {
        await api('/api/account/change-password', {
          method: 'POST',
          body: JSON.stringify({
            current_password: curr,
            new_password: newP,
          }),
        });
        showChangePwdAlert('Password updated successfully', 'success');
        if (inputCurrPwd) inputCurrPwd.value = '';
        if (inputNewPwd) inputNewPwd.value = '';
        if (inputConfirmPwd) inputConfirmPwd.value = '';
        if (errNewPwdLen) errNewPwdLen.style.display = 'none';
        if (errConfirmMismatch) errConfirmMismatch.style.display = 'none';
        if (currentUser) currentUser.force_password_reset = false;
        sessionStorage.setItem('abt_user', JSON.stringify(currentUser));
        showToast('Password updated successfully', 'success');
      } catch (err) {
        showChangePwdAlert(err.message || 'Failed to update password', 'error');
      } finally {
        btnSubmitChangePwd.disabled = false;
        btnSubmitChangePwd.textContent = 'Update Password';
      }
    });
  }

  // Web Push Subscription Handlers
  async function performPushSubscribe(reg, vapidData) {
    // 1. Check if existing subscription found; always unsubscribe first
    const existing = await reg.pushManager.getSubscription();
    if (existing) {
      console.log('[PUSH] Existing subscription found, unsubscribing first to refresh key...');
      try {
        await existing.unsubscribe();
      } catch (unsubErr) {
        console.warn('[PUSH] Unsubscribe error:', unsubErr);
      }
    }

    // 2. Subscribe with current VAPID key
    const convertedKey = urlBase64ToUint8Array(vapidData.public_key);
    const newSub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: convertedKey,
    });

    // 3. Extract keys
    const p256dh = btoa(String.fromCharCode.apply(null, new Uint8Array(newSub.getKey('p256dh'))));
    const auth = btoa(String.fromCharCode.apply(null, new Uint8Array(newSub.getKey('auth'))));

    // 4. Send the new subscription to backend
    await api('/api/push/subscribe', {
      method: 'POST',
      body: JSON.stringify({
        endpoint: newSub.endpoint,
        keys: { p256dh, auth },
        preferences: {
          budget_alerts: $('#pref-budget-alerts')?.checked ?? true,
          bill_reminders: $('#pref-bill-reminders')?.checked ?? true,
          weekly_recap: $('#pref-weekly-recap')?.checked ?? true,
        },
      }),
    });

    // 5. Store key_hash in localStorage
    if (vapidData.key_hash) {
      localStorage.setItem('saarth_vapid_hash', vapidData.key_hash);
    }

    return newSub;
  }

  async function checkAndUpdatePushState() {
    const toggleBtn = $('#btn-toggle-push');
    if (!toggleBtn) return;

    if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) {
      toggleBtn.disabled = true;
      toggleBtn.textContent = 'Push Not Supported in Browser';
      return;
    }

    if (Notification.permission === 'denied') {
      toggleBtn.disabled = true;
      toggleBtn.textContent = 'Permission Blocked';
      return;
    }

    try {
      const reg = await navigator.serviceWorker.ready;
      let sub = await reg.pushManager.getSubscription();

      // Check if VAPID key has changed while subscription exists
      if (sub) {
        try {
          const vapidData = await api('/api/push/vapid-key');
          const storedHash = localStorage.getItem('saarth_vapid_hash');
          if (vapidData && vapidData.key_hash) {
            if (storedHash && storedHash !== vapidData.key_hash) {
              console.log('[PUSH] VAPID key changed (stored:', storedHash, '!= current:', vapidData.key_hash, '). Auto-resubscribing...');
              sub = await performPushSubscribe(reg, vapidData);
            } else if (!storedHash) {
              localStorage.setItem('saarth_vapid_hash', vapidData.key_hash);
            }
          }
        } catch (syncErr) {
          console.warn('[PUSH] Key version check error:', syncErr);
        }
      }

      if (sub) {
        toggleBtn.textContent = 'Disable Push Notifications';
        toggleBtn.classList.remove('btn-secondary');
        toggleBtn.classList.add('btn-primary');
      } else {
        toggleBtn.textContent = 'Enable Push Notifications';
        toggleBtn.classList.remove('btn-primary');
        toggleBtn.classList.add('btn-secondary');
      }
    } catch (e) {
      // Ignored
    }
  }

  const togglePushBtn = $('#btn-toggle-push');
  if (togglePushBtn) {
    togglePushBtn.addEventListener('click', async () => {
      togglePushBtn.disabled = true;
      try {
        const reg = await navigator.serviceWorker.ready;
        const sub = await reg.pushManager.getSubscription();

        if (sub) {
          // Toggle OFF flow:
          // Unsubscribe on browser side AND call POST /api/push/unsubscribe on backend
          const ep = sub.endpoint;
          try {
            await sub.unsubscribe();
          } catch (unsubErr) {
            console.warn('[PUSH] Unsubscribe error:', unsubErr);
          }
          await api('/api/push/unsubscribe', {
            method: 'POST',
            body: JSON.stringify({ endpoint: ep }),
          }).catch(() => null);
          showToast('Web Push notifications disabled', 'info');
        } else {
          // Toggle ON flow:
          const perm = await Notification.requestPermission();
          if (perm !== 'granted') {
            showToast('Notification permission was not granted', 'error');
            await checkAndUpdatePushState();
            return;
          }

          const vapidData = await api('/api/push/vapid-key');
          await performPushSubscribe(reg, vapidData);
          showToast('Web Push notifications activated!', 'success');
        }
      } catch (err) {
        showToast(err.message || 'Push toggle failed', 'error');
      } finally {
        togglePushBtn.disabled = false;
        await checkAndUpdatePushState();
      }
    });
  }

  const testPushBtn = $('#btn-test-push');
  if (testPushBtn) {
    testPushBtn.addEventListener('click', async () => {
      testPushBtn.disabled = true;
      testPushBtn.textContent = 'Sending...';
      try {
        await api('/api/push/test', { method: 'POST' });
        showToast('Test push notification triggered! Check your system notification tray.', 'success');
      } catch (err) {
        showToast(err.message || 'Could not send test notification. Ensure push is enabled first.', 'error');
      } finally {
        testPushBtn.disabled = false;
        testPushBtn.textContent = 'Send Test Push Notification';
      }
    });
  }

  // Categories in Settings
  function renderSettingsCategories(customCats) {
    const listEl = $('#custom-categories-list');
    if (!listEl) return;

    if (customCats.length === 0) {
      listEl.innerHTML = '<span style="color:var(--text-tertiary);font-size:12px;">No custom categories added yet.</span>';
      return;
    }

    listEl.innerHTML = customCats.map((cat) => `
      <span class="custom-cat-chip" style="display:inline-flex;align-items:center;gap:6px;padding:4px 10px;background:var(--bg-elevated);border:1px solid var(--border-medium);border-radius:var(--radius-pill);font-size:12px;">
        ${escapeHtml(cat)}
        <button type="button" class="btn-del-cat" data-name="${escapeHtml(cat)}" style="background:none;border:none;cursor:pointer;color:var(--danger);font-size:14px;padding:0 2px;line-height:1;">&times;</button>
      </span>
    `).join('');

    listEl.querySelectorAll('.btn-del-cat').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const catName = btn.dataset.name;
        try {
          await api(`/api/categories/${encodeURIComponent(catName)}`, { method: 'DELETE' });
          showToast(`Category "${catName}" removed`, 'success');
          loadSettings();
        } catch (err) {
          showToast(err.message || 'Failed to remove category', 'error');
        }
      });
    });
  }

  const addCategoryBtn = $('#btn-add-category');
  if (addCategoryBtn) {
    addCategoryBtn.addEventListener('click', async () => {
      const input = $('#new-category-input');
      const val = input?.value?.trim();
      if (!val) {
        showToast('Please enter a category name', 'error');
        return;
      }
      try {
        await api('/api/categories', {
          method: 'POST',
          body: JSON.stringify({ name: val }),
        });
        showToast(`Category "${val}" added!`, 'success');
        if (input) input.value = '';
        loadSettings();
      } catch (err) {
        showToast(err.message || 'Failed to add category', 'error');
      }
    });
  }

  // ================================================================
  // ---------- MANUAL ENTRY & MANAGEMENT SUITE ----------
  // ================================================================

  let allCachedCategories = [];

  async function loadAllCategories() {
    try {
      const data = await api('/api/categories');
      allCachedCategories = data.categories || [];
    } catch (e) {
      allCachedCategories = [
        'food', 'groceries', 'travel', 'rent', 'bills', 'entertainment',
        'shopping', 'health', 'other', 'eating out', 'utilities',
        'personal care', 'emergency fund', 'sip / investments', 'miscellaneous'
      ];
    }
    populateCategoryDropdowns();
    return allCachedCategories;
  }

  function populateCategoryDropdowns() {
    const dropdowns = [
      '#qa-category',
      '#expense-category',
      '#tx-category-filter',
      '#budget-add-category',
      '#rec-edit-category',
      '#rec-category'
    ];
    const cats = allCachedCategories.length > 0 ? allCachedCategories : ['food', 'travel', 'shopping', 'bills', 'other'];

    dropdowns.forEach((sel) => {
      const el = $(sel);
      if (!el) return;
      const curVal = el.value;
      let html = '';
      if (sel === '#tx-category-filter') {
        html = '<option value="">All Categories</option>';
      }
      cats.forEach((c) => {
        const cap = c.charAt(0).toUpperCase() + c.slice(1);
        html += `<option value="${escapeHtml(c)}">${escapeHtml(cap)}</option>`;
      });
      el.innerHTML = html;
      if (curVal) el.value = curVal;
    });
  }

  // ---------- Quick-Add Bar ----------
  function renderQuickAddBar(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const todayStr = new Date().toISOString().slice(0, 10);
    const formId = containerId + '-form';
    const amtId = containerId + '-amt';
    const catId = containerId + '-cat';
    const noteId = containerId + '-note';
    const dateId = containerId + '-date';
    const tagId = containerId + '-tag';
    const btnId = containerId + '-btn';

    let catOpts = '';
    const cats = allCachedCategories.length > 0 ? allCachedCategories : [
      'food', 'groceries', 'travel', 'rent', 'bills', 'entertainment',
      'shopping', 'health', 'other'
    ];
    cats.forEach((c) => {
      const cap = c.charAt(0).toUpperCase() + c.slice(1);
      catOpts += `<option value="${escapeHtml(c)}">${escapeHtml(cap)}</option>`;
    });

    container.innerHTML = `
      <div class="quick-add-bar-wrap">
        <div class="quick-add-header">
          <span class="quick-add-title">Quick Log Expense</span>
        </div>
        <form class="quick-add-form" id="${formId}" onsubmit="return false;">
          <div class="quick-add-field quick-add-amount-wrap" data-tooltip="Enter the amount spent">
            <label for="${amtId}">Amount *</label>
            <input type="number" id="${amtId}" class="form-input quick-add-input" placeholder="₹0.00" step="0.01" min="0.01" required data-tooltip="Enter the amount spent">
          </div>
          <div class="quick-add-field" data-tooltip="Choose the spending category">
            <label for="${catId}">Category *</label>
            <select id="${catId}" class="form-input quick-add-select" required data-tooltip="Choose the spending category">
              ${catOpts}
            </select>
          </div>
          <div class="quick-add-field quick-add-note-wrap" data-tooltip="Optional note about this expense">
            <label for="${noteId}">Note</label>
            <input type="text" id="${noteId}" class="form-input quick-add-input" placeholder="e.g. Lunch with team" data-tooltip="Optional note about this expense">
          </div>
          <div class="quick-add-field quick-add-date-wrap" data-tooltip="Date of expense (defaults to today)">
            <label for="${dateId}">Date</label>
            <input type="date" id="${dateId}" class="form-input quick-add-input" value="${todayStr}" required data-tooltip="Date of expense (defaults to today)">
          </div>
          <div class="quick-add-field quick-add-tag-wrap" data-tooltip="Add a tag like 'work' or 'trip' to filter later">
            <label for="${tagId}">Tag</label>
            <input type="text" id="${tagId}" class="form-input quick-add-input" placeholder="e.g. office" data-tooltip="Add a tag like 'work' or 'trip' to filter later">
          </div>
          <div class="quick-add-btn-wrap">
            <button type="submit" class="btn-primary quick-add-submit-btn" id="${btnId}" data-tooltip="Save this expense to your tracker">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px;"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
              <span>Add</span>
            </button>
          </div>
        </form>
      </div>
    `;

    const form = document.getElementById(formId);
    if (!form) return;
    form.addEventListener('submit', async () => {
      const amtInput = document.getElementById(amtId);
      const catSelect = document.getElementById(catId);
      const noteInput = document.getElementById(noteId);
      const dateInput = document.getElementById(dateId);
      const tagInput = document.getElementById(tagId);
      const submitBtn = document.getElementById(btnId);

      const amount = parseFloat(amtInput?.value);
      const category = catSelect?.value;
      const note = noteInput?.value?.trim() || '';
      const entryDate = dateInput?.value || todayStr;
      const rawTag = tagInput?.value?.trim() || '';
      const tags = rawTag ? rawTag.split(/[\s,]+/).map((t) => t.trim().replace(/^#/, '')).filter(Boolean) : [];

      if (isNaN(amount) || amount <= 0) {
        showToast('Please enter a valid expense amount', 'error');
        if (amtInput) amtInput.focus();
        return;
      }
      if (!category) {
        showToast('Please choose a category', 'error');
        return;
      }

      submitBtn.disabled = true;
      submitBtn.innerHTML = '<span>Saving...</span>';

      try {
        await api('/api/transactions', {
          method: 'POST',
          body: JSON.stringify({
            amount,
            category,
            note,
            entry_date: entryDate,
            tags,
          }),
        });

        showToast(`Logged ₹${amount.toFixed(2)} under ${category}`, 'success');
        showUndoToast('Expense logged');
        if (amtInput) amtInput.value = '';
        if (noteInput) noteInput.value = '';
        if (tagInput) tagInput.value = '';
        if (dateInput) dateInput.value = todayStr;

        await refreshBudgetsAndDashboard();
      } catch (err) {
        showToast(err.message || 'Failed to log expense', 'error');
      } finally {
        submitBtn.disabled = false;
        submitBtn.innerHTML = `
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px;"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          <span>Add</span>
        `;
      }
    });
  }

  // ---------- Full Transactions View ----------
  let txSelectedIds = new Set();
  let currentTransactionsData = [];

  async function loadTransactionsView() {
    console.log("LOAD_TRANSACTIONS_VIEW_START");
    window.loadTransactionsView = loadTransactionsView;
    renderQuickAddBar('tx-quick-add-wrap');
    populateCategoryDropdowns();

    const loader = $('#tx-loader');
    const tableContainer = $('#tx-table-container');
    const totalCountEl = $('#tx-total-count');
    const totalSumEl = $('#tx-total-sum');

    if (loader) loader.style.display = 'flex';

    // Parse filters
    const query = $('#tx-search-input')?.value?.trim() || '';
    const category = $('#tx-category-filter')?.value || '';
    const preset = $('#tx-date-preset')?.value || 'this_month';
    const sortVal = $('#tx-sort-select')?.value || 'date_desc';

    let sortBy = 'date';
    let sortOrder = 'desc';
    if (sortVal === 'date_asc') { sortBy = 'date'; sortOrder = 'asc'; }
    else if (sortVal === 'amount_desc') { sortBy = 'amount'; sortOrder = 'desc'; }
    else if (sortVal === 'amount_asc') { sortBy = 'amount'; sortOrder = 'asc'; }
    else if (sortVal === 'category_asc') { sortBy = 'category'; sortOrder = 'asc'; }

    let startDate = null;
    let endDate = null;
    const now = new Date();

    const pad = (n) => String(n).padStart(2, '0');
    if (preset === 'this_month') {
      const y = now.getFullYear();
      const m = now.getMonth();
      const lastDay = new Date(y, m + 1, 0).getDate();
      startDate = `${y}-${pad(m + 1)}-01`;
      endDate = `${y}-${pad(m + 1)}-${pad(lastDay)}`;
    } else if (preset === 'last_month') {
      const prev = new Date(now.getFullYear(), now.getMonth() - 1, 1);
      const y = prev.getFullYear();
      const m = prev.getMonth();
      const lastDay = new Date(y, m + 1, 0).getDate();
      startDate = `${y}-${pad(m + 1)}-01`;
      endDate = `${y}-${pad(m + 1)}-${pad(lastDay)}`;
    } else if (preset === 'custom') {
      startDate = $('#tx-date-from')?.value || null;
      endDate = $('#tx-date-to')?.value || null;
    }

    try {
      const params = new URLSearchParams();
      if (query) params.append('query', query);
      if (category) params.append('category', category);
      if (startDate) params.append('start_date', startDate);
      if (endDate) params.append('end_date', endDate);
      params.append('sort_by', sortBy);
      params.append('sort_order', sortOrder);
      params.append('limit', '100');

      const data = await api('/api/transactions?' + params.toString());
      currentTransactionsData = data.transactions || [];

      if (totalCountEl) totalCountEl.textContent = `Showing ${currentTransactionsData.length} transaction${currentTransactionsData.length === 1 ? '' : 's'}`;
      const sum = currentTransactionsData.reduce((acc, t) => acc + (parseFloat(t.amount) || 0), 0);
      if (totalSumEl) totalSumEl.textContent = `Total: ${formatCurrency(sum)}`;

      renderTransactionsTable(currentTransactionsData);
    } catch (err) {
      if (tableContainer) {
        tableContainer.innerHTML = `<div class="empty-state" style="padding:32px;"><p style="color:var(--danger);">Failed to load transactions: ${escapeHtml(err.message)}</p></div>`;
      }
    } finally {
      if (loader) loader.style.display = 'none';
      updateTxBulkBar();
    }
  }

  function renderTransactionsTable(transactions) {
    const tableContainer = $('#tx-table-container');
    if (!tableContainer) return;

    if (transactions.length === 0) {
      tableContainer.innerHTML = `
        <div class="empty-state" style="padding:48px 20px;">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:36px;height:36px;opacity:0.25;margin-bottom:8px;">
            <rect x="2" y="4" width="20" height="16" rx="2"/>
            <line x1="6" y1="12" x2="18" y2="12"/>
          </svg>
          <p>No transactions found matching your criteria.</p>
        </div>
      `;
      return;
    }

    let rowsHtml = '';
    transactions.forEach((tx) => {
      const isSelected = txSelectedIds.has(tx.id);
      const tagsList = Array.isArray(tx.tags) ? tx.tags : [];
      const tagsHtml = tagsList.map((tag) => `<span class="txn-tag-chip">#${escapeHtml(tag)}</span>`).join('');
      const merchantDisplay = tx.merchant ? escapeHtml(tx.merchant) : '<span style="color:var(--text-tertiary);">--</span>';

      rowsHtml += `
        <tr data-id="${tx.id}">
          <td style="width:36px;text-align:center;">
            <input type="checkbox" class="tx-select-cb" data-id="${tx.id}" ${isSelected ? 'checked' : ''}>
          </td>
          <td style="white-space:nowrap;font-size:12px;color:var(--text-secondary);">${formatDate(tx.date)}</td>
          <td><strong>${merchantDisplay}</strong></td>
          <td><span class="txn-category">${escapeHtml(tx.category)}</span></td>
          <td style="color:var(--text-secondary);max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
            ${escapeHtml(tx.note || '')}
            ${tagsHtml ? `<div style="margin-top:2px;">${tagsHtml}</div>` : ''}
          </td>
          <td style="text-align:right;font-weight:600;white-space:nowrap;">${formatCurrency(tx.amount)}</td>
          <td style="width:90px;text-align:right;white-space:nowrap;">
            <div class="txn-row-actions">
              <button class="btn-icon-action btn-edit-tx" data-id="${tx.id}" title="Edit transaction">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px;"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
              </button>
              <button class="btn-icon-action btn-add-bill-tx" data-tx-id="${tx.id}" title="Attach bill/receipt">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px;"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
              </button>
              <button class="btn-icon-action danger btn-del-tx" data-id="${tx.id}" title="Delete transaction">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px;"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
              </button>
            </div>
          </td>
        </tr>
      `;
    });

    tableContainer.innerHTML = `
      <table class="txn-manage-table">
        <thead>
          <tr>
            <th style="width:36px;text-align:center;"><input type="checkbox" id="tx-select-all-cb"></th>
            <th>Date</th>
            <th>Merchant</th>
            <th>Category</th>
            <th>Note / Tags</th>
            <th style="text-align:right;">Amount</th>
            <th style="text-align:right;">Actions</th>
          </tr>
        </thead>
        <tbody>
          ${rowsHtml}
        </tbody>
      </table>
    `;

    // Row selection checkboxes
    tableContainer.querySelectorAll('.tx-select-cb').forEach((cb) => {
      cb.addEventListener('change', () => {
        const id = parseInt(cb.dataset.id, 10);
        if (cb.checked) txSelectedIds.add(id);
        else txSelectedIds.delete(id);
        updateTxBulkBar();
      });
    });

    // Select-all checkbox
    const selectAllCb = document.getElementById('tx-select-all-cb');
    if (selectAllCb) {
      selectAllCb.addEventListener('change', () => {
        const isChecked = selectAllCb.checked;
        tableContainer.querySelectorAll('.tx-select-cb').forEach((cb) => {
          cb.checked = isChecked;
          const id = parseInt(cb.dataset.id, 10);
          if (isChecked) txSelectedIds.add(id);
          else txSelectedIds.delete(id);
        });
        updateTxBulkBar();
      });
    }

    // Edit expense row handlers
    tableContainer.querySelectorAll('.btn-edit-tx').forEach((btn) => {
      btn.addEventListener('click', () => {
        const id = parseInt(btn.dataset.id, 10);
        const tx = currentTransactionsData.find((t) => t.id === id);
        if (tx) openExpenseModal(tx);
      });
    });

    // Delete expense row handlers
    tableContainer.querySelectorAll('.btn-del-tx').forEach((btn) => {
      btn.addEventListener('click', () => {
        const id = parseInt(btn.dataset.id, 10);
        const tx = currentTransactionsData.find((t) => t.id === id);
        const amtStr = tx ? formatCurrency(tx.amount) : 'this expense';
        openSimpleConfirmModal(
          'Delete Expense',
          `Are you sure you want to delete ${amtStr}?`,
          async () => {
            await api(`/api/transactions/${id}`, { method: 'DELETE' });
            showToast('Expense deleted', 'success');
            showUndoToast('Expense deleted');
            txSelectedIds.delete(id);
            await refreshBudgetsAndDashboard();
          }
        );
      });
    });

    // Add bill on transaction
    tableContainer.querySelectorAll('.btn-add-bill-tx').forEach((btn) => {
      btn.addEventListener('click', () => {
        openAddBillModal(btn.dataset.txId);
      });
    });
  }

  function updateTxBulkBar() {
    const bulkBar = $('#tx-bulk-bar');
    const bulkCount = $('#tx-bulk-count');
    if (!bulkBar) return;

    if (txSelectedIds.size > 0) {
      bulkBar.style.display = 'flex';
      if (bulkCount) bulkCount.textContent = `${txSelectedIds.size} transaction${txSelectedIds.size === 1 ? '' : 's'} selected`;
    } else {
      bulkBar.style.display = 'none';
    }
  }

  // Bulk delete modal
  const bulkDeleteBtn = $('#tx-bulk-delete-btn');
  const bulkDeleteDesc = $('#bulk-delete-desc');
  const bulkDeleteTypedWrap = $('#bulk-delete-typed-wrap');
  const bulkDeleteTypedInput = $('#bulk-delete-typed-input');
  const bulkDeleteActionBtn = $('#bulk-delete-action-btn');
  const bulkDeleteClose = $('#bulk-delete-close');
  const bulkDeleteCancel = $('#bulk-delete-cancel-btn');

  if (bulkDeleteClose) bulkDeleteClose.addEventListener('click', () => closeModal('#modal-bulk-delete', true));
  if (bulkDeleteCancel) bulkDeleteCancel.addEventListener('click', () => closeModal('#modal-bulk-delete', true));

  if (bulkDeleteBtn) {
    bulkDeleteBtn.addEventListener('click', () => {
      const count = txSelectedIds.size;
      if (count === 0) return;

      if (bulkDeleteDesc) {
        bulkDeleteDesc.textContent = `Are you sure you want to permanently delete ${count} transaction${count === 1 ? '' : 's'}?`;
      }

      if (count > 10) {
        if (bulkDeleteTypedWrap) bulkDeleteTypedWrap.style.display = 'block';
        if (bulkDeleteTypedInput) {
          bulkDeleteTypedInput.value = '';
          bulkDeleteTypedInput.oninput = () => {
            if (bulkDeleteActionBtn) {
              bulkDeleteActionBtn.disabled = bulkDeleteTypedInput.value.trim() !== 'DELETE';
            }
          };
        }
        if (bulkDeleteActionBtn) bulkDeleteActionBtn.disabled = true;
      } else {
        if (bulkDeleteTypedWrap) bulkDeleteTypedWrap.style.display = 'none';
        if (bulkDeleteActionBtn) bulkDeleteActionBtn.disabled = false;
      }

      openModal('#modal-bulk-delete');
    });
  }

  if (bulkDeleteActionBtn) {
    bulkDeleteActionBtn.addEventListener('click', async () => {
      const ids = Array.from(txSelectedIds);
      if (ids.length === 0) return;

      bulkDeleteActionBtn.disabled = true;
      bulkDeleteActionBtn.textContent = 'Deleting...';

      try {
        const res = await api('/api/transactions/bulk-delete', {
          method: 'POST',
          body: JSON.stringify({ transaction_ids: ids }),
        });

        showToast(`Deleted ${res.deleted_count} transactions`, 'success');
        txSelectedIds.clear();
        closeModal('#modal-bulk-delete', true);
        await refreshBudgetsAndDashboard();
      } catch (err) {
        showToast(err.message || 'Bulk delete failed', 'error');
      } finally {
        bulkDeleteActionBtn.disabled = false;
        bulkDeleteActionBtn.textContent = 'Delete Selected';
      }
    });
  }

  // Transaction filter event listeners
  const txSearchInput = $('#tx-search-input');
  if (txSearchInput) {
    let debounceTimer = null;
    txSearchInput.addEventListener('input', () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => loadTransactionsView(), 300);
    });
  }

  const txCatFilter = $('#tx-category-filter');
  if (txCatFilter) {
    txCatFilter.addEventListener('change', () => loadTransactionsView());
  }

  const txDatePreset = $('#tx-date-preset');
  const txCustomDateRow = $('#tx-custom-date-row');
  if (txDatePreset) {
    txDatePreset.addEventListener('change', () => {
      if (txCustomDateRow) {
        txCustomDateRow.style.display = txDatePreset.value === 'custom' ? 'block' : 'none';
      }
      if (txDatePreset.value !== 'custom') {
        loadTransactionsView();
      }
    });
  }

  const txDateFrom = $('#tx-date-from');
  const txDateTo = $('#tx-date-to');
  if (txDateFrom) txDateFrom.addEventListener('change', () => loadTransactionsView());
  if (txDateTo) txDateTo.addEventListener('change', () => loadTransactionsView());

  const txSortSelect = $('#tx-sort-select');
  if (txSortSelect) txSortSelect.addEventListener('change', () => loadTransactionsView());

  // ---------- Add / Edit Expense Modal ----------
  let expenseFormInitial = '';

  function openExpenseModal(tx = null) {
    populateCategoryDropdowns();
    const modal = $('#modal-expense-entry');
    const titleEl = $('#expense-modal-title');
    const editIdInput = $('#expense-edit-id');
    const amtInput = $('#expense-amount');
    const catSelect = $('#expense-category');
    const dateInput = $('#expense-date');
    const merchInput = $('#expense-merchant');
    const noteInput = $('#expense-note');
    const tagsInput = $('#expense-tags');
    const errEl = $('#expense-modal-error');

    if (!modal) return;
    if (errEl) errEl.style.display = 'none';

    const todayStr = new Date().toISOString().slice(0, 10);

    if (tx) {
      if (titleEl) titleEl.textContent = 'Edit Expense';
      if (editIdInput) editIdInput.value = tx.id;
      if (amtInput) amtInput.value = tx.amount;
      if (catSelect) catSelect.value = (tx.category || '').toLowerCase();
      if (dateInput) {
        dateInput.value = tx.date ? tx.date.slice(0, 10) : todayStr;
      }
      if (merchInput) merchInput.value = tx.merchant || '';
      if (noteInput) noteInput.value = tx.note || '';
      if (tagsInput) tagsInput.value = (tx.tags || []).join(', ');
    } else {
      if (titleEl) titleEl.textContent = 'Add Expense';
      if (editIdInput) editIdInput.value = '';
      if (amtInput) amtInput.value = '';
      if (dateInput) dateInput.value = todayStr;
      if (merchInput) merchInput.value = '';
      if (noteInput) noteInput.value = '';
      if (tagsInput) tagsInput.value = '';
    }

    expenseFormInitial = JSON.stringify({
      amt: amtInput?.value,
      cat: catSelect?.value,
      date: dateInput?.value,
      merch: merchInput?.value,
      note: noteInput?.value,
      tags: tagsInput?.value,
    });

    openModal('#modal-expense-entry', () => {
      const cur = JSON.stringify({
        amt: amtInput?.value,
        cat: catSelect?.value,
        date: dateInput?.value,
        merch: merchInput?.value,
        note: noteInput?.value,
        tags: tagsInput?.value,
      });
      return cur !== expenseFormInitial;
    });
  }

  const btnOpenAddExpenseModal = $('#btn-open-add-expense-modal');
  if (btnOpenAddExpenseModal) {
    btnOpenAddExpenseModal.addEventListener('click', () => openExpenseModal(null));
  }

  const expenseModalClose = $('#expense-modal-close');
  const expenseCancelBtn = $('#expense-cancel-btn');
  const expenseSaveBtn = $('#expense-save-btn');

  if (expenseModalClose) expenseModalClose.addEventListener('click', () => closeModal('#modal-expense-entry'));
  if (expenseCancelBtn) expenseCancelBtn.addEventListener('click', () => closeModal('#modal-expense-entry'));

  if (expenseSaveBtn) {
    expenseSaveBtn.addEventListener('click', async () => {
      const editId = $('#expense-edit-id')?.value;
      const amtInput = $('#expense-amount');
      const catSelect = $('#expense-category');
      const dateInput = $('#expense-date');
      const merchInput = $('#expense-merchant');
      const noteInput = $('#expense-note');
      const tagsInput = $('#expense-tags');
      const errEl = $('#expense-modal-error');

      const amount = parseFloat(amtInput?.value);
      const category = catSelect?.value;
      const entryDate = dateInput?.value;
      const merchant = merchInput?.value?.trim() || null;
      const note = noteInput?.value?.trim() || '';
      const rawTags = tagsInput?.value?.trim() || '';
      const tags = rawTags ? rawTags.split(/[\s,]+/).map((t) => t.trim().replace(/^#/, '')).filter(Boolean) : [];

      if (isNaN(amount) || amount <= 0) {
        if (errEl) { errEl.textContent = 'Please enter a valid amount greater than zero.'; errEl.style.display = 'block'; }
        if (amtInput) amtInput.focus();
        return;
      }
      if (!category) {
        if (errEl) { errEl.textContent = 'Please select a category.'; errEl.style.display = 'block'; }
        return;
      }
      if (!entryDate) {
        if (errEl) { errEl.textContent = 'Please pick a transaction date.'; errEl.style.display = 'block'; }
        return;
      }

      expenseSaveBtn.disabled = true;
      expenseSaveBtn.textContent = 'Saving...';

      try {
        if (editId) {
          await api(`/api/transactions/${editId}`, {
            method: 'PUT',
            body: JSON.stringify({
              amount,
              category,
              note,
              entry_date: entryDate,
              merchant,
              tags,
            }),
          });
          showToast('Expense updated successfully', 'success');
          showUndoToast('Expense updated');
        } else {
          await api('/api/transactions', {
            method: 'POST',
            body: JSON.stringify({
              amount,
              category,
              note,
              entry_date: entryDate,
              merchant,
              tags,
            }),
          });
          showToast(`Logged ₹${amount.toFixed(2)} under ${category}`, 'success');
          showUndoToast('Expense logged');
        }

        closeModal('#modal-expense-entry', true);
        await refreshBudgetsAndDashboard();
      } catch (err) {
        if (errEl) {
          errEl.textContent = err.message || 'Failed to save expense';
          errEl.style.display = 'block';
        }
      } finally {
        expenseSaveBtn.disabled = false;
        expenseSaveBtn.textContent = 'Save Expense';
      }
    });
  }

  // ---------- Income Modal ----------
  let incomeFormInitial = '';
  function openIncomeModal() {
    const modal = $('#modal-income-entry');
    const amtInput = $('#income-amount');
    const srcInput = $('#income-source');
    const dateInput = $('#income-date');
    const errEl = $('#income-modal-error');

    if (!modal) return;
    if (errEl) errEl.style.display = 'none';

    const todayStr = new Date().toISOString().slice(0, 10);
    if (amtInput) amtInput.value = '';
    if (srcInput) srcInput.value = '';
    if (dateInput) dateInput.value = todayStr;

    incomeFormInitial = JSON.stringify({
      amt: amtInput?.value,
      src: srcInput?.value,
      date: dateInput?.value,
    });

    openModal('#modal-income-entry', () => {
      const cur = JSON.stringify({
        amt: amtInput?.value,
        src: srcInput?.value,
        date: dateInput?.value,
      });
      return cur !== incomeFormInitial;
    });

    if (amtInput) amtInput.focus();
  }

  const incomeModalClose = $('#income-modal-close');
  const incomeCancelBtn = $('#income-cancel-btn');
  const incomeSaveBtn = $('#income-save-btn');

  if (incomeModalClose) incomeModalClose.addEventListener('click', () => closeModal('#modal-income-entry'));
  if (incomeCancelBtn) incomeCancelBtn.addEventListener('click', () => closeModal('#modal-income-entry'));

  if (incomeSaveBtn) {
    incomeSaveBtn.addEventListener('click', async () => {
      const amtInput = $('#income-amount');
      const srcInput = $('#income-source');
      const dateInput = $('#income-date');
      const errEl = $('#income-modal-error');

      const amount = parseFloat(amtInput?.value);
      const source = srcInput?.value?.trim() || 'salary';
      const entryDate = dateInput?.value;

      if (isNaN(amount) || amount <= 0) {
        if (errEl) { errEl.textContent = 'Please enter a valid amount greater than zero.'; errEl.style.display = 'block'; }
        if (amtInput) amtInput.focus();
        return;
      }
      if (!entryDate) {
        if (errEl) { errEl.textContent = 'Please pick a date for the income entry.'; errEl.style.display = 'block'; }
        return;
      }

      incomeSaveBtn.disabled = true;
      incomeSaveBtn.textContent = 'Saving...';

      try {
        await api('/api/income', {
          method: 'POST',
          body: JSON.stringify({
            amount,
            source,
            entry_date: entryDate,
          }),
        });

        showToast(`Logged ₹${amount.toFixed(2)} income (${source})`, 'success');
        closeModal('#modal-income-entry', true);

        await refreshBudgetsAndDashboard();
        if (currentView === 'calendar') loadCalendar();
        if (currentView === 'insights') loadInsights();
      } catch (err) {
        if (errEl) {
          errEl.textContent = err.message || 'Failed to save income';
          errEl.style.display = 'block';
        }
      } finally {
        incomeSaveBtn.disabled = false;
        incomeSaveBtn.textContent = 'Save Income';
      }
    });
  }

  // ---------- Budget Manager in Settings ----------
  function renderSettingsBudgets(budgets, allCats) {
    const container = $('#budget-manager-container');
    if (!container) return;

    if (!budgets || budgets.length === 0) {
      container.innerHTML = '<span style="color:var(--text-tertiary);font-size:12px;">No budget limits configured yet. Click "Add Budget" to set category limits.</span>';
      return;
    }

    let rowsHtml = '';
    budgets.forEach((b) => {
      const cat = b.category || '';
      const limit = b.monthly_limit || 0;
      const spent = b.current_spend || 0;
      const hasBudget = b.has_budget;
      const isCustom = b.is_custom;
      const isRollover = b.rollover_enabled;

      let statusHtml = '<span style="color:var(--text-tertiary);">No limit</span>';
      if (hasBudget) {
        const rem = limit - spent;
        if (rem >= 0) {
          statusHtml = `<span style="color:var(--success);font-weight:600;">${formatCurrency(rem)} left</span>`;
        } else {
          statusHtml = `<span style="color:var(--danger);font-weight:600;">${formatCurrency(Math.abs(rem))} over</span>`;
        }
      }

      rowsHtml += `
        <tr data-cat="${escapeHtml(cat)}">
          <td>
            <strong>${escapeHtml(cat.charAt(0).toUpperCase() + cat.slice(1))}</strong>
            ${isCustom ? '<span style="font-size:10px;padding:2px 6px;border-radius:var(--radius-pill);background:var(--bg-elevated);color:var(--text-tertiary);margin-left:6px;">Custom</span>' : ''}
          </td>
          <td>
            <div class="budget-inline-limit-wrap">
              <input type="number" class="budget-inline-limit-input" data-cat="${escapeHtml(cat)}" value="${limit}" min="0" step="50" data-tooltip="Monthly spending limit for this category">
              <button class="btn-primary btn-sm btn-save-budget-inline" data-cat="${escapeHtml(cat)}" style="padding:4px 8px;font-size:11px;" data-tooltip="Save monthly spending limit">Save</button>
            </div>
          </td>
          <td style="color:var(--text-secondary);">${formatCurrency(spent)}</td>
          <td>${statusHtml}</td>
          <td>
            <label class="rollover-switch-label" style="transform:scale(0.85);transform-origin:left center;" data-tooltip="Carry unused budget forward to next month">
              <input type="checkbox" class="budget-mgr-rollover-cb" data-cat="${escapeHtml(cat)}" ${isRollover ? 'checked' : ''} data-tooltip="Carry unused budget forward to next month">
              <span class="rollover-slider"></span>
              <span class="rollover-switch-text">${isRollover ? 'On' : 'Off'}</span>
            </label>
          </td>
          <td style="text-align:right;">
            ${hasBudget ? `
              <button class="btn-icon-action danger btn-del-budget-row" data-cat="${escapeHtml(cat)}" title="Remove budget limit" data-tooltip="Remove spending limit for this category">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px;"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
              </button>
            ` : ''}
          </td>
        </tr>
      `;
    });

    container.innerHTML = `
      <table class="budget-mgr-table">
        <thead>
          <tr>
            <th>Category</th>
            <th>Monthly Limit</th>
            <th>Spend This Month</th>
            <th>Remaining</th>
            <th>Rollover</th>
            <th style="text-align:right;">Action</th>
          </tr>
        </thead>
        <tbody>
          ${rowsHtml}
        </tbody>
      </table>
    `;

    // Inline Save button
    container.querySelectorAll('.btn-save-budget-inline').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const cat = btn.dataset.cat;
        const input = container.querySelector(`.budget-inline-limit-input[data-cat="${cat}"]`);
        const val = parseFloat(input?.value);
        if (isNaN(val) || val < 0) {
          showToast('Please enter a valid budget limit', 'error');
          return;
        }

        btn.disabled = true;
        btn.textContent = '...';
        try {
          await api(`/api/budgets/${encodeURIComponent(cat)}`, {
            method: 'PATCH',
            body: JSON.stringify({ monthly_limit: val }),
          });
          showToast(`Budget for ${cat} updated to ₹${val}`, 'success');
          await refreshBudgetsAndDashboard();
        } catch (err) {
          showToast(err.message || 'Failed to update budget', 'error');
        } finally {
          btn.disabled = false;
          btn.textContent = 'Save';
        }
      });
    });

    // Enter key on inline input
    container.querySelectorAll('.budget-inline-limit-input').forEach((input) => {
      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          const cat = input.dataset.cat;
          const saveBtn = container.querySelector(`.btn-save-budget-inline[data-cat="${cat}"]`);
          if (saveBtn) saveBtn.click();
        }
      });
    });

    // Rollover switch
    container.querySelectorAll('.budget-mgr-rollover-cb').forEach((cb) => {
      cb.addEventListener('change', async () => {
        const cat = cb.dataset.cat;
        const enabled = cb.checked;
        const textSpan = cb.parentElement.querySelector('.rollover-switch-text');
        if (textSpan) textSpan.textContent = enabled ? 'On' : 'Off';

        try {
          await api(`/api/budgets/${encodeURIComponent(cat)}`, {
            method: 'PATCH',
            body: JSON.stringify({ rollover_enabled: enabled }),
          });
          showToast(`Rollover for ${cat} ${enabled ? 'enabled' : 'disabled'}`, 'success');
          await refreshBudgetsAndDashboard();
        } catch (err) {
          cb.checked = !enabled;
          if (textSpan) textSpan.textContent = !enabled ? 'On' : 'Off';
          showToast(err.message || 'Failed to toggle rollover', 'error');
        }
      });
    });

    // Delete budget limit
    container.querySelectorAll('.btn-del-budget-row').forEach((btn) => {
      btn.addEventListener('click', () => {
        const cat = btn.dataset.cat;
        openSimpleConfirmModal(
          'Delete Budget Limit',
          `Are you sure you want to remove the monthly limit for "${cat}"?`,
          async () => {
            await api(`/api/budgets/${encodeURIComponent(cat)}`, { method: 'DELETE' });
            showToast(`Budget limit for ${cat} removed`, 'success');
            await refreshBudgetsAndDashboard();
          }
        );
      });
    });
  }

  // Add budget button in Settings
  const btnAddBudgetRowTrigger = $('#btn-add-budget-row-trigger');
  const budgetAddClose = $('#budget-add-close');
  const budgetAddCancel = $('#budget-add-cancel-btn');
  const budgetAddSave = $('#budget-add-save-btn');

  if (budgetAddClose) budgetAddClose.addEventListener('click', () => closeModal('#modal-budget-add', true));
  if (budgetAddCancel) budgetAddCancel.addEventListener('click', () => closeModal('#modal-budget-add', true));

  if (btnAddBudgetRowTrigger) {
    btnAddBudgetRowTrigger.addEventListener('click', () => {
      populateCategoryDropdowns();
      const limitInput = $('#budget-add-limit');
      const rollInput = $('#budget-add-rollover');
      const errEl = $('#budget-add-error');

      if (limitInput) limitInput.value = '';
      if (rollInput) rollInput.checked = false;
      if (errEl) errEl.style.display = 'none';

      openModal('#modal-budget-add');
    });
  }

  if (budgetAddSave) {
    budgetAddSave.addEventListener('click', async () => {
      const cat = $('#budget-add-category')?.value;
      const limitVal = parseFloat($('#budget-add-limit')?.value);
      const rollover = $('#budget-add-rollover')?.checked || false;
      const errEl = $('#budget-add-error');

      if (!cat) {
        if (errEl) { errEl.textContent = 'Please choose a category'; errEl.style.display = 'block'; }
        return;
      }
      if (isNaN(limitVal) || limitVal <= 0) {
        if (errEl) { errEl.textContent = 'Please enter a valid monthly limit amount'; errEl.style.display = 'block'; }
        return;
      }

      budgetAddSave.disabled = true;
      budgetAddSave.textContent = 'Saving...';

      try {
        await api('/api/budgets', {
          method: 'POST',
          body: JSON.stringify({
            category: cat,
            monthly_limit: limitVal,
            rollover_enabled: rollover,
          }),
        });
        showToast(`Budget for ${cat} set to ₹${limitVal}`, 'success');
        closeModal('#modal-budget-add', true);
        await refreshBudgetsAndDashboard();
      } catch (err) {
        if (errEl) { errEl.textContent = err.message || 'Failed to save budget'; errEl.style.display = 'block'; }
      } finally {
        budgetAddSave.disabled = false;
        budgetAddSave.textContent = 'Save Budget';
      }
    });
  }

  // ---------- Savings Goals in Settings ----------
  let cachedGoalsList = [];

  function renderSettingsGoals(goals) {
    cachedGoalsList = goals || [];
    const container = $('#settings-goals-container');
    if (!container) return;

    if (cachedGoalsList.length === 0) {
      container.innerHTML = '<span style="color:var(--text-tertiary);font-size:12px;">No savings goals set. Tap "Add Goal" to start tracking toward a financial target.</span>';
      return;
    }

    const today = new Date();
    let cardsHtml = '';

    cachedGoalsList.forEach((g) => {
      const target = parseFloat(g.target_amount) || 0;
      const saved = parseFloat(g.saved_amount) || 0;
      const pct = target > 0 ? Math.min(100, Math.round((saved / target) * 100)) : 0;
      const remaining = Math.max(0, target - saved);

      let reqText = `Remaining: ${formatCurrency(remaining)}`;
      if (g.target_date && remaining > 0) {
        const tDate = new Date(g.target_date);
        const monthsLeft = Math.max(1, (tDate.getFullYear() - today.getFullYear()) * 12 + (tDate.getMonth() - today.getMonth()));
        const reqMonthly = Math.ceil(remaining / monthsLeft);
        reqText = `Required: ${formatCurrency(reqMonthly)} / mo (${monthsLeft} mo left)`;
      } else if (remaining === 0) {
        reqText = 'Goal completed!';
      }

      cardsHtml += `
        <div class="goal-card-item" data-id="${g.id}">
          <div class="goal-card-top">
            <div>
              <div class="goal-card-title">${escapeHtml(g.name)}</div>
              ${g.target_date ? `<span class="goal-card-target-date">Target Date: ${formatDate(g.target_date)}</span>` : ''}
            </div>
            <div style="text-align:right;">
              <strong>${formatCurrency(saved)}</strong> <span style="color:var(--text-tertiary);">/ ${formatCurrency(target)}</span>
            </div>
          </div>
          <div class="goal-card-progress-bar">
            <div class="goal-card-progress-fill" style="width:${pct}%;"></div>
          </div>
          <div class="goal-card-stats">
            <span>${pct}% saved</span>
            <span class="goal-card-monthly-req">${reqText}</span>
          </div>
          <div class="goal-card-actions">
            <button class="btn-primary btn-sm btn-contrib-goal-trigger" data-id="${g.id}">Add Contribution</button>
            <button class="btn-secondary btn-sm btn-edit-goal-trigger" data-id="${g.id}">Edit</button>
            <button class="btn-secondary btn-sm danger-text btn-del-goal-trigger" data-id="${g.id}">Delete</button>
          </div>
        </div>
      `;
    });

    container.innerHTML = cardsHtml;

    // Contribute buttons
    container.querySelectorAll('.btn-contrib-goal-trigger').forEach((btn) => {
      btn.addEventListener('click', () => {
        const gid = parseInt(btn.dataset.id, 10);
        const goal = cachedGoalsList.find((x) => x.id === gid);
        if (goal) openGoalContributeModal(goal);
      });
    });

    // Edit goal buttons
    container.querySelectorAll('.btn-edit-goal-trigger').forEach((btn) => {
      btn.addEventListener('click', () => {
        const gid = parseInt(btn.dataset.id, 10);
        const goal = cachedGoalsList.find((x) => x.id === gid);
        if (goal) openGoalModal(goal);
      });
    });

    // Delete goal buttons
    container.querySelectorAll('.btn-del-goal-trigger').forEach((btn) => {
      btn.addEventListener('click', () => {
        const gid = parseInt(btn.dataset.id, 10);
        const goal = cachedGoalsList.find((x) => x.id === gid);
        openSimpleConfirmModal(
          'Delete Savings Goal',
          `Are you sure you want to delete goal "${goal?.name || 'this goal'}"?`,
          async () => {
            await api(`/api/goals/${gid}`, { method: 'DELETE' });
            showToast('Goal deleted', 'success');
            loadSettings();
            loadGlanceData();
            refreshBudgetsAndDashboard();
          }
        );
      });
    });
  }

  // Add / Edit Goal Modal
  const btnAddGoalTrigger = $('#btn-add-goal-trigger');
  const goalModalClose = $('#goal-modal-close');
  const goalCancelBtn = $('#goal-cancel-btn');
  const goalSaveBtn = $('#goal-save-btn');

  if (goalModalClose) goalModalClose.addEventListener('click', () => closeModal('#modal-goal-entry'));
  if (goalCancelBtn) goalCancelBtn.addEventListener('click', () => closeModal('#modal-goal-entry'));

  function openGoalModal(goal = null) {
    const titleEl = $('#goal-modal-title');
    const idInput = $('#goal-edit-id');
    const nameInput = $('#goal-name-input');
    const targetInput = $('#goal-target-input');
    const dateInput = $('#goal-date-input');
    const errEl = $('#goal-modal-error');

    if (errEl) errEl.style.display = 'none';

    if (goal) {
      if (titleEl) titleEl.textContent = 'Edit Savings Goal';
      if (idInput) idInput.value = goal.id;
      if (nameInput) nameInput.value = goal.name || '';
      if (targetInput) targetInput.value = goal.target_amount || '';
      if (dateInput) dateInput.value = goal.target_date ? goal.target_date.slice(0, 10) : '';
    } else {
      if (titleEl) titleEl.textContent = 'Add Savings Goal';
      if (idInput) idInput.value = '';
      if (nameInput) nameInput.value = '';
      if (targetInput) targetInput.value = '';
      if (dateInput) dateInput.value = '';
    }

    const initVal = JSON.stringify({ n: nameInput?.value, t: targetInput?.value, d: dateInput?.value });
    openModal('#modal-goal-entry', () => {
      const cur = JSON.stringify({ n: nameInput?.value, t: targetInput?.value, d: dateInput?.value });
      return cur !== initVal;
    });
  }

  if (btnAddGoalTrigger) {
    btnAddGoalTrigger.addEventListener('click', () => openGoalModal(null));
  }

  if (goalSaveBtn) {
    goalSaveBtn.addEventListener('click', async () => {
      const gid = $('#goal-edit-id')?.value;
      const name = $('#goal-name-input')?.value?.trim();
      const targetVal = parseFloat($('#goal-target-input')?.value);
      const targetDate = $('#goal-date-input')?.value || null;
      const errEl = $('#goal-modal-error');

      if (!name) {
        if (errEl) { errEl.textContent = 'Please enter a goal name.'; errEl.style.display = 'block'; }
        return;
      }
      if (isNaN(targetVal) || targetVal <= 0) {
        if (errEl) { errEl.textContent = 'Please enter a valid target amount greater than zero.'; errEl.style.display = 'block'; }
        return;
      }

      goalSaveBtn.disabled = true;
      goalSaveBtn.textContent = 'Saving...';

      try {
        if (gid) {
          await api(`/api/goals/${gid}`, {
            method: 'PUT',
            body: JSON.stringify({
              name,
              target_amount: targetVal,
              target_date: targetDate,
            }),
          });
          showToast(`Goal "${name}" updated`, 'success');
        } else {
          await api('/api/goals', {
            method: 'POST',
            body: JSON.stringify({
              name,
              target_amount: targetVal,
              target_date: targetDate,
            }),
          });
          showToast(`Goal "${name}" created!`, 'success');
        }

        closeModal('#modal-goal-entry', true);
        loadSettings();
        loadGlanceData();
        refreshBudgetsAndDashboard();
      } catch (err) {
        if (errEl) { errEl.textContent = err.message || 'Failed to save goal'; errEl.style.display = 'block'; }
      } finally {
        goalSaveBtn.disabled = false;
        goalSaveBtn.textContent = 'Save Goal';
      }
    });
  }

  // Goal Contribute Modal
  const contribModalClose = $('#contrib-modal-close');
  const contribCancelBtn = $('#contrib-cancel-btn');
  const contribSaveBtn = $('#contrib-save-btn');

  if (contribModalClose) contribModalClose.addEventListener('click', () => closeModal('#modal-goal-contribute'));
  if (contribCancelBtn) contribCancelBtn.addEventListener('click', () => closeModal('#modal-goal-contribute'));

  let activeContribGoal = null;

  function openGoalContributeModal(goal) {
    activeContribGoal = goal;
    const titleEl = $('#contrib-goal-title');
    const descEl = $('#contrib-goal-desc');
    const amtInput = $('#contrib-amount-input');
    const noteInput = $('#contrib-note-input');
    const errEl = $('#contrib-modal-error');

    if (errEl) errEl.style.display = 'none';
    if (titleEl) titleEl.textContent = `Contribute to ${goal.name}`;
    if (descEl) descEl.textContent = `Currently saved: ${formatCurrency(goal.saved_amount)} of ${formatCurrency(goal.target_amount)}`;
    if (amtInput) amtInput.value = '';
    if (noteInput) noteInput.value = '';

    openModal('#modal-goal-contribute');
  }

  if (contribSaveBtn) {
    contribSaveBtn.addEventListener('click', async () => {
      if (!activeContribGoal) return;
      const amount = parseFloat($('#contrib-amount-input')?.value);
      const note = $('#contrib-note-input')?.value?.trim() || null;
      const errEl = $('#contrib-modal-error');

      if (isNaN(amount) || amount <= 0) {
        if (errEl) { errEl.textContent = 'Please enter a contribution amount.'; errEl.style.display = 'block'; }
        return;
      }

      contribSaveBtn.disabled = true;
      contribSaveBtn.textContent = 'Adding...';

      try {
        await api('/api/goals/contribute', {
          method: 'POST',
          body: JSON.stringify({
            goal_name: activeContribGoal.name,
            amount,
            note,
          }),
        });

        showToast(`Added ${formatCurrency(amount)} to ${activeContribGoal.name}!`, 'success');
        closeModal('#modal-goal-contribute', true);
        loadSettings();
        loadGlanceData();
        refreshBudgetsAndDashboard();
      } catch (err) {
        if (errEl) { errEl.textContent = err.message || 'Contribution failed'; errEl.style.display = 'block'; }
      } finally {
        contribSaveBtn.disabled = false;
        contribSaveBtn.textContent = 'Add Contribution';
      }
    });
  }

  // ---------- Recurring Expenses Upgrades in Settings ----------
  let cachedRecurringList = [];

  function renderSettingsRecurring(bills) {
    cachedRecurringList = bills || [];
    const listEl = $('#settings-recurring-list');
    if (!listEl) return;

    if (cachedRecurringList.length === 0) {
      listEl.innerHTML = '<span style="color:var(--text-tertiary);font-size:12px;">No recurring bills scheduled. Tap "Add Bill" above to track rent, wifi, or subscriptions.</span>';
      return;
    }

    listEl.innerHTML = cachedRecurringList.map((b) => `
      <div style="display:flex;justify-content:space-between;align-items:center;padding:12px 0;border-bottom:1px solid var(--border-subtle);font-size:13px;flex-wrap:wrap;gap:8px;">
        <div>
          <strong style="color:var(--text-primary);">${escapeHtml(b.name)}</strong>
          <span style="color:var(--text-secondary);margin-left:6px;">(${escapeHtml(b.category || 'other')} · ${escapeHtml(b.frequency)})</span>
          <span style="margin-left:8px;font-size:10px;padding:2px 7px;border-radius:var(--radius-pill);${b.active ? 'background:rgba(16,185,129,0.15);color:#34D399;' : 'background:var(--bg-elevated);color:var(--text-tertiary);'}">
            ${b.active ? 'Active' : 'Paused'}
          </span>
          <div style="font-size:11px;color:var(--text-tertiary);margin-top:2px;">Next due: ${formatDate(b.next_due_date)}</div>
        </div>
        <div style="display:flex;align-items:center;gap:8px;">
          <span style="font-weight:600;color:var(--text-primary);margin-right:4px;">${formatCurrency(b.amount)}</span>
          <button class="btn-secondary btn-sm btn-toggle-rec" data-id="${b.id}" style="font-size:11px;padding:4px 8px;">
            ${b.active ? 'Pause' : 'Activate'}
          </button>
          <button class="btn-secondary btn-sm btn-edit-rec" data-id="${b.id}" style="font-size:11px;padding:4px 8px;">
            Edit
          </button>
          <button class="btn-secondary btn-sm danger-text btn-del-rec" data-id="${b.id}" style="font-size:11px;padding:4px 8px;">
            Delete
          </button>
        </div>
      </div>
    `).join('');

    // Toggle active / paused
    listEl.querySelectorAll('.btn-toggle-rec').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const id = btn.dataset.id;
        try {
          const res = await api(`/api/recurring/${id}/toggle`, { method: 'POST' });
          showToast(`Recurring bill ${res.active ? 'activated' : 'paused'}`, 'success');
          loadSettings();
          loadDashboard();
        } catch (err) {
          showToast(err.message || 'Failed to toggle bill status', 'error');
        }
      });
    });

    // Edit recurring bill
    listEl.querySelectorAll('.btn-edit-rec').forEach((btn) => {
      btn.addEventListener('click', () => {
        const id = parseInt(btn.dataset.id, 10);
        const bill = cachedRecurringList.find((b) => b.id === id);
        if (bill) openRecurringEditModal(bill);
      });
    });

    // Delete recurring bill
    listEl.querySelectorAll('.btn-del-rec').forEach((btn) => {
      btn.addEventListener('click', () => {
        const id = parseInt(btn.dataset.id, 10);
        const bill = cachedRecurringList.find((b) => b.id === id);
        openSimpleConfirmModal(
          'Delete Recurring Bill',
          `Are you sure you want to delete "${bill?.name || 'this bill'}"?`,
          async () => {
            await api(`/api/recurring/${id}`, { method: 'DELETE' });
            showToast('Recurring bill deleted', 'success');
            loadSettings();
            loadDashboard();
          }
        );
      });
    });
  }

  // Edit recurring bill modal
  const recEditClose = $('#rec-edit-close');
  const recEditCancel = $('#rec-edit-cancel-btn');
  const recEditSave = $('#rec-edit-save-btn');

  if (recEditClose) recEditClose.addEventListener('click', () => closeModal('#modal-recurring-edit'));
  if (recEditCancel) recEditCancel.addEventListener('click', () => closeModal('#modal-recurring-edit'));

  function openRecurringEditModal(bill) {
    populateCategoryDropdowns();
    const idInput = $('#rec-edit-id');
    const nameInput = $('#rec-edit-name');
    const amtInput = $('#rec-edit-amount');
    const catSelect = $('#rec-edit-category');
    const freqSelect = $('#rec-edit-frequency');
    const dateInput = $('#rec-edit-due-date');
    const errEl = $('#rec-edit-error');

    if (errEl) errEl.style.display = 'none';
    if (idInput) idInput.value = bill.id;
    if (nameInput) nameInput.value = bill.name || '';
    if (amtInput) amtInput.value = bill.amount || '';
    if (catSelect) catSelect.value = (bill.category || 'bills').toLowerCase();
    if (freqSelect) freqSelect.value = bill.frequency || 'monthly';
    if (dateInput) dateInput.value = bill.next_due_date ? bill.next_due_date.slice(0, 10) : '';

    const initVal = JSON.stringify({
      n: nameInput?.value, a: amtInput?.value, c: catSelect?.value, f: freqSelect?.value, d: dateInput?.value
    });

    openModal('#modal-recurring-edit', () => {
      const cur = JSON.stringify({
        n: nameInput?.value, a: amtInput?.value, c: catSelect?.value, f: freqSelect?.value, d: dateInput?.value
      });
      return cur !== initVal;
    });
  }

  if (recEditSave) {
    recEditSave.addEventListener('click', async () => {
      const id = $('#rec-edit-id')?.value;
      const name = $('#rec-edit-name')?.value?.trim();
      const amount = parseFloat($('#rec-edit-amount')?.value);
      const category = $('#rec-edit-category')?.value;
      const frequency = $('#rec-edit-frequency')?.value;
      const dueDate = $('#rec-edit-due-date')?.value;
      const errEl = $('#rec-edit-error');

      if (!name) {
        if (errEl) { errEl.textContent = 'Please enter a name.'; errEl.style.display = 'block'; }
        return;
      }
      if (isNaN(amount) || amount <= 0) {
        if (errEl) { errEl.textContent = 'Please enter a valid amount.'; errEl.style.display = 'block'; }
        return;
      }
      if (!dueDate) {
        if (errEl) { errEl.textContent = 'Please pick a next due date.'; errEl.style.display = 'block'; }
        return;
      }

      recEditSave.disabled = true;
      recEditSave.textContent = 'Saving...';

      try {
        await api(`/api/recurring/${id}`, {
          method: 'PUT',
          body: JSON.stringify({
            name,
            amount,
            category,
            frequency,
            start_date: dueDate,
          }),
        });

        showToast(`Bill "${name}" updated successfully`, 'success');
        closeModal('#modal-recurring-edit', true);
        loadSettings();
        loadDashboard();
      } catch (err) {
        if (errEl) { errEl.textContent = err.message || 'Failed to update bill'; errEl.style.display = 'block'; }
      } finally {
        recEditSave.disabled = false;
        recEditSave.textContent = 'Save Changes';
      }
    });
  }

  // ---------- Udhar Manual Management ----------
  const btnAddUdharTrigger = $('#btn-add-udhar-trigger');
  const udharModalClose = $('#udhar-modal-close');
  const udharCancelBtn = $('#udhar-cancel-btn');
  const udharSaveBtn = $('#udhar-save-btn');
  const udharKindSelect = $('#udhar-kind-select');
  const udharDueDateWrap = $('#udhar-due-date-wrap');
  const udharPersonInput = $('#udhar-person-input');
  const udharAmountInput = $('#udhar-amount-input');
  const udharBalanceWarn = $('#udhar-balance-warning');

  if (udharModalClose) udharModalClose.addEventListener('click', () => closeModal('#modal-udhar-entry'));
  if (udharCancelBtn) udharCancelBtn.addEventListener('click', () => closeModal('#modal-udhar-entry'));

  function updateUdharModalKindUi() {
    const kind = udharKindSelect?.value || 'lent';
    if (udharDueDateWrap) {
      udharDueDateWrap.style.display = (kind === 'lent' || kind === 'borrowed') ? 'flex' : 'none';
    }
    checkUdharBalanceWarning();
  }

  function checkUdharBalanceWarning() {
    if (!udharBalanceWarn) return;
    const kind = udharKindSelect?.value;
    const pName = udharPersonInput?.value?.trim().toLowerCase();
    const amt = parseFloat(udharAmountInput?.value);

    if (!pName || isNaN(amt) || amt <= 0 || (kind !== 'received_back' && kind !== 'paid_back')) {
      udharBalanceWarn.style.display = 'none';
      return;
    }

    if (!cachedUdharData) {
      udharBalanceWarn.style.display = 'none';
      return;
    }

    const persons = cachedUdharData.persons || cachedUdharData.people || [];
    const p = persons.find((x) => (x.person_key || (x.name || x.person_name || '').toLowerCase()) === pName || (x.name || '').toLowerCase() === pName);

    if (!p) {
      udharBalanceWarn.style.display = 'none';
      return;
    }

    const net = p.net || 0;
    if (kind === 'received_back' && amt > net) {
      udharBalanceWarn.textContent = `Warning: Received back amount (${formatCurrency(amt)}) exceeds friend's outstanding debt of ${formatCurrency(net)}.`;
      udharBalanceWarn.style.display = 'block';
    } else if (kind === 'paid_back' && amt > Math.abs(net)) {
      udharBalanceWarn.textContent = `Warning: Paid back amount (${formatCurrency(amt)}) exceeds your recorded debt of ${formatCurrency(Math.abs(net))}.`;
      udharBalanceWarn.style.display = 'block';
    } else {
      udharBalanceWarn.style.display = 'none';
    }
  }

  if (udharKindSelect) udharKindSelect.addEventListener('change', updateUdharModalKindUi);
  if (udharPersonInput) udharPersonInput.addEventListener('input', checkUdharBalanceWarning);
  if (udharAmountInput) udharAmountInput.addEventListener('input', checkUdharBalanceWarning);

  function openUdharModal(entry = null, defaultPersonName = null) {
    const titleEl = $('#udhar-modal-title');
    const idInput = $('#udhar-edit-id');
    const errEl = $('#udhar-modal-error');
    const noteInput = $('#udhar-note-input');
    const dateInput = $('#udhar-date-input');
    const dueDateInput = $('#udhar-due-date-input');

    if (errEl) errEl.style.display = 'none';
    if (udharBalanceWarn) udharBalanceWarn.style.display = 'none';

    const todayStr = new Date().toISOString().slice(0, 10);

    if (entry) {
      if (titleEl) titleEl.textContent = 'Edit Udhar Entry';
      if (idInput) idInput.value = entry.id;
      if (udharPersonInput) udharPersonInput.value = entry.person_name || defaultPersonName || '';
      if (udharKindSelect) udharKindSelect.value = entry.kind || 'lent';
      if (udharAmountInput) udharAmountInput.value = entry.amount || '';
      if (noteInput) noteInput.value = entry.note || '';
      if (dateInput) dateInput.value = entry.entry_date ? entry.entry_date.slice(0, 10) : todayStr;
      if (dueDateInput) dueDateInput.value = entry.due_date ? entry.due_date.slice(0, 10) : '';
    } else {
      if (titleEl) titleEl.textContent = 'Add Udhar Entry';
      if (idInput) idInput.value = '';
      if (udharPersonInput) udharPersonInput.value = defaultPersonName || '';
      if (udharKindSelect) udharKindSelect.value = 'lent';
      if (udharAmountInput) udharAmountInput.value = '';
      if (noteInput) noteInput.value = '';
      if (dateInput) dateInput.value = todayStr;
      if (dueDateInput) dueDateInput.value = '';
    }

    updateUdharModalKindUi();

    const initVal = JSON.stringify({
      p: udharPersonInput?.value,
      k: udharKindSelect?.value,
      a: udharAmountInput?.value,
      n: noteInput?.value,
      d: dateInput?.value,
      dd: dueDateInput?.value,
    });

    openModal('#modal-udhar-entry', () => {
      const cur = JSON.stringify({
        p: udharPersonInput?.value,
        k: udharKindSelect?.value,
        a: udharAmountInput?.value,
        n: noteInput?.value,
        d: dateInput?.value,
        dd: dueDateInput?.value,
      });
      return cur !== initVal;
    });
  }

  if (btnAddUdharTrigger) {
    btnAddUdharTrigger.addEventListener('click', () => openUdharModal(null));
  }

  if (udharSaveBtn) {
    udharSaveBtn.addEventListener('click', async () => {
      const editId = $('#udhar-edit-id')?.value;
      const personName = udharPersonInput?.value?.trim();
      const kind = udharKindSelect?.value;
      const amount = parseFloat(udharAmountInput?.value);
      const note = $('#udhar-note-input')?.value?.trim() || '';
      const entryDate = $('#udhar-date-input')?.value;
      const dueDate = (kind === 'lent' || kind === 'borrowed') ? ($('#udhar-due-date-input')?.value || null) : null;
      const errEl = $('#udhar-modal-error');

      if (!personName) {
        if (errEl) { errEl.textContent = 'Please enter a friend or person name.'; errEl.style.display = 'block'; }
        return;
      }
      if (isNaN(amount) || amount <= 0) {
        if (errEl) { errEl.textContent = 'Please enter a valid amount greater than zero.'; errEl.style.display = 'block'; }
        return;
      }
      if (!entryDate) {
        if (errEl) { errEl.textContent = 'Please pick a date.'; errEl.style.display = 'block'; }
        return;
      }

      udharSaveBtn.disabled = true;
      udharSaveBtn.textContent = 'Saving...';

      try {
        if (editId) {
          await api(`/api/udhar/${editId}`, {
            method: 'PUT',
            body: JSON.stringify({
              person_name: personName,
              kind,
              amount,
              note,
              entry_date: entryDate,
              due_date: dueDate,
            }),
          });
          showToast('Udhar entry updated', 'success');
        } else {
          await api('/api/udhar', {
            method: 'POST',
            body: JSON.stringify({
              person_name: personName,
              kind,
              amount,
              note,
              entry_date: entryDate,
              due_date: dueDate,
            }),
          });
          showToast(`Udhar entry recorded for ${personName}`, 'success');
        }

        closeModal('#modal-udhar-entry', true);
        closeModal('#modal-udhar-ledger', true);
        loadUdhar();
        refreshBudgetsAndDashboard();
      } catch (err) {
        if (errEl) { errEl.textContent = err.message || 'Failed to save udhar entry'; errEl.style.display = 'block'; }
      } finally {
        udharSaveBtn.disabled = false;
        udharSaveBtn.textContent = 'Save Udhar';
      }
    });
  }

  // Udhar Ledger Modal
  let activeLedgerPerson = null;

  function openUdharLedgerModal(person) {
    activeLedgerPerson = person;
    const modal = $('#modal-udhar-ledger');
    const titleEl = $('#udhar-ledger-title');
    const subtitleEl = $('#udhar-ledger-subtitle');
    const tableWrap = $('#udhar-ledger-table-wrap');

    if (!modal || !tableWrap) return;

    const pName = person.name || person.person_name || 'Friend';
    const net = person.net || 0;
    const netText = net > 0 ? `Owes you ${formatCurrency(net)}` : (net < 0 ? `You owe ${formatCurrency(Math.abs(net))}` : 'Settled up');

    if (titleEl) titleEl.textContent = `Ledger: ${pName}`;
    if (subtitleEl) subtitleEl.textContent = `Net Balance: ${netText}`;

    const history = person.history || [];
    if (history.length === 0) {
      tableWrap.innerHTML = '<div class="empty-state" style="padding:24px;"><p>No transaction history recorded with this person.</p></div>';
    } else {
      let rowsHtml = '';
      history.forEach((h) => {
        const isLent = h.kind === 'lent';
        const isPastDue = h.due_date && !h.resolved && new Date(h.due_date) < new Date();
        const kindLabel = isLent ? 'Lent' : 'Borrowed';
        const kindColor = isLent ? 'lent-color' : 'borrowed-color';

        rowsHtml += `
          <tr class="${isPastDue ? 'udhar-overdue-row' : ''}">
            <td style="white-space:nowrap;">${formatDate(h.entry_date)}</td>
            <td><strong class="${kindColor}">${kindLabel}</strong></td>
            <td style="font-weight:600;">${formatCurrency(h.amount)}</td>
            <td style="color:var(--text-secondary);max-width:140px;overflow:hidden;text-overflow:ellipsis;">${escapeHtml(h.note || '--')}</td>
            <td>
              ${h.due_date ? `
                <div style="font-size:11px;${isPastDue ? 'color:var(--danger);font-weight:600;' : 'color:var(--text-tertiary);'}">
                  Due: ${formatDate(h.due_date)}
                  ${h.resolved ? '<span class="udhar-resolved-badge">Resolved</span>' : ''}
                </div>
              ` : '<span style="color:var(--text-tertiary);">--</span>'}
            </td>
            <td style="text-align:right;white-space:nowrap;">
              <div class="txn-row-actions">
                ${h.due_date && !h.resolved ? `
                  <button class="btn-secondary btn-sm btn-resolve-udhar" data-id="${h.id}" style="font-size:10px;padding:2px 6px;">Resolve</button>
                ` : ''}
                <button class="btn-icon-action btn-edit-udhar-entry" data-id="${h.id}" title="Edit entry">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:13px;height:13px;"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                </button>
                <button class="btn-icon-action danger btn-del-udhar-entry" data-id="${h.id}" title="Delete entry">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:13px;height:13px;"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                </button>
              </div>
            </td>
          </tr>
        `;
      });

      tableWrap.innerHTML = `
        <table class="udhar-ledger-table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Kind</th>
              <th>Amount</th>
              <th>Note</th>
              <th>Due Date</th>
              <th style="text-align:right;">Actions</th>
            </tr>
          </thead>
          <tbody>
            ${rowsHtml}
          </tbody>
        </table>
      `;

      // Resolve due date buttons
      tableWrap.querySelectorAll('.btn-resolve-udhar').forEach((btn) => {
        btn.addEventListener('click', async () => {
          const eid = btn.dataset.id;
          try {
            await api(`/api/udhar/${eid}/resolve`, { method: 'POST' });
            showToast('Due date marked as resolved', 'success');
            loadUdhar();
            refreshBudgetsAndDashboard();
            closeModal('#modal-udhar-ledger', true);
          } catch (err) {
            showToast(err.message || 'Failed to resolve due date', 'error');
          }
        });
      });

      // Edit entry button
      tableWrap.querySelectorAll('.btn-edit-udhar-entry').forEach((btn) => {
        btn.addEventListener('click', () => {
          const eid = parseInt(btn.dataset.id, 10);
          const entry = history.find((h) => h.id === eid);
          if (entry) {
            closeModal('#modal-udhar-ledger', true);
            openUdharModal(entry, pName);
          }
        });
      });

      // Delete entry with balance recalculation shown
      tableWrap.querySelectorAll('.btn-del-udhar-entry').forEach((btn) => {
        btn.addEventListener('click', () => {
          const eid = parseInt(btn.dataset.id, 10);
          const entry = history.find((h) => h.id === eid);
          if (!entry) return;

          // Recalculate balance
          const delta = (entry.kind === 'lent' ? -1 : 1) * parseFloat(entry.amount);
          const curNet = person.net || 0;
          const newNet = curNet + delta;

          const desc = `Deleting this entry of ${formatCurrency(entry.amount)} (${entry.kind}) will update ${pName}'s net balance from ${formatCurrency(curNet)} to ${formatCurrency(newNet)}. Proceed?`;

          openSimpleConfirmModal('Delete Udhar Entry', desc, async () => {
            await api(`/api/udhar/${eid}`, { method: 'DELETE' });
            showToast('Udhar entry deleted', 'success');
            closeModal('#modal-udhar-ledger', true);
            loadUdhar();
            refreshBudgetsAndDashboard();
          });
        });
      });
    }

    openModal('#modal-udhar-ledger');
  }

  const udharLedgerClose = $('#udhar-ledger-close');
  const udharLedgerDone = $('#udhar-ledger-done-btn');
  const udharLedgerAddEntry = $('#udhar-ledger-add-entry-btn');

  if (udharLedgerClose) udharLedgerClose.addEventListener('click', () => closeModal('#modal-udhar-ledger', true));
  if (udharLedgerDone) udharLedgerDone.addEventListener('click', () => closeModal('#modal-udhar-ledger', true));
  if (udharLedgerAddEntry) {
    udharLedgerAddEntry.addEventListener('click', () => {
      const pName = activeLedgerPerson?.name || activeLedgerPerson?.person_name || null;
      closeModal('#modal-udhar-ledger', true);
      openUdharModal(null, pName);
    });
  }

  // Simple Destructive Confirmation Modal
  let activeSimpleConfirmCallback = null;

  function openSimpleConfirmModal(title, desc, onConfirm) {
    const modal = $('#modal-simple-confirm');
    const titleEl = $('#simple-confirm-title');
    const descEl = $('#simple-confirm-desc');
    const actionBtn = $('#simple-confirm-action');

    if (!modal) return;
    if (titleEl) titleEl.textContent = title || 'Confirm Action';
    if (descEl) descEl.textContent = desc || 'Are you sure you want to proceed?';

    activeSimpleConfirmCallback = onConfirm;
    openModal('#modal-simple-confirm');
  }

  const simpleConfirmClose = $('#simple-confirm-close');
  const simpleConfirmCancel = $('#simple-confirm-cancel');
  const simpleConfirmAction = $('#simple-confirm-action');

  if (simpleConfirmClose) simpleConfirmClose.addEventListener('click', () => closeModal('#modal-simple-confirm', true));
  if (simpleConfirmCancel) simpleConfirmCancel.addEventListener('click', () => closeModal('#modal-simple-confirm', true));
  if (simpleConfirmAction) {
    simpleConfirmAction.addEventListener('click', async () => {
      if (activeSimpleConfirmCallback) {
        simpleConfirmAction.disabled = true;
        simpleConfirmAction.textContent = 'Processing...';
        try {
          await activeSimpleConfirmCallback();
          closeModal('#modal-simple-confirm', true);
        } catch (err) {
          showToast(err.message || 'Operation failed', 'error');
        } finally {
          simpleConfirmAction.disabled = false;
          simpleConfirmAction.textContent = 'Confirm';
          activeSimpleConfirmCallback = null;
        }
      }
    });
  }

  const settingsAddBillBtn = $('#btn-settings-add-bill');
  if (settingsAddBillBtn) {
    settingsAddBillBtn.addEventListener('click', () => {
      openModal('#modal-recurring');
    });
  }

  // Data & Privacy Actions
  const settingsRedoOb = $('#btn-settings-redo-onboarding');
  if (settingsRedoOb) {
    settingsRedoOb.addEventListener('click', () => {
      sessionStorage.removeItem('abt_onboarding_skipped');
      showOnboarding(1);
    });
  }

  const settingsExportJson = $('#btn-settings-export-json');
  if (settingsExportJson) {
    settingsExportJson.addEventListener('click', async () => {
      settingsExportJson.disabled = true;
      try {
        const res = await fetch('/api/data/export-all', {
          headers: { 'Authorization': 'Bearer ' + authToken },
        });
        if (!res.ok) throw new Error('Export failed');
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;
        a.download = `abt_export_${currentUser?.id || 'data'}.json`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        a.remove();
        showToast('Complete data JSON exported', 'success');
      } catch (err) {
        showToast(err.message || 'Failed to export data', 'error');
      } finally {
        settingsExportJson.disabled = false;
      }
    });
  }

  // Clear Confirmation Modal Logic
  let activeClearAction = null;

  function openClearConfirmModal(action) {
    activeClearAction = action;
    const modal = $('#modal-clear-confirm');
    const titleEl = $('#clear-modal-title');
    const descEl = $('#clear-modal-desc');
    const rangePicker = $('#clear-range-picker');
    const inputWrap = $('#clear-input-wrap');
    const typeLabel = $('#clear-type-label');
    const typedInput = $('#clear-typed-input');
    const actionBtn = $('#clear-action-btn');

    if (!modal) return;

    if (typedInput) typedInput.value = '';
    if (actionBtn) actionBtn.disabled = true;

    let targetPhrase = '';

    if (action === 'transactions') {
      titleEl.textContent = 'Clear transactions?';
      descEl.textContent = 'Warning: This will delete transaction history. You can optionally pick a date range below.';
      if (rangePicker) rangePicker.style.display = 'block';
      targetPhrase = 'CLEAR TRANSACTIONS';
    } else if (action === 'udhar') {
      titleEl.textContent = 'Clear udhar records?';
      descEl.textContent = 'Warning: This will permanently delete all lending and borrowing entries and logs.';
      if (rangePicker) rangePicker.style.display = 'none';
      targetPhrase = 'CLEAR UDHAR';
    } else if (action === 'everything') {
      titleEl.textContent = 'Clear all data?';
      descEl.textContent = 'High-risk action: This permanently wipes all transactions, receipts, budgets, udhar, and chats.';
      if (rangePicker) rangePicker.style.display = 'none';
      targetPhrase = 'CLEAR EVERYTHING';
    } else if (action === 'account') {
      titleEl.textContent = 'Delete account?';
      descEl.textContent = 'Permanent deletion: Your account and all associated data will be completely deleted and you will be signed out.';
      if (rangePicker) rangePicker.style.display = 'none';
      targetPhrase = 'DELETE MY ACCOUNT';
    }

    if (typeLabel) typeLabel.textContent = `Type "${targetPhrase}" to confirm:`;
    if (typedInput) {
      typedInput.placeholder = targetPhrase;
      typedInput.oninput = () => {
        actionBtn.disabled = typedInput.value.trim() !== targetPhrase;
      };
    }

    modal.style.display = 'flex';
  }

  const clearModalClose = $('#clear-modal-close');
  const clearCancelBtn = $('#clear-cancel-btn');
  const clearActionBtn = $('#clear-action-btn');

  if (clearModalClose) clearModalClose.addEventListener('click', () => closeModal('#modal-clear-confirm'));
  if (clearCancelBtn) clearCancelBtn.addEventListener('click', () => closeModal('#modal-clear-confirm'));

  if (clearActionBtn) {
    clearActionBtn.addEventListener('click', async () => {
      clearActionBtn.disabled = true;
      clearActionBtn.textContent = 'Processing...';

      try {
        if (activeClearAction === 'transactions') {
          const startDate = $('#clear-start-date')?.value || null;
          const endDate = $('#clear-end-date')?.value || null;
          const res = await api('/api/data/clear-transactions', {
            method: 'POST',
            body: JSON.stringify({ start_date: startDate, end_date: endDate }),
          });
          showToast(`Cleared ${res.cleared || 0} transactions`, 'success');
        } else if (activeClearAction === 'udhar') {
          const res = await api('/api/data/clear-udhar', { method: 'POST' });
          showToast(`Cleared ${res.cleared || 0} udhar records`, 'success');
        } else if (activeClearAction === 'everything') {
          await api('/api/data/clear-everything', {
            method: 'POST',
            body: JSON.stringify({ confirmation: 'CLEAR EVERYTHING' }),
          });
          showToast('All financial records cleared', 'success');
        } else if (activeClearAction === 'account') {
          await api('/api/data/account', {
            method: 'DELETE',
            body: JSON.stringify({ confirmation: 'DELETE MY ACCOUNT' }),
          });
          showToast('Account deleted. Goodbye.', 'info');
          closeModal('#modal-clear-confirm');
          doLogout();
          return;
        }

        closeModal('#modal-clear-confirm');
        await refreshBudgetsAndDashboard();
      } catch (err) {
        showToast(err.message || 'Operation failed', 'error');
      } finally {
        clearActionBtn.disabled = false;
        clearActionBtn.textContent = 'Confirm & Delete';
      }
    });
  }

  // Destructive triggers
  const btnClearTx = $('#btn-clear-tx-trigger');
  const btnClearUdhar = $('#btn-clear-udhar-trigger');
  const btnClearAll = $('#btn-clear-all-trigger');
  const btnDeleteAcc = $('#btn-delete-acc-trigger');

  if (btnClearTx) btnClearTx.addEventListener('click', () => openClearConfirmModal('transactions'));
  if (btnClearUdhar) btnClearUdhar.addEventListener('click', () => openClearConfirmModal('udhar'));
  if (btnClearAll) btnClearAll.addEventListener('click', () => openClearConfirmModal('everything'));
  if (btnDeleteAcc) btnDeleteAcc.addEventListener('click', () => openClearConfirmModal('account'));

  // ================================================================
  // ---------- Udhar Reminder Nudge Modal ----------
  // ================================================================

  async function openUdharReminderModal(personKey) {
    const modal = $('#modal-udhar-reminder');
    const textEl = $('#udhar-reminder-text');
    const waBtn = $('#btn-wa-reminder');
    const copyBtn = $('#btn-copy-reminder');

    if (!modal) return;

    if (textEl) textEl.textContent = 'Generating reminder...';
    modal.style.display = 'flex';

    try {
      const data = await api(`/api/udhar/person/${encodeURIComponent(personKey)}/reminder`);
      const reminderText = data.text || '';
      const waLink = data.wa_link || `https://wa.me/?text=${encodeURIComponent(reminderText)}`;

      if (textEl) textEl.textContent = reminderText;
      if (waBtn) waBtn.href = waLink;

      if (copyBtn) {
        copyBtn.onclick = async () => {
          try {
            await navigator.clipboard.writeText(reminderText);
            showToast('Reminder message copied to clipboard!', 'success');
          } catch (e) {
            showToast('Could not copy automatically. Please select text manually.', 'info');
          }
        };
      }
    } catch (err) {
      if (textEl) textEl.textContent = 'Could not load reminder message: ' + err.message;
    }
  }

  const udharReminderClose = $('#udhar-reminder-close');
  const udharReminderCancel = $('#udhar-reminder-cancel-btn');

  if (udharReminderClose) udharReminderClose.addEventListener('click', () => closeModal('#modal-udhar-reminder'));
  if (udharReminderCancel) udharReminderCancel.addEventListener('click', () => closeModal('#modal-udhar-reminder'));



  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  }

  // ---------- Init ----------

  tryRestore();
})();
