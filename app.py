from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
import os
import json
import re
from dotenv import load_dotenv
from utils.score_calculator import calculate_scores
from utils.ai_formation import recommend_formation_with_ai, generate_opponent_advice_with_ai, is_ai_key_configured
from functools import wraps

load_dotenv(override=True)

PLAYER_POSITION_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'player_position.txt')
PLAYER_POSITION_JSON_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'player_position.json')
SCORE_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '测试数据 12.2.xlsx')


def load_player_positions_from_file():
    """
    解析位置文件，返回 ({ 名字: 位置 }, 来源文件名)。
    优先读取结构化 JSON（player_position.json），再兼容旧版 TXT。
    """
    # 1) 优先 JSON：更结构化、可扩展
    if os.path.exists(PLAYER_POSITION_JSON_FILE):
        result = {}
        with open(PLAYER_POSITION_JSON_FILE, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)

        if isinstance(data, dict):
            # 兼容 { "Adam": "门将" } 或 { "Adam": ["门将", "中场"] } 结构
            for name, pos in data.items():
                name = str(name).strip()
                if not name:
                    continue
                if isinstance(pos, list):
                    values = [str(x).strip() for x in pos if str(x).strip()]
                    if values:
                        result[name] = '/'.join(values)
                else:
                    p = str(pos).strip()
                    if p:
                        result[name] = p
        elif isinstance(data, list):
            # 兼容 [{ "name":"Adam", "positions":[...] }, { "name":"Arno", "position":"中后卫" }]
            for item in data:
                if not isinstance(item, dict):
                    continue
                name = str(item.get('name', '')).strip()
                if not name:
                    continue
                positions = item.get('positions')
                if isinstance(positions, list):
                    values = [str(x).strip() for x in positions if str(x).strip()]
                    if values:
                        result[name] = '/'.join(values)
                        continue
                position = str(item.get('position', '')).strip()
                if position:
                    result[name] = position
        return result, 'player_position.json'

    # 2) 兼容 TXT：支持英文/中文冒号，忽略空行和注释
    result = {}
    if not os.path.exists(PLAYER_POSITION_FILE):
        return result, 'none'
    with open(PLAYER_POSITION_FILE, 'r', encoding='utf-8-sig') as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith('#'):
                continue
            parts = re.split(r'[:：]', line, maxsplit=1)
            if len(parts) != 2:
                continue
            name = parts[0].strip()
            pos = parts[1].strip()
            if not name or not pos:
                continue
            result[name] = pos
    return result, 'player_position.txt'


def load_player_scores():
    """
    读取测试表并返回 {name: {pass, dribble, speed, shooting}}。
    分数文件异常时返回空字典，避免影响主流程。
    """
    scores, error = calculate_scores(SCORE_FILE_PATH)
    if error or not isinstance(scores, dict):
        return {}
    return scores


def load_players_for_ai():
    conn = get_db_connection()
    rows = conn.execute('SELECT id, name, number, characteristic, position FROM players ORDER BY number').fetchall()
    conn.close()
    players = [{'id': r['id'], 'name': r['name'], 'number': r['number'], 'characteristic': r['characteristic'] or '', 'position': r['position'] or ''} for r in rows]
    score_map = load_player_scores()
    for p in players:
        s = score_map.get(p['name'], {}) if isinstance(score_map, dict) else {}
        p['scores'] = {
            'pass': s.get('pass'),
            'dribble': s.get('dribble'),
            'speed': s.get('speed'),
            'shooting': s.get('shooting'),
        }
    return players

app = Flask(__name__)
app.secret_key = 'yungu-football-secret-key'  # 设置 Session 密钥

