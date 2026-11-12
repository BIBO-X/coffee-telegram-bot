import logging
import os
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from database import db

# إعدادات البوت
BOT_TOKEN = os.getenv("BOT_TOKEN")

# إعدادات الاقتصاد المتوازنة
ECONOMY = {
    "click_base": 1,           # قوة النقر الأساسية
    "click_upgrade_bonus": 1,  # زيادة قوة النقر لكل ترقية
    "daily_bonus_base": 50,    # المكافأة اليومية الأساسية
    "daily_bonus_multiplier": 1.5,  # مضاعف المكافأة حسب المستوى
    "offline_cap_hours": 8,    # الحد الأقصى للأرباح الغير متصلة
}

# تعريف الترقيات المتوازنة
UPGRADES = {
    "click_1": {
        "name": "⚡ إصبع قوي",
        "description": "+1 لكل نقرة",
        "base_cost": 20,
        "cost_multiplier": 1.5,
        "type": "click",
        "value": 1
    },
    "click_2": {
        "name": "💪 يد محترفة",
        "description": "+3 لكل نقرة",
        "base_cost": 100,
        "cost_multiplier": 1.6,
        "type": "click",
        "value": 3
    },
    "auto_1": {
        "name": "🌱 بذرة قهوة",
        "description": "+0.5 قهوة/ثانية",
        "base_cost": 50,
        "cost_multiplier": 1.4,
        "type": "auto",
        "value": 0.5
    },
    "auto_2": {
        "name": "🌿 شجرة صغيرة",
        "description": "+2 قهوة/ثانية",
        "base_cost": 200,
        "cost_multiplier": 1.45,
        "type": "auto",
        "value": 2
    },
    "auto_3": {
        "name": "🌳 مزرعة صغيرة",
        "description": "+5 قهوة/ثانية",
        "base_cost": 800,
        "cost_multiplier": 1.5,
        "type": "auto",
        "value": 5
    },
    "auto_4": {
        "name": "🏭 مصنع قهوة",
        "description": "+20 قهوة/ثانية",
        "base_cost": 3000,
        "cost_multiplier": 1.55,
        "type": "auto",
        "value": 20
    },
    "auto_5": {
        "name": "🏢 إمبراطورية قهوة",
        "description": "+100 قهوة/ثانية",
        "base_cost": 15000,
        "cost_multiplier": 1.6,
        "type": "auto",
        "value": 100
    }
}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== دوال مساعدة ==========

def format_number(n):
    """تنسيق الأرقام الكبيرة"""
    if n >= 1e9:
        return f"{n/1e9:.1f}B"
    elif n >= 1e6:
        return f"{n/1e6:.1f}M"
    elif n >= 1e3:
        return f"{n/1e3:.1f}K"
    return f"{int(n)}"

def calculate_upgrade_cost(upgrade_id: str, owned_quantity: int) -> int:
    """حساب تكلفة الترقية"""
    upgrade = UPGRADES[upgrade_id]
    return int(upgrade["base_cost"] * (upgrade["cost_multiplier"] ** owned_quantity))

def calculate_player_cps(upgrades: dict) -> float:
    """حساب إنتاج اللاعب التلقائي"""
    total_cps = 0
    for upgrade_id, quantity in upgrades.items():
        if upgrade_id in UPGRADES and UPGRADES[upgrade_id]["type"] == "auto":
            total_cps += UPGRADES[upgrade_id]["value"] * quantity
    return total_cps

def calculate_player_click_power(upgrades: dict) -> float:
    """حساب قوة نقرة اللاعب"""
    total_power = ECONOMY["click_base"]
    for upgrade_id, quantity in upgrades.items():
        if upgrade_id in UPGRADES and UPGRADES[upgrade_id]["type"] == "click":
            total_power += UPGRADES[upgrade_id]["value"] * quantity
    return total_power

