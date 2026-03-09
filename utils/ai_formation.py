import json
import os
import re
from urllib import error, request

# 允许将 key 直接写死在代码中（不推荐提交到远端仓库）
HARDCODED_AI_PROVIDER = "deepseek"  # deepseek 或 siliconflow
HARDCODED_DEEPSEEK_API_KEY = "sk-4ece11ea64d949bb8a8cef0b5c59c0c6"
HARDCODED_DEEPSEEK_MODEL = "deepseek-chat"
HARDCODED_SILICONFLOW_API_KEY = "sk-fuvbyfglpmdnvkijpykyfvncbexddysbtrarkggokxwfbucr"
HARDCODED_SILICONFLOW_MODEL = "Qwen/Qwen2.5-72B-Instruct"


def _ai_debug_enabled():
    return (os.getenv("AI_DEBUG_LOG", "1").strip().lower() in {"1", "true", "yes", "on"})


def _debug_print(tag, payload):
    if not _ai_debug_enabled():
        return
    print(f"[AI_DEBUG] {tag}")
    try:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    except Exception:
        print(str(payload))


# 仅保留阵型位置信息（坐标由前端处理）
FORMATION_SLOTS = {
    "232": ["GK", "LB", "RB", "CM1", "CM2", "CM3", "ST1", "ST2"],
    "322": ["GK", "CB1", "CB2", "CB3", "CM1", "CM2", "ST1", "ST2"],
    "331": ["GK", "CB1", "CB2", "CB3", "CM1", "CM2", "CM3", "ST"],
}


SLOT_MEANING = {
    "GK": "门将",
    "LB": "左后卫",
    "CB1": "中卫",
    "CB2": "中卫",
    "CB3": "中卫",
    "RB": "右后卫",
    "LM": "左中场/左前卫",
    "CM": "中场",
    "CM1": "中场",
    "CM2": "中场",
    "CM3": "中场",
    "RM": "右中场/右前卫",
    "LW": "左边锋",
    "RW": "右边锋",
    "ST": "中锋",
    "CF1": "前锋",
    "CF2": "前锋",
    "ST1": "前锋",
    "ST2": "前锋",
    "CDM1": "后腰",
    "CDM2": "后腰",
    "CAM": "前腰",
    "LWB": "左翼卫",
    "RWB": "右翼卫",
}


