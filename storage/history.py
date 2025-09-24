import json, os, time

HIST_FILE = "storage/history.json"

def load_history():
    if not os.path.exists(HIST_FILE):
        return {"seen": [], "last_total": 0, "ts": int(time.time())}
    with open(HIST_FILE,"r",encoding="utf-8") as f:
        return json.load(f)

def save_history(data):
    os.makedirs("storage", exist_ok=True)
    with open(HIST_FILE,"w",encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def update_all(history, items):
    """
    items: list[str] 经过连通性检测后仍可用的订阅URL
    直接按给定顺序去重保存，旧链接若未通过检测会被移除。
    """
    merged = []
    seen = set()
    for url in items:
        if url and url not in seen:
            merged.append(url)
            seen.add(url)

    history["seen"] = merged
    history["last_total"] = len(merged)
    history["ts"] = int(time.time())
    return merged
