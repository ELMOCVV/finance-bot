from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

CURRENCY_FLAGS: dict[str, str] = {
    "UAH": "🇺🇦", "USD": "🇺🇸", "USDT": "💵",
    "EUR": "🇪🇺", "BTC": "₿",   "ETH": "Ξ",
}


def currency_flag(currency: str) -> str:
    return CURRENCY_FLAGS.get(currency.upper(), "💱")


# ── Головне меню ──────────────────────────────────────────────────────────────

def main_menu_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="💸 Расход", callback_data="menu:add_expense"),
        InlineKeyboardButton(text="💰 Доход",   callback_data="menu:add_income"),
    )
    b.row(
        InlineKeyboardButton(text="📊 Баланс",    callback_data="menu:balance"),
        InlineKeyboardButton(text="📷 Фото чека", callback_data="menu:add_photo"),
    )
    b.row(
        InlineKeyboardButton(text="🔄 Перевод",   callback_data="menu:transfer"),
        InlineKeyboardButton(text="💼 Финансист", callback_data="menu:advisor"),
    )
    b.row(InlineKeyboardButton(text="⚙️ Меню", callback_data="menu:settings"))
    return b.as_markup()


def settings_menu_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="💰 Транзакции", callback_data="menu:transactions"),
        InlineKeyboardButton(text="🏦 Счета",    callback_data="menu:accounts"),
    )
    b.row(
        InlineKeyboardButton(text="📊 Аналитика", callback_data="menu:analytics"),
        InlineKeyboardButton(text="🎯 Цели",      callback_data="menu:goals"),
    )
    b.row(
        InlineKeyboardButton(text="💳 Долги",   callback_data="menu:debts"),
        InlineKeyboardButton(text="📋 Бюджеты", callback_data="menu:budgets"),
    )
    b.row(
        InlineKeyboardButton(text="🔔 Подписки", callback_data="menu:subscriptions"),
        InlineKeyboardButton(text="🏷 Категории", callback_data="menu:categories"),
    )
    b.row(InlineKeyboardButton(text="🏦 Подключить Monobank", callback_data="mono:menu"))
    b.row(InlineKeyboardButton(text="🧹 Начать с нуля", callback_data="reset:start"))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main"))
    return b.as_markup()


# ── Рахунки ───────────────────────────────────────────────────────────────────

def accounts_list_keyboard(accounts: list) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for acc in accounts:
        flag = currency_flag(acc.currency)
        star = " ⭐" if acc.is_default else ""
        label = f"{flag} {acc.name}{star} | {acc.balance:.2f} {acc.currency}"
        b.row(InlineKeyboardButton(text=label[:60], callback_data=f"acc:view:{acc.id}"))
    b.row(InlineKeyboardButton(text="➕ Добавить счёт", callback_data="acc:add"))
    b.row(InlineKeyboardButton(text="⬅️ Меню",           callback_data="menu:main"))
    return b.as_markup()


def currency_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="🇺🇦 UAH",  callback_data="currency:UAH"),
        InlineKeyboardButton(text="🇺🇸 USD",  callback_data="currency:USD"),
    )
    b.row(
        InlineKeyboardButton(text="💵 USDT", callback_data="currency:USDT"),
        InlineKeyboardButton(text="🇪🇺 EUR",  callback_data="currency:EUR"),
    )
    b.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel:account"))
    return b.as_markup()


def account_view_keyboard(acc_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✏️ Редактировать счёт", callback_data=f"acc:edit:{acc_id}"))
    b.row(InlineKeyboardButton(text="🗑 Удалить счёт",   callback_data=f"acc:del_confirm:{acc_id}"))
    b.row(InlineKeyboardButton(text="⬅️ Назад",              callback_data="menu:accounts"))
    return b.as_markup()


def edit_account_keyboard(acc_id: int, is_default: bool = False) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="📝 Изменить название",  callback_data=f"acc:edit_name:{acc_id}"),
        InlineKeyboardButton(text="💵 Изменить баланс", callback_data=f"acc:edit_bal:{acc_id}"),
    )
    if not is_default:
        b.row(InlineKeyboardButton(text="⭐ Сделать основным", callback_data=f"acc:set_default:{acc_id}"))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"acc:view:{acc_id}"))
    return b.as_markup()


