import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from contextlib import contextmanager

# إعدادات الاتصال بقاعدة البيانات
DATABASE_URL = os.getenv("DATABASE_URL")

class Database:
    def __init__(self):
        self.database_url = DATABASE_URL
        self.init_tables()
    
    @contextmanager
    def get_connection(self):
        """إدارة الاتصال بقاعدة البيانات"""
        conn = psycopg2.connect(self.database_url)
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def init_tables(self):
        """إنشاء الجداول المطلوبة"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # جدول اللاعبين الرئيسي
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS players (
                    user_id BIGINT PRIMARY KEY,
                    username VARCHAR(255),
                    first_name VARCHAR(255),
                    coins DECIMAL(20, 2) DEFAULT 0,
                    total_earned DECIMAL(20, 2) DEFAULT 0,
                    click_power DECIMAL(10, 2) DEFAULT 1,
                    cps DECIMAL(10, 2) DEFAULT 0,
                    level INTEGER DEFAULT 1,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_daily_bonus TIMESTAMP DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # جدول الترقيات المملوكة
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS player_upgrades (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT REFERENCES players(user_id) ON DELETE CASCADE,
                    upgrade_id VARCHAR(50),
                    quantity INTEGER DEFAULT 0,
                    UNIQUE(user_id, upgrade_id)
                )
            """)
            
            # جدول سجل المعاملات (للأمان والتتبع)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT REFERENCES players(user_id) ON DELETE CASCADE,
                    transaction_type VARCHAR(50),
                    amount DECIMAL(20, 2),
                    balance_after DECIMAL(20, 2),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.close()
    
    # ========== دوال اللاعبين ==========
    
    def get_or_create_player(self, user_id: int, username: str = None, first_name: str = None):
        """جلب بيانات اللاعب أو إنشاؤه إذا لم يكن موجوداً"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # محاولة جلب اللاعب
            cursor.execute(
                "SELECT * FROM players WHERE user_id = %s",
                (user_id,)
            )
            player = cursor.fetchone()
            
            if not player:
                # إنشاء لاعب جديد
                cursor.execute("""
                    INSERT INTO players (user_id, username, first_name, coins, click_power, cps)
                    VALUES (%s, %s, %s, 0, 1, 0)
                    RETURNING *
                """, (user_id, username, first_name))
                player = cursor.fetchone()
                conn.commit()
            
            cursor.close()
            return dict(player)
    
    def update_player_coins(self, user_id: int, new_coins: float, total_earned: float = None):
        """تحديث رصيد اللاعب"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            if total_earned is not None:
                cursor.execute("""
                    UPDATE players 
                    SET coins = %s, total_earned = %s, last_active = CURRENT_TIMESTAMP
                    WHERE user_id = %s
                """, (new_coins, total_earned, user_id))
            else:
                cursor.execute("""
                    UPDATE players 
                    SET coins = %s, last_active = CURRENT_TIMESTAMP
                    WHERE user_id = %s
                """, (new_coins, user_id))
            
            cursor.close()
    
    def add_coins(self, user_id: int, amount: float, transaction_type: str = "earn"):
        """إضافة عملات للاعب مع تسجيل المعاملة"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # جلب الرصيد الحالي
            cursor.execute(
                "SELECT coins, total_earned FROM players WHERE user_id = %s",
                (user_id,)
            )
            result = cursor.fetchone()
            
            if not result:
                cursor.close()
                return None
            
            new_balance = float(result['coins']) + amount
            new_total = float(result['total_earned']) + amount
            
            # تحديث الرصيد
            cursor.execute("""
                UPDATE players 
                SET coins = %s, total_earned = %s, last_active = CURRENT_TIMESTAMP
                WHERE user_id = %s
                RETURNING coins
            """, (new_balance, new_total, user_id))
            
            updated = cursor.fetchone()
            
            # تسجيل المعاملة
            cursor.execute("""
                INSERT INTO transactions (user_id, transaction_type, amount, balance_after)
                VALUES (%s, %s, %s, %s)
            """, (user_id, transaction_type, amount, new_balance))
            
            conn.commit()
            cursor.close()
            return float(updated['coins'])
    
    def spend_coins(self, user_id: int, amount: float, transaction_type: str = "spend") -> bool:
        """خصم عملات من اللاعب (للشراء)"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # التحقق من الرصيد
            cursor.execute(
                "SELECT coins FROM players WHERE user_id = %s",
                (user_id,)
            )
            result = cursor.fetchone()
            
            if not result or float(result['coins']) < amount:
                cursor.close()
                return False
            
            new_balance = float(result['coins']) - amount
            
            # خصم المبلغ
            cursor.execute("""
                UPDATE players 
                SET coins = %s, last_active = CURRENT_TIMESTAMP
                WHERE user_id = %s
                RETURNING coins
            """, (new_balance, user_id))
            
            updated = cursor.fetchone()
            
            # تسجيل المعاملة
            cursor.execute("""
                INSERT INTO transactions (user_id, transaction_type, amount, balance_after)
                VALUES (%s, %s, %s, %s)
            """, (user_id, transaction_type, -amount, new_balance))
            
            conn.commit()
            cursor.close()
            return True
    
    def update_player_stats(self, user_id: int, click_power: float = None, cps: float = None, level: int = None):
        """تحديث إحصائيات اللاعب"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            updates = []
            params = []
            
            if click_power is not None:
                updates.append("click_power = %s")
                params.append(click_power)
            
            if cps is not None:
                updates.append("cps = %s")
                params.append(cps)
            
            if level is not None:
                updates.append("level = %s")
                params.append(level)
            
            if updates:
                updates.append("last_active = CURRENT_TIMESTAMP")
                params.append(user_id)
                
                query = f"UPDATE players SET {', '.join(updates)} WHERE user_id = %s"
                cursor.execute(query, params)
            
            cursor.close()
    
    # ========== دوال الترقيات ==========
    
    def get_player_upgrades(self, user_id: int) -> dict:
        """جلب جميع ترقيات اللاعب"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                "SELECT upgrade_id, quantity FROM player_upgrades WHERE user_id = %s",
                (user_id,)
            )
            upgrades = {row['upgrade_id']: row['quantity'] for row in cursor.fetchall()}
            cursor.close()
            return upgrades
    
    def add_upgrade(self, user_id: int, upgrade_id: str):
        """إضافة ترقية للاعب"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO player_upgrades (user_id, upgrade_id, quantity)
                VALUES (%s, %s, 1)
                ON CONFLICT (user_id, upgrade_id)
                DO UPDATE SET quantity = player_upgrades.quantity + 1
            """, (user_id, upgrade_id))
            cursor.close()
    
    # ========== دوال المكافأة اليومية ==========
    
    def can_claim_daily(self, user_id: int) -> tuple:
        """التحقق من إمكانية المطالبة بالمكافأة اليومية"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                "SELECT last_daily_bonus FROM players WHERE user_id = %s",
                (user_id,)
            )
            result = cursor.fetchone()
            cursor.close()
            
            if not result or result['last_daily_bonus'] is None:
                return True, 0
            
            last_claim = result['last_daily_bonus']
            now = datetime.now()
            time_diff = now - last_claim
            
            if time_diff >= timedelta(hours=24):
                return True, 0
            else:
                remaining = timedelta(hours=24) - time_diff
                hours = remaining.seconds // 3600
                minutes = (remaining.seconds % 3600) // 60
                return False, f"{hours}h {minutes}m"
    
    def claim_daily_bonus(self, user_id: int, bonus_amount: float):
        """منح المكافأة اليومية"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # تحديث وقت المطالبة
            cursor.execute("""
                UPDATE players 
                SET last_daily_bonus = CURRENT_TIMESTAMP
                WHERE user_id = %s
                RETURNING coins, total_earned
            """, (user_id,))
            
            result = cursor.fetchone()
            new_balance = float(result['coins']) + bonus_amount
            new_total = float(result['total_earned']) + bonus_amount
            
            cursor.execute("""
                UPDATE players 
                SET coins = %s, total_earned = %s
                WHERE user_id = %s
            """, (new_balance, new_total, user_id))
            
            # تسجيل المعاملة
            cursor.execute("""
                INSERT INTO transactions (user_id, transaction_type, amount, balance_after)
                VALUES (%s, %s, %s, %s)
            """, (user_id, "daily_bonus", bonus_amount, new_balance))
            
            conn.commit()
            cursor.close()
            return new_balance
    
    # ========== دوال الإنتاج التلقائي ==========
    
    def calculate_offline_earnings(self, user_id: int) -> float:
        """حساب الأرباح أثناء الغياب"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                SELECT cps, last_active 
                FROM players 
                WHERE user_id = %s
            """, (user_id,))
            
            result = cursor.fetchone()
            cursor.close()
            
            if not result or float(result['cps']) == 0:
                return 0
            
            last_active = result['last_active']
            now = datetime.now()
            hours_away = (now - last_active).total_seconds() / 3600
            
            # الحد الأقصى 8 ساعات من الأرباح الغير متصلة
            hours_away = min(hours_away, 8)
            
            earnings = float(result['cps']) * hours_away * 3600  # تحويل للثواني
            
            return earnings
    
    # ========== دوال المتصدرين ==========
    
    def get_leaderboard(self, limit: int = 10) -> list:
        """جلب قائمة المتصدرين"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                SELECT user_id, first_name, coins, total_earned, level
                FROM players
                ORDER BY total_earned DESC
                LIMIT %s
            """, (limit,))
            
            leaders = [dict(row) for row in cursor.fetchall()]
            cursor.close()
            return leaders

# إنشاء instance عام
db = Database()