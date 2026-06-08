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
        InlineKeyboardButton(text="💸 Витрата", callback_data="menu:add_expense"),
        InlineKeyboardButton(text="💰 Дохід",   callback_data="menu:add_income"),
    )
    b.row(
        InlineKeyboardButton(text="📊 Баланс",    callback_data="menu:balance"),
        InlineKeyboardButton(text="📷 Фото чека", callback_data="menu:add_photo"),
    )
    b.row(
        InlineKeyboardButton(text="🔄 Переказ",   callback_data="menu:transfer"),
        InlineKeyboardButton(text="💼 Фінансист", callback_data="menu:advisor"),
    )
    b.row(InlineKeyboardButton(text="⚙️ Меню", callback_data="menu:settings"))
    return b.as_markup()


def settings_menu_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="💰 Транзакції", callback_data="menu:transactions"),
        InlineKeyboardButton(text="🏦 Рахунки",    callback_data="menu:accounts"),
    )
    b.row(
        InlineKeyboardButton(text="📊 Аналітика", callback_data="menu:analytics"),
        InlineKeyboardButton(text="🎯 Цілі",      callback_data="menu:goals"),
    )
    b.row(
        InlineKeyboardButton(text="💳 Борги",   callback_data="menu:debts"),
        InlineKeyboardButton(text="📋 Бюджети", callback_data="menu:budgets"),
    )
    b.row(
        InlineKeyboardButton(text="🔔 Підписки", callback_data="menu:subscriptions"),
        InlineKeyboardButton(text="🏷 Категорії", callback_data="menu:categories"),
    )
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
    b.row(InlineKeyboardButton(text="➕ Додати рахунок", callback_data="acc:add"))
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
    b.row(InlineKeyboardButton(text="❌ Скасувати", callback_data="cancel:account"))
    return b.as_markup()


def account_view_keyboard(acc_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✏️ Редагувати рахунок", callback_data=f"acc:edit:{acc_id}"))
    b.row(InlineKeyboardButton(text="🗑 Видалити рахунок",   callback_data=f"acc:del_confirm:{acc_id}"))
    b.row(InlineKeyboardButton(text="⬅️ Назад",              callback_data="menu:accounts"))
    return b.as_markup()


def edit_account_keyboard(acc_id: int, is_default: bool = False) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="📝 Змінити назву",  callback_data=f"acc:edit_name:{acc_id}"),
        InlineKeyboardButton(text="💵 Змінити баланс", callback_data=f"acc:edit_bal:{acc_id}"),
    )
    if not is_default:
        b.row(InlineKeyboardButton(text="⭐ Зробити основним", callback_data=f"acc:set_default:{acc_id}"))
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
    b.row(InlineKeyboardButton(text="❌ Скасувати", callback_data="cancel:flow"))
    return b.as_markup()


def transfer_confirm_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✅ Підтвердити", callback_data="transfer:confirm"))
    b.row(InlineKeyboardButton(text="❌ Скасувати",   callback_data="cancel:flow"))
    return b.as_markup()


def confirm_edit_keyboard(confirm_cb: str, cancel_cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Зберегти",   callback_data=confirm_cb)],
        [InlineKeyboardButton(text="❌ Скасувати",  callback_data=cancel_cb)],
    ])


# ── Транзакції ────────────────────────────────────────────────────────────────

def confirm_multi_transaction_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✅ Підтвердити всі", callback_data="multi:confirm"))
    b.row(
        InlineKeyboardButton(text="✏️ Редагувати", callback_data="multi:edit"),
        InlineKeyboardButton(text="❌ Скасувати",   callback_data="multi:cancel"),
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
    b.row(InlineKeyboardButton(text="⬅️ До підтвердження", callback_data="multi:back"))
    return b.as_markup()


def confirm_transaction_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="✅ Підтвердити", callback_data="tx:confirm"),
        InlineKeyboardButton(text="✏️ Редагувати",  callback_data="tx:edit"),
    )
    b.row(InlineKeyboardButton(text="❌ Скасувати", callback_data="tx:cancel"))
    return b.as_markup()