# ── Перекази ──────────────────────────────────────────────────────────────────

def transfer_account_keyboard(accounts: list, step: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for acc in accounts:
        flag = currency_flag(acc.currency)
        star = " ⭐" if acc.is_default else ""
        b.row(InlineKeyboardButton(
            text=f"{flag} {acc.name}{star} — {acc.balance:,.2f} {acc.currency}",
            callback_data=f"transfer:{step}:{acc.id}",
        ))
    b.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel:flow"))
    return b.as_markup()


def transfer_confirm_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✅ Подтвердить", callback_data="transfer:confirm"))
    b.row(InlineKeyboardButton(text="❌ Отмена",   callback_data="cancel:flow"))
    return b.as_markup()


def confirm_edit_keyboard(confirm_cb: str, cancel_cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Сохранить",   callback_data=confirm_cb)],
        [InlineKeyboardButton(text="❌ Отмена",  callback_data=cancel_cb)],
    ])


# ── Транзакції ────────────────────────────────────────────────────────────────

def confirm_multi_transaction_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✅ Подтвердить все", callback_data="multi:confirm"))
    b.row(
        InlineKeyboardButton(text="✏️ Редактировать", callback_data="multi:edit"),
        InlineKeyboardButton(text="❌ Отмена",   callback_data="multi:cancel"),
    )
    return b.as_markup()


_NUM_EMOJI = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


def multi_tx_select_keyboard(multi_txs: list) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for i, tx in enumerate(multi_txs):
        num = _NUM_EMOJI[i] if i < len(_NUM_EMOJI) else f"{i + 1}."
        desc = (tx.get("description") or "?")[:18]
        label = f"{num} {tx.get('amount', 0)} {tx.get('currency', 'UAH')} — {desc}"
        b.row(InlineKeyboardButton(text=label[:60], callback_data=f"multi:edit:{i}"))
    b.row(InlineKeyboardButton(text="⬅️ К подтверждению", callback_data="multi:back"))
    return b.as_markup()


def confirm_transaction_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="✅ Подтвердить", callback_data="tx:confirm"),
        InlineKeyboardButton(text="✏️ Редактировать",  callback_data="tx:edit"),
    )
    b.row(InlineKeyboardButton(text="❌ Отмена", callback_data="tx:cancel"))
    return b.as_markup()


def new_category_keyboard(cat_name: str) -> InlineKeyboardMarkup:
    safe = cat_name[:40]
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(
        text=f"✅ Создать «{safe}» и сохранить",
        callback_data=f"newcat:create:{safe}",
    ))
    b.row(InlineKeyboardButton(text="🔄 Выбрать другую категорию", callback_data="newcat:pick"))
    b.row(InlineKeyboardButton(text="❌ Отмена", callback_data="tx:cancel"))
    return b.as_markup()


def edit_transaction_keyboard(show_new_cat: bool = False) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="💵 Изменить сумму",  callback_data="txedit:amount"),
        InlineKeyboardButton(text="📝 Изменить описание",  callback_data="txedit:desc"),
    )
    b.row(
        InlineKeyboardButton(text="🏷 Изменить категорию", callback_data="txedit:category"),
        InlineKeyboardButton(text="🏦 Изменить счёт",   callback_data="txedit:account"),
    )
    if show_new_cat:
        b.row(InlineKeyboardButton(text="➕ Новая категория", callback_data="txedit:new_cat"))
    b.row(InlineKeyboardButton(text="⬅️ К подтверждению", callback_data="txedit:back"))
    return b.as_markup()


