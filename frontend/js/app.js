/* ── GoodMoney — Main Application ─────────────────────── */

let user = null;
let settings = {};
let adminPage = 0;
let minesGame = null;
let feedTimer = null;

// ── Init ──────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", async () => {
    const lang = detectLanguage();
    setLanguage(lang);

    try {
        const tg = window.Telegram?.WebApp;
        if (tg) {
            tg.ready();
            tg.expand();
            tg.setHeaderColor("#0a0e17");
            tg.setBackgroundColor("#0a0e17");
        }
    } catch (e) {}

    try {
        settings = await apiCall("/api/settings");
    } catch (e) {
        console.warn("Failed to load settings", e);
        settings = {
            min_deposit: 10, profit_percent: 10,
            maturity_hours: 10, referral_percent: 10,
            min_withdrawal: 1, withdrawal_fee: 0.01,
        };
    }

    const urlParams = new URLSearchParams(window.location.search);
    const ref = urlParams.get("ref") || "";

    try {
        const startParam = window.Telegram?.WebApp?.initDataUnsafe?.start_param || ref;
        const regData = await apiCall("/api/user/register", "POST", {
            ref: startParam,
            language: currentLang,
        });
        user = regData.user;
    } catch (e) {
        console.error("Registration error", e);
    }

    updateUI();
    showScreen("dashboard");

    setInterval(refreshData, 30000);
});


// ── Navigation ────────────────────────────────────────

function navigate(screen) {
    document.querySelectorAll(".screen").forEach(s => s.classList.remove("active"));
    const el = document.getElementById(screen + "-screen");
    if (el) {
        el.classList.add("active");
    }

    document.querySelectorAll(".nav-btn").forEach(b => b.classList.remove("active"));
    const navMap = { dashboard: 0, history: 1, tasks: 2, referral: 3, admin: 4 };
    const navBtns = document.querySelectorAll(".nav-btn");
    if (navMap[screen] !== undefined && navBtns[navMap[screen]]) {
        navBtns[navMap[screen]].classList.add("active");
    }

    if (screen === "dashboard") loadDashboard();
    if (screen === "deposit") loadDeposit();
    if (screen === "withdraw") loadWithdraw();
    if (screen === "history") loadHistory();
    if (screen === "referral") loadReferral();
    if (screen === "tasks") loadTasks();
    if (screen === "admin") loadAdmin();
    if (screen === "mines") loadMines();
}

function showScreen(name) {
    document.querySelectorAll(".screen").forEach(s => s.classList.remove("active"));
    const el = document.getElementById(name + "-screen");
    if (el) el.classList.add("active");
    if (name === "dashboard") loadDashboard();
}

// ── Dashboard ─────────────────────────────────────────

async function loadDashboard() {
    if (!user) return;
    try {
        user = await apiCall("/api/user/me");
    } catch (e) {}

    document.getElementById("balance-value").textContent = (user.balance || 0).toFixed(4);
    document.getElementById("total-earned").textContent = (user.total_earned || 0).toFixed(4);

    document.getElementById("stat-profit").textContent = "+" + settings.profit_percent + "%";
    document.getElementById("stat-hours").textContent = settings.maturity_hours + "h";
    document.getElementById("stat-min").textContent = settings.min_deposit;

    if (user.is_admin) {
        document.getElementById("admin-nav-btn").style.display = "";
    }

    loadFeed();

    try {
        const active = await apiCall("/api/deposit/active");
        const section = document.getElementById("active-deposits-section");
        const list = document.getElementById("active-deposits-list");
        if (active.active_deposits && active.active_deposits.length > 0) {
            section.style.display = "block";
            list.innerHTML = active.active_deposits.map(d => {
                const now = Date.now() / 1000;
                const total = d.matures_at - d.created_at;
                const elapsed = now - d.created_at;
                const pct = Math.min(100, (elapsed / total) * 100);
                const remaining = Math.max(0, d.matures_at - now);
                const hours = Math.floor(remaining / 3600);
                const mins = Math.floor((remaining % 3600) / 60);
                const expectedProfit = d.amount * (settings.profit_percent / 100);
                return `
                    <div class="deposit-item">
                        <div class="deposit-item-left">
                            <div class="dep-amount">${d.amount.toFixed(4)} TON</div>
                            <div class="dep-time">${t("time_left", { hours, mins })}</div>
                            <div class="progress-bar"><div class="progress-bar-fill" style="width:${pct}%"></div></div>
                        </div>
                        <div class="deposit-item-right">
                            <span class="dep-status pending">${t("maturing")}</span>
                            <div style="font-size:12px;color:var(--success);margin-top:4px">${t("profit_amount", { amount: expectedProfit.toFixed(4) })}</div>
                        </div>
                    </div>
                `;
            }).join("");
        } else {
            section.style.display = "none";
        }
    } catch (e) {}
}

