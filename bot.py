import logging
import os
import asyncio
import threading
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from database import db

BOT_TOKEN = os.getenv("BOT_TOKEN")

# رابط اللعبة المصغرة - عدّل هذا بعد رفع اللعبة
GAME_URL = os.getenv("GAME_URL", "https://bibo-x.github.io/coffee-farm-game/")

# رابط الـ API على Railway
API_URL = os.getenv("RAILWAY_STATIC_URL", "https://your-app.up.railway.app")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== دوال مساعدة ==========

def format_number(n):
    if n >= 1e9:
        return f"{n/1e9:.1f}B"
    elif n >= 1e6:
        return f"{n/1e6:.1f}M"
    elif n >= 1e3:
        return f"{n/1e3:.1f}K"
    return f"{int(n)}"

# ========== معالجات الأوامر ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر البداية مع زر اللعبة المصغرة"""
    user = update.effective_user
    
    # إنشاء أو جلب اللاعب
    player = db.get_or_create_player(user.id, user.username, user.first_name)
    
    # حساب الأرباح الغير متصلة
    offline_earnings = db.calculate_offline_earnings(user.id)
    if offline_earnings > 0:
        db.add_coins(user.id, offline_earnings, "offline_earnings")
        player = db.get_player(user.id)
    
    keyboard = [
        [InlineKeyboardButton("🎮 العب الآن", web_app=WebAppInfo(url=GAME_URL))],
        [InlineKeyboardButton("🛒 المتجر", callback_data="shop")],
        [InlineKeyboardButton("🏆 المتصدرون", callback_data="leaderboard")],
        [InlineKeyboardButton("🎁 المكافأة اليومية", callback_data="daily")],
        [InlineKeyboardButton("📋 المهمة اليومية", callback_data="quest")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = f"""
☕ **أهلاً بك في مزرعة القهوة يا {user.first_name}!**

💰 **رصيدك:** {format_number(player['coins'])}
⚡ **إنتاجك:** {format_number(player['cps'])}/ثانية
👆 **قوة النقرة:** {format_number(player['click_power'])}
📊 **المستوى:** {player['level']}

🎯 **هدفك:** ابنِ إمبراطورية القهوة الخاصة بك!

{"💤 **أرباح أثناء غيابك:** +" + format_number(offline_earnings) if offline_earnings > 0 else ""}

اضغط الزر بالأسفل لبدء اللعب! 👇
    """
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض المتجر"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    player = db.get_player(user.id)
    
    keyboard = [
        [InlineKeyboardButton("🎮 افتح اللعبة للشراء", web_app=WebAppInfo(url=GAME_URL))],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"""
🛒 **متجر الترقيات**

💰 **رصيدك:** {format_number(player['coins'])}

افتح اللعبة المصغرة لشراء الترقيات!
        """,
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

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
    player = db.get_player(user.id)
    
    can_claim, remaining = db.can_claim_daily(user.id)
    
    if not can_claim:
        await query.answer(
            f"⏳ يمكنك المطالبة بعد: {remaining}",
            show_alert=True
        )
        return
    
    # حساب المكافأة
    bonus = int(50 * (1.5 ** (player['level'] - 1)))
    
    # منح المكافأة
    new_balance = db.claim_daily_bonus(user.id, bonus)
    
    keyboard = [
        [InlineKeyboardButton("🎮 العب الآن", web_app=WebAppInfo(url=GAME_URL))],
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

async def daily_quest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """المهمة اليومية"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    quest = db.get_daily_quest(user.id)
    
    status = "✅ مكتملة!" if quest['completed'] else "⏳ قيد التقدم"
    if quest['claimed']:
        status = "🎁 تم المطالبة بالمكافأة"
    
    keyboard = []
    if quest['completed'] and not quest['claimed']:
        keyboard.append([InlineKeyboardButton("🎁 المطالبة بالمكافأة", callback_data="claim_quest")])
    
    keyboard.append([InlineKeyboardButton("🎮 العب الآن", web_app=WebAppInfo(url=GAME_URL))])
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="back")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"""
📋 **المهمة اليومية**

{status}

🎯 **التقدم:**
• النقرات: {quest['clicks']}/100
• القهوة المكتسبة: {format_number(quest['earned'])}/1000

🎁 **المكافأة:** 500 قهوة
        """,
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def claim_quest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """المطالبة بمكافأة المهمة"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    result = db.claim_quest_reward(user.id)
    
    if not result:
        await query.answer("❌ لم تكمل المهمة بعد!", show_alert=True)
        return
    
    keyboard = [
        [InlineKeyboardButton("🎮 العب الآن", web_app=WebAppInfo(url=GAME_URL))],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"""
🎉 **مبروك!**

✅ حصلت على مكافأة المهمة: **+{format_number(result['reward'])}** قهوة!
💰 **رصيدك الجديد:** {format_number(result['new_balance'])}

عد غداً لمزيد من المهمات! 📋
        """,
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """العودة للقائمة الرئيسية"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    player = db.get_player(user.id)
    
    keyboard = [
        [InlineKeyboardButton("🎮 العب الآن", web_app=WebAppInfo(url=GAME_URL))],
        [InlineKeyboardButton("🛒 المتجر", callback_data="shop")],
        [InlineKeyboardButton("🏆 المتصدرون", callback_data="leaderboard")],
        [InlineKeyboardButton("🎁 المكافأة اليومية", callback_data="daily")],
        [InlineKeyboardButton("📋 المهمة اليومية", callback_data="quest")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"""
☕ **مزرعة القهوة**

💰 **رصيدك:** {format_number(player['coins'])}
⚡ **إنتاجك:** {format_number(player['cps'])}/ثانية
👆 **قوة النقرة:** {format_number(player['click_power'])}
📊 **المستوى:** {player['level']}

ماذا تريد أن تفعل؟
        """,
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

# ========== تشغيل API في خيط منفصل ==========

def run_api():
    """تشغيل Flask API في خيط منفصل"""
    from api import app
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, use_reloader=False)

# ========== التشغيل الرئيسي ==========

def main():
    # تشغيل API في الخلفية
    api_thread = threading.Thread(target=run_api, daemon=True)
    api_thread.start()
    
    logger.info("🌐 API يعمل في الخلفية...")
    
    # إنشاء تطبيق تيليجرام
    application = Application.builder().token(BOT_TOKEN).build()
    
    # إضافة المعالجات
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(shop, pattern="^shop$"))
    application.add_handler(CallbackQueryHandler(leaderboard, pattern="^leaderboard$"))
    application.add_handler(CallbackQueryHandler(daily_bonus, pattern="^daily$"))
    application.add_handler(CallbackQueryHandler(daily_quest, pattern="^quest$"))
    application.add_handler(CallbackQueryHandler(claim_quest, pattern="^claim_quest$"))
    application.add_handler(CallbackQueryHandler(back_to_main, pattern="^back$"))
    
    # تشغيل البوت
    logger.info("🤖 البوت يعمل الآن...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()