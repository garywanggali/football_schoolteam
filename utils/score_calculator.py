import pandas as pd
import numpy as np
import os

def calculate_scores(file_path):
    try:
        if not os.path.exists(file_path):
            return None, "文件不存在"
            
        # 兼容旧版 pandas/xlrd
        if file_path.endswith('.xlsx'):
            df = pd.read_excel(file_path, engine='openpyxl')
        else:
            df = pd.read_excel(file_path)
    except Exception as e:
        return None, str(e)

    results = {}
    
    # 清洗数据
    df = df.dropna(subset=['姓名'])
    
    # 1. 计算绕桩基准 (最快时间)
    # 将无法转换的值设为NaN
    valid_dribble = pd.to_numeric(df['绕桩/秒'], errors='coerce').dropna()
    min_dribble = valid_dribble.min() if not valid_dribble.empty else 0

    # 2. 计算速度基准
    valid_sprint = pd.to_numeric(df['半场冲刺/秒'], errors='coerce').dropna()
    min_sprint = valid_sprint.min() if not valid_sprint.empty else 0
    
    valid_curve = pd.to_numeric(df['曲线跑/秒'], errors='coerce').dropna()
    min_curve = valid_curve.min() if not valid_curve.empty else 0

    for index, row in df.iterrows():
        name = row['姓名']
        if pd.isna(name): continue
        
        scores = {}
        
        # --- 传球 ---
        # 10m传球: 假设10次满分 (100分)
        p10 = pd.to_numeric(row['10m传球'], errors='coerce')
        if np.isnan(p10): p10 = 0
        score_p10 = min(p10 * 10, 100) 
        
        # 30m吊准: 3次75分, 每少一次扣10分, 每多一次加10分
        p30 = pd.to_numeric(row['30m吊˙准'], errors='coerce')
        if np.isnan(p30): p30 = 0
        score_p30 = 75 + (p30 - 3) * 10
        score_p30 = max(0, min(100, score_p30))
        
        scores['pass'] = round(score_p10 * 0.6 + score_p30 * 0.4, 1)
        
        # --- 盘带 (绕桩) ---
        dribble_time = pd.to_numeric(row['绕桩/秒'], errors='coerce')
        if not np.isnan(dribble_time) and min_dribble > 0:
            diff = dribble_time - min_dribble
            deduction = (diff / 0.25) * 3
            scores['dribble'] = round(max(0, 90 - deduction), 1)
        else:
            scores['dribble'] = 0
            
        # --- 速度 ---
        sprint_time = pd.to_numeric(row['半场冲刺/秒'], errors='coerce')
        if not np.isnan(sprint_time) and min_sprint > 0:
            diff = sprint_time - min_sprint
            score_sprint = max(0, 90 - (diff / 0.25) * 3)
        else:
            score_sprint = 0
            
        curve_time = pd.to_numeric(row['曲线跑/秒'], errors='coerce')
        if not np.isnan(curve_time) and min_curve > 0:
            diff = curve_time - min_curve
            score_curve = max(0, 90 - (diff / 0.1) * 3.5)
        else:
            score_curve = 0
            
        if score_sprint > 0 and score_curve > 0:
            scores['speed'] = round((score_sprint + score_curve) / 2, 1)
        elif score_sprint > 0:
            scores['speed'] = round(score_sprint, 1)
        elif score_curve > 0:
            scores['speed'] = round(score_curve, 1)
        else:
            scores['speed'] = 0
            
        # --- 射门 ---
        # 移动射门
        move_shot_str = str(row['移动射门 5脚'])
        move_score = 0
        if '//' in move_shot_str:
            try:
                parts = move_shot_str.split('//')
                goals = int(parts[0])
                targets = int(parts[1])
                # 算法: 进球占70%, 射正占30% (满分100)
                move_score = (goals / 5) * 70 + (targets / 5) * 30
            except:
                pass
        
        # 定点射门
        static_shot_str = str(row['定点射门 5脚'])
        static_score = 0
        has_static = False
        if '//' in static_shot_str:
             try:
                parts = static_shot_str.split('//')
                goals = int(parts[0])
                targets = int(parts[1])
                static_score = (goals / 5) * 70 + (targets / 5) * 30
                has_static = True
             except:
                pass
        
        if has_static:
            scores['shooting'] = round((move_score + static_score) / 2, 1)
        else:
            scores['shooting'] = round(move_score, 1)

        results[name] = scores
        
    return results, None