// ── Deposit ───────────────────────────────────────────

async function loadDeposit() {
    document.getElementById("dep-min").textContent = settings.min_deposit + " TON";
    document.getElementById("dep-profit").textContent = "+" + settings.profit_percent + "%";
    document.getElementById("dep-maturity").textContent = settings.maturity_hours + "h";

    try {
        const info = await apiCall("/api/deposit/info");
        document.getElementById("deposit-address").textContent = info.wallet_address || "-";
        document.getElementById("deposit-comment").textContent = info.deposit_comment || "-";
        document.getElementById("dep-balance").textContent = (info.balance || 0).toFixed(4) + " TON";
    } catch (e) {}
}

async function createInvestment() {
    const amount = parseFloat(document.getElementById("invest-amount").value);
    if (!amount || amount < settings.min_deposit) {
        showToast(t("min_deposit") + ": " + settings.min_deposit + " TON", "error");
        return;
    }
    try {
        const res = await apiCall("/api/deposit/invest", "POST", { amount });
        showToast(t("success") + "! +" + res.profit.toFixed(2) + " TON " + t("in") + " " + res.maturity_hours + "h", "success");
        document.getElementById("invest-amount").value = "";
        await loadDeposit();
        await loadDashboard();
    } catch (e) {
        showToast(e.message || t("error"), "error");
    }
}

// ── Withdraw ──────────────────────────────────────────

async function loadWithdraw() {
    if (!user) return;
    try {
        user = await apiCall("/api/user/me");
    } catch (e) {}
    document.getElementById("withdraw-balance").textContent = (user.balance || 0).toFixed(4);
    document.getElementById("withdraw-fee").textContent = settings.withdrawal_fee;
    updateWithdrawNet();
}

function setMaxWithdraw() {
    if (!user) return;
    document.getElementById("withdraw-amount").value = user.balance || 0;
    updateWithdrawNet();
}

function updateWithdrawNet() {
    const amount = parseFloat(document.getElementById("withdraw-amount").value) || 0;
    const fee = settings.withdrawal_fee || 0.01;
    const net = Math.max(0, amount - fee);
    document.getElementById("withdraw-net").textContent = net.toFixed(4);
}

document.addEventListener("input", (e) => {
    if (e.target.id === "withdraw-amount") updateWithdrawNet();
});

async function submitWithdraw() {
    const amount = parseFloat(document.getElementById("withdraw-amount").value);
    const address = document.getElementById("withdraw-address").value.trim();

    if (!amount || amount < (settings.min_withdrawal || 1)) {
        showToast(t("invalid_amount"), "error");
        return;
    }
    if (!user || amount > user.balance) {
        showToast(t("insufficient_balance"), "error");
        return;
    }
    if (!address || address.length < 20) {
        showToast(t("invalid_address"), "error");
        return;
    }

    try {
        await apiCall("/api/withdraw/create", "POST", {
            amount: amount,
            to_address: address,
        });
        showToast(t("withdrawal_created"), "success");
        document.getElementById("withdraw-amount").value = "";
        document.getElementById("withdraw-address").value = "";
        loadWithdraw();
    } catch (e) {
        showToast(e.message || t("error"), "error");
    }
}

// ── History ───────────────────────────────────────────

