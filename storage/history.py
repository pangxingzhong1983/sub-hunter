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
    items: list[str] 全部新检测通过的可用订阅URL
    """
    history["seen"] = sorted(set(items))
    history["last_total"] = len(history["seen"])
    history["ts"] = int(time.time())
    return history["seen"]
