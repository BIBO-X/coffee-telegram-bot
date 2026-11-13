import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from contextlib import contextmanager

DATABASE_URL = os.getenv("DATABASE_URL")

class Database:
    def __init__(self):
        self.database_url = DATABASE_URL
        self.init_tables()
    
    @contextmanager
    def get_connection(self):
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
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
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
                    experience INTEGER DEFAULT 0,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_daily_bonus TIMESTAMP DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS player_upgrades (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT REFERENCES players(user_id) ON DELETE CASCADE,
                    upgrade_id VARCHAR(50),
                    quantity INTEGER DEFAULT 0,
                    UNIQUE(user_id, upgrade_id)
                )
            """)
            
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
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_quests (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT REFERENCES players(user_id) ON DELETE CASCADE,
                    quest_date DATE DEFAULT CURRENT_DATE,
                    clicks INTEGER DEFAULT 0,
                    earned DECIMAL(20, 2) DEFAULT 0,
                    completed BOOLEAN DEFAULT FALSE,
                    claimed BOOLEAN DEFAULT FALSE,
                    UNIQUE(user_id, quest_date)
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS friends (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT REFERENCES players(user_id) ON DELETE CASCADE,
                    friend_id BIGINT REFERENCES players(user_id) ON DELETE CASCADE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, friend_id)
                )
            """)
            
            cursor.close()
    
    # ========== دوال اللاعبين ==========
    
    def get_or_create_player(self, user_id: int, username: str = None, first_name: str = None):
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("SELECT * FROM players WHERE user_id = %s", (user_id,))
            player = cursor.fetchone()
            
            if not player:
                cursor.execute("""
                    INSERT INTO players (user_id, username, first_name, coins, click_power, cps)
                    VALUES (%s, %s, %s, 0, 1, 0)
                    RETURNING *
                """, (user_id, username, first_name))
                player = cursor.fetchone()
                conn.commit()
            
            cursor.close()
            return dict(player)
    
    def get_player(self, user_id: int):
        """جلب بيانات اللاعب فقط"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("SELECT * FROM players WHERE user_id = %s", (user_id,))
            player = cursor.fetchone()
            cursor.close()
            return dict(player) if player else None
    
    def add_coins(self, user_id: int, amount: float, transaction_type: str = "earn"):
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("SELECT coins, total_earned FROM players WHERE user_id = %s", (user_id,))
            result = cursor.fetchone()
            
            if not result:
                cursor.close()
                return None
            
            new_balance = float(result['coins']) + amount
            new_total = float(result['total_earned']) + amount
            
            cursor.execute("""
                UPDATE players 
                SET coins = %s, total_earned = %s, last_active = CURRENT_TIMESTAMP
                WHERE user_id = %s
                RETURNING coins
            """, (new_balance, new_total, user_id))
            
            updated = cursor.fetchone()
            
            cursor.execute("""
                INSERT INTO transactions (user_id, transaction_type, amount, balance_after)
                VALUES (%s, %s, %s, %s)
            """, (user_id, transaction_type, amount, new_balance))
            
            conn.commit()
            cursor.close()
            return float(updated['coins'])
    
    def spend_coins(self, user_id: int, amount: float, transaction_type: str = "spend") -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("SELECT coins FROM players WHERE user_id = %s", (user_id,))
            result = cursor.fetchone()
            
            if not result or float(result['coins']) < amount:
                cursor.close()
                return False
            
            new_balance = float(result['coins']) - amount
            
            cursor.execute("""
                UPDATE players 
                SET coins = %s, last_active = CURRENT_TIMESTAMP
                WHERE user_id = %s
                RETURNING coins
            """, (new_balance, user_id))
            
            updated = cursor.fetchone()
            
            cursor.execute("""
                INSERT INTO transactions (user_id, transaction_type, amount, balance_after)
                VALUES (%s, %s, %s, %s)
            """, (user_id, transaction_type, -amount, new_balance))
            
            conn.commit()
            cursor.close()
            return True
    
    def update_player_stats(self, user_id: int, click_power: float = None, cps: float = None, level: int = None, experience: int = None):
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
            
            if experience is not None:
                updates.append("experience = %s")
                params.append(experience)
            
            if updates:
                updates.append("last_active = CURRENT_TIMESTAMP")
                params.append(user_id)
                
                query = f"UPDATE players SET {', '.join(updates)} WHERE user_id = %s"
                cursor.execute(query, params)
            
            cursor.close()
    
    # ========== دوال الترقيات ==========
    
    def get_player_upgrades(self, user_id: int) -> dict:
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("SELECT upgrade_id, quantity FROM player_upgrades WHERE user_id = %s", (user_id,))
            upgrades = {row['upgrade_id']: row['quantity'] for row in cursor.fetchall()}
            cursor.close()
            return upgrades
    
    def add_upgrade(self, user_id: int, upgrade_id: str):
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
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("SELECT last_daily_bonus FROM players WHERE user_id = %s", (user_id,))
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
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
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
            
            cursor.execute("""
                INSERT INTO transactions (user_id, transaction_type, amount, balance_after)
                VALUES (%s, %s, %s, %s)
            """, (user_id, "daily_bonus", bonus_amount, new_balance))
            
            conn.commit()
            cursor.close()
            return new_balance
    
    # ========== دوال الإنتاج التلقائي ==========
    
    def calculate_offline_earnings(self, user_id: int) -> float:
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("SELECT cps, last_active FROM players WHERE user_id = %s", (user_id,))
            result = cursor.fetchone()
            cursor.close()
            
            if not result or float(result['cps']) == 0:
                return 0
            
            last_active = result['last_active']
            now = datetime.now()
            hours_away = (now - last_active).total_seconds() / 3600
            hours_away = min(hours_away, 8)
            
            return float(result['cps']) * hours_away * 3600
    
    # ========== دوال المتصدرين ==========
    
    def get_leaderboard(self, limit: int = 10) -> list:
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
    
    # ========== دوال المستويات ==========
    
    def add_experience(self, user_id: int, exp_amount: int):
        """إضافة نقاط خبرة ورفع المستوى"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("SELECT experience, level FROM players WHERE user_id = %s", (user_id,))
            result = cursor.fetchone()
            
            if not result:
                cursor.close()
                return None
            
            new_exp = result['experience'] + exp_amount
            current_level = result['level']
            
            # حساب المستوى الجديد (كل مستوى يحتاج level * 100 نقطة)
            exp_needed = current_level * 100
            leveled_up = False
            
            while new_exp >= exp_needed:
                new_exp -= exp_needed
                current_level += 1
                exp_needed = current_level * 100
                leveled_up = True
            
            cursor.execute("""
                UPDATE players 
                SET experience = %s, level = %s
                WHERE user_id = %s
            """, (new_exp, current_level, user_id))
            
            conn.commit()
            cursor.close()
            
            return {
                'leveled_up': leveled_up,
                'new_level': current_level,
                'current_exp': new_exp,
                'exp_needed': exp_needed
            }
    
    # ========== دوال المهمات اليومية ==========
    
    def get_daily_quest(self, user_id: int):
        """جلب مهمة اليوم"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # التحقق من وجود مهمة اليوم
            cursor.execute("""
                SELECT * FROM daily_quests 
                WHERE user_id = %s AND quest_date = CURRENT_DATE
            """, (user_id,))
            
            quest = cursor.fetchone()
            
            if not quest:
                # إنشاء مهمة جديدة لليوم
                cursor.execute("""
                    INSERT INTO daily_quests (user_id, quest_date)
                    VALUES (%s, CURRENT_DATE)
                    RETURNING *
                """, (user_id,))
                quest = cursor.fetchone()
                conn.commit()
            
            cursor.close()
            return dict(quest)
    
    def update_quest_progress(self, user_id: int, clicks: int = 0, earned: float = 0):
        """تحديث تقدم المهمة"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("""
                UPDATE daily_quests 
                SET clicks = clicks + %s, earned = earned + %s
                WHERE user_id = %s AND quest_date = CURRENT_DATE
                RETURNING clicks, earned
            """, (clicks, earned, user_id))
            
            result = cursor.fetchone()
            
            # التحقق من إكمال المهمة (100 نقرة أو 1000 عملة)
            if result and (result['clicks'] >= 100 or result['earned'] >= 1000):
                cursor.execute("""
                    UPDATE daily_quests 
                    SET completed = TRUE
                    WHERE user_id = %s AND quest_date = CURRENT_DATE
                """, (user_id,))
            
            conn.commit()
            cursor.close()
            return dict(result) if result else None
    
    def claim_quest_reward(self, user_id: int):
        """المطالبة بمكافأة المهمة"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("""
                SELECT completed, claimed FROM daily_quests 
                WHERE user_id = %s AND quest_date = CURRENT_DATE
            """, (user_id,))
            
            quest = cursor.fetchone()
            
            if not quest or not quest['completed'] or quest['claimed']:
                cursor.close()
                return None
            
            # منح المكافأة
            reward = 500
            cursor.execute("""
                UPDATE daily_quests 
                SET claimed = TRUE
                WHERE user_id = %s AND quest_date = CURRENT_DATE
            """, (user_id,))
            
            conn.commit()
            cursor.close()
            
            new_balance = self.add_coins(user_id, reward, "quest_reward")
            return {'reward': reward, 'new_balance': new_balance}
    
    # ========== دوال الأصدقاء ==========
    
    def add_friend(self, user_id: int, friend_id: int):
        """إضافة صديق"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO friends (user_id, friend_id)
                    VALUES (%s, %s)
                """, (user_id, friend_id))
                conn.commit()
                return True
            except psycopg2.IntegrityError:
                return False
            finally:
                cursor.close()
    
    def get_friends(self, user_id: int):
        """جلب قائمة الأصدقاء"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                SELECT p.user_id, p.first_name, p.level, p.total_earned
                FROM friends f
                JOIN players p ON f.friend_id = p.user_id
                WHERE f.user_id = %s
                ORDER BY p.total_earned DESC
            """, (user_id,))
            friends = [dict(row) for row in cursor.fetchall()]
            cursor.close()
            return friends

db = Database()