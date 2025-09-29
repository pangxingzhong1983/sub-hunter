import json
import os
import time

HIST_FILE = "storage/history.json"

# Control automatic history backups. Default: disabled to avoid unexpected .bak files.
# To enable backups set environment variable ENABLE_HISTORY_BACKUP=true
ENABLE_HISTORY_BACKUP = os.environ.get("ENABLE_HISTORY_BACKUP", "false").lower() in (
    "1",
    "true",
    "yes",
)


def load_history(path: str = None):
    """读取历史文件，path 为空时使用模块默认 HIST_FILE。
    返回 dict，确保含有 keys: seen(或 links), last_total, ts, fail, reserve
    """
    p = path or HIST_FILE
    if not os.path.exists(p):
        # 兼容旧结构：提供基础字段
        return {
            "seen": [],
            "links": [],
            "last_total": 0,
            "ts": int(time.time()),
            "fail": {},
            "reserve": [],
            # 新增：resource_keys 用于记录每个 URL 的资源键（owner/repo/base 等），方便长期去重
            "resource_keys": {},
        }
    with open(p, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except Exception:
            # 损坏的历史文件以安全默认替代
            return {
                "seen": [],
                "links": [],
                "last_total": 0,
                "ts": int(time.time()),
                "fail": {},
                "reserve": [],
                "resource_keys": {},
            }
    # 兼容处理：保证字段存在
    if "seen" not in data and "links" in data:
        data["seen"] = data.get("links", [])
    data.setdefault("seen", [])
    data.setdefault("links", data.get("seen", []))
    data.setdefault("last_total", len(data.get("seen", [])))
    data.setdefault("ts", int(time.time()))
    data.setdefault("fail", {})
    data.setdefault("reserve", [])
    # 确保 resource_keys 字段存在并为 dict
    data.setdefault("resource_keys", {})
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


def ensure_increment(
    valid: list,
    hist_path: str,
    daily_increment: int,
    fail_threshold: int,
    resource_map: dict = None,
) -> list:
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
    resource_keys = hist.get("resource_keys", {})

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

    # 更新 resource_keys 映射（若提供 resource_map）
    if resource_map is None:
        resource_map = {}
    for u in final:
        if u in resource_map:
            resource_keys[u] = resource_map[u]
        else:
            # 保持原有映射（若存在），否则不新增空映射
            resource_keys.setdefault(u, resource_keys.get(u))

    # === 按发布者做永久性历史压缩（基于 lastmod 时间优先） ===
    # PER_OWNER_HISTORY_LIMIT: 每个 owner 在历史中保留的最大条数
    per_owner_limit = int(
        os.environ.get(
            "PER_OWNER_HISTORY_LIMIT", os.environ.get("PER_OWNER_LIMIT", "5")
        )
    )
    if per_owner_limit > 0:
        # 构建 owner -> [ (url, lastmod_ts) ] 映射
        owner_map = {}
        for u in list(final):
            meta = resource_keys.get(u) or {}
            owner_key = (
                meta.get("owner_key")
                or (resource_map.get(u) or {}).get("owner_key")
                or u
            )
            # lastmod 支持多个来源：resource_keys cache 优先，其次 resource_map
            lastmod = None
            try:
                lastmod = meta.get("lastmod")
            except Exception:
                lastmod = None
            if not lastmod and u in resource_map:
                try:
                    lastmod = resource_map[u].get("lastmod")
                except Exception:
                    lastmod = None
            try:
                lastmod_val = int(lastmod) if lastmod else 0
            except Exception:
                lastmod_val = 0
            owner_map.setdefault(owner_key, []).append((u, lastmod_val))

        # 对每个 owner 保留 per_owner_limit 条最新的，其余移入 reserve
        to_remove = set()
        for owner, items in owner_map.items():
            if len(items) <= per_owner_limit:
                continue
            # 根据 lastmod 降序排序，若相同按 url 保持稳定顺序
            items_sorted = sorted(items, key=lambda x: (-x[1], x[0]))
            keep = set(u for u, _ in items_sorted[:per_owner_limit])
            for u, _ in items_sorted[per_owner_limit:]:
                to_remove.add(u)
        if to_remove:
            # 移到 reserve 并从 final 中删除
            for u in to_remove:
                if u in final:
                    final.remove(u)
                    reserve.append(u)
            # 更新统计
            # Note: we do not decrement last_total here because last_total reflects final length
            # but we update last_total below when writing.
            # 将 resource_keys 中被移除的项保留（以便后续复原或审计）
            print(
                f"[历史压缩] 根据 lastmod 每发布者保留 {per_owner_limit} 条，移除 {len(to_remove)} 条至 reserve"
            )

    # 3) 更新历史结构并写回
    hist["seen"] = final
    hist["links"] = final
    hist["last_total"] = len(final)
    hist["fail"] = fail_map
    hist["reserve"] = reserve
    hist["resource_keys"] = resource_keys
    hist["ts"] = int(time.time())

    # backup existing history before overwrite
    try:
        if ENABLE_HISTORY_BACKUP:
            if os.path.exists(hist_path):
                bak_path = f"{hist_path}.bak.{int(time.time())}"
                import shutil

                shutil.copy2(hist_path, bak_path)
                print(f"[历史备份] 已备份原 history 到: {bak_path}")
        else:
            # backups disabled by configuration to avoid cluttering the data directory
            pass
    except Exception as e:
        print(f"[历史备份失败] {e}")
    save_history(hist, hist_path)
    # export reserve list for audit
    try:
        if hist.get("reserve"):
            reserve_path = os.path.join(
                os.path.dirname(hist_path) or ".", f"reserve-{int(time.time())}.json"
            )
            with open(reserve_path, "w", encoding="utf-8") as rf:
                json.dump(hist.get("reserve", []), rf, ensure_ascii=False, indent=2)
            print(f"[历史保留导出] 已导出 reserve 到: {reserve_path}")
    except Exception as e:
        print(f"[导出 reserve 失败] {e}")
    return final