# ========== معالجات الأوامر ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر البداية"""
    user = update.effective_user
    
    # إنشاء أو جلب اللاعب
    player = db.get_or_create_player(user.id, user.username, user.first_name)
    
    # حساب الأرباح الغير متصلة
    offline_earnings = db.calculate_offline_earnings(user.id)
    if offline_earnings > 0:
        db.add_coins(user.id, offline_earnings, "offline_earnings")
        player = db.get_or_create_player(user.id)
    
    keyboard = [
        [InlineKeyboardButton("🎮 العب الآن", callback_data="play")],
        [InlineKeyboardButton("🛒 المتجر", callback_data="shop")],
        [InlineKeyboardButton("🏆 المتصدرون", callback_data="leaderboard")],
        [InlineKeyboardButton("🎁 المكافأة اليومية", callback_data="daily")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = f"""
☕ **أهلاً بك في مزرعة القهوة يا {user.first_name}!**

💰 **رصيدك:** {format_number(player['coins'])}
⚡ **إنتاجك:** {format_number(player['cps'])}/ثانية
👆 **قوة النقرة:** {format_number(player['click_power'])}

🎯 **هدفك:** ابنِ إمبراطورية القهوة الخاصة بك!

{"💤 **أرباح أثناء غيابك:** +" + format_number(offline_earnings) if offline_earnings > 0 else ""}
    """
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء اللعب"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    player = db.get_or_create_player(user.id)
    
    keyboard = [
        [InlineKeyboardButton("☕ انقر للحصاد!", callback_data="click")],
        [InlineKeyboardButton("🛒 المتجر", callback_data="shop")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"""
🎮 **لوحة اللعب**

💰 **الرصيد:** {format_number(player['coins'])}
⚡ **إنتاج تلقائي:** {format_number(player['cps'])}/ثانية
👆 **قوة النقرة:** {format_number(player['click_power'])}

انقر الزر بالأسفل لجمع القهوة! ☕
        """,
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة النقر"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    player = db.get_or_create_player(user.id)
    
    # إضافة العملات من النقرة
    new_balance = db.add_coins(user.id, player['click_power'], "click")
    
    keyboard = [
        [InlineKeyboardButton("☕ انقر مرة أخرى!", callback_data="click")],
        [InlineKeyboardButton("🛒 المتجر", callback_data="shop")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"""
✅ **+{format_number(player['click_power'])} قهوة!**

💰 **الرصيد الجديد:** {format_number(new_balance)}
⚡ **إنتاج تلقائي:** {format_number(player['cps'])}/ثانية

استمر في النقر! ☕
        """,
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض المتجر"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    player = db.get_or_create_player(user.id)
    upgrades = db.get_player_upgrades(user.id)
    
    keyboard = []
    
    for upgrade_id, upgrade in UPGRADES.items():
        owned = upgrades.get(upgrade_id, 0)
        cost = calculate_upgrade_cost(upgrade_id, owned)
        
        button_text = f"{upgrade['name']} - {format_number(cost)} 💰 (لديك: {owned})"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"buy_{upgrade_id}")])
    
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="back")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"""
🛒 **متجر الترقيات**

💰 **رصيدك:** {format_number(player['coins'])}

اختر ترقية لشرائها:
        """,
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def buy_upgrade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شراء ترقية"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    upgrade_id = query.data.replace("buy_", "")
    
    if upgrade_id not in UPGRADES:
        await query.answer("❌ ترقية غير صالحة!", show_alert=True)
        return
    
    player = db.get_or_create_player(user.id)
    upgrades = db.get_player_upgrades(user.id)
    owned = upgrades.get(upgrade_id, 0)
    cost = calculate_upgrade_cost(upgrade_id, owned)
    
    # التحقق من الرصيد
    if player['coins'] < cost:
        await query.answer(f"❌ تحتاج إلى {format_number(cost - player['coins'])} إضافية!", show_alert=True)
        return
    
    # خصم العملات
    if db.spend_coins(user.id, cost, "upgrade_purchase"):
        # إضافة الترقية
        db.add_upgrade(user.id, upgrade_id)
        
        # تحديث الإحصائيات
        new_upgrades = db.get_player_upgrades(user.id)
        new_cps = calculate_player_cps(new_upgrades)
        new_click_power = calculate_player_click_power(new_upgrades)
        
        db.update_player_stats(user.id, click_power=new_click_power, cps=new_cps)
        
        await query.answer(f"✅ تم شراء {UPGRADES[upgrade_id]['name']}!", show_alert=True)
        
        # العودة للمتجر
        await shop(update, context)
    else:
        await query.answer("❌ حدث خطأ في الشراء!", show_alert=True)

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض المتصدرين"""
    query = update.callback_query
    await query.answer()
    
    leaders = db.get_leaderboard(10)
    
    if not leaders:
        await query.edit_message_text(
            "🏆 **لوحة المتصدرين**\n\nلا يوجد لاعبون بعد!",
            parse_mode="Markdown"
        )
        return
    
    leaderboard_text = "🏆 **أعلى 10 لاعبين:**\n\n"
    
    for idx, leader in enumerate(leaders, 1):
        medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
        name = leader['first_name'] or f"Player_{leader['user_id']}"
        leaderboard_text += f"{medal} **{name}**\n"
        leaderboard_text += f"   💰 {format_number(leader['total_earned'])} | المستوى {leader['level']}\n\n"
    
    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="back")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        leaderboard_text,
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def daily_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """المكافأة اليومية"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    player = db.get_or_create_player(user.id)
    
    can_claim, remaining = db.can_claim_daily(user.id)
    
    if not can_claim:
        await query.answer(
            f"⏳ يمكنك المطالبة بعد: {remaining}",
            show_alert=True
        )
        return
    
    # حساب المكافأة
    bonus = int(ECONOMY["daily_bonus_base"] * (ECONOMY["daily_bonus_multiplier"] ** (player['level'] - 1)))
    
    # منح المكافأة
    new_balance = db.claim_daily_bonus(user.id, bonus)
    
    keyboard = [
        [InlineKeyboardButton("🎮 العب الآن", callback_data="play")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"""
🎁 **مكافأة يومية!**

✅ حصلت على: **+{format_number(bonus)}** قهوة!
💰 **رصيدك الجديد:** {format_number(new_balance)}

عد بعد 24 ساعة للحصول على المزيد! 🕐
        """,
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """العودة للقائمة الرئيسية"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    player = db.get_or_create_player(user.id)
    
    keyboard = [
        [InlineKeyboardButton("🎮 العب الآن", callback_data="play")],
        [InlineKeyboardButton("🛒 المتجر", callback_data="shop")],
        [InlineKeyboardButton("🏆 المتصدرون", callback_data="leaderboard")],
        [InlineKeyboardButton("🎁 المكافأة اليومية", callback_data="daily")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"""
☕ **مزرعة القهوة**

💰 **رصيدك:** {format_number(player['coins'])}
⚡ **إنتاجك:** {format_number(player['cps'])}/ثانية
👆 **قوة النقرة:** {format_number(player['click_power'])}

ماذا تريد أن تفعل؟
        """,
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

# ========== دالة الإنتاج التلقائي ==========

async def passive_income_job(context: ContextTypes.DEFAULT_TYPE):
    """وظيفة الإنتاج التلقائي (تعمل كل دقيقة)"""
    # هذه الوظيفة يمكن استخدامها لإضافة إنتاج تلقائي دوري
    # حالياً نعتمد على حساب الأرباح عند العودة
    pass

# ========== التشغيل الرئيسي ==========

def main():
    # إنشاء التطبيق
    application = Application.builder().token(BOT_TOKEN).build()
    
    # إضافة المعالجات
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(play, pattern="^play$"))
    application.add_handler(CallbackQueryHandler(click, pattern="^click$"))
    application.add_handler(CallbackQueryHandler(shop, pattern="^shop$"))
    application.add_handler(CallbackQueryHandler(buy_upgrade, pattern="^buy_"))
    application.add_handler(CallbackQueryHandler(leaderboard, pattern="^leaderboard$"))
    application.add_handler(CallbackQueryHandler(daily_bonus, pattern="^daily$"))
    application.add_handler(CallbackQueryHandler(back_to_main, pattern="^back$"))
    
    # تشغيل البوت
    logger.info("🤖 البوت يعمل الآن...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()