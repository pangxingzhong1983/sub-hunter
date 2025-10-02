#!/usr/bin/env python3
"""
更新历史数据中的 GitHub Pages 地址为 raw.githubusercontent.com 格式
"""

import json
import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main_extract_fast import _convert_github_pages_to_raw, canonicalize_url

def update_history_urls(filepath: str):
    """更新历史文件中的 GitHub Pages 地址"""
    
    if not os.path.exists(filepath):
        print(f"历史文件不存在: {filepath}")
        return
    
    print(f"正在更新历史文件: {filepath}")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 备份原始数据
    backup_path = filepath + '.url_update_backup'
    with open(backup_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"已备份原始数据到: {backup_path}")
    
    conversion_count = 0
    
    # 更新 seen 列表
    if 'seen' in data:
        updated_seen = []
        for url in data['seen']:
            converted_url = canonicalize_url(url)
            if converted_url != url:
                conversion_count += 1
                print(f"[seen转换] {url} -> {converted_url}")
            updated_seen.append(converted_url)
        data['seen'] = updated_seen
    
    # 更新 links 列表
    if 'links' in data:
        updated_links = []
        for url in data['links']:
            converted_url = canonicalize_url(url)
            if converted_url != url:
                conversion_count += 1
                print(f"[links转换] {url} -> {converted_url}")
            updated_links.append(converted_url)
        data['links'] = updated_links
    
    # 更新 resource_keys（这个需要重新构建键）
    if 'resource_keys' in data:
        updated_resource_keys = {}
        for url, meta in data['resource_keys'].items():
            converted_url = canonicalize_url(url)
            if converted_url != url:
                conversion_count += 1
                print(f"[resource_keys转换] {url} -> {converted_url}")
            updated_resource_keys[converted_url] = meta
        data['resource_keys'] = updated_resource_keys
    
    # 更新 fail 记录
    if 'fail' in data:
        updated_fail = {}
        for url, count in data['fail'].items():
            converted_url = canonicalize_url(url)
            if converted_url != url:
                conversion_count += 1
                print(f"[fail转换] {url} -> {converted_url}")
            updated_fail[converted_url] = count
        data['fail'] = updated_fail
    
    # 保存更新后的数据
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ URL 更新完成，共转换了 {conversion_count} 个地址")

def main():
    """主函数"""
    
    # 获取项目根目录
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    history_path = os.path.join(project_root, 'data', 'history.json')
    
    print("🔥 开始更新 GitHub Pages 地址...")
    
    # 更新历史文件
    update_history_urls(history_path)
    
    print("\n✅ 更新完成！")

if __name__ == "__main__":
    main()