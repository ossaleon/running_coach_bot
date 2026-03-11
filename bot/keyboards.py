from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def gender_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Male", callback_data="gender_M"),
            InlineKeyboardButton("Female", callback_data="gender_F"),
            InlineKeyboardButton("Other", callback_data="gender_Other"),
        ]
    ])


def experience_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Beginner (< 1 year)", callback_data="exp_beginner")],
        [InlineKeyboardButton("Intermediate (1-3 years)", callback_data="exp_intermediate")],
        [InlineKeyboardButton("Advanced (3+ years)", callback_data="exp_advanced")],
    ])


def preferred_days_keyboard(selected: list[str] = None) -> InlineKeyboardMarkup:
    selected = selected or []
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    buttons = []
    row = []
    for day in days:
        check = "V " if day in selected else ""
        row.append(InlineKeyboardButton(f"{check}{day}", callback_data=f"day_{day}"))
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("Done", callback_data="days_done")])
    return buttons and InlineKeyboardMarkup(buttons)


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Confirm", callback_data="confirm_yes"),
            InlineKeyboardButton("Start Over", callback_data="confirm_no"),
        ]
    ])


def objective_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("5K", callback_data="obj_5K")],
        [InlineKeyboardButton("10K", callback_data="obj_10K")],
        [InlineKeyboardButton("Half Marathon", callback_data="obj_half_marathon")],
        [InlineKeyboardButton("Marathon", callback_data="obj_marathon")],
        [InlineKeyboardButton("Base Building", callback_data="obj_base_building")],
        [InlineKeyboardButton("General Fitness", callback_data="obj_general_fitness")],
    ])


def rpe_keyboard() -> InlineKeyboardMarkup:
    rows = []
    row = []
    for i in range(1, 11):
        row.append(InlineKeyboardButton(str(i), callback_data=f"rpe_{i}"))
        if len(row) == 5:
            rows.append(row)
            row = []
    return InlineKeyboardMarkup(rows)


def yes_no_keyboard(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Yes", callback_data=f"{prefix}_yes"),
            InlineKeyboardButton("No", callback_data=f"{prefix}_no"),
        ]
    ])


def plan_approval_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Approve", callback_data="plan_approve"),
            InlineKeyboardButton("Reject", callback_data="plan_reject"),
        ]
    ])


def settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Change reminder time", callback_data="settings_reminder")],
        [InlineKeyboardButton("Change timezone", callback_data="settings_timezone")],
    ])