async function loadHistory() {
    try {
        const depData = await apiCall("/api/deposit/history");
        const depList = document.getElementById("history-deposits");
        if (depData.deposits && depData.deposits.length > 0) {
            depList.innerHTML = depData.deposits.map(d => {
                const date = new Date(d.created_at * 1000).toLocaleDateString();
                const statusClass = d.status;
                const statusText = t(d.status === "paid" ? "paid" : d.status === "pending" ? "maturing" : d.status);
                return `
                    <div class="history-item">
                        <div class="history-item-left">
                            <span class="history-amount">${d.amount.toFixed(4)} TON</span>
                            <span class="history-date">${date}</span>
                            ${d.profit > 0 ? `<span class="history-profit">+${d.profit.toFixed(4)} TON</span>` : ""}
                        </div>
                        <span class="history-status ${statusClass}">${statusText}</span>
                    </div>
                `;
            }).join("");
        } else {
            depList.innerHTML = `<div class="empty-state"><div class="empty-state-icon">📋</div><p>${t("no_deposits")}</p></div>`;
        }
    } catch (e) {}

    try {
        const wdData = await apiCall("/api/withdraw/history");
        const wdList = document.getElementById("history-withdrawals");
        if (wdData.withdrawals && wdData.withdrawals.length > 0) {
            wdList.innerHTML = wdData.withdrawals.map(w => {
                const date = new Date(w.created_at * 1000).toLocaleDateString();
                const txLink = w.tx_hash && w.tx_hash !== "sent" && w.tx_hash !== ""
                    ? `<a href="https://tonviewer.com/transaction/${encodeURIComponent(w.tx_hash)}" target="_blank" class="tx-link">Tonviewer ↗</a>`
                    : "";
                return `
                    <div class="history-item">
                        <div class="history-item-left">
                            <span class="history-amount">${w.amount.toFixed(4)} TON</span>
                            <span class="history-date">${date} ${txLink}</span>
                        </div>
                        <span class="history-status ${w.status}">${t(w.status)}</span>
                    </div>
                `;
            }).join("");
        } else {
            wdList.innerHTML = `<div class="empty-state"><div class="empty-state-icon">📋</div><p>${t("no_withdrawals")}</p></div>`;
        }
    } catch (e) {}
}

function switchHistoryTab(tab) {
    document.querySelectorAll(".tabs .tab").forEach(t => t.classList.remove("active"));
    event.target.classList.add("active");
    document.getElementById("history-deposits").style.display = tab === "deposits" ? "" : "none";
    document.getElementById("history-withdrawals").style.display = tab === "withdrawals" ? "" : "none";
}

// ── Referral ──────────────────────────────────────────

async function loadReferral() {
    try {
        const data = await apiCall("/api/referral/info");
        document.getElementById("ref-percent").textContent = data.referral_percent + "%";
        document.getElementById("ref-count").textContent = data.referral_count;
        document.getElementById("ref-earnings").textContent = (data.referral_earnings || 0).toFixed(2);
        document.getElementById("referral-link").textContent = data.referral_link;

        // Milestone progress
        const count = data.referral_count || 0;
        const nextMilestone = Math.ceil((count + 1) / 10) * 10;
        const progress = count % 10;
        const milestoneEl = document.getElementById("milestone-progress");
        if (milestoneEl) {
            milestoneEl.textContent = `${progress}/10 → ${nextMilestone}`;
        }

        if (data.referrals && data.referrals.length > 0) {
            document.getElementById("referral-list-section").style.display = "block";
            document.getElementById("referral-list").innerHTML = data.referrals.map(r => `
                <div class="history-item">
                    <div class="history-item-left">
                        <span class="history-amount">${r.first_name || r.username || "User " + r.user_id}</span>
                        <span class="history-date">${new Date(r.created_at * 1000).toLocaleDateString()}</span>
                    </div>
                    <span style="font-size:13px;color:var(--text-secondary)">${(r.total_deposited || 0).toFixed(2)} TON</span>
                </div>
            `).join("");
        }
    } catch (e) {}
}

function shareReferral() {
    const link = document.getElementById("referral-link").textContent;
    const text = currentLang === "ru"
        ? "Присоединяйся к GoodMoney! Заработай +10% за 10 часов 💎"
        : "Join GoodMoney! Earn +10% in 10 hours 💎";
    try {
        window.Telegram?.WebApp?.openTelegramLink(
            `https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(text)}`
        );
    } catch (e) {
        if (navigator.share) {
            navigator.share({ title: "GoodMoney", text: text, url: link });
        } else {
            copyText(link);
        }
    }
}

// ── Tasks ─────────────────────────────────────────────

async function loadTasks() {
    if (!user) return;
    const container = document.getElementById("tasks-list");
    try {
        const data = await apiCall("/api/tasks");
        const tasks = data.tasks;
        if (!tasks || tasks.length === 0) {
            container.innerHTML = `<p style="text-align:center;color:var(--text-secondary)">${t("no_tasks")}</p>`;
            return;
        }
        container.innerHTML = tasks.map(task => `
            <div class="task-card ${task.completed ? 'task-completed' : ''}">
                <div class="task-info">
                    <div class="task-name">${t("task_" + task.id)}</div>
                    <div class="task-reward">+${task.reward} TON</div>
                </div>
                <div class="task-actions">
                    <a href="${task.link}" target="_blank" class="btn btn-secondary btn-small">${t("task_go")}</a>
                    ${task.completed
                        ? `<span class="task-done">${t("task_done")}</span>`
                        : `<button class="btn btn-primary btn-small" onclick="claimTask('${task.id}')">${t("task_check")}</button>`
                    }
                </div>
            </div>
        `).join("");
    } catch (e) {
        container.innerHTML = `<p style="text-align:center;color:var(--text-secondary)">${t("error")}</p>`;
    }
}