# 简单的登录装饰器
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# 数据库连接
def get_db_connection():
    conn = sqlite3.connect('football-schoolteam.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == 'yungu2026':  # 简单的硬编码密码
            session['logged_in'] = True
            return redirect(url_for('admin'))
        else:
            flash('密码错误，请重试', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('home'))

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/news')
def news():
    return render_template('news.html')

@app.route('/history')
def history():
    conn = get_db_connection()
    events = conn.execute('SELECT * FROM history ORDER BY year').fetchall()
    conn.close()
    return render_template('history.html', events=events)


@app.route('/results')
def results():
    conn = get_db_connection()
    results_data = conn.execute('SELECT * FROM results ORDER BY match_date DESC').fetchall()
    conn.close()
    return render_template('results.html', results=results_data)


@app.route('/player_intro')
def player_intro():
    conn = get_db_connection()
    players = [dict(p) for p in conn.execute('SELECT * FROM players').fetchall()]
    conn.close()
    return render_template('player_intro.html', players=players)


@app.route('/analysis')
def analysis():
    conn = get_db_connection()
    rows = conn.execute('SELECT name, characteristic, position FROM players').fetchall()
    db_players = {}
    for p in rows:
        d = dict(p)
        db_players[d.get('name', '')] = {
            'characteristic': d.get('characteristic') or '',
            'position': d.get('position') or ''
        }
    conn.close()

    scores, error = calculate_scores(SCORE_FILE_PATH)
    
    if error:
        return f"Error processing data: {error}"
    
    # 转换为前端友好的格式
    indicators = [
        {"name": "传球", "max": 100},
        {"name": "盘带", "max": 100},
        {"name": "速度", "max": 100},
        {"name": "射门", "max": 100},
        {"name": "体能", "max": 100}
    ]
    
    chart_data = []
    for name, s in scores.items():
        # 体能：基于现有数据推算 + 人工补充（55-92 区间）
        fitness = s.get('fitness')
        if fitness is None:
            base = (s.get('pass', 0) + s.get('dribble', 0) + s.get('speed', 0) + s.get('shooting', 0)) / 4
            fitness = round(min(92, max(55, base * 0.85 + (sum(ord(c) for c in name) % 25))))
        info = db_players.get(name, {})
        if isinstance(info, str):
            info = {'characteristic': info, 'position': ''}
        chart_data.append({
            "value": [s.get('pass', 0), s.get('dribble', 0), s.get('speed', 0), s.get('shooting', 0), fitness],
            "name": name,
            "characteristic": info.get('characteristic', ''),
            "position": info.get('position', '')
        })
        
    return render_template('analysis.html', indicators=indicators, chart_data=chart_data)


@app.route('/formation')
def formation():
    conn = get_db_connection()
    rows = conn.execute('SELECT id, name, number, characteristic, position FROM players ORDER BY number').fetchall()
    conn.close()
    players = [{'id': r['id'], 'name': r['name'], 'number': r['number'], 'characteristic': r['characteristic'] or '', 'position': r['position'] or ''} for r in rows]
    ai_enabled = is_ai_key_configured()
    return render_template('formation.html', players=players, ai_enabled=ai_enabled)


@app.route('/api/formation/recommend', methods=['POST'])
def ai_recommend_formation():
    body = request.get_json(silent=True) or {}
    formation_name = (body.get('formation') or '232').strip()

    players = load_players_for_ai()

    try:
        result = recommend_formation_with_ai(players=players, formation=formation_name)
        return jsonify({'ok': True, 'data': result})
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    except Exception:
        return jsonify({'ok': False, 'error': 'AI 排阵失败，请稍后重试'}), 500


@app.route('/api/formation/opponent_advice', methods=['POST'])
def ai_opponent_advice():
    body = request.get_json(silent=True) or {}
    formation_name = (body.get('formation') or '232').strip()
    opponent_info = (body.get('opponent_info') or '').strip()
    current_assignments = body.get('current_assignments') or []
    players = load_players_for_ai()

    try:
        result = generate_opponent_advice_with_ai(
            players=players,
            formation=formation_name,
            opponent_info=opponent_info,
            current_assignments=current_assignments,
        )
        return jsonify({'ok': True, 'data': result})
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    except Exception:
        return jsonify({'ok': False, 'error': 'AI 赛前建议生成失败，请稍后重试'}), 500


# ----------------- 后台管理 -----------------
@app.route('/admin', methods=['GET', 'POST'])
@login_required
def admin():
    conn = get_db_connection()

    # 判断是哪个表单提交
    if request.method == 'POST':
        form_type = request.form.get('form_type')

        if form_type == 'add_player':
            # 添加球员
            name = request.form['name']
            number = request.form['number']
            age = request.form['age']
            conn.execute(
                "INSERT INTO players (name, number, age) VALUES (?, ?, ?)",
                (name, number, age)
            )
        elif form_type == 'update_characteristic':
            player_id = request.form['player_id']
            characteristic = request.form.get('characteristic', '').strip()
            conn.execute(
                "UPDATE players SET characteristic = ? WHERE id = ?",
                (characteristic or None, player_id)
            )
        elif form_type == 'add_result':
            match_date = request.form['match_date']
            location = request.form['location']
            opponent = request.form['opponent']
            our_score = request.form['our_score']
            opponent_score = request.form['opponent_score']
            conn.execute(
                "INSERT INTO results (match_date, location, opponent, our_score, opponent_score) VALUES (?, ?, ?, ?, ?)",
                (match_date, location, opponent, our_score, opponent_score)
            )
        elif form_type == 'add_stats':
            player_id = request.form['player_id']
            match_date = request.form['match_date']
            stat_type = request.form['stat_type']
            value = request.form['value']

            conn.execute(
                "INSERT INTO stats (player_id, match_date, stat_type, value) VALUES (?, ?, ?, ?)",
                (player_id, match_date, stat_type, value)
            )
        elif form_type == 'add_skill':
            player_id = request.form['player_id']
            test_id = request.form['test_id']
            speed = request.form['speed']
            defense = request.form['defense']
            dribble = request.form['dribble']
            pass_short = request.form['pass_short']
            pass_long = request.form['pass_long']
            shooting = request.form['shooting']
            overall = 1

            conn.execute(
                """
                INSERT INTO skills_detail ( test_id, speed, defense, dribble, pass_short,pass_long, shooting,overall,player_id)
                VALUES (?, ?, ?, ?, ?, ?, ? , ?, ?)
                """,
                ( test_id, speed, defense, dribble, pass_short, pass_long,shooting,overall,player_id)
            )
        elif form_type == 'add_test':
            test_date = request.form['test_date']
            print(test_date)
            conn.execute(
                "INSERT INTO skills_test (test_date) VALUES (?)",
                (test_date,)
            )
        elif form_type == 'import_positions':
            positions, source = load_player_positions_from_file()
            for name, position in positions.items():
                conn.execute("UPDATE players SET position = ? WHERE name = ?", (position, name))
            if source == 'none':
                flash('未找到 player_position.json 或 player_position.txt', 'warning')
            else:
                flash(f'已从 {source} 导入 {len(positions)} 条位置信息', 'success')

        conn.commit()
        return redirect(url_for('admin'))
    
    results = conn.execute('SELECT * FROM results ORDER BY match_date DESC').fetchall()

    players_raw = conn.execute('SELECT * FROM players').fetchall()
    players = [dict(p) for p in players_raw]

    stats_raw = conn.execute('SELECT * FROM stats').fetchall()
    stats = [dict(s) for s in stats_raw]

    skills_raw = conn.execute('SELECT * FROM skills_test ORDER BY test_date DESC').fetchall()
    skills = [dict(s) for s in skills_raw]


    # 给每个球员初始化进球数
    for p in players:
        p['goals'] = 0
    # 遍历 stats，把进球加进去
    for s in stats:
        if s['stat_type'] == 'goal':  # 我们只统计进球
            for p in players:
                if p['id'] == s['player_id']:
                    p['goals'] += s['value']

    
    conn.close()
    return render_template(
    'admin.html',
    players=players,
    results=results,
    stats=stats,
    skills=skills
)


# 删除球员
@app.route('/delete_player/<int:player_id>')
@login_required
def delete_player(player_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM players WHERE id = ?', (player_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))

# 删除战绩
@app.route('/delete_result/<int:result_id>')
@login_required
def delete_result(result_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM results WHERE id = ?', (result_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5200, debug=True)




