/* ── GoodMoney — API Client ───────────────────────────── */

const API_BASE = "";

function getInitData() {
    try {
        return window.Telegram?.WebApp?.initData || "";
    } catch (e) {
        return "";
    }
}

async function apiCall(endpoint, method = "GET", body = null) {
    const headers = {
        "Content-Type": "application/json",
        "X-Init-Data": getInitData(),
    };
    const opts = { method, headers };
    if (body && method !== "GET") {
        opts.body = JSON.stringify(body);
    }
    const resp = await fetch(`${API_BASE}${endpoint}`, opts);
    const data = await resp.json();
    if (!resp.ok) {
        throw new Error(data.detail || "API Error");
    }
    return data;
}