def new_category_keyboard(cat_name: str) -> InlineKeyboardMarkup:
    safe = cat_name[:40]
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(
        text=f"✅ Створити «{safe}» і зберегти",
        callback_data=f"newcat:create:{safe}",
    ))
    b.row(InlineKeyboardButton(text="🔄 Вибрати іншу категорію", callback_data="newcat:pick"))
    b.row(InlineKeyboardButton(text="❌ Скасувати", callback_data="tx:cancel"))
    return b.as_markup()


def edit_transaction_keyboard(show_new_cat: bool = False) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="💵 Змінити суму",  callback_data="txedit:amount"),
        InlineKeyboardButton(text="📝 Змінити опис",  callback_data="txedit:desc"),
    )
    b.row(
        InlineKeyboardButton(text="🏷 Змінити категорію", callback_data="txedit:category"),
        InlineKeyboardButton(text="🏦 Змінити рахунок",   callback_data="txedit:account"),
    )
    if show_new_cat:
        b.row(InlineKeyboardButton(text="➕ Нова категорія", callback_data="txedit:new_cat"))
    b.row(InlineKeyboardButton(text="⬅️ До підтвердження", callback_data="txedit:back"))
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
    b.row(InlineKeyboardButton(text="🗑 Видалити", callback_data=f"tx:del_confirm:{tx_id}"))
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
    b.row(InlineKeyboardButton(text="➕ Додати ціль", callback_data="goal:add"))
    b.row(InlineKeyboardButton(text="⬅️ Меню",         callback_data="menu:main"))
    return b.as_markup()


def goal_view_keyboard(goal_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🗑 Видалити ціль", callback_data=f"goal:del_confirm:{goal_id}"))
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
    b.row(InlineKeyboardButton(text="➕ Додати борг", callback_data="debt:add"))
    b.row(InlineKeyboardButton(text="⬅️ Меню",         callback_data="menu:main"))
    return b.as_markup()


def debt_view_keyboard(debt_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🗑 Видалити борг", callback_data=f"debt:del_confirm:{debt_id}"))
    b.row(InlineKeyboardButton(text="⬅️ Назад",          callback_data="menu:debts"))
    return b.as_markup()


# ── Бюджети ───────────────────────────────────────────────────────────────────

def budget_list_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="➕ Додати бюджет", callback_data="budgets:add"))
    b.row(InlineKeyboardButton(text="⬅️ Меню",           callback_data="menu:main"))
    return b.as_markup()


def budget_categories_keyboard(categories: list) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for cat in categories:
        b.row(InlineKeyboardButton(
            text=f"{cat.icon or ''} {cat.name}",
            callback_data=f"bcat:{cat.id}",
        ))
    b.row(InlineKeyboardButton(text="❌ Скасувати", callback_data="cancel:flow"))
    return b.as_markup()


def use_current_month_keyboard(month: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ Поточний ({month})", callback_data="budget:cur_month")],
        [InlineKeyboardButton(text="❌ Скасувати", callback_data="cancel:flow")],
    ])


# ── Підтвердження видалення ───────────────────────────────────────────────────

def confirm_delete_keyboard(confirm_cb: str, cancel_cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Так, видалити", callback_data=confirm_cb)],
        [InlineKeyboardButton(text="❌ Скасувати",      callback_data=cancel_cb)],
    ])


# ── Утиліти ───────────────────────────────────────────────────────────────────

def skip_keyboard(skip_cb: str, cancel_cb: str = "cancel:flow") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⏭ Пропустити", callback_data=skip_cb),
        InlineKeyboardButton(text="❌ Скасувати",   callback_data=cancel_cb),
    ]])


def back_keyboard(cb: str = "menu:main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⬅️ Назад", callback_data=cb),
    ]])


# ── Підписки ──────────────────────────────────────────────────────────────────

_MONTHS_UA_SHORT = ["Січ", "Лют", "Бер", "Кві", "Тра", "Чер",
                    "Лип", "Сер", "Вер", "Жов", "Лис", "Гру"]