async function claimTask(taskId) {
    try {
        const res = await apiCall("/api/tasks/claim", "POST", { task_id: taskId });
        showToast(`+${res.reward} TON! ${t("task_done")}`, "success");
        await loadTasks();
        await loadDashboard();
    } catch (e) {
        showToast(e.message || t("error"), "error");
    }
}

// ── Admin ─────────────────────────────────────────────

async function loadAdmin() {
    loadAdminStats();
}

async function loadAdminStats() {
    try {
        const stats = await apiCall("/api/admin/stats");
        document.getElementById("a-users").textContent = stats.total_users;
        document.getElementById("a-deposits").textContent = stats.total_deposits;
        document.getElementById("a-dep-vol").textContent = (stats.total_deposit_amount || 0).toFixed(2) + " TON";
        document.getElementById("a-profit").textContent = (stats.total_profit_paid || 0).toFixed(2) + " TON";
        document.getElementById("a-pending").textContent = stats.pending_deposits;
        document.getElementById("a-withdrawals").textContent = stats.total_withdrawals;
        document.getElementById("a-withdrawn").textContent = (stats.total_withdrawn || 0).toFixed(2) + " TON";
        document.getElementById("a-wallet").textContent = (stats.wallet_balance || 0).toFixed(4) + " TON";
        document.getElementById("a-wallet-addr").textContent = stats.wallet_address || "-";
    } catch (e) {}
}

async function loadAdminUsers() {
    try {
        const data = await apiCall(`/api/admin/users?limit=20&offset=${adminPage * 20}`);
        const list = document.getElementById("admin-user-list");
        list.innerHTML = data.users.map(u => `
            <div class="admin-user-item">
                <div class="admin-user-header">
                    <span class="admin-user-name">${u.first_name || u.username || "ID:" + u.user_id}
                        ${u.is_admin ? " ⭐" : ""} ${u.is_blocked ? " 🚫" : ""}
                    </span>
                    <div class="admin-user-actions">
                        <button onclick="toggleBlock(${u.user_id}, ${!u.is_blocked})">${u.is_blocked ? "Unblock" : "Block"}</button>
                        <button onclick="toggleAdmin(${u.user_id}, ${!u.is_admin})">${u.is_admin ? "Remove Admin" : "Make Admin"}</button>
                        <button onclick="promptAdjustBalance(${u.user_id})">Balance</button>
                        <button onclick="promptAdminDeposit(${u.user_id})">Deposit</button>
                    </div>
                </div>
                <div class="admin-user-details">
                    <span>ID: ${u.user_id}</span>
                    <span>Balance: ${(u.balance || 0).toFixed(4)}</span>
                    <span>Deposited: ${(u.total_deposited || 0).toFixed(2)}</span>
                    <span>Withdrawn: ${(u.total_withdrawn || 0).toFixed(2)}</span>
                </div>
            </div>
        `).join("");
        document.getElementById("admin-users-page").textContent = adminPage + 1;
    } catch (e) {}
}

function adminUsersPage(delta) {
    adminPage = Math.max(0, adminPage + delta);
    loadAdminUsers();
}

async function toggleBlock(userId, blocked) {
    try {
        await apiCall("/api/admin/block", "POST", { user_id: userId, blocked });
        loadAdminUsers();
        showToast(t("success"), "success");
    } catch (e) {
        showToast(t("error"), "error");
    }
}

async function toggleAdmin(userId, isAdmin) {
    try {
        await apiCall("/api/admin/grant", "POST", { user_id: userId, is_admin: isAdmin });
        loadAdminUsers();
        showToast(t("success"), "success");
    } catch (e) {
        showToast(t("error"), "error");
    }
}

function promptAdjustBalance(userId) {
    // Remove any existing modal
    const existing = document.getElementById("balance-modal");
    if (existing) existing.remove();

    const modal = document.createElement("div");
    modal.id = "balance-modal";
    modal.className = "modal-overlay";
    modal.innerHTML = `
        <div class="modal-content">
            <h3>${t("adjust_balance") || "Adjust Balance"}</h3>
            <p style="color:var(--text-secondary);font-size:13px;margin-bottom:12px">User ID: ${userId}</p>
            <div class="input-group">
                <label>${t("amount") || "Amount"} (+ / −)</label>
                <input type="number" id="balance-modal-input" placeholder="10 or -5" step="0.01" autofocus>
            </div>
            <div style="display:flex;gap:8px;margin-top:12px">
                <button class="btn btn-primary" onclick="submitAdjustBalance(${userId})">${t("confirm") || "Confirm"}</button>
                <button class="btn btn-secondary" onclick="document.getElementById('balance-modal').remove()">${t("cancel") || "Cancel"}</button>
            </div>
        </div>
    `;
    document.getElementById("app").appendChild(modal);
    document.getElementById("balance-modal-input").focus();
}