def tx_account_select_keyboard(accounts: list) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for acc in accounts:
        flag = currency_flag(acc.currency)
        star = " ⭐" if acc.is_default else ""
        b.row(InlineKeyboardButton(
            text=f"{flag} {acc.name}{star} — {acc.balance:.2f} {acc.currency}",
            callback_data=f"txacc:{acc.id}",
        ))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="txedit:back"))
    return b.as_markup()


def categories_keyboard(categories: list, back_cb: str = "txedit:back") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for cat in categories:
        b.row(InlineKeyboardButton(
            text=f"{cat.icon or ''} {cat.name}",
            callback_data=f"catpick:{cat.id}",
        ))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=back_cb))
    return b.as_markup()


def transaction_list_keyboard(items: list) -> InlineKeyboardMarkup:
    """Список останніх транзакцій і переказів (items мають .kind = 'tx' | 'transfer')."""
    b = InlineKeyboardBuilder()
    type_emoji = {"expense": "➖", "income": "➕", "transfer": "🔄", "debt_payment": "💳"}
    for item in items:
        e = type_emoji.get(item.type, "💸")
        desc = (item.description or "")[:18]
        date_s = item.date.strftime("%d.%m")
        label = f"{e} {item.amount:.0f} {item.currency} {desc} ({date_s})"
        prefix = "transfer:view" if item.kind == "transfer" else "tx:view"
        b.row(InlineKeyboardButton(text=label[:60], callback_data=f"{prefix}:{item.id}"))
    b.row(InlineKeyboardButton(text="⬅️ Меню", callback_data="menu:main"))
    return b.as_markup()


def transaction_view_keyboard(tx_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🗑 Удалить", callback_data=f"tx:del_confirm:{tx_id}"))
    b.row(InlineKeyboardButton(text="⬅️ Назад",    callback_data="menu:transactions"))
    return b.as_markup()


# ── Цілі ─────────────────────────────────────────────────────────────────────

def goals_keyboard(goals: list) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for g in goals:
        pct = round(g.progress_percent)
        b.row(
            InlineKeyboardButton(text=f"🎯 {g.name} — {pct}%", callback_data=f"goal:view:{g.id}"),
            InlineKeyboardButton(text="🗑", callback_data=f"goal:del_confirm:{g.id}"),
        )
    b.row(InlineKeyboardButton(text="➕ Добавить цель", callback_data="goal:add"))
    b.row(InlineKeyboardButton(text="⬅️ Меню",         callback_data="menu:main"))
    return b.as_markup()


def goal_view_keyboard(goal_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🗑 Удалить цель", callback_data=f"goal:del_confirm:{goal_id}"))
    b.row(InlineKeyboardButton(text="⬅️ Назад",          callback_data="menu:goals"))
    return b.as_markup()


# ── Борги ─────────────────────────────────────────────────────────────────────

def debts_keyboard(debts: list) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for d in debts:
        b.row(
            InlineKeyboardButton(
                text=f"💳 {d.name}: {d.remaining_amount:.0f} {d.currency}",
                callback_data=f"debt:view:{d.id}",
            ),
            InlineKeyboardButton(text="🗑", callback_data=f"debt:del_confirm:{d.id}"),
        )
    b.row(InlineKeyboardButton(text="➕ Добавить долг", callback_data="debt:add"))
    b.row(InlineKeyboardButton(text="⬅️ Меню",         callback_data="menu:main"))
    return b.as_markup()


def debt_view_keyboard(debt_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🗑 Удалить долг", callback_data=f"debt:del_confirm:{debt_id}"))
    b.row(InlineKeyboardButton(text="⬅️ Назад",          callback_data="menu:debts"))
    return b.as_markup()


# ── Бюджети ───────────────────────────────────────────────────────────────────

def budget_list_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="➕ Добавить бюджет", callback_data="budgets:add"))
    b.row(InlineKeyboardButton(text="⬅️ Меню",           callback_data="menu:main"))
    return b.as_markup()


def budget_categories_keyboard(categories: list) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for cat in categories:
        b.row(InlineKeyboardButton(
            text=f"{cat.icon or ''} {cat.name}",
            callback_data=f"bcat:{cat.id}",
        ))
    b.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel:flow"))
    return b.as_markup()


def use_current_month_keyboard(month: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ Текущий ({month})", callback_data="budget:cur_month")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel:flow")],
    ])