MONTHS_UA_GEN = ["січня", "лютого", "березня", "квітня", "травня", "червня",
                 "липня", "серпня", "вересня", "жовтня", "листопада", "грудня"]


def subscriptions_keyboard(subs: list) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for s in subs:
        icon = "🔔" if s.is_active else "⏸"
        per = "міс." if s.period == "monthly" else "рік"
        label = f"{icon} {s.name} — {s.amount:.0f} {s.currency}/{per}"
        b.row(InlineKeyboardButton(text=label[:60], callback_data=f"sub:view:{s.id}"))
    b.row(InlineKeyboardButton(text="➕ Додати підписку", callback_data="sub:add"))
    b.row(InlineKeyboardButton(text="⬅️ Меню",             callback_data="menu:main"))
    return b.as_markup()


def subscription_view_keyboard(sub_id: int, is_active: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✏️ Редагувати", callback_data=f"sub:edit:{sub_id}"))
    toggle = "⏸ Призупинити" if is_active else "▶️ Активувати"
    b.row(
        InlineKeyboardButton(text=toggle,       callback_data=f"sub:toggle:{sub_id}"),
        InlineKeyboardButton(text="🗑 Видалити", callback_data=f"sub:del_confirm:{sub_id}"),
    )
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:subscriptions"))
    return b.as_markup()


def edit_subscription_keyboard(sub_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="📝 Назва",  callback_data=f"sub:edit_name:{sub_id}"),
        InlineKeyboardButton(text="💵 Сума",   callback_data=f"sub:edit_amount:{sub_id}"),
    )
    b.row(InlineKeyboardButton(text="🕐 Час нагадування", callback_data=f"sub:edit_hour:{sub_id}"))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"sub:view:{sub_id}"))
    return b.as_markup()


def sub_period_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Щомісячна", callback_data="sub:period:monthly")],
        [InlineKeyboardButton(text="📆 Щорічна",   callback_data="sub:period:yearly")],
        [InlineKeyboardButton(text="❌ Скасувати",  callback_data="cancel:flow")],
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
    b.row(InlineKeyboardButton(text="❌ Скасувати", callback_data="cancel:flow"))
    return b.as_markup()


def sub_month_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for i, name in enumerate(_MONTHS_UA_SHORT, 1):
        b.button(text=f"{i}. {name}", callback_data=f"sub:month:{i}")
    b.adjust(3)
    b.row(InlineKeyboardButton(text="❌ Скасувати", callback_data="cancel:flow"))
    return b.as_markup()


def sub_account_keyboard(accounts: list) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for acc in accounts:
        flag = currency_flag(acc.currency)
        b.row(InlineKeyboardButton(
            text=f"{flag} {acc.name} — {acc.balance:.2f} {acc.currency}",
            callback_data=f"sub:acc:{acc.id}",
        ))
    b.row(InlineKeyboardButton(text="🚫 Без рахунку",  callback_data="sub:no_acc"))
    b.row(InlineKeyboardButton(text="❌ Скасувати",    callback_data="cancel:flow"))
    return b.as_markup()


# ── Категорії ─────────────────────────────────────────────────────────────────

def categories_manage_keyboard(categories: list) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for cat in categories:
        label = f"{cat.icon or '🏷'} {cat.name}"
        b.row(InlineKeyboardButton(text=label[:60], callback_data=f"cat:view:{cat.id}"))
    b.row(InlineKeyboardButton(text="➕ Додати категорію", callback_data="cat:add"))
    b.row(InlineKeyboardButton(text="⬅️ Меню", callback_data="menu:settings"))
    return b.as_markup()


def category_view_keyboard(cat_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="✏️ Перейменувати", callback_data=f"cat:rename:{cat_id}"),
        InlineKeyboardButton(text="🗑 Видалити",      callback_data=f"cat:del_confirm:{cat_id}"),
    )
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:categories"))
    return b.as_markup()


def category_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💸 Витрата", callback_data="cattype:expense"),
            InlineKeyboardButton(text="💰 Дохід",   callback_data="cattype:income"),
        ],
        [InlineKeyboardButton(text="❌ Скасувати", callback_data="cancel:flow")],
    ])