function submitAdjustBalance(userId) {
    const input = document.getElementById("balance-modal-input");
    const num = parseFloat(input.value);
    if (isNaN(num)) { showToast(t("error"), "error"); return; }
    apiCall("/api/admin/balance", "POST", { user_id: userId, amount: num })
        .then(() => {
            showToast(t("success"), "success");
            loadAdminUsers();
            const modal = document.getElementById("balance-modal");
            if (modal) modal.remove();
        })
        .catch(() => showToast(t("error"), "error"));
}

function promptAdminDeposit(userId) {
    const existing = document.getElementById("deposit-modal");
    if (existing) existing.remove();

    const modal = document.createElement("div");
    modal.id = "deposit-modal";
    modal.className = "modal-overlay";
    modal.innerHTML = `
        <div class="modal-content">
            <h3>${t("admin_create_deposit") || "Create Deposit"}</h3>
            <p style="color:var(--text-secondary);font-size:13px;margin-bottom:12px">User ID: ${userId}</p>
            <div class="input-group">
                <label>${t("amount") || "Amount"} (TON)</label>
                <input type="number" id="deposit-modal-input" placeholder="10" min="0.01" step="0.01" autofocus>
            </div>
            <div style="display:flex;gap:8px;margin-top:12px">
                <button class="btn btn-primary" onclick="submitAdminDeposit(${userId})">${t("confirm") || "Confirm"}</button>
                <button class="btn btn-secondary" onclick="document.getElementById('deposit-modal').remove()">${t("cancel") || "Cancel"}</button>
            </div>
        </div>
    `;
    document.getElementById("app").appendChild(modal);
    document.getElementById("deposit-modal-input").focus();
}

function submitAdminDeposit(userId) {
    const input = document.getElementById("deposit-modal-input");
    const num = parseFloat(input.value);
    if (isNaN(num) || num <= 0) { showToast(t("invalid_amount"), "error"); return; }
    apiCall("/api/admin/deposit", "POST", { user_id: userId, amount: num })
        .then((res) => {
            showToast(`${t("success")}! Deposit ${res.amount} TON (+${res.profit.toFixed(2)} TON in ${res.maturity_hours}h)`, "success");
            loadAdminUsers();
            const modal = document.getElementById("deposit-modal");
            if (modal) modal.remove();
        })
        .catch((e) => showToast(e.message || t("error"), "error"));
}

async function loadAdminSettings() {
    try {
        const data = await apiCall("/api/admin/settings");
        const form = document.getElementById("admin-settings-form");
        const labels = {
            min_deposit: "Min Deposit (TON)",
            profit_percent: "Profit (%)",
            deposit_maturity_seconds: "Maturity (seconds)",
            referral_percent: "Referral (%)",
            min_withdrawal: "Min Withdrawal (TON)",
            withdrawal_fee: "Withdrawal Fee (TON)",
        };
        form.innerHTML = Object.entries(data).map(([key, value]) => `
            <div class="setting-item">
                <label>${labels[key] || key}</label>
                <input type="number" step="any" data-key="${key}" value="${value}">
            </div>
        `).join("");
    } catch (e) {}
}

async function saveAdminSettings() {
    const inputs = document.querySelectorAll("#admin-settings-form input");
    const settingsData = {};
    inputs.forEach(inp => {
        settingsData[inp.dataset.key] = inp.value;
    });
    try {
        await apiCall("/api/admin/settings", "POST", { settings: settingsData });
        showToast(t("success"), "success");
        settings = await apiCall("/api/settings");
    } catch (e) {
        showToast(t("error"), "error");
    }
}

async function sendBroadcast() {
    const msg = document.getElementById("broadcast-message").value.trim();
    if (!msg) return;
    try {
        const queueData = await apiCall("/api/admin/broadcast", "POST", { message: msg });
        const result = await apiCall("/api/admin/broadcast/send", "POST", {
            user_ids: queueData.user_ids,
            message: msg,
        });
        document.getElementById("broadcast-result").innerHTML =
            `<p style="color:var(--success);margin-top:12px">Sent: ${result.sent}, Failed: ${result.failed}</p>`;
        document.getElementById("broadcast-message").value = "";
    } catch (e) {
        showToast(t("error"), "error");
    }
}

