/* ================================================================
   ABT — AI Budget Tracker Application Logic
   Auth · Chat · Dashboard · Udhar · Insights · Goals
   ================================================================ */

(() => {
    "use strict";

    // ---------- Storage Keys ----------
    const TOKEN_KEY   = "abt_token";
    const USER_KEY    = "abt_user";
    const SESSION_KEY = "abt_session_id";

    // ---------- In-Memory State ----------
    let activeToken     = null;
    let activeUser      = null;
    let activeSessionId = null;
    let isWaiting       = false;
    let authMode        = "login";
    let currentTab      = "chat";

    // ---------- Helpers ----------
    function uid() { return crypto.randomUUID(); }

    function formatCurrency(amount) {
        return "\u20B9" + Number(amount).toLocaleString("en-IN", {
            minimumFractionDigits: 0,
            maximumFractionDigits: 0,
        });
    }

    function monthLabel(monthStr) {
        if (!monthStr) return "";
        const [y, m] = monthStr.split("-");
        const d = new Date(parseInt(y), parseInt(m) - 1);
        return d.toLocaleDateString("en-IN", { month: "long", year: "numeric" });
    }

    function formatDate(dateStr) {
        if (!dateStr) return "";
        const d = new Date(dateStr);
        return d.toLocaleDateString("en-IN", { month: "short", day: "numeric", year: "numeric" });
    }

    function statusTier(pct) {
        if (pct === null || pct === undefined) return "safe";
        if (pct >= 100) return "danger";
        if (pct >= 70)  return "warning";
        return "safe";
    }

    // ---------- Auth Storage ----------
    function getToken() {
        return activeToken || sessionStorage.getItem(TOKEN_KEY) || localStorage.getItem(TOKEN_KEY) || sessionStorage.getItem("art_token") || localStorage.getItem("art_token");
    }

    function getUser() {
        if (activeUser) return activeUser;
        const raw = sessionStorage.getItem(USER_KEY) || localStorage.getItem(USER_KEY) || sessionStorage.getItem("art_user") || localStorage.getItem("art_user");
        try { return raw ? JSON.parse(raw) : null; } catch { return null; }
    }

    function setAuth(token, user) {
        activeToken     = token;
        activeUser      = user;
        activeSessionId = uid();

        sessionStorage.setItem(TOKEN_KEY, token);
        sessionStorage.setItem(USER_KEY, JSON.stringify(user));
        sessionStorage.setItem(SESSION_KEY, activeSessionId);

        localStorage.setItem(TOKEN_KEY, token);
        localStorage.setItem(USER_KEY, JSON.stringify(user));
    }

    function clearAuth() {
        activeToken     = null;
        activeUser      = null;
        activeSessionId = uid();

        [TOKEN_KEY, USER_KEY, SESSION_KEY, "art_token", "art_user", "art_session_id"].forEach(k => {
            sessionStorage.removeItem(k);
            localStorage.removeItem(k);
        });
    }

    // ---------- Authenticated Fetch ----------
    async function authFetch(url, options = {}) {
        const token = getToken();
        if (!token) { handleLogout(); throw new Error("Not authenticated"); }
        const res = await fetch(url, {
            ...options,
            headers: {
                ...(options.headers || {}),
                "Authorization": `Bearer ${token}`,
            }
        });
        if (res.status === 401) { handleLogout(); throw new Error("Session expired"); }
        return res;
    }

    // ---------- DOM Refs ----------
    // Auth
    const authScreen    = document.getElementById("authScreen");
    const authCard      = document.getElementById("authCard");
    const tabLogin      = document.getElementById("tabLogin");
    const tabSignup     = document.getElementById("tabSignup");
    const authError     = document.getElementById("authError");
    const authForm      = document.getElementById("authForm");
    const authEmail     = document.getElementById("authEmail");
    const authPassword  = document.getElementById("authPassword");
    const authSubmitBtn = document.getElementById("authSubmitBtn");
    const authToggleBtn = document.getElementById("authToggleBtn");
    const authSwitchHint= document.getElementById("authSwitchHint");

    // App shell
    const mainApp       = document.getElementById("mainApp");
    const logoutBtn     = document.getElementById("logoutBtn");
    const sidebarEmail  = document.getElementById("sidebarEmail");
    const sidebarAvatar = document.getElementById("sidebarAvatar");
    const drawerEmail   = document.getElementById("drawerEmail");
    const drawerAvatar  = document.getElementById("drawerAvatar");

    // Mobile nav
    const mobileMenuBtn = document.getElementById("mobileMenuBtn");
    const mobileOverlay = document.getElementById("mobileOverlay");
    const mobileDrawer  = document.getElementById("mobileDrawer");
    const drawerClose   = document.getElementById("drawerClose");
    const drawerLogout  = document.getElementById("drawerLogout");

    // Tab panes
    const tabPaneChat      = document.getElementById("tabChat");
    const tabPaneDashboard = document.getElementById("tabDashboard");
    const tabPaneUdhar     = document.getElementById("tabUdhar");

    // Sidebar nav buttons
    const navChat      = document.getElementById("navChat");
    const navDashboard = document.getElementById("navDashboard");
    const navUdhar     = document.getElementById("navUdhar");

    // Mobile tabbar
    const tabbarChat      = document.getElementById("tabbarChat");
    const tabbarDashboard = document.getElementById("tabbarDashboard");
    const tabbarUdhar     = document.getElementById("tabbarUdhar");
    const tabbarInsights  = document.getElementById("tabbarInsights");

    // Insights
    const tabPaneInsights = document.getElementById("tabInsights");
    const recapSpent      = document.getElementById("recapSpent");
    const recapChange     = document.getElementById("recapChange");
    const recapTopCat     = document.getElementById("recapTopCat");
    const recapStreak     = document.getElementById("recapStreak");
    const insightCards    = document.getElementById("insightCards");
    const goalsListInsights = document.getElementById("goalsListInsights");
    const safeSpendCard   = document.getElementById("safeSpendCard");
    const safeAmount      = document.getElementById("safeAmount");
    const addGoalBtn      = document.getElementById("addGoalBtn");
    const recapNarration  = document.getElementById("recapNarration");

    // Home Card
    const homeCard        = document.getElementById("homeCard");
    const homeSafeSpend   = document.getElementById("homeSafeSpend");
    const homeSavingsRate = document.getElementById("homeSavingsRate");
    const homeGoalProgress= document.getElementById("homeGoalProgress");
    const homeStreakBadge = document.getElementById("homeStreakBadge");

    // Chat
    const chatMessages  = document.getElementById("chatMessages");
    const chatEmpty     = document.getElementById("chatEmpty");
    const suggestionChips = document.getElementById("suggestionChips");
    const chatForm      = document.getElementById("chatForm");
    const chatInput     = document.getElementById("chatInput");
    const sendBtn       = document.getElementById("sendBtn");

    // Dashboard
    const dashMonth        = document.getElementById("dashMonth");
    const dashTotalSpent   = document.getElementById("dashTotalSpent");
    const dashTotalBudget  = document.getElementById("dashTotalBudget");
    const dashUdharNet     = document.getElementById("dashUdharNet");
    const dashCategoryBars = document.getElementById("dashCategoryBars");
    const budgetVsActual   = document.getElementById("budgetVsActual");
    const trendCanvas      = document.getElementById("trendCanvas");
    const dailyCanvas      = document.getElementById("dailyCanvas");
    const dashDailyMonth   = document.getElementById("dashDailyMonth");

    // Udhar
    const addUdharBtn        = document.getElementById("addUdharBtn");
    const udharTotalLent     = document.getElementById("udharTotalLent");
    const udharTotalBorrowed = document.getElementById("udharTotalBorrowed");
    const udharNet           = document.getElementById("udharNet");
    const udharPersons       = document.getElementById("udharPersons");
    const udharModal         = document.getElementById("udharModal");
    const udharModalClose    = document.getElementById("udharModalClose");
    const udharCancelBtn     = document.getElementById("udharCancelBtn");
    const udharForm          = document.getElementById("udharForm");
    const udharPerson        = document.getElementById("udharPerson");
    const udharKind          = document.getElementById("udharKind");
    const udharAmount        = document.getElementById("udharAmount");
    const udharNote          = document.getElementById("udharNote");
    const udharDue           = document.getElementById("udharDue");

    // ================================================================
    // AUTH
    // ================================================================

    function setAuthMode(mode) {
        authMode = mode;
        authError.style.display = "none";
        authError.textContent   = "";

        if (mode === "login") {
            tabLogin.classList.add("active");
            tabSignup.classList.remove("active");
            tabLogin.setAttribute("aria-selected", "true");
            tabSignup.setAttribute("aria-selected", "false");
            authSubmitBtn.textContent = "Sign In";
            authSwitchHint.textContent = "Don't have an account?";
            authToggleBtn.textContent  = "Create an account";
            authPassword.setAttribute("autocomplete", "current-password");
        } else {
            tabSignup.classList.add("active");
            tabLogin.classList.remove("active");
            tabSignup.setAttribute("aria-selected", "true");
            tabLogin.setAttribute("aria-selected", "false");
            authSubmitBtn.textContent = "Create Account";
            authSwitchHint.textContent = "Already have an account?";
            authToggleBtn.textContent  = "Sign in";
            authPassword.setAttribute("autocomplete", "new-password");
        }
    }

    function showAuthError(msg) {
        authError.textContent   = msg;
        authError.style.display = "block";
    }

    async function handleAuthSubmit(e) {
        e.preventDefault();
        authError.style.display = "none";

        const email    = authEmail.value.trim();
        const password = authPassword.value;

        if (!email || !password) {
            showAuthError("Please fill in both email and password.");
            return;
        }

        authSubmitBtn.disabled    = true;
        authSubmitBtn.textContent = authMode === "login" ? "Signing in..." : "Creating account...";

        try {
            const res = await fetch(authMode === "login" ? "/api/login" : "/api/signup", {
                method:  "POST",
                headers: { "Content-Type": "application/json" },
                body:    JSON.stringify({ email, password }),
            });

            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || "Authentication failed.");

            setAuth(data.token, data.user);
            authEmail.value    = "";
            authPassword.value = "";
            showMainApp(data.user);

        } catch (err) {
            showAuthError(err.message);
        } finally {
            authSubmitBtn.disabled    = false;
            authSubmitBtn.textContent = authMode === "login" ? "Sign In" : "Create Account";
        }
    }

    function handleLogout() {
        clearAuth();
        resetAppState();
        mainApp.style.display   = "none";
        authScreen.style.display = "flex";
        authEmail.value    = "";
        authPassword.value = "";
        setAuthMode("login");
    }

    function showMainApp(user) {
        activeUser = user;
        authScreen.style.display = "none";
        mainApp.style.display    = "flex";

        // Update UI with user info
        const initials = (user.email || "U").charAt(0).toUpperCase();
        sidebarEmail.textContent  = user.email;
        sidebarAvatar.textContent = initials;
        drawerEmail.textContent   = user.email;
        drawerAvatar.textContent  = initials;

        resetAppState();
        loadChatHistory();
        loadHomeCard();
        switchTab("chat");
    }

    // ================================================================
    // TAB SWITCHING
    // ================================================================

    const navBtns    = [navChat, navDashboard, navUdhar, document.getElementById("navInsights")];
    const tabbarBtns = [tabbarChat, tabbarDashboard, tabbarUdhar, tabbarInsights];
    const tabPanes   = {
        chat:      tabPaneChat,
        dashboard: tabPaneDashboard,
        udhar:     tabPaneUdhar,
        insights:  tabPaneInsights,
    };

    function switchTab(tab) {
        currentTab = tab;

        // Update sidebar
        navBtns.forEach(btn => {
            const isActive = btn.dataset.tab === tab;
            btn.classList.toggle("active", isActive);
            btn.setAttribute("aria-selected", String(isActive));
        });

        // Update tabbar
        tabbarBtns.forEach(btn => {
            btn.classList.toggle("active", btn.dataset.tab === tab);
        });

        // Update drawer items
        document.querySelectorAll(".drawer-item[data-tab]").forEach(btn => {
            btn.classList.toggle("active", btn.dataset.tab === tab);
        });

        // Show correct pane
        Object.entries(tabPanes).forEach(([key, pane]) => {
            pane.classList.toggle("active", key === tab);
        });

        // Lazy-load data
        if (tab === "dashboard") loadDashboard();
        if (tab === "udhar")     loadUdhar();
        if (tab === "insights")  loadInsights();

        closeMobileDrawer();
    }

    // ================================================================
    // MOBILE DRAWER
    // ================================================================

    function openMobileDrawer() {
        mobileDrawer.classList.add("open");
        mobileOverlay.style.display = "block";
        requestAnimationFrame(() => mobileOverlay.classList.add("visible"));
    }

    function closeMobileDrawer() {
        mobileDrawer.classList.remove("open");
        mobileOverlay.classList.remove("visible");
        setTimeout(() => { mobileOverlay.style.display = "none"; }, 250);
    }

    mobileMenuBtn.addEventListener("click", openMobileDrawer);
    mobileOverlay.addEventListener("click", closeMobileDrawer);
    drawerClose.addEventListener("click", closeMobileDrawer);

    // ================================================================
    // STATE RESET
    // ================================================================

    function resetAppState() {
        // Reset chat
        chatMessages.innerHTML = "";
        chatMessages.appendChild(chatEmpty);
        chatEmpty.style.display = "flex";
        chatInput.value = "";
        autoResize();
        isWaiting = false;
        sendBtn.disabled = true;

        // Reset dashboard visuals
        dashTotalSpent.textContent  = "--";
        dashTotalBudget.textContent = "--";
        dashUdharNet.textContent    = "--";
        dashCategoryBars.innerHTML  = '<div class="dash-empty">No spending recorded yet.</div>';
        budgetVsActual.innerHTML    = '<div class="dash-empty">No budgets set yet.</div>';

        // Clear canvas
        clearCanvas(trendCanvas);
        clearCanvas(dailyCanvas);

        // Reset insights
        recapSpent.textContent   = "--";
        recapChange.textContent  = "--";
        recapTopCat.textContent  = "--";
        recapStreak.textContent  = "-- days";
        insightCards.innerHTML   = '<div class="dash-empty">Log some expenses to see personalised insights.</div>';
        goalsListInsights.innerHTML = '<div class="dash-empty">No goals set yet. Ask the assistant to help you create one.</div>';
        safeSpendCard.style.display  = "none";
        if (recapNarration) recapNarration.textContent = "";

        // Reset home card
        if (homeSafeSpend) homeSafeSpend.textContent = "--";
        if (homeSavingsRate) homeSavingsRate.textContent = "--";
        if (homeGoalProgress) homeGoalProgress.textContent = "--";
        if (homeStreakBadge) homeStreakBadge.textContent = "-- day streak";

        // Reset udhar
        udharTotalLent.textContent     = "--";
        udharTotalBorrowed.textContent = "--";
        udharNet.textContent           = "--";
        udharPersons.innerHTML         = '<div class="dash-empty">No udhar entries yet. Use "Add Entry" to get started.</div>';
    }

    function clearCanvas(canvas) {
        const ctx = canvas.getContext("2d");
        ctx.clearRect(0, 0, canvas.width, canvas.height);
    }

    // ================================================================
    // CHAT
    // ================================================================

    async function loadChatHistory() {
        try {
            const res = await authFetch("/api/chat/history");
            if (!res.ok) return;
            const data = await res.json();
            if (!data.messages || data.messages.length === 0) return;

            // Hide empty state since we have history
            chatEmpty.style.display = "none";

            data.messages.forEach(msg => {
                appendMessage(msg.content, msg.role === "user" ? "user" : "assistant", false);
            });
            scrollToBottom();
        } catch (err) {
            console.warn("Could not load chat history:", err);
        }
    }

    async function loadHomeCard() {
        if (!activeUser) return;
        try {
            const [snapRes, streakRes] = await Promise.all([
                authFetch("/api/snapshot"),
                authFetch("/api/streak"),
            ]);

            if (snapRes.ok) {
                const snap = await snapRes.json();
                if (homeSafeSpend) {
                    homeSafeSpend.textContent = snap.safe_to_spend_today !== null && snap.safe_to_spend_today !== undefined
                        ? formatCurrency(snap.safe_to_spend_today)
                        : "--";
                }
                if (homeSavingsRate) {
                    homeSavingsRate.textContent = snap.savings_rate_pct !== null && snap.savings_rate_pct !== undefined
                        ? `${snap.savings_rate_pct}%`
                        : "--";
                }
                if (homeGoalProgress) {
                    if (snap.goals && snap.goals.length > 0) {
                        const topGoal = snap.goals[0];
                        homeGoalProgress.textContent = `${topGoal.name} (${topGoal.pct_complete}%)`;
                    } else {
                        homeGoalProgress.textContent = "No goals set";
                    }
                }
            }

            if (streakRes.ok) {
                const streakData = await streakRes.json();
                if (homeStreakBadge) {
                    const days = streakData.streak || 0;
                    homeStreakBadge.textContent = `${days} day${days === 1 ? "" : "s"} streak`;
                }
            }
        } catch (err) {
            console.warn("Home card load error:", err);
        }
    }

    function appendMessage(text, role, scroll = true) {
        // Hide empty state on first real message
        if (chatEmpty && chatEmpty.parentNode === chatMessages) {
            chatEmpty.style.display = "none";
        }

        const row = document.createElement("div");
        row.className = `message-row ${role}`;

        const content = document.createElement("div");
        content.className = "message-content";
        content.textContent = text;

        row.appendChild(content);
        chatMessages.appendChild(row);

        if (scroll) scrollToBottom();
    }

    function scrollToBottom() {
        requestAnimationFrame(() => {
            chatMessages.scrollTop = chatMessages.scrollHeight;
        });
    }

    function showTyping() {
        const row = document.createElement("div");
        row.className = "typing-row";
        row.id = "typingRow";
        const dots = document.createElement("div");
        dots.className = "typing-dots";
        dots.innerHTML = `<span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>`;
        row.appendChild(dots);
        chatMessages.appendChild(row);
        scrollToBottom();
    }

    function hideTyping() {
        const el = document.getElementById("typingRow");
        if (el) el.remove();
    }

    async function sendMessage(text) {
        text = text.trim();
        if (!text || isWaiting || !activeUser) return;

        isWaiting = true;
        sendBtn.disabled = true;
        chatInput.value  = "";
        autoResize();

        appendMessage(text, "user");
        showTyping();

        try {
            const res = await authFetch("/api/chat", {
                method:  "POST",
                headers: { "Content-Type": "application/json" },
                body:    JSON.stringify({ message: text, session_id: activeSessionId }),
            });

            hideTyping();

            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();

            if (data.user_id && activeUser && data.user_id !== activeUser.id) {
                console.warn("[Security] Stale reply discarded.");
                return;
            }

            appendMessage(data.reply, "assistant");

            // Refresh data
            if (currentTab === "dashboard") loadDashboard();
            if (currentTab === "insights") loadInsights();
            loadHomeCard();

        } catch (err) {
            hideTyping();
            appendMessage("Something went wrong — please try again.", "assistant");
            console.error("Chat error:", err);
        } finally {
            isWaiting    = false;
            sendBtn.disabled = chatInput.value.trim().length === 0;
        }
    }

    function autoResize() {
        chatInput.style.height = "auto";
        const maxHeight = 144;
        chatInput.style.height = Math.min(chatInput.scrollHeight, maxHeight) + "px";
        sendBtn.disabled = chatInput.value.trim().length === 0 || isWaiting;
    }

    // Chat form events
    chatForm.addEventListener("submit", e => {
        e.preventDefault();
        sendMessage(chatInput.value);
    });

    chatInput.addEventListener("input", autoResize);

    chatInput.addEventListener("keydown", e => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendMessage(chatInput.value);
        }
    });

    // Suggestion chips
    document.addEventListener("click", e => {
        const chip = e.target.closest(".chip");
        if (chip && chip.dataset.message) {
            chatInput.value = chip.dataset.message;
            autoResize();
            sendMessage(chip.dataset.message);
        }
    });

    // Visual Viewport API for keyboard handling
    if (window.visualViewport) {
        let lastHeight = window.visualViewport.height;
        window.visualViewport.addEventListener("resize", () => {
            const currentHeight = window.visualViewport.height;
            if (currentHeight < lastHeight) {
                // Keyboard opened — scroll to bottom so composer stays visible
                scrollToBottom();
            }
            lastHeight = currentHeight;
        });
    }

    // ================================================================
    // DASHBOARD
    // ================================================================

    const CATEGORY_COLORS = {
        food:          "#F97316",
        groceries:     "#22C55E",
        travel:        "#38BDF8",
        rent:          "#A855F7",
        bills:         "#EC4899",
        shopping:      "#EAB308",
        health:        "#14B8A6",
        entertainment: "#6366F1",
        other:         "#71717A",
    };

    function getCatColor(cat) {
        return CATEGORY_COLORS[cat.toLowerCase()] || "#5865F2";
    }

    async function loadDashboard() {
        if (!activeUser) return;
        try {
            const res = await authFetch("/api/dashboard");
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            renderDashboard(data);
        } catch (err) {
            console.error("Dashboard error:", err);
        }
    }

    function renderDashboard(data) {
        dashMonth.textContent = monthLabel(data.month);
        dashDailyMonth.textContent = monthLabel(data.month);

        dashTotalSpent.textContent = formatCurrency(data.total_spent || 0);
        dashTotalBudget.textContent = data.total_budget
            ? formatCurrency(data.total_budget)
            : "Not set";

        const net = data.udhar_net || 0;
        dashUdharNet.textContent = formatCurrency(Math.abs(net));
        dashUdharNet.style.color = net >= 0 ? "var(--green)" : "var(--red)";

        // Category bars
        renderCategoryBars(data.categories || []);

        // Budget vs actual
        renderBudgetVsActual(data.categories || []);

        // Charts
        renderTrendChart(data.monthly_trends || []);
        renderDailyChart(data.daily_spend || []);
    }

    function renderCategoryBars(categories) {
        if (!categories.length) {
            dashCategoryBars.innerHTML = '<div class="dash-empty">No spending recorded yet.</div>';
            return;
        }

        const max = Math.max(...categories.map(c => c.spent), 1);
        dashCategoryBars.innerHTML = "";

        categories.slice(0, 8).forEach(cat => {
            const pct = Math.round((cat.spent / max) * 100);
            const row = document.createElement("div");
            row.className = "cat-bar-row";
            row.innerHTML = `
                <div class="cat-bar-meta">
                    <span class="cat-bar-name">${escHtml(cat.category)}</span>
                    <span class="cat-bar-amount">${formatCurrency(cat.spent)}</span>
                </div>
                <div class="cat-bar-track">
                    <div class="cat-bar-fill" style="width:${pct}%;background:${getCatColor(cat.category)};"></div>
                </div>
            `;
            dashCategoryBars.appendChild(row);
        });
    }

    function renderBudgetVsActual(categories) {
        const withBudget = categories.filter(c => c.budget !== null);
        if (!withBudget.length) {
            budgetVsActual.innerHTML = '<div class="dash-empty">No budgets set yet.</div>';
            return;
        }

        budgetVsActual.innerHTML = "";
        withBudget.forEach(cat => {
            const pct = Math.min(cat.percentage || 0, 120);
            const tier = statusTier(cat.percentage);
            const row = document.createElement("div");
            row.className = "bva-row";
            row.innerHTML = `
                <span class="bva-label">${escHtml(cat.category)}</span>
                <div class="bva-track">
                    <div class="bva-fill ${tier}" style="width:${Math.min(pct, 100)}%"></div>
                </div>
                <span class="bva-pct ${tier}">${Math.round(cat.percentage || 0)}%</span>
            `;
            budgetVsActual.appendChild(row);
        });
    }

    function renderTrendChart(trends) {
        const ctx = trendCanvas.getContext("2d");
        const W = trendCanvas.width;
        const H = trendCanvas.height;
        ctx.clearRect(0, 0, W, H);

        if (!trends.length) {
            ctx.fillStyle = "rgba(255,255,255,0.1)";
            ctx.font = "12px Inter, sans-serif";
            ctx.textAlign = "center";
            ctx.fillText("No data yet", W / 2, H / 2);
            return;
        }

        const pad = { top: 16, right: 16, bottom: 30, left: 48 };
        const chartW = W - pad.left - pad.right;
        const chartH = H - pad.top - pad.bottom;
        const max = Math.max(...trends.map(t => t.total), 1);

        const xs = trends.map((_, i) => pad.left + (i / (trends.length - 1 || 1)) * chartW);
        const ys = trends.map(t => pad.top + chartH - (t.total / max) * chartH);

        // Grid lines
        ctx.strokeStyle = "rgba(255,255,255,0.05)";
        ctx.lineWidth = 1;
        [0, 0.25, 0.5, 0.75, 1].forEach(frac => {
            const y = pad.top + chartH * frac;
            ctx.beginPath();
            ctx.moveTo(pad.left, y);
            ctx.lineTo(pad.left + chartW, y);
            ctx.stroke();
        });

        // Fill area
        const grad = ctx.createLinearGradient(0, pad.top, 0, pad.top + chartH);
        grad.addColorStop(0, "rgba(88,101,242,0.25)");
        grad.addColorStop(1, "rgba(88,101,242,0)");
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.moveTo(xs[0], pad.top + chartH);
        xs.forEach((x, i) => ctx.lineTo(x, ys[i]));
        ctx.lineTo(xs[xs.length - 1], pad.top + chartH);
        ctx.closePath();
        ctx.fill();

        // Line
        ctx.strokeStyle = "#5865F2";
        ctx.lineWidth = 2;
        ctx.lineJoin = "round";
        ctx.beginPath();
        xs.forEach((x, i) => i === 0 ? ctx.moveTo(x, ys[i]) : ctx.lineTo(x, ys[i]));
        ctx.stroke();

        // Dots
        xs.forEach((x, i) => {
            ctx.fillStyle = "#5865F2";
            ctx.beginPath();
            ctx.arc(x, ys[i], 3, 0, Math.PI * 2);
            ctx.fill();
        });

        // X labels
        ctx.fillStyle = "rgba(255,255,255,0.35)";
        ctx.font = "10px Inter, sans-serif";
        ctx.textAlign = "center";
        trends.forEach((t, i) => {
            const label = t.month ? t.month.slice(5) : "";
            ctx.fillText(label, xs[i], H - 6);
        });

        // Y axis
        ctx.textAlign = "right";
        [0, 0.5, 1].forEach(frac => {
            const val = Math.round(max * (1 - frac));
            const y = pad.top + chartH * frac;
            ctx.fillText(val >= 1000 ? (val / 1000).toFixed(0) + "k" : val, pad.left - 6, y + 4);
        });
    }

    function renderDailyChart(daily) {
        const ctx = dailyCanvas.getContext("2d");
        const W = dailyCanvas.width;
        const H = dailyCanvas.height;
        ctx.clearRect(0, 0, W, H);

        if (!daily.length) {
            ctx.fillStyle = "rgba(255,255,255,0.1)";
            ctx.font = "12px Inter, sans-serif";
            ctx.textAlign = "center";
            ctx.fillText("No daily data yet", W / 2, H / 2);
            return;
        }

        const pad = { top: 8, right: 16, bottom: 28, left: 48 };
        const chartW = W - pad.left - pad.right;
        const chartH = H - pad.top - pad.bottom;
        const max = Math.max(...daily.map(d => d.total), 1);
        const barW = Math.max(2, (chartW / daily.length) - 3);

        daily.forEach((d, i) => {
            const barH = (d.total / max) * chartH;
            const x = pad.left + (i / daily.length) * chartW;
            const y = pad.top + chartH - barH;

            ctx.fillStyle = "rgba(88,101,242,0.7)";
            ctx.beginPath();
            ctx.roundRect(x, y, barW, barH, 2);
            ctx.fill();

            // Day label every ~5 days
            if (i % 5 === 0) {
                ctx.fillStyle = "rgba(255,255,255,0.3)";
                ctx.font = "9px Inter, sans-serif";
                ctx.textAlign = "center";
                const day = d.day ? d.day.slice(-2) : i + 1;
                ctx.fillText(day, x + barW / 2, H - 4);
            }
        });
    }

    // ================================================================
    // UDHAR
    // ================================================================

    async function loadUdhar() {
        if (!activeUser) return;
        try {
            const res = await authFetch("/api/udhar");
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            renderUdhar(data);
        } catch (err) {
            console.error("Udhar error:", err);
        }
    }

    function renderUdhar(data) {
        udharTotalLent.textContent     = formatCurrency(data.total_lent || 0);
        udharTotalBorrowed.textContent = formatCurrency(data.total_borrowed || 0);
        const net = data.net || 0;
        udharNet.textContent = (net >= 0 ? "+" : "-") + formatCurrency(Math.abs(net));
        udharNet.style.color = net >= 0 ? "var(--green)" : "var(--red)";

        if (!data.persons || !data.persons.length) {
            udharPersons.innerHTML = '<div class="dash-empty">No udhar entries yet. Use "Add Entry" to get started.</div>';
            return;
        }

        udharPersons.innerHTML = "";
        data.persons.forEach(person => renderPersonCard(person));
    }

    function renderPersonCard(person) {
        const net = person.net;
        const netClass = net > 0 ? "owed" : net < 0 ? "owes" : "settled";
        const netLabel = net > 0 ? "owes you" : net < 0 ? "you owe" : "settled";
        const netDisplay = (net >= 0 ? "" : "") + formatCurrency(Math.abs(net));

        const card = document.createElement("div");
        card.className = "person-card";

        card.innerHTML = `
            <div class="person-card-header" role="button" tabindex="0" aria-expanded="false">
                <span class="person-name">${escHtml(person.name)}</span>
                <div class="person-net">
                    <span class="person-net-amount ${netClass}">${escHtml(netDisplay)}</span>
                    <span class="person-net-label">${escHtml(netLabel)}</span>
                </div>
            </div>
            <div class="person-history" id="history-${escHtml(person.key)}">
                ${(person.history || []).map(h => `
                    <div class="history-item">
                        <div class="history-left">
                            <span class="history-kind ${h.kind}">${h.kind}</span>
                            <span>${escHtml(h.note || "")}</span>
                            <span style="color:var(--text-muted)">${formatDate(h.entry_date)}</span>
                        </div>
                        <span class="history-amount">${formatCurrency(h.amount)}</span>
                    </div>
                `).join("")}
                <button type="button" class="person-repay-btn" data-person="${escHtml(person.name)}">
                    Record repayment
                </button>
            </div>
        `;

        // Toggle history on header click
        const header = card.querySelector(".person-card-header");
        const history = card.querySelector(".person-history");
        header.addEventListener("click", () => {
            const open = history.classList.toggle("open");
            header.setAttribute("aria-expanded", String(open));
        });
        header.addEventListener("keydown", e => {
            if (e.key === "Enter" || e.key === " ") { e.preventDefault(); header.click(); }
        });

        // Repay button
        const repayBtn = card.querySelector(".person-repay-btn");
        repayBtn.addEventListener("click", async () => {
            const personName = repayBtn.dataset.person;
            const amountStr = prompt(`Record repayment for ${personName} — enter amount (INR):`);
            if (!amountStr) return;
            const amount = parseFloat(amountStr);
            if (isNaN(amount) || amount <= 0) { alert("Invalid amount."); return; }
            try {
                const res = await authFetch("/api/udhar/repay", {
                    method:  "POST",
                    headers: { "Content-Type": "application/json" },
                    body:    JSON.stringify({ person_name: personName, amount }),
                });
                if (!res.ok) throw new Error("Failed");
                loadUdhar();
            } catch {
                alert("Could not record repayment.");
            }
        });

        udharPersons.appendChild(card);
    }

    // Udhar modal
    addUdharBtn.addEventListener("click", () => {
        udharForm.reset();
        udharModal.style.display = "flex";
    });

    [udharModalClose, udharCancelBtn].forEach(btn => {
        btn.addEventListener("click", () => { udharModal.style.display = "none"; });
    });

    udharModal.addEventListener("click", e => {
        if (e.target === udharModal) udharModal.style.display = "none";
    });

    udharForm.addEventListener("submit", async e => {
        e.preventDefault();
        const payload = {
            person_name: udharPerson.value.trim(),
            kind:        udharKind.value,
            amount:      parseFloat(udharAmount.value),
            note:        udharNote.value.trim(),
            due_date:    udharDue.value || null,
        };
        if (!payload.person_name || !payload.amount) return;
        try {
            const res = await authFetch("/api/udhar", {
                method:  "POST",
                headers: { "Content-Type": "application/json" },
                body:    JSON.stringify(payload),
            });
            if (!res.ok) throw new Error("Failed");
            udharModal.style.display = "none";
            loadUdhar();
        } catch {
            alert("Could not save udhar entry.");
        }
    });

    // ================================================================
    // UTILITY
    // ================================================================

    function escHtml(str) {
        if (str === null || str === undefined) return "";
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    // ================================================================
    // INSIGHTS TAB
    // ================================================================

    async function loadInsights() {
        if (!activeUser) return;
        try {
            const [recapRes, insightsRes, goalsRes, snapRes] = await Promise.all([
                authFetch("/api/recap"),
                authFetch("/api/insights"),
                authFetch("/api/goals"),
                authFetch("/api/snapshot"),
            ]);

            if (recapRes.ok) {
                const recap = await recapRes.json();
                renderRecap(recap);
            }
            if (insightsRes.ok) {
                const { insights } = await insightsRes.json();
                renderInsightCards(insights || []);
            }
            if (goalsRes.ok) {
                const { goals } = await goalsRes.json();
                renderGoals(goals || []);
            }
            if (snapRes.ok) {
                const snap = await snapRes.json();
                if (snap.safe_to_spend_today !== null && snap.safe_to_spend_today !== undefined) {
                    safeSpendCard.style.display = "flex";
                    safeAmount.textContent = formatCurrency(snap.safe_to_spend_today);
                } else {
                    safeSpendCard.style.display = "none";
                }
            }
        } catch (err) {
            console.error("Insights load error:", err);
        }
    }

    function renderRecap(recap) {
        recapSpent.textContent = formatCurrency(recap.total_spent || 0);

        const changePct = recap.spend_change_pct;
        if (changePct !== null && changePct !== undefined) {
            const sign = changePct > 0 ? "+" : "";
            recapChange.textContent = `${sign}${changePct}%`;
            recapChange.className = "recap-value " + (changePct > 0 ? "negative" : "positive");
        } else {
            recapChange.textContent = "First week";
        }

        recapTopCat.textContent = recap.top_category ? recap.top_category.category : "None";
        recapStreak.textContent = `${recap.logging_streak || 0} days`;

        if (recap.narration && recapNarration) {
            recapNarration.textContent = recap.narration;
            recapNarration.style.display = "block";
        } else if (recapNarration) {
            recapNarration.style.display = "none";
        }
    }

    function renderInsightCards(insights) {
        if (!insights.length) {
            insightCards.innerHTML = '<div class="dash-empty">Log some expenses and income to see personalised insights.</div>';
            return;
        }
        insightCards.innerHTML = "";
        insights.forEach(ins => {
            const card = document.createElement("div");
            let tier = "healthy";
            if (ins.id === "savings_rate" && ins.value < 20) tier = "warning";
            if (ins.id === "emergency_fund" && !ins.healthy) tier = "warning";
            if (ins.id === "goals_behind" && ins.value > 0) tier = "warning";
            if (ins.id === "top_category" && ins.direction === "up") tier = "alert";
            card.className = `insight-card ${tier}`;

            let valueDisplay = "";
            if (ins.unit === "%" ) valueDisplay = `${ins.value}%`;
            else if (ins.unit === "months") valueDisplay = `${ins.value} mo`;
            else if (ins.value !== undefined && typeof ins.value === "number" && !ins.unit) {
                valueDisplay = formatCurrency(ins.value);
            } else {
                valueDisplay = String(ins.value);
            }

            let extra = "";
            if (ins.id === "top_category" && ins.change_pct !== null && ins.change_pct !== undefined) {
                const sign = ins.change_pct > 0 ? "+" : "";
                const dirClass = ins.direction === "up" ? "insight-direction-up" : "insight-direction-down";
                extra = `<span class="${dirClass}">${sign}${ins.change_pct}% vs last month</span>`;
            }

            card.innerHTML = `
                <div class="insight-card-title">${escHtml(ins.title)}</div>
                <div class="insight-card-value">${escHtml(valueDisplay)} ${extra}</div>
                <div class="insight-card-note">${escHtml(ins.note || "")}</div>
            `;
            insightCards.appendChild(card);
        });
    }

    function renderGoals(goals) {
        if (!goals.length) {
            goalsListInsights.innerHTML = '<div class="dash-empty">No goals set yet. Use "Add Goal" or ask the assistant.</div>';
            return;
        }
        goalsListInsights.innerHTML = "";
        goals.forEach(g => {
            const fillClass = g.pct_complete >= 100 ? "complete" : "";
            const paceHtml = g.pace ? `<span class="goal-pace ${g.pace}">${g.pace === "on_pace" ? "On pace" : "Behind"}</span>` : "";
            const reqHtml = g.required_monthly ? `Need ${formatCurrency(g.required_monthly)}/mo` : "";

            const row = document.createElement("div");
            row.className = "goal-row";
            row.innerHTML = `
                <div class="goal-row-header">
                    <span class="goal-name">${escHtml(g.name)}</span>
                    <span class="goal-pct">${g.pct_complete}%</span>
                </div>
                <div class="goal-progress-track">
                    <div class="goal-progress-fill ${fillClass}" style="width:${Math.min(g.pct_complete,100)}%"></div>
                </div>
                <div class="goal-meta">
                    <span>${formatCurrency(g.saved_amount)} of ${formatCurrency(g.target_amount)}</span>
                    <span>${reqHtml}</span>
                    ${paceHtml}
                </div>
            `;
            goalsListInsights.appendChild(row);
        });
    }

    // ================================================================
    // GOAL ADD MODAL (injected dynamically)
    // ================================================================

    (function setupGoalModal() {
        // Create modal HTML
        const modalEl = document.createElement("div");
        modalEl.id = "goalModal";
        modalEl.className = "modal-backdrop";
        modalEl.style.display = "none";
        modalEl.setAttribute("role", "dialog");
        modalEl.setAttribute("aria-modal", "true");
        modalEl.setAttribute("aria-labelledby", "goalModalTitle");
        modalEl.innerHTML = `
            <div class="modal">
                <div class="modal-header">
                    <h3 id="goalModalTitle">Add Savings Goal</h3>
                    <button type="button" class="modal-close" id="goalModalClose" aria-label="Close">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                    </button>
                </div>
                <form id="goalForm">
                    <div class="modal-body">
                        <div class="form-field">
                            <label for="goalName">Goal name</label>
                            <input type="text" id="goalName" placeholder="e.g. Emergency fund, New phone" required>
                        </div>
                        <div class="form-field">
                            <label for="goalTarget">Target amount (INR)</label>
                            <input type="number" id="goalTarget" placeholder="e.g. 60000" min="1" required>
                        </div>
                        <div class="form-field">
                            <label for="goalDate">Target date (optional)</label>
                            <input type="date" id="goalDate">
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn-ghost" id="goalCancelBtn">Cancel</button>
                        <button type="submit" class="btn-primary">Save Goal</button>
                    </div>
                </form>
            </div>
        `;
        document.body.appendChild(modalEl);

        const goalForm      = document.getElementById("goalForm");
        const goalModalClose= document.getElementById("goalModalClose");
        const goalCancelBtn = document.getElementById("goalCancelBtn");

        function openGoalModal() { goalForm.reset(); modalEl.style.display = "flex"; }
        function closeGoalModal() { modalEl.style.display = "none"; }

        if (addGoalBtn) addGoalBtn.addEventListener("click", openGoalModal);
        goalModalClose.addEventListener("click", closeGoalModal);
        goalCancelBtn.addEventListener("click", closeGoalModal);
        modalEl.addEventListener("click", e => { if (e.target === modalEl) closeGoalModal(); });

        goalForm.addEventListener("submit", async e => {
            e.preventDefault();
            const name   = document.getElementById("goalName").value.trim();
            const target = parseFloat(document.getElementById("goalTarget").value);
            const date   = document.getElementById("goalDate").value || null;
            if (!name || !target) return;

            try {
                const res = await authFetch("/api/goals", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ name, target_amount: target, target_date: date }),
                });
                if (!res.ok) throw new Error("Failed");
                closeGoalModal();
                loadInsights();
            } catch {
                alert("Could not save goal.");
            }
        });
    })();

    // ================================================================
    // EVENT WIRING
    // ================================================================

    // Auth
    tabLogin.addEventListener("click",  () => setAuthMode("login"));
    tabSignup.addEventListener("click", () => setAuthMode("signup"));
    authToggleBtn.addEventListener("click", () => setAuthMode(authMode === "login" ? "signup" : "login"));
    authForm.addEventListener("submit", handleAuthSubmit);
    logoutBtn.addEventListener("click",  handleLogout);
    drawerLogout.addEventListener("click", handleLogout);

    // Sidebar nav
    navBtns.forEach(btn => {
        btn.addEventListener("click", () => switchTab(btn.dataset.tab));
    });

    // Tabbar
    tabbarBtns.forEach(btn => {
        btn.addEventListener("click", () => switchTab(btn.dataset.tab));
    });

    // Drawer nav items
    document.querySelectorAll(".drawer-item[data-tab]").forEach(btn => {
        btn.addEventListener("click", () => switchTab(btn.dataset.tab));
    });

    // ================================================================
    // INIT
    // ================================================================

    const savedToken = getToken();
    const savedUser  = getUser();

    if (savedToken && savedUser) {
        activeToken = savedToken;
        showMainApp(savedUser);
    } else {
        authScreen.style.display = "flex";
        mainApp.style.display    = "none";
    }

    // PWA Service Worker
    if ("serviceWorker" in navigator) {
        window.addEventListener("load", () => {
            navigator.serviceWorker.register("/sw.js").catch(err => {
                console.warn("[SW] Registration:", err);
            });
        });
    }

})();
