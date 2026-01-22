from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
from utils.score_calculator import calculate_scores
from functools import wraps

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
    players = conn.execute('SELECT * FROM players').fetchall()
    conn.close()
    return render_template('player_intro.html', players=players)


@app.route('/analysis')
def analysis():
    file_path = '测试数据 12.2.xlsx'
    scores, error = calculate_scores(file_path)
    
    if error:
        return f"Error processing data: {error}"
    
    # 转换为前端友好的格式
    indicators = [
        {"name": "传球", "max": 100},
        {"name": "盘带", "max": 100},
        {"name": "速度", "max": 100},
        {"name": "射门", "max": 100}
    ]
    
    chart_data = []
    for name, s in scores.items():
        chart_data.append({
            "value": [s.get('pass', 0), s.get('dribble', 0), s.get('speed', 0), s.get('shooting', 0)],
            "name": name
        })
        
    return render_template('analysis.html', indicators=indicators, chart_data=chart_data)

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