function switchAdminTab(tab) {
    document.querySelectorAll(".admin-tab").forEach(t => t.classList.remove("active"));
    event.target.classList.add("active");
    document.querySelectorAll(".admin-panel").forEach(p => p.classList.remove("active"));
    document.getElementById("admin-" + tab).classList.add("active");
    if (tab === "stats") loadAdminStats();
    if (tab === "users") loadAdminUsers();
    if (tab === "settings") loadAdminSettings();
    if (tab === "fakefeed") updateFakeStatus();
}

// ── Utils ─────────────────────────────────────────────

function copyToClipboard(elementId) {
    const text = document.getElementById(elementId).textContent;
    copyText(text);
}

function copyText(text) {
    navigator.clipboard.writeText(text).then(() => {
        showToast(t("copied"), "success");
    }).catch(() => {
        const ta = document.createElement("textarea");
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
        showToast(t("copied"), "success");
    });
}

function showToast(message, type = "") {
    const toast = document.getElementById("toast");
    toast.textContent = message;
    toast.className = "toast show " + type;
    setTimeout(() => {
        toast.className = "toast";
    }, 3000);
}

function updateUI() {
    if (!user) return;
    document.getElementById("balance-value").textContent = (user.balance || 0).toFixed(4);
    document.getElementById("total-earned").textContent = (user.total_earned || 0).toFixed(4);
}

async function refreshData() {
    try {
        user = await apiCall("/api/user/me");
        settings = await apiCall("/api/settings");
        updateUI();
        const currentScreen = document.querySelector(".screen.active");
        if (currentScreen && currentScreen.id === "dashboard-screen") {
            loadDashboard();
        }
    } catch (e) {}
}

// ── Live Feed ─────────────────────────────────────────

async function loadFeed() {
    try {
        const data = await fetch("/api/feed/recent?limit=15").then(r => r.json());
        const list = document.getElementById("live-feed-list");
        if (!data.feed || data.feed.length === 0) {
            list.innerHTML = `<div class="empty-state"><p style="font-size:13px;color:var(--text-secondary)">${t("no_activity")}</p></div>`;
            return;
        }
        list.innerHTML = data.feed.map(e => {
            const icon = e.event_type === "deposit" ? "💎" : e.event_type === "payout" ? "💰" : "💸";
            const now = Date.now() / 1000;
            let rightHtml = "";
            if (e.event_type === "deposit" && e.matures_at > now) {
                const rem = e.matures_at - now;
                const h = Math.floor(rem / 3600);
                const m = Math.floor((rem % 3600) / 60);
                rightHtml = `<div class="feed-timer">⏱ ${h}h ${m}m</div>`;
            } else if (e.event_type === "payout" && e.profit > 0) {
                rightHtml = `<div class="feed-profit">+${e.profit.toFixed(2)} TON</div>`;
            }
            const ago = _timeAgo(now - e.created_at);
            rightHtml += `<div class="feed-time-ago">${ago}</div>`;
            const label = e.event_type === "deposit" ? t("deposit") : e.event_type === "payout" ? t("paid") : t("withdraw");
            return `
                <div class="feed-item">
                    <div class="feed-item-left">
                        <span class="feed-event-icon">${icon}</span>
                        <div>
                            <div class="feed-amount">${e.amount.toFixed(2)} TON <span style="font-weight:400;font-size:11px;color:var(--text-secondary)">${label}</span></div>
                            <div class="feed-name">${e.display_name}</div>
                        </div>
                    </div>
                    <div class="feed-item-right">${rightHtml}</div>
                </div>`;
        }).join("");
    } catch (e) {}

    if (feedTimer) clearTimeout(feedTimer);
    feedTimer = setTimeout(() => {
        const cs = document.querySelector(".screen.active");
        if (cs && cs.id === "dashboard-screen") loadFeed();
    }, 15000);
}

function _timeAgo(seconds) {
    if (seconds < 60) return t("just_now");
    if (seconds < 3600) return Math.floor(seconds / 60) + t("min_ago");
    if (seconds < 86400) return Math.floor(seconds / 3600) + t("hour_ago");
    return Math.floor(seconds / 86400) + t("day_ago");
}

// ── Mines Game ────────────────────────────────────────