def _extract_json(text):
    """尽可能从模型输出中提取 JSON。"""
    text = (text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _build_prompt(formation, players):
    slots = FORMATION_SLOTS[formation]
    slot_desc = [{"slot_key": s, "role": SLOT_MEANING.get(s, s)} for s in slots]
    payload = []
    for p in players:
        payload.append({
            "id": p["id"],
            "name": p["name"],
            "number": p["number"],
            "position": p.get("position") or "",
            "characteristic": p.get("characteristic") or "",
            "scores": {
                "pass": (p.get("scores") or {}).get("pass"),
                "dribble": (p.get("scores") or {}).get("dribble"),
                "speed": (p.get("scores") or {}).get("speed"),
                "shooting": (p.get("scores") or {}).get("shooting"),
            },
        })

    # 给模型一个可验证的统计，减少“唯一/最强”这类无依据描述
    goalkeeper_candidates = [
        {"id": p["id"], "name": p["name"]}
        for p in payload
        if "门将" in p.get("position", "")
    ]

    system_prompt = (
        "你是校园足球教练助理。你要根据球员位置和技术特点，输出最合理的首发排阵。"
        "必须严格输出 JSON，且只输出 JSON，不要写任何解释。"
    )
    user_prompt = {
        "task": f"根据给定阵型把球员分配到 {len(slots)} 个位置（八人制）",
        "formation": formation,
        "slots": slot_desc,
        "players": payload,
        "validation_hints": {
            "goalkeeper_candidates": goalkeeper_candidates,
            "goalkeeper_candidates_count": len(goalkeeper_candidates)
        },
        "output_schema": {
            "formation": formation,
            "assignments": [
                {
                    "slot_key": "GK",
                    "player_id": 1
                }
            ]
        },
        "rules": [
            "必须覆盖所有 slot_key，且每个 slot_key 仅出现一次",
            "同一球员不能重复分配到多个位置",
            "player_id 必须来自 players 列表",
            "阵型必须是八人制，共 8 个位置",
            "GK 位置必须分配给 position 中包含“门将”的球员",
            "如果有多个门将候选，任选其一即可，不要额外说明",
            "必须优先参考 scores（pass/dribble/speed/shooting）进行位置分配",
            "若某球员分数字段缺失，可回退参考 position 和 characteristic"
        ]
    }
    return system_prompt, json.dumps(user_prompt, ensure_ascii=False)


def _resolve_ai_provider():
    """
    统一解析 AI 配置，默认走 DeepSeek。
    支持:
    - AI_PROVIDER=deepseek|siliconflow
    - DEEPSEEK_API_KEY / DEEPSEEK_MODEL
    - SILICONFLOW_API_KEY / SILICONFLOW_MODEL
    """
    provider = (
        os.getenv("AI_PROVIDER")
        or HARDCODED_AI_PROVIDER
        or "deepseek"
    ).strip().lower()
    if provider == "deepseek":
        api_key = (HARDCODED_DEEPSEEK_API_KEY or os.getenv("DEEPSEEK_API_KEY", "")).strip()
        if not api_key:
            raise ValueError("未配置 DEEPSEEK_API_KEY")
        return {
            "provider": "deepseek",
            "url": "https://api.deepseek.com/v1/chat/completions",
            "api_key": api_key,
            "model": (HARDCODED_DEEPSEEK_MODEL or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")).strip(),
        }

    if provider == "siliconflow":
        api_key = (HARDCODED_SILICONFLOW_API_KEY or os.getenv("SILICONFLOW_API_KEY", "")).strip()
        if not api_key:
            raise ValueError("未配置 SILICONFLOW_API_KEY")
        return {
            "provider": "siliconflow",
            "url": "https://api.siliconflow.cn/v1/chat/completions",
            "api_key": api_key,
            "model": (HARDCODED_SILICONFLOW_MODEL or os.getenv("SILICONFLOW_MODEL", "Qwen/Qwen2.5-72B-Instruct")).strip(),
        }

    raise ValueError("AI_PROVIDER 仅支持 deepseek 或 siliconflow")


def is_ai_key_configured():
    provider = (
        os.getenv("AI_PROVIDER")
        or HARDCODED_AI_PROVIDER
        or "deepseek"
    ).strip().lower()
    if provider == "deepseek":
        return bool((HARDCODED_DEEPSEEK_API_KEY or os.getenv("DEEPSEEK_API_KEY", "")).strip())
    if provider == "siliconflow":
        return bool((HARDCODED_SILICONFLOW_API_KEY or os.getenv("SILICONFLOW_API_KEY", "")).strip())
    return False


def recommend_formation_with_ai(players, formation):
    """
    调用 AI 生成阵型推荐。
    返回: {"formation": str, "assignments": [{"slot_key","player_id"}]}
    """
    if formation not in FORMATION_SLOTS:
        raise ValueError("不支持的阵型")
    if len(players) < 8:
        raise ValueError("球员数量不足 8 人，无法排阵")

    provider_cfg = _resolve_ai_provider()

    system_prompt, user_prompt = _build_prompt(formation, players)
    req_body = {
        "model": provider_cfg["model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 1200,
    }

    # 调试打印：确认给模型的原始输入，便于排查“门将识别”问题
    goalkeepers = [
        {
            "id": p.get("id"),
            "name": p.get("name"),
            "position": p.get("position", ""),
            "characteristic": p.get("characteristic", ""),
        }
        for p in players
        if "门将" in str(p.get("position", ""))
    ]
    scored_players_count = sum(
        1 for p in players
        if any((p.get("scores") or {}).get(k) is not None for k in ("pass", "dribble", "speed", "shooting"))
    )
    _debug_print("request_meta", {
        "provider": provider_cfg.get("provider"),
        "model": provider_cfg.get("model"),
        "formation": formation,
        "players_count": len(players),
        "scored_players_count": scored_players_count,
        "goalkeeper_candidates_count": len(goalkeepers),
        "goalkeeper_candidates": goalkeepers,
    })
    _debug_print("request_body", req_body)

    req = request.Request(
        provider_cfg["url"],
        data=json.dumps(req_body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {provider_cfg['api_key']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise ValueError(f"AI 接口请求失败: {exc.code} {detail}") from exc
    except error.URLError as exc:
        raise ValueError(f"AI 接口连接失败: {exc.reason}") from exc

    data = json.loads(raw)
    _debug_print("raw_response", data)
    content = (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )
    parsed = _extract_json(content)
    _debug_print("parsed_response", parsed if parsed is not None else {"parsed": None, "content": content})
    if not parsed:
        raise ValueError("AI 返回格式无法解析为 JSON")

    slots = set(FORMATION_SLOTS[formation])
    valid_ids = {p["id"] for p in players}
    assignments = parsed.get("assignments", [])
    if not isinstance(assignments, list):
        raise ValueError("AI 返回 assignments 格式错误")

    normalized = []
    used_slots = set()
    used_players = set()
    for a in assignments:
        if not isinstance(a, dict):
            continue
        slot_key = str(a.get("slot_key", "")).strip()
        player_id = a.get("player_id")
        if slot_key not in slots or slot_key in used_slots:
            continue
        if not isinstance(player_id, int) or player_id not in valid_ids or player_id in used_players:
            continue
        normalized.append({
            "slot_key": slot_key,
            "player_id": player_id,
        })
        used_slots.add(slot_key)
        used_players.add(player_id)

    gk_assignment = next((x for x in normalized if x["slot_key"] == "GK"), None)
    if not gk_assignment:
        raise ValueError("AI 返回结果缺少门将位置")
    gk_player = next((p for p in players if p["id"] == gk_assignment["player_id"]), None)
    if not gk_player or "门将" not in str(gk_player.get("position", "")):
        raise ValueError("AI 返回的门将人选不符合位置要求")

    if len(normalized) != len(slots):
        raise ValueError("AI 返回结果不完整，请重试")

    return {"formation": formation, "assignments": normalized}


def generate_opponent_advice_with_ai(players, formation, opponent_info, current_assignments=None):
    """
    根据对手信息生成八人制赛前建议。
    返回:
    {
      "formation": "232",
      "opponent_summary": "...",
      "key_threats": ["...", "..."],
      "lineup_advice": ["...", "..."],
      "tactical_plan": ["...", "..."]
    }
    """
    if formation not in FORMATION_SLOTS:
        raise ValueError("不支持的阵型")
    if len(players) < 8:
        raise ValueError("球员数量不足 8 人，无法生成建议")
    if not str(opponent_info or "").strip():
        raise ValueError("请先输入对手信息")

    provider_cfg = _resolve_ai_provider()
    slots = FORMATION_SLOTS[formation]

    player_payload = []
    for p in players:
        player_payload.append({
            "id": p["id"],
            "name": p["name"],
            "number": p["number"],
            "position": p.get("position") or "",
            "characteristic": p.get("characteristic") or "",
            "scores": {
                "pass": (p.get("scores") or {}).get("pass"),
                "dribble": (p.get("scores") or {}).get("dribble"),
                "speed": (p.get("scores") or {}).get("speed"),
                "shooting": (p.get("scores") or {}).get("shooting"),
            },
        })

    assignment_payload = []
    for item in (current_assignments or []):
        if not isinstance(item, dict):
            continue
        slot_key = str(item.get("slot_key", "")).strip()
        player_id = item.get("player_id")
        if slot_key and isinstance(player_id, int):
            assignment_payload.append({"slot_key": slot_key, "player_id": player_id})

    system_prompt = (
        "你是校园足球教练助理。请基于八人制比赛场景，结合我方球员位置与能力分数，"
        "根据对手信息输出阵容与战术建议。必须只输出 JSON。"
    )
    user_prompt = {
        "task": "根据对手信息输出八人制赛前建议",
        "formation": formation,
        "slots": slots,
        "opponent_info": str(opponent_info).strip(),
        "players": player_payload,
        "current_assignments": assignment_payload,
        "output_schema": {
            "formation": formation,
            "opponent_summary": "一句话概括对手特点",
            "key_threats": ["威胁点1", "威胁点2", "威胁点3"],
            "lineup_advice": ["人员/位置调整建议1", "建议2", "建议3"],
            "tactical_plan": ["战术执行建议1", "建议2", "建议3"]
        },
        "rules": [
            "只能基于输入数据给建议，不得编造未提供的球员信息",
            "优先参考 scores，再结合 position 与 characteristic",
            "建议要具体可执行，每条不超过30字",
            "输出字段必须完整，若信息不足可给保守建议"
        ]
    }

    req_body = {
        "model": provider_cfg["model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)},
        ],
        "temperature": 0.3,
        "max_tokens": 1400,
    }

    _debug_print("opponent_advice_request_body", req_body)

    req = request.Request(
        provider_cfg["url"],
        data=json.dumps(req_body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {provider_cfg['api_key']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=40) as resp:
            raw = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise ValueError(f"AI 接口请求失败: {exc.code} {detail}") from exc
    except error.URLError as exc:
        raise ValueError(f"AI 接口连接失败: {exc.reason}") from exc

    data = json.loads(raw)
    _debug_print("opponent_advice_raw_response", data)
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    parsed = _extract_json(content)
    _debug_print("opponent_advice_parsed_response", parsed if parsed is not None else {"parsed": None, "content": content})

    if not isinstance(parsed, dict):
        raise ValueError("AI 返回格式无法解析为 JSON")

    result = {
        "formation": str(parsed.get("formation") or formation),
        "opponent_summary": str(parsed.get("opponent_summary") or "").strip(),
        "key_threats": parsed.get("key_threats") if isinstance(parsed.get("key_threats"), list) else [],
        "lineup_advice": parsed.get("lineup_advice") if isinstance(parsed.get("lineup_advice"), list) else [],
        "tactical_plan": parsed.get("tactical_plan") if isinstance(parsed.get("tactical_plan"), list) else [],
    }
    # 保底清洗，避免 UI 空白
    result["key_threats"] = [str(x).strip()[:40] for x in result["key_threats"] if str(x).strip()][:5]
    result["lineup_advice"] = [str(x).strip()[:40] for x in result["lineup_advice"] if str(x).strip()][:5]
    result["tactical_plan"] = [str(x).strip()[:40] for x in result["tactical_plan"] if str(x).strip()][:5]
    if not result["opponent_summary"]:
        result["opponent_summary"] = "对手信息已读取，建议以稳守反击为主。"
    if not result["lineup_advice"]:
        result["lineup_advice"] = ["门将固定，后场优先防守稳定型球员。"]
    if not result["tactical_plan"]:
        result["tactical_plan"] = ["开场10分钟先稳住中后场，观察对手强侧。"]
    return result
