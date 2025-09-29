import json, os, time

HIST_FILE = "storage/history.json"

def load_history(path: str = None):
    """读取历史文件，path 为空时使用模块默认 HIST_FILE。
    返回 dict，确保含有 keys: seen(或 links), last_total, ts, fail, reserve
    """
    p = path or HIST_FILE
    if not os.path.exists(p):
        # 兼容旧结构：提供基础字段
        return {"seen": [], "links": [], "last_total": 0, "ts": int(time.time()), "fail": {}, "reserve": []}
    with open(p, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except Exception:
            # 损坏的历史文件以安全默认替代
            return {"seen": [], "links": [], "last_total": 0, "ts": int(time.time()), "fail": {}, "reserve": []}
    # 兼容处理：保证字段存在
    if "seen" not in data and "links" in data:
        data["seen"] = data.get("links", [])
    data.setdefault("seen", [])
    data.setdefault("links", data.get("seen", []))
    data.setdefault("last_total", len(data.get("seen", [])))
    data.setdefault("ts", int(time.time()))
    data.setdefault("fail", {})
    data.setdefault("reserve", [])
    return data


def save_history(data: dict, path: str = None):
    p = path or HIST_FILE
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def update_all(history: dict, items: list[str], path: str = None):
    """直接将 items 去重后写入 history（覆盖旧的 seen/links）。兼容 legacy 用法。
    保持与原来接口一致：update_all(history, items)
    """
    merged = []
    seen = set()
    for url in items:
        if url and url not in seen:
            merged.append(url)
            seen.add(url)

    history["seen"] = merged
    history["links"] = merged
    history["last_total"] = len(merged)
    history["ts"] = int(time.time())
    if path:
        save_history(history, path)
    else:
        save_history(history)
    return merged


def ensure_increment(valid: list, hist_path: str, daily_increment: int, fail_threshold: int) -> list:
    """按每日增量/失败阈值更新历史并返回最终保留列表。

    算法（保守、安全）：
    - 读取 hist_path（若不存在则初始化空历史结构）
    - 对历史列表中的每个已有 url：
        - 若在本次 valid 中出现：保留，并清除失败计数
        - 否则失败计数 +1；若失败计数 >= fail_threshold 则移入 reserve（删除），否则仍保留
    - 将本次 valid 中未包含在最终保留中的新 url 作为候选，按 daily_increment 限额追加到最终列表
    - 更新并写回 hist_path
    """
    # 读取目标历史
    hist = load_history(hist_path)
    # 兼容字段
    current_links = hist.get("links") or hist.get("seen") or []
    fail_map = hist.get("fail", {})
    reserve = hist.get("reserve", [])

    # 规范化 valid
    valid_set = []
    seen_set = set()
    for u in valid:
        if u and u not in seen_set:
            valid_set.append(u)
            seen_set.add(u)

    # 1) 处理已有条目
    final = []
    for url in current_links:
        if url in seen_set:
            # 仍然可用，保留并重置失败计数
            final.append(url)
            if url in fail_map:
                del fail_map[url]
        else:
            # 本次检测未命中，失败计数+1
            fail_map[url] = int(fail_map.get(url, 0)) + 1
            if fail_map[url] < fail_threshold:
                final.append(url)
            else:
                # 淘汰并放到 reserve
                if url not in reserve:
                    reserve.append(url)

    # 2) 新增的有效链接按 daily_increment 限额追加
    to_add = []
    if int(daily_increment) <= 0:
        # 不限制每日增量，直接把所有新的有效链接追加
        for u in valid_set:
            if u not in final:
                to_add.append(u)
    else:
        for u in valid_set:
            if u not in final and len(to_add) < int(daily_increment):
                to_add.append(u)
    final.extend(to_add)

    # 3) 更新历史结构并写回
    hist["seen"] = final
    hist["links"] = final
    hist["last_total"] = len(final)
    hist["fail"] = fail_map
    hist["reserve"] = reserve
    hist["ts"] = int(time.time())

    save_history(hist, hist_path)
    return final