async function loadMines() {
    if (!user) return;
    try { user = await apiCall("/api/user/me"); } catch (e) {}
    document.getElementById("mines-balance").textContent = (user.balance || 0).toFixed(4);

    try {
        const active = await apiCall("/api/mines/active");
        if (active.active) {
            minesGame = active;
            showMinesGameArea(active);
        } else {
            minesGame = null;
            showMinesSetup();
        }
    } catch (e) {
        showMinesSetup();
    }
}

function showMinesSetup() {
    document.getElementById("mines-setup").style.display = "";
    document.getElementById("mines-game-area").style.display = "none";
    document.getElementById("mines-server-seed-reveal").style.display = "none";
    document.getElementById("mines-server-hash").textContent = "-";
    document.getElementById("mines-client-seed").textContent = "-";
}

function showMinesGameArea(game) {
    document.getElementById("mines-setup").style.display = "none";
    document.getElementById("mines-game-area").style.display = "";
    document.getElementById("mines-current-bet").textContent = game.bet;
    document.getElementById("mines-multiplier").textContent = game.multiplier.toFixed(2);
    document.getElementById("mines-profit").textContent = (game.bet * game.multiplier - game.bet).toFixed(4);
    document.getElementById("mines-cashout-amount").textContent = (game.bet * game.multiplier).toFixed(2);
    document.getElementById("mines-next-multiplier").textContent = game.next_multiplier ? game.next_multiplier.toFixed(2) : "-";
    document.getElementById("mines-server-hash").textContent = game.server_seed_hash || "-";
    document.getElementById("mines-client-seed").textContent = game.client_seed || "-";

    if (game.multiplier <= 1.0) {
        document.getElementById("mines-cashout-btn").style.display = "none";
    } else {
        document.getElementById("mines-cashout-btn").style.display = "";
    }

    renderMinesGrid(game);
}

function renderMinesGrid(game) {
    const grid = document.getElementById("mines-grid");
    const revealed = game.revealed || [];
    const mines = game.mines || [];
    const gameOver = game.game_over || false;

    grid.innerHTML = "";
    for (let i = 0; i < 25; i++) {
        const cell = document.createElement("div");
        cell.className = "mine-cell";
        cell.dataset.index = i;

        if (revealed.includes(i)) {
            if (mines.includes(i)) {
                cell.classList.add("mine");
                cell.textContent = "💣";
            } else {
                cell.classList.add("revealed");
                cell.textContent = "💎";
            }
        } else if (gameOver && mines.includes(i)) {
            cell.classList.add("mine");
            cell.textContent = "💣";
        } else if (gameOver) {
            cell.classList.add("disabled");
        } else {
            cell.onclick = () => revealMineCell(i);
        }

        grid.appendChild(cell);
    }
}

function setMinesCount(count) {
    document.getElementById("mines-count").value = count;
    document.querySelectorAll(".mines-preset").forEach(b => b.classList.remove("active"));
    event.target.classList.add("active");
}

async function startMinesGame() {
    const bet = parseFloat(document.getElementById("mines-bet").value);
    const mines = parseInt(document.getElementById("mines-count").value);

    if (!bet || bet < 0.1) {
        showToast(t("invalid_amount"), "error");
        return;
    }
    if (!user || bet > user.balance) {
        showToast(t("insufficient_balance"), "error");
        return;
    }
    if (mines < 1 || mines > 24) {
        showToast(t("invalid_mines"), "error");
        return;
    }

    try {
        const game = await apiCall("/api/mines/start", "POST", { bet, mines_count: mines });
        minesGame = {
            ...game,
            active: true,
            next_multiplier: null,
        };
        // Compute next multiplier client-side
        minesGame.next_multiplier = calcNextMult(mines, 1);
        showMinesGameArea(minesGame);
        document.getElementById("mines-balance").textContent =
            ((user.balance || 0) - bet).toFixed(4);
    } catch (e) {
        showToast(e.message || t("error"), "error");
    }
}

function calcNextMult(minesCount, revealedCount) {
    let prob = 1.0;
    for (let i = 0; i < revealedCount; i++) {
        prob *= (25 - minesCount - i) / (25 - i);
    }
    return prob > 0 ? Math.round(0.97 / prob * 100) / 100 : 0;
}

