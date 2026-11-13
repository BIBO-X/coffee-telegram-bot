from flask import Flask, request, jsonify
from flask_cors import CORS
from database import db
import os

app = Flask(__name__)
CORS(app)

# ========== API endpoints ==========

@app.route('/api/player/<int:user_id>', methods=['GET'])
def get_player(user_id):
    """جلب بيانات اللاعب"""
    player = db.get_or_create_player(user_id)
    upgrades = db.get_player_upgrades(user_id)
    
    # حساب الأرباح الغير متصلة
    offline_earnings = db.calculate_offline_earnings(user_id)
    if offline_earnings > 0:
        db.add_coins(user_id, offline_earnings, "offline_earnings")
        player = db.get_player(user_id)
    
    return jsonify({
        'success': True,
        'player': {
            'user_id': player['user_id'],
            'first_name': player['first_name'],
            'coins': float(player['coins']),
            'total_earned': float(player['total_earned']),
            'click_power': float(player['click_power']),
            'cps': float(player['cps']),
            'level': player['level'],
            'experience': player['experience'],
            'upgrades': upgrades
        },
        'offline_earnings': offline_earnings
    })

@app.route('/api/click', methods=['POST'])
def click():
    """معالجة النقرة"""
    data = request.json
    user_id = data.get('user_id')
    
    if not user_id:
        return jsonify({'success': False, 'error': 'Missing user_id'}), 400
    
    player = db.get_player(user_id)
    if not player:
        return jsonify({'success': False, 'error': 'Player not found'}), 404
    
    # إضافة العملات
    new_balance = db.add_coins(user_id, float(player['click_power']), "click")
    
    # تحديث المهمة اليومية
    db.update_quest_progress(user_id, clicks=1, earned=float(player['click_power']))
    
    # إضافة خبرة
    exp_result = db.add_experience(user_id, 1)
    
    return jsonify({
        'success': True,
        'new_balance': new_balance,
        'gained': float(player['click_power']),
        'level_info': exp_result
    })

@app.route('/api/buy_upgrade', methods=['POST'])
def buy_upgrade():
    """شراء ترقية"""
    data = request.json
    user_id = data.get('user_id')
    upgrade_id = data.get('upgrade_id')
    
    if not user_id or not upgrade_id:
        return jsonify({'success': False, 'error': 'Missing parameters'}), 400
    
    # تعريف الترقيات
    UPGRADES = {
        "click_1": {"name": "⚡ إصبع قوي", "base_cost": 20, "cost_multiplier": 1.5, "type": "click", "value": 1},
        "click_2": {"name": "💪 يد محترفة", "base_cost": 100, "cost_multiplier": 1.6, "type": "click", "value": 3},
        "auto_1": {"name": "🌱 بذرة قهوة", "base_cost": 50, "cost_multiplier": 1.4, "type": "auto", "value": 0.5},
        "auto_2": {"name": "🌿 شجرة صغيرة", "base_cost": 200, "cost_multiplier": 1.45, "type": "auto", "value": 2},
        "auto_3": {"name": "🌳 مزرعة صغيرة", "base_cost": 800, "cost_multiplier": 1.5, "type": "auto", "value": 5},
        "auto_4": {"name": "🏭 مصنع قهوة", "base_cost": 3000, "cost_multiplier": 1.55, "type": "auto", "value": 20},
        "auto_5": {"name": "🏢 إمبراطورية قهوة", "base_cost": 15000, "cost_multiplier": 1.6, "type": "auto", "value": 100},
    }
    
    if upgrade_id not in UPGRADES:
        return jsonify({'success': False, 'error': 'Invalid upgrade'}), 400
    
    player = db.get_player(user_id)
    upgrades = db.get_player_upgrades(user_id)
    
    owned = upgrades.get(upgrade_id, 0)
    cost = int(UPGRADES[upgrade_id]["base_cost"] * (UPGRADES[upgrade_id]["cost_multiplier"] ** owned))
    
    if float(player['coins']) < cost:
        return jsonify({'success': False, 'error': 'Insufficient funds', 'cost': cost}), 400
    
    # خصم وشراء
    if db.spend_coins(user_id, cost, "upgrade_purchase"):
        db.add_upgrade(user_id, upgrade_id)
        
        # تحديث الإحصائيات
        new_upgrades = db.get_player_upgrades(user_id)
        
        total_cps = sum(UPGRADES[u]["value"] * q for u, q in new_upgrades.items() if UPGRADES[u]["type"] == "auto")
        total_click = 1 + sum(UPGRADES[u]["value"] * q for u, q in new_upgrades.items() if UPGRADES[u]["type"] == "click")
        
        db.update_player_stats(user_id, click_power=total_click, cps=total_cps)
        
        return jsonify({
            'success': True,
            'new_balance': float(player['coins']) - cost,
            'upgrade': UPGRADES[upgrade_id]['name']
        })
    
    return jsonify({'success': False, 'error': 'Purchase failed'}), 500

@app.route('/api/daily_bonus/<int:user_id>', methods=['POST'])
def daily_bonus(user_id):
    """المكافأة اليومية"""
    can_claim, remaining = db.can_claim_daily(user_id)
    
    if not can_claim:
        return jsonify({'success': False, 'remaining': remaining}), 400
    
    player = db.get_player(user_id)
    bonus = int(50 * (1.5 ** (player['level'] - 1)))
    
    new_balance = db.claim_daily_bonus(user_id, bonus)
    
    return jsonify({
        'success': True,
        'bonus': bonus,
        'new_balance': new_balance
    })

@app.route('/api/quest/<int:user_id>', methods=['GET'])
def get_quest(user_id):
    """جلب المهمة اليومية"""
    quest = db.get_daily_quest(user_id)
    return jsonify({'success': True, 'quest': quest})

@app.route('/api/quest/claim/<int:user_id>', methods=['POST'])
def claim_quest(user_id):
    """المطالبة بمكافأة المهمة"""
    result = db.claim_quest_reward(user_id)
    
    if not result:
        return jsonify({'success': False, 'error': 'Quest not completed or already claimed'}), 400
    
    return jsonify({'success': True, **result})

@app.route('/api/leaderboard', methods=['GET'])
def leaderboard():
    """لوحة المتصدرين"""
    leaders = db.get_leaderboard(10)
    return jsonify({'success': True, 'leaders': leaders})

@app.route('/api/friends/<int:user_id>', methods=['GET'])
def get_friends(user_id):
    """جلب الأصدقاء"""
    friends = db.get_friends(user_id)
    return jsonify({'success': True, 'friends': friends})

@app.route('/api/friends/add', methods=['POST'])
def add_friend():
    """إضافة صديق"""
    data = request.json
    user_id = data.get('user_id')
    friend_id = data.get('friend_id')
    
    if not user_id or not friend_id:
        return jsonify({'success': False, 'error': 'Missing parameters'}), 400
    
    success = db.add_friend(user_id, friend_id)
    
    if success:
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': 'Already friends or invalid'}), 400

@app.route('/')
def index():
    return jsonify({'status': 'Coffee Farm API is running! ☕'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)