# ── Підтвердження видалення ───────────────────────────────────────────────────

def confirm_delete_keyboard(confirm_cb: str, cancel_cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, удалить", callback_data=confirm_cb)],
        [InlineKeyboardButton(text="❌ Отмена",      callback_data=cancel_cb)],
    ])


# ── Утиліти ───────────────────────────────────────────────────────────────────

def skip_keyboard(skip_cb: str, cancel_cb: str = "cancel:flow") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⏭ Пропустить", callback_data=skip_cb),
        InlineKeyboardButton(text="❌ Отмена",   callback_data=cancel_cb),
    ]])


def back_keyboard(cb: str = "menu:main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⬅️ Назад", callback_data=cb),
    ]])


# ── Підписки ──────────────────────────────────────────────────────────────────

_MONTHS_UA_SHORT = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн",
                    "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]
MONTHS_UA_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня",
                 "июля", "августа", "сентября", "октября", "ноября", "декабря"]


def subscriptions_keyboard(subs: list) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for s in subs:
        icon = "🔔" if s.is_active else "⏸"
        per = "мес." if s.period == "monthly" else "год"
        label = f"{icon} {s.name} — {s.amount:.0f} {s.currency}/{per}"
        b.row(InlineKeyboardButton(text=label[:60], callback_data=f"sub:view:{s.id}"))
    b.row(InlineKeyboardButton(text="➕ Добавить подписку", callback_data="sub:add"))
    b.row(InlineKeyboardButton(text="⬅️ Меню",             callback_data="menu:main"))
    return b.as_markup()


def subscription_view_keyboard(sub_id: int, is_active: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"sub:edit:{sub_id}"))
    toggle = "⏸ Приостановить" if is_active else "▶️ Активировать"
    b.row(
        InlineKeyboardButton(text=toggle,       callback_data=f"sub:toggle:{sub_id}"),
        InlineKeyboardButton(text="🗑 Удалить", callback_data=f"sub:del_confirm:{sub_id}"),
    )
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:subscriptions"))
    return b.as_markup()


def edit_subscription_keyboard(sub_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="📝 Название",  callback_data=f"sub:edit_name:{sub_id}"),
        InlineKeyboardButton(text="💵 Сумма",   callback_data=f"sub:edit_amount:{sub_id}"),
    )
    b.row(InlineKeyboardButton(text="🕐 Время напоминания", callback_data=f"sub:edit_hour:{sub_id}"))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"sub:view:{sub_id}"))
    return b.as_markup()


def sub_period_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Ежемесячная", callback_data="sub:period:monthly")],
        [InlineKeyboardButton(text="📆 Ежегодная",   callback_data="sub:period:yearly")],
        [InlineKeyboardButton(text="❌ Отмена",  callback_data="cancel:flow")],
    ])


def sub_currency_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="🇺🇦 UAH",  callback_data="subcur:UAH"),
        InlineKeyboardButton(text="🇺🇸 USD",  callback_data="subcur:USD"),
    )
    b.row(
        InlineKeyboardButton(text="💵 USDT", callback_data="subcur:USDT"),
        InlineKeyboardButton(text="🇪🇺 EUR",  callback_data="subcur:EUR"),
    )
    b.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel:flow"))
    return b.as_markup()


def sub_month_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for i, name in enumerate(_MONTHS_UA_SHORT, 1):
        b.button(text=f"{i}. {name}", callback_data=f"sub:month:{i}")
    b.adjust(3)
    b.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel:flow"))
    return b.as_markup()


