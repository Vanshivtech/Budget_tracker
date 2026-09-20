/* ================================================================
   Budget Tracker — Client-Side Application Logic
   Authentication, Real-time Budget Overview, Recent Transactions,
   Contextual AI Chat & Multi-User Tab Isolation
   ================================================================ */

(() => {
    "use strict";

    // ---------- Storage Keys ----------
    const TOKEN_KEY = "budget_tracker_token";
    const USER_KEY = "budget_tracker_user";
    const SESSION_KEY = "budget_tracker_session_id";

    // ---------- Active In-Memory State (Per-Tab Isolated) ----------
    let activeToken = null;
    let activeUser = null;
    let activeSessionId = null;
    let isWaiting = false;
    let authMode = "login"; // "login" | "signup"

    // Welcome banner HTML template for clean resets
    const WELCOME_BANNER_HTML = `
        <div class="welcome-message" id="welcomeBanner">
            <div class="welcome-avatar">
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none">
                    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z" fill="currentColor"/>
                </svg>
            </div>
            <h3>Welcome to your Budget Assistant 👋</h3>
            <p>Track expenses, set budgets, or adjust transactions using everyday English. Try clicking an example below:</p>
            <div class="welcome-examples">
                <button class="example-chip" data-message="spent 350 on lunch">🍜 "Spent 350 on lunch"</button>
                <button class="example-chip" data-message="set food budget to 8000">📊 "Set food budget to 8000"</button>
                <button class="example-chip" data-message="actually it was 400">✏️ "Actually it was 400"</button>
                <button class="example-chip" data-message="how am I doing this month?">📈 "How am I doing this month?"</button>
            </div>
        </div>
    `;

    // Initialize session ID
    function initSessionId() {
        let id = sessionStorage.getItem(SESSION_KEY);
        if (!id) {
            id = crypto.randomUUID();
            sessionStorage.setItem(SESSION_KEY, id);
        }
        return id;
    }

    activeSessionId = initSessionId();

    function getToken() {
        return activeToken || sessionStorage.getItem(TOKEN_KEY) || localStorage.getItem(TOKEN_KEY);
    }

    function getUser() {
        if (activeUser) return activeUser;
        const raw = sessionStorage.getItem(USER_KEY) || localStorage.getItem(USER_KEY);
        try {
            return raw ? JSON.parse(raw) : null;
        } catch {
            return null;
        }
    }

    function setAuth(token, user) {
        activeToken = token;
        activeUser = user;
        activeSessionId = crypto.randomUUID();

        // Write to both sessionStorage (tab-scoped) and localStorage (persistent)
        sessionStorage.setItem(TOKEN_KEY, token);
        sessionStorage.setItem(USER_KEY, JSON.stringify(user));
        sessionStorage.setItem(SESSION_KEY, activeSessionId);

        localStorage.setItem(TOKEN_KEY, token);
        localStorage.setItem(USER_KEY, JSON.stringify(user));
    }

    function clearAuth() {
        activeToken = null;
        activeUser = null;
        activeSessionId = crypto.randomUUID();

        sessionStorage.removeItem(TOKEN_KEY);
        sessionStorage.removeItem(USER_KEY);
        sessionStorage.removeItem(SESSION_KEY);

        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(USER_KEY);
        localStorage.removeItem(SESSION_KEY);
    }

    // ---------- DOM References ----------
    // Auth
    const authScreen    = document.getElementById("authScreen");
    const mainApp       = document.getElementById("mainApp");
    const authForm      = document.getElementById("authForm");
    const authEmail     = document.getElementById("authEmail");
    const authPassword  = document.getElementById("authPassword");
    const authSubmitBtn = document.getElementById("authSubmitBtn");
    const authError     = document.getElementById("authError");
    const tabLogin      = document.getElementById("tabLogin");
    const tabSignup     = document.getElementById("tabSignup");
    const authToggleBtn = document.getElementById("authToggleBtn");
    const authToggleHint= document.getElementById("authToggleHint");

    // Nav
    const navUserEmail  = document.getElementById("navUserEmail");
    const logoutBtn     = document.getElementById("logoutBtn");

    // Overview
    const overviewPanel = document.getElementById("overviewPanel");
    const overviewToggle= document.getElementById("overviewToggle");
    const overviewMonth = document.getElementById("overviewMonth");
    const totalSpent    = document.getElementById("totalSpent");
    const totalBudget   = document.getElementById("totalBudget");
    const emptyState    = document.getElementById("emptyState");
    const categoryList  = document.getElementById("categoryList");
    const recentList    = document.getElementById("recentList");
    const categoriesSection = document.getElementById("categoriesSection");
    const recentSection = document.getElementById("recentSection");

    // Chat
    const chatMessages  = document.getElementById("chatMessages");
    const chatForm      = document.getElementById("chatForm");
    const chatInput     = document.getElementById("chatInput");
    const sendBtn       = document.getElementById("sendBtn");
    const chatStatus    = document.getElementById("chatStatus");
    const quickActions  = document.getElementById("quickActions");

    // ---------- Category Visuals ----------
    const CATEGORY_COLORS = {
        food: "#F97316",
        groceries: "#10B981",
        travel: "#38BDF8",
        rent: "#A855F7",
        bills: "#EC4899",
        shopping: "#EAB308",
        health: "#14B8A6",
        entertainment: "#6366F1",
        other: "#94A3B8"
    };

    const CATEGORY_ICONS = {
        food: "🍜",
        groceries: "🛒",
        travel: "🚗",
        rent: "🏠",
        bills: "📄",
        shopping: "🛍️",
        health: "💊",
        entertainment: "🎬",
        other: "💳"
    };

    // ---------- Formatters & Helpers ----------
    function formatCurrency(amount) {
        return "₹" + Number(amount).toLocaleString("en-IN", {
            minimumFractionDigits: 0,
            maximumFractionDigits: 0,
        });
    }

    function monthLabel(monthStr) {
        if (!monthStr) return "";
        const [y, m] = monthStr.split("-");
        const date = new Date(parseInt(y), parseInt(m) - 1);
        return date.toLocaleDateString("en-IN", { month: "long", year: "numeric" });
    }

    function formatRelativeDate(dateStr) {
        if (!dateStr) return "";
        const date = new Date(dateStr);
        const now = new Date();
        const diffMs = now.getTime() - date.getTime();
        const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

        if (date.toDateString() === now.toDateString()) return "Today";

        const yesterday = new Date(now);
        yesterday.setDate(yesterday.getDate() - 1);
        if (date.toDateString() === yesterday.toDateString()) return "Yesterday";

        if (diffDays > 1 && diffDays < 7) return `${diffDays} days ago`;
        return date.toLocaleDateString("en-IN", { month: "short", day: "numeric" });
    }

    function statusTier(pct) {
        if (pct === null || pct === undefined) return null;
        if (pct >= 100) return "danger";
        if (pct >= 70)  return "warning";
        return "safe";
    }

    function scrollToBottom() {
        requestAnimationFrame(() => {
            chatMessages.scrollTop = chatMessages.scrollHeight;
        });
    }

    // ---------- State Resets (Zero Stale Data) ----------
    function resetChatUI() {
        chatMessages.innerHTML = WELCOME_BANNER_HTML;
        chatInput.value = "";
        autoResize();
        isWaiting = false;
        sendBtn.disabled = false;
        chatStatus.textContent = "Online";
        chatStatus.style.color = "var(--green)";
    }

    function resetOverviewUI() {
        overviewMonth.textContent = "";
        totalSpent.textContent = "₹0";
        totalBudget.textContent = "";
        categoryList.innerHTML = "";
        recentList.innerHTML = "";
        emptyState.style.display = "block";
        categoriesSection.style.display = "none";
        recentSection.style.display = "none";
        updateContextualChips([]);
    }

    function resetAppState() {
        resetChatUI();
        resetOverviewUI();
    }

    // ---------- Authenticated Fetch ----------
    async function authFetch(url, options = {}) {
        const token = getToken();
        if (!token) {
            handleLogout();
            throw new Error("No authentication token available.");
        }

        const headers = {
            ...(options.headers || {}),
            "Authorization": `Bearer ${token}`
        };

        const res = await fetch(url, { ...options, headers });
        if (res.status === 401) {
            handleLogout();
            throw new Error("Session expired. Please log in again.");
        }
        return res;
    }

    // ---------- Auth Management ----------
    function setAuthMode(mode) {
        authMode = mode;
        authError.style.display = "none";
        authError.textContent = "";

        if (mode === "login") {
            tabLogin.classList.add("active");
            tabSignup.classList.remove("active");
            authSubmitBtn.textContent = "Sign In";
            authToggleHint.textContent = "Don't have an account?";
            authToggleBtn.textContent = "Create an account";
        } else {
            tabSignup.classList.add("active");
            tabLogin.classList.remove("active");
            authSubmitBtn.textContent = "Create Account";
            authToggleHint.textContent = "Already have an account?";
            authToggleBtn.textContent = "Sign in";
        }
    }

    function showAuthError(msg) {
        authError.textContent = msg;
        authError.style.display = "block";
    }

    async function handleAuthSubmit(e) {
        e.preventDefault();
        authError.style.display = "none";
        const email = authEmail.value.trim();
        const password = authPassword.value;

        if (!email || !password) {
            showAuthError("Please fill in both email and password.");
            return;
        }

        authSubmitBtn.disabled = true;
        authSubmitBtn.textContent = authMode === "login" ? "Signing in…" : "Creating account…";

        const endpoint = authMode === "login" ? "/api/login" : "/api/signup";

        try {
            const res = await fetch(endpoint, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email, password })
            });

            const data = await res.json();
            if (!res.ok) {
                throw new Error(data.detail || "Authentication failed. Please check your credentials.");
            }

            // 1. Overwrite token and user in memory and storages BEFORE any API call
            setAuth(data.token, data.user);

            // 2. Clear input fields
            authEmail.value = "";
            authPassword.value = "";

            // 3. Reset and show fresh app state
            showMainApp(data.user);

        } catch (err) {
            showAuthError(err.message);
        } finally {
            authSubmitBtn.disabled = false;
            authSubmitBtn.textContent = authMode === "login" ? "Sign In" : "Create Account";
        }
    }

    function handleLogout() {
        clearAuth();
        resetAppState();

        mainApp.style.display = "none";
        authScreen.style.display = "flex";
        authEmail.value = "";
        authPassword.value = "";
        setAuthMode("login");
    }

    function showMainApp(user) {
        activeUser = user;
        authScreen.style.display = "none";
        mainApp.style.display = "flex";
        navUserEmail.textContent = user.email;

        // Reset all UI state so previous session messages/cards are 100% gone
        resetAppState();

        // Fetch fresh summary for this newly authenticated user
        fetchSummary();
    }

    // ---------- Budget Overview Rendering ----------
    function renderCategoryCard(item) {
        const card = document.createElement("div");
        card.className = "category-card";

        const hasBudget = item.budget !== null && item.budget !== undefined;
        const pct = item.percentage;
        const tier = statusTier(pct);
        const isOver = pct !== null && pct >= 100;
        const catColor = CATEGORY_COLORS[item.category] || CATEGORY_COLORS.other;

        if (!hasBudget) {
            card.classList.add("no-budget-card");
        }

        let badgeHtml = "";
        if (hasBudget && pct !== null) {
            const labels = {
                safe: "On track",
                warning: "Approaching limit",
                danger: isOver ? "Over budget" : "Near limit"
            };
            badgeHtml = `
                <div class="category-badge-wrap">
                    <span class="category-pct pct-${tier}">${pct}%</span>
                    <span class="category-status-pill badge-${tier}">${labels[tier]}</span>
                </div>
            `;
        }

        let amountsHtml;
        if (hasBudget) {
            amountsHtml = `<span class="category-spent-num">${formatCurrency(item.spent)}</span> of ${formatCurrency(item.budget)}`;
        } else {
            amountsHtml = `<span class="category-spent-num">${formatCurrency(item.spent)}</span> <span style="color:var(--text-muted)">· no limit set</span>`;
        }

        const barWidth = hasBudget ? Math.min(Math.max(pct, 4), 100) : 0;

        card.innerHTML = `
            <div class="category-top-row">
                <div class="category-title-wrap">
                    <span class="category-dot" style="background: ${catColor}"></span>
                    <span class="category-name">${item.category}</span>
                </div>
                ${badgeHtml}
            </div>
            <div class="category-amounts">${amountsHtml}</div>
            ${hasBudget ? `
                <div class="progress-track">
                    <div class="progress-fill fill-${tier}" style="width: ${barWidth}%"></div>
                </div>
            ` : ""}
        `;

        return card;
    }

    function renderRecentTransaction(tx) {
        const item = document.createElement("div");
        item.className = "recent-item";

        const cat = (tx.category || "other").toLowerCase();
        const icon = CATEGORY_ICONS[cat] || "💳";
        const relDate = formatRelativeDate(tx.date);

        item.innerHTML = `
            <div class="recent-left">
                <div class="recent-icon-badge">${icon}</div>
                <div class="recent-details">
                    <span class="recent-category">${tx.category}</span>
                    <span class="recent-note" title="${tx.note || tx.category}">${tx.note || "No note"}</span>
                </div>
            </div>
            <div class="recent-right">
                <div class="recent-amount">${formatCurrency(tx.amount)}</div>
                <div class="recent-date">${relDate}</div>
            </div>
        `;

        return item;
    }

    function updateContextualChips(categories) {
        // Reset base chips
        quickActions.innerHTML = `
            <button class="action-chip" data-message="Log an expense">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M12 4v16m-8-8h16" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/></svg>
                Log expense
            </button>
            <button class="action-chip" data-message="Budget status">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M9 19V6l12-3v13M9 19c0 1.1-1.34 2-3 2s-3-.9-3-2 1.34-2 3-2 3 .9 3 2zM21 16c0 1.1-1.34 2-3 2s-3-.9-3-2 1.34-2 3-2 3 .9 3 2z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
                Budget status
            </button>
            <button class="action-chip" data-message="Monthly summary">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M4 6h16M4 12h16M4 18h10" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
                Monthly summary
            </button>
        `;

        // Check for categories over budget (percentage >= 100) or high spend (>= 70)
        const overBudgetCats = (categories || []).filter(c => c.percentage !== null && c.percentage >= 100);
        const nearBudgetCats = (categories || []).filter(c => c.percentage !== null && c.percentage >= 70 && c.percentage < 100);

        if (overBudgetCats.length > 0) {
            const topOver = overBudgetCats[0];
            const chip = document.createElement("button");
            chip.className = "action-chip context-warning";
            chip.dataset.message = `Why is ${topOver.category} over budget?`;
            chip.innerHTML = `⚠️ Why is ${topOver.category} over budget?`;
            quickActions.appendChild(chip);
        } else if (nearBudgetCats.length > 0) {
            const topNear = nearBudgetCats[0];
            const chip = document.createElement("button");
            chip.className = "action-chip";
            chip.dataset.message = `How much is left in my ${topNear.category} budget?`;
            chip.innerHTML = `📊 Check ${topNear.category} balance`;
            quickActions.appendChild(chip);
        }

        // Re-attach listeners to action chips
        quickActions.querySelectorAll(".action-chip").forEach(chip => {
            chip.addEventListener("click", () => {
                chatInput.value = chip.dataset.message;
                chatInput.focus();
            });
        });
    }

    async function fetchSummary() {
        const expectedUser = activeUser;
        if (!expectedUser) return;

        try {
            const res = await authFetch("/api/summary");
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();

            // Defensive check: if response belongs to a different user, drop it!
            if (data.user_id && activeUser && data.user_id !== activeUser.id) {
                console.warn(`[Security] Received summary for user ${data.user_id}, but active user is ${activeUser.id}. Discarding stale data.`);
                return;
            }

            overviewMonth.textContent = monthLabel(data.month);

            // Total Hero Card
            totalSpent.textContent = formatCurrency(data.total_spent);
            if (data.total_budget) {
                const totalPct = Math.round((data.total_spent / data.total_budget) * 100);
                totalBudget.textContent = `of ${formatCurrency(data.total_budget)} total budget (${totalPct}%)`;
            } else {
                totalBudget.textContent = "No total monthly limit set";
            }

            // Categories
            categoryList.innerHTML = "";
            const hasCategories = data.categories && data.categories.length > 0;
            const hasTransactions = data.recent_transactions && data.recent_transactions.length > 0;

            if (!hasCategories && !hasTransactions) {
                emptyState.style.display = "block";
                categoriesSection.style.display = "none";
                recentSection.style.display = "none";
            } else {
                emptyState.style.display = "none";
                categoriesSection.style.display = "flex";
                recentSection.style.display = "flex";

                // Render categories
                data.categories.forEach(item => {
                    categoryList.appendChild(renderCategoryCard(item));
                });

                // Render recent transactions
                recentList.innerHTML = "";
                if (hasTransactions) {
                    data.recent_transactions.forEach(tx => {
                        recentList.appendChild(renderRecentTransaction(tx));
                    });
                } else {
                    recentList.innerHTML = `<p style="font-size:0.85rem;color:var(--text-muted);padding:8px 0;">No transactions yet.</p>`;
                }
            }

            // Update contextual quick action chips
            updateContextualChips(data.categories || []);

        } catch (err) {
            console.error("Summary fetch error:", err);
        }
    }

    // ---------- Chat Management ----------
    function removeWelcomeBanner() {
        const banner = document.getElementById("welcomeBanner");
        if (banner && banner.parentNode) {
            banner.remove();
        }
    }

    function addMessage(text, role) {
        removeWelcomeBanner();

        const wrapper = document.createElement("div");
        wrapper.className = `message message-${role}`;

        const avatar = document.createElement("div");
        avatar.className = "message-avatar";

        if (role === "user") {
            avatar.textContent = "Y";
        } else {
            avatar.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z" fill="currentColor"/>
            </svg>`;
        }

        const bubble = document.createElement("div");
        bubble.className = "message-bubble";
        bubble.textContent = text;

        wrapper.appendChild(avatar);
        wrapper.appendChild(bubble);
        chatMessages.appendChild(wrapper);
        scrollToBottom();
    }

    function showTyping() {
        const el = document.createElement("div");
        el.className = "typing-indicator";
        el.id = "typingIndicator";

        const avatar = document.createElement("div");
        avatar.className = "message-avatar";
        avatar.style.background = "var(--bg-elevated)";
        avatar.style.color = "var(--text-secondary)";
        avatar.style.border = "1px solid var(--border-subtle)";
        avatar.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z" fill="currentColor"/>
        </svg>`;

        const bubble = document.createElement("div");
        bubble.className = "typing-bubble";
        bubble.innerHTML = `<span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>`;

        el.appendChild(avatar);
        el.appendChild(bubble);
        chatMessages.appendChild(el);
        scrollToBottom();
    }

    function hideTyping() {
        const el = document.getElementById("typingIndicator");
        if (el) el.remove();
    }

    async function sendMessage(text) {
        if (!text.trim() || isWaiting || !activeUser) return;
        const expectedUserId = activeUser.id;

        isWaiting = true;
        sendBtn.disabled = true;
        chatStatus.textContent = "Thinking…";
        chatStatus.style.color = "var(--amber)";

        addMessage(text, "user");
        chatInput.value = "";
        autoResize();
        showTyping();

        try {
            const res = await authFetch("/api/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message: text, session_id: activeSessionId })
            });

            hideTyping();

            if (!res.ok) throw new Error(`HTTP ${res.status}`);

            const data = await res.json();

            // Defensive check: if response belongs to another user, discard it!
            if (data.user_id && activeUser && data.user_id !== activeUser.id) {
                console.warn(`[Security] Received chat reply for user ${data.user_id}, but active user is ${activeUser.id}. Discarding stale reply.`);
                return;
            }

            addMessage(data.reply, "bot");

            // Auto-refresh budget overview and recent transactions after every exchange
            await fetchSummary();

        } catch (err) {
            hideTyping();
            addMessage("Something went wrong — please try again.", "bot");
            console.error("Chat error:", err);
        } finally {
            isWaiting = false;
            sendBtn.disabled = false;
            chatStatus.textContent = "Online";
            chatStatus.style.color = "var(--green)";
        }
    }

    function autoResize() {
        chatInput.style.height = "auto";
        chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + "px";
    }

    // ---------- Event Listeners ----------

    // Auth events
    tabLogin.addEventListener("click", () => setAuthMode("login"));
    tabSignup.addEventListener("click", () => setAuthMode("signup"));
    authToggleBtn.addEventListener("click", () => {
        setAuthMode(authMode === "login" ? "signup" : "login");
    });
    authForm.addEventListener("submit", handleAuthSubmit);
    logoutBtn.addEventListener("click", handleLogout);

    // Chat form events
    chatForm.addEventListener("submit", (e) => {
        e.preventDefault();
        sendMessage(chatInput.value);
    });

    chatInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendMessage(chatInput.value);
        }
    });

    chatInput.addEventListener("input", autoResize);

    // Welcome example chips click handler
    document.addEventListener("click", (e) => {
        const chip = e.target.closest(".example-chip");
        if (chip && chip.dataset.message) {
            sendMessage(chip.dataset.message);
        }
    });

    // Mobile overview toggle
    overviewToggle.addEventListener("click", () => {
        overviewPanel.classList.toggle("collapsed");
    });

    // Default collapse on mobile
    if (window.innerWidth <= 900) {
        overviewPanel.classList.add("collapsed");
    }

    // ---------- App Initialization ----------
    const existingToken = getToken();
    const existingUser = getUser();

    if (existingToken && existingUser) {
        activeToken = existingToken;
        showMainApp(existingUser);
    } else {
        authScreen.style.display = "flex";
        mainApp.style.display = "none";
    }

})();