async function revealMineCell(index) {
    if (!minesGame) return;
    const cell = document.querySelector(`.mine-cell[data-index="${index}"]`);
    if (!cell || cell.classList.contains("revealed") || cell.classList.contains("mine")) return;

    cell.style.opacity = "0.5";
    try {
        const res = await apiCall("/api/mines/reveal", "POST", { cell: index });
        cell.style.opacity = "";

        if (res.result === "mine") {
            minesGame = { ...minesGame, ...res, game_over: true };
            renderMinesGrid(minesGame);
            document.getElementById("mines-multiplier").textContent = "0.00";
            document.getElementById("mines-profit").textContent = (-minesGame.bet).toFixed(4);
            document.getElementById("mines-cashout-btn").style.display = "none";
            document.getElementById("mines-server-seed-reveal").style.display = "";
            document.getElementById("mines-server-seed").textContent = res.server_seed;
            showToast(t("mine_hit"), "error");
            setTimeout(() => {
                showMinesSetup();
                loadMines();
            }, 3000);
        } else if (res.result === "win_all") {
            minesGame = { ...minesGame, ...res, game_over: true };
            renderMinesGrid(minesGame);
            document.getElementById("mines-multiplier").textContent = res.multiplier.toFixed(2);
            document.getElementById("mines-profit").textContent = res.profit.toFixed(4);
            document.getElementById("mines-cashout-btn").style.display = "none";
            document.getElementById("mines-server-seed-reveal").style.display = "";
            document.getElementById("mines-server-seed").textContent = res.server_seed;
            showToast(t("all_safe") + " +" + res.profit.toFixed(4) + " TON!", "success");
            setTimeout(() => {
                showMinesSetup();
                loadMines();
            }, 3000);
        } else {
            minesGame.revealed = res.revealed;
            minesGame.multiplier = res.multiplier;
            minesGame.next_multiplier = res.next_multiplier;
            cell.classList.add("revealed");
            cell.textContent = "💎";
            cell.onclick = null;
            document.getElementById("mines-multiplier").textContent = res.multiplier.toFixed(2);
            document.getElementById("mines-profit").textContent = res.profit.toFixed(4);
            document.getElementById("mines-cashout-amount").textContent = (minesGame.bet * res.multiplier).toFixed(2);
            document.getElementById("mines-next-multiplier").textContent = res.next_multiplier ? res.next_multiplier.toFixed(2) : "-";
            if (res.multiplier > 1.0) {
                document.getElementById("mines-cashout-btn").style.display = "";
            }
        }
    } catch (e) {
        cell.style.opacity = "";
        showToast(e.message || t("error"), "error");
    }
}

async function minesCashout() {
    if (!minesGame) return;
    try {
        const res = await apiCall("/api/mines/cashout", "POST");
        minesGame.mines = res.mines;
        minesGame.game_over = true;
        renderMinesGrid(minesGame);
        document.getElementById("mines-cashout-btn").style.display = "none";
        document.getElementById("mines-server-seed-reveal").style.display = "";
        document.getElementById("mines-server-seed").textContent = res.server_seed;
        showToast("+" + res.profit.toFixed(4) + " TON! " + t("cashout_success"), "success");
        setTimeout(() => {
            showMinesSetup();
            loadMines();
        }, 2000);
    } catch (e) {
        showToast(e.message || t("error"), "error");
    }
}

// ── Admin Fake Feed ───────────────────────────────────

async function launchFakeFeed() {
    const type = document.getElementById("fake-type").value;
    const count = parseInt(document.getElementById("fake-count").value) || 10;
    const period = parseInt(document.getElementById("fake-period").value) || 30;
    const minAmt = parseFloat(document.getElementById("fake-min-amount").value) || 10;
    const maxAmt = parseFloat(document.getElementById("fake-max-amount").value) || 100;
    const maturity = parseFloat(document.getElementById("fake-maturity").value) || 10;

    try {
        const res = await apiCall("/api/admin/fake-feed", "POST", {
            event_type: type,
            count: count,
            period_minutes: period,
            min_amount: minAmt,
            max_amount: maxAmt,
            maturity_hours: maturity,
        });
        document.getElementById("fake-feed-result").innerHTML =
            `<p style="color:var(--success);margin-top:8px">${res.message}</p>`;
        setTimeout(() => {
            document.getElementById("fake-feed-result").innerHTML = "";
        }, 4000);
        updateFakeStatus();
    } catch (e) {
        showToast(e.message || t("error"), "error");
    }
}

async function stopFakeFeed() {
    try {
        await apiCall("/api/admin/fake-feed/stop", "POST");
        showToast(t("success"), "success");
        updateFakeStatus();
    } catch (e) {
        showToast(e.message || t("error"), "error");
    }
}

async function updateFakeStatus() {
    try {
        const res = await apiCall("/api/admin/fake-feed/status", "GET");
        const el = document.getElementById("fake-feed-status");
        if (res.running) {
            el.style.display = "block";
            document.getElementById("fake-status-text").textContent = t("fake_running");
        } else {
            el.style.display = "none";
        }
    } catch (e) {}
}