def sub_account_keyboard(accounts: list) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for acc in accounts:
        flag = currency_flag(acc.currency)
        b.row(InlineKeyboardButton(
            text=f"{flag} {acc.name} — {acc.balance:.2f} {acc.currency}",
            callback_data=f"sub:acc:{acc.id}",
        ))
    b.row(InlineKeyboardButton(text="🚫 Без счёта",  callback_data="sub:no_acc"))
    b.row(InlineKeyboardButton(text="❌ Отмена",    callback_data="cancel:flow"))
    return b.as_markup()


# ── Категорії ─────────────────────────────────────────────────────────────────

def categories_manage_keyboard(categories: list) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for cat in categories:
        label = f"{cat.icon or '🏷'} {cat.name}"
        b.row(InlineKeyboardButton(text=label[:60], callback_data=f"cat:view:{cat.id}"))
    b.row(InlineKeyboardButton(text="➕ Добавить категорию", callback_data="cat:add"))
    b.row(InlineKeyboardButton(text="⬅️ Меню", callback_data="menu:settings"))
    return b.as_markup()


def category_view_keyboard(cat_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="✏️ Переименовать", callback_data=f"cat:rename:{cat_id}"),
        InlineKeyboardButton(text="🗑 Удалить",      callback_data=f"cat:del_confirm:{cat_id}"),
    )
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:categories"))
    return b.as_markup()


def category_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💸 Расход", callback_data="cattype:expense"),
            InlineKeyboardButton(text="💰 Доход",   callback_data="cattype:income"),
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel:flow")],
    ])


# ── Monobank ──────────────────────────────────────────────────────────────────

def monobank_menu_keyboard(connections: list) -> InlineKeyboardMarkup:
    """Меню Monobank: наявні підключення + додати нове."""
    b = InlineKeyboardBuilder()
    for conn in connections:
        n = len(conn.cards)
        b.row(InlineKeyboardButton(
            text=f"💳 Monobank ({n} карт.)", callback_data=f"mono:view:{conn.id}",
        ))
    b.row(InlineKeyboardButton(text="➕ Подключить Monobank", callback_data="mono:start"))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:settings"))
    return b.as_markup()


def monobank_connection_keyboard(connection_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔌 Отключить", callback_data=f"mono:disconnect_confirm:{connection_id}"))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="mono:menu"))
    return b.as_markup()


def mono_cards_keyboard(accounts: list[dict], selected: set[int]) -> InlineKeyboardMarkup:
    """Мультиселект карток Monobank зі вбудованими прапорцями ☐/☑️.

    accounts — список dict з полями: currency (буквений), last4.
    """
    b = InlineKeyboardBuilder()
    for i, acc in enumerate(accounts):
        mark = "☑️" if i in selected else "☐"
        label = f"{mark} 💳 Mono {acc['currency']} •{acc['last4']}"
        b.row(InlineKeyboardButton(text=label, callback_data=f"mono:toggle:{i}"))
    b.row(InlineKeyboardButton(text="Готово ✅", callback_data="mono:cards_done"))
    b.row(InlineKeyboardButton(text="❌ Отмена", callback_data="mono:cancel"))
    return b.as_markup()


def mono_backfill_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Не подтягивать", callback_data="mono:bf:none")],
        [InlineKeyboardButton(text="За неделю", callback_data="mono:bf:week")],
        [InlineKeyboardButton(text="За 31 день (максимум)", callback_data="mono:bf:month")],
    ])


def mono_confirm_keyboard(pid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Да", callback_data=f"mono:ok:{pid}"),
        InlineKeyboardButton(text="✏️ Изменить", callback_data=f"mono:edit:{pid}"),
        InlineKeyboardButton(text="🚫 Не учитывать", callback_data=f"mono:skip:{pid}"),
    ]])


def mono_category_keyboard(categories: list, pid: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for cat in categories:
        b.row(InlineKeyboardButton(
            text=f"{cat.icon or '🏷'} {cat.name}",
            callback_data=f"mono:cat:{pid}:{cat.id}",
        ))
    b.row(InlineKeyboardButton(text="🚫 Не учитывать", callback_data=f"mono:skip:{pid}"))
    return b.as_markup()
