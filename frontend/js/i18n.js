/* ── GoodMoney — Internationalization (RU/EN) ────────── */

const I18N = {
    en: {
        loading: "Loading...",
        your_balance: "Your Balance",
        earned: "Earned",
        how_it_works: "How it works",
        legend: "Our AI algorithms perform arbitrage trading across TON DEX platforms (DeDust, STON.fi), generating consistent returns from price differences.",
        profit: "Profit",
        maturity: "Maturity",
        min_dep: "Min Dep",
        active_deposits: "Active Deposits",
        deposit: "Deposit",
        withdraw: "Withdraw",
        home: "Home",
        history: "History",
        referrals: "Referrals",
        make_deposit: "Make a Deposit",
        deposit_desc: "Deposit TON and earn profit after the maturity period",
        min_deposit: "Min deposit",
        profit_label: "Profit",
        maturity_label: "Maturity",
        deposit_method: "Deposit Method",
        ton_connect: "TON Connect",
        manual_transfer: "Manual Transfer",
        amount: "Amount (TON)",
        send_deposit: "Send Deposit",
        manual_desc: "Send TON to the address below with the exact comment:",
        wallet_address: "Wallet Address",
        comment: "Comment (required!)",
        copy: "Copy",
        comment_warning: "Always include the comment! Deposits without the correct comment cannot be matched to your account.",
        withdraw_title: "Withdraw",
        available_balance: "Available Balance",
        ton_address: "TON Address",
        fee: "Fee",
        you_receive: "You receive",
        confirm_withdraw: "Confirm Withdrawal",
        max: "MAX",
        history_title: "History",
        deposits: "Deposits",
        withdrawals: "Withdrawals",
        referral_title: "Referral Program",
        invite_friends: "Invite Friends & Earn",
        referral_desc: "Get a percentage of your referrals' deposit profits!",
        commission: "Commission",
        your_link: "Your Referral Link",
        share: "Share Link",
        your_referrals: "Your Referrals",
        no_deposits: "No deposits yet",
        no_withdrawals: "No withdrawals yet",
        no_referrals: "No referrals yet",
        pending: "Pending",
        maturing: "Maturing",
        paid: "Paid",
        sent: "Sent",
        failed: "Failed",
        copied: "Copied!",
        error: "Error",
        success: "Success",
        withdrawal_created: "Withdrawal request created!",
        insufficient_balance: "Insufficient balance",
        invalid_amount: "Invalid amount",
        invalid_address: "Invalid TON address",
        connect_wallet: "Connect wallet first",
        deposit_min_error: "Minimum deposit: {min} TON",
        time_left: "{hours}h {mins}m left",
        profit_amount: "+{amount} TON",
    },
    ru: {
        loading: "Загрузка...",
        your_balance: "Ваш баланс",
        earned: "Заработано",
        how_it_works: "Как это работает",
        legend: "Наши AI-алгоритмы проводят арбитражную торговлю на DEX-платформах TON (DeDust, STON.fi), генерируя стабильный доход за счёт разницы цен.",
        profit: "Прибыль",
        maturity: "Срок",
        min_dep: "Мин. деп.",
        active_deposits: "Активные депозиты",
        deposit: "Депозит",
        withdraw: "Вывод",
        home: "Главная",
        history: "История",
        referrals: "Рефералы",
        make_deposit: "Сделать депозит",
        deposit_desc: "Внесите TON и получите прибыль после периода созревания",
        min_deposit: "Мин. депозит",
        profit_label: "Прибыль",
        maturity_label: "Срок",
        deposit_method: "Способ пополнения",
        ton_connect: "TON Connect",
        manual_transfer: "Ручной перевод",
        amount: "Сумма (TON)",
        send_deposit: "Отправить депозит",
        manual_desc: "Отправьте TON на адрес ниже с указанным комментарием:",
        wallet_address: "Адрес кошелька",
        comment: "Комментарий (обязательно!)",
        copy: "Копировать",
        comment_warning: "Всегда указывайте комментарий! Депозиты без правильного комментария не могут быть привязаны к вашему аккаунту.",
        withdraw_title: "Вывод",
        available_balance: "Доступный баланс",
        ton_address: "Адрес TON",
        fee: "Комиссия",
        you_receive: "Вы получите",
        confirm_withdraw: "Подтвердить вывод",
        max: "МАКС",
        history_title: "История",
        deposits: "Депозиты",
        withdrawals: "Выводы",
        referral_title: "Реферальная программа",
        invite_friends: "Приглашай друзей и зарабатывай",
        referral_desc: "Получайте процент от прибыли депозитов ваших рефералов!",
        commission: "Комиссия",
        your_link: "Ваша реферальная ссылка",
        share: "Поделиться",
        your_referrals: "Ваши рефералы",
        no_deposits: "Нет депозитов",
        no_withdrawals: "Нет выводов",
        no_referrals: "Нет рефералов",
        pending: "Ожидание",
        maturing: "Созревает",
        paid: "Выплачено",
        sent: "Отправлено",
        failed: "Ошибка",
        copied: "Скопировано!",
        error: "Ошибка",
        success: "Успешно",
        withdrawal_created: "Запрос на вывод создан!",
        insufficient_balance: "Недостаточно средств",
        invalid_amount: "Неверная сумма",
        invalid_address: "Неверный адрес TON",
        connect_wallet: "Сначала подключите кошелёк",
        deposit_min_error: "Минимальный депозит: {min} TON",
        time_left: "Осталось {hours}ч {mins}м",
        profit_amount: "+{amount} TON",
    },
};

let currentLang = "en";

function setLanguage(lang) {
    currentLang = lang;
    localStorage.setItem("goodmoney_lang", lang);
    document.getElementById("lang-label").textContent = lang.toUpperCase();
    document.querySelectorAll("[data-i18n]").forEach((el) => {
        const key = el.getAttribute("data-i18n");
        if (I18N[lang][key]) {
            el.textContent = I18N[lang][key];
        }
    });
}

function toggleLanguage() {
    const newLang = currentLang === "en" ? "ru" : "en";
    setLanguage(newLang);
    if (typeof apiCall === "function") {
        apiCall("/api/user/language", "POST", { language: newLang }).catch(() => {});
    }
}

function t(key, params) {
    let text = (I18N[currentLang] && I18N[currentLang][key]) || key;
    if (params) {
        for (const [k, v] of Object.entries(params)) {
            text = text.replace(`{${k}}`, v);
        }
    }
    return text;
}

function detectLanguage() {
    const saved = localStorage.getItem("goodmoney_lang");
    if (saved) return saved;
    try {
        const tg = window.Telegram?.WebApp;
        if (tg?.initDataUnsafe?.user?.language_code) {
            return tg.initDataUnsafe.user.language_code.startsWith("ru") ? "ru" : "en";
        }
    } catch (e) {}
    return navigator.language?.startsWith("ru") ? "ru" : "en";
}
