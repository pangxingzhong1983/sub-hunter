#!/usr/bin/env python3
"""
清理脚本：从历史数据中移除无效的订阅链接
主要清理：
1. 论坛链接、教程页面
2. 无效 token 的订阅链接
3. GitHub 非订阅页面
"""

import json
import os
import sys
from urllib.parse import urlparse, parse_qs
import re

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main_extract_fast import _is_valid_token, _validate_subscription_url_params

def is_valid_subscription_url(url: str) -> bool:
    """检查 URL 是否为有效的订阅链接"""
    
    # 黑名单模式
    BLACKLIST_PATTERNS = [
        "forums/topic/", "forum.php", "/thread-", "/viewtopic.php", 
        "/showthread.php", "/discussion/", "sockscap64.com/forums",
        "github.com/releases", "/issues/", "/pull/", "/wiki/", "/docs/",
        "youtube.com", "youtu.be", "bilibili.com", "telegram.me", "t.me/",
        "/download/", "/archive/", "/blob/", "/commit/", "/compare/",
        "blackmatrix7/ios_rule_script", "domain-filter/", "easylist",
        "easyprivacy", "easylistchina", "adrules", "adguard",
        "clashx-pro/distribution_groups", "sub-web.netlify.app",
        "loyalsoldier/clash-rules", "help.wwkejishe.top/free-shadowrocket"
    ]
    
    url_lower = url.lower()
    
    # 检查黑名单模式
    for pattern in BLACKLIST_PATTERNS:
        if pattern in url_lower:
            print(f"[黑名单剔除] {url}")
            return False
    
    # 检查 URL 参数（token/key 验证）
    if not _validate_subscription_url_params(url):
        print(f"[无效参数剔除] {url}")
        return False
    
    # 白名单后缀（yaml/yml/txt）
    path = urlparse(url).path.lower()
    if path.endswith(('.yaml', '.yml', '.txt')):
        return True
    
    # 包含订阅关键词
    subscription_keywords = [
        'subscribe', 'subscription', 'sub', 'clash', 'v2ray', 'ss', 
        'vless', 'vmess', 'trojan', 'hysteria', 'tuic', 'nodes', 
        'proxies', 'proxy'
    ]
    
    if any(keyword in url_lower for keyword in subscription_keywords):
        return True
    
    print(f"[无关键词剔除] {url}")
    return False

def clean_history_file(filepath: str):
    """清理历史文件中的无效链接"""
    
    if not os.path.exists(filepath):
        print(f"历史文件不存在: {filepath}")
        return
    
    print(f"正在清理历史文件: {filepath}")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 备份原始数据
    backup_path = filepath + '.backup'
    with open(backup_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"已备份原始数据到: {backup_path}")
    
    original_seen_count = len(data.get('seen', []))
    original_links_count = len(data.get('links', []))
    
    # 清理 seen 列表
    if 'seen' in data:
        valid_seen = [url for url in data['seen'] if is_valid_subscription_url(url)]
        data['seen'] = valid_seen
        print(f"seen: {original_seen_count} -> {len(valid_seen)} (-{original_seen_count - len(valid_seen)})")
    
    # 清理 links 列表
    if 'links' in data:
        valid_links = [url for url in data['links'] if is_valid_subscription_url(url)]
        data['links'] = valid_links
        print(f"links: {original_links_count} -> {len(valid_links)} (-{original_links_count - len(valid_links)})")
    
    # 清理 resource_keys
    if 'resource_keys' in data:
        original_keys_count = len(data['resource_keys'])
        valid_keys = {url: meta for url, meta in data['resource_keys'].items() 
                     if is_valid_subscription_url(url)}
        data['resource_keys'] = valid_keys
        print(f"resource_keys: {original_keys_count} -> {len(valid_keys)} (-{original_keys_count - len(valid_keys)})")
    
    # 清理 fail 记录
    if 'fail' in data:
        original_fail_count = len(data['fail'])
        valid_fail = {url: count for url, count in data['fail'].items() 
                     if is_valid_subscription_url(url)}
        data['fail'] = valid_fail
        print(f"fail: {original_fail_count} -> {len(valid_fail)} (-{original_fail_count - len(valid_fail)})")
    
    # 保存清理后的数据
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 历史文件清理完成: {filepath}")

def main():
    """主函数"""
    
    # 获取项目根目录
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    history_path = os.path.join(project_root, 'data', 'history.json')
    
    print("🔥 开始清理无效订阅链接...")
    
    # 清理历史文件
    clean_history_file(history_path)
    
    print("\n✅ 清理完成！")
    print("💡 建议运行 main_extract_fast.py 重新生成输出文件")

if __name__ == "__main__":
    main()