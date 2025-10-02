#!/usr/bin/env python3
"""
测试智能 GitHub 地址转换功能
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main_extract_fast import _detect_github_info_from_url, _convert_github_pages_to_raw, canonicalize_url

def test_smart_github_conversion():
    """测试智能 GitHub 地址转换"""
    
    test_cases = [
        # 您提到的具体例子
        "https://thebestvpn.github.io/uploads/2025/09/2-20250929.txt",
        "https://cdn.jsdelivr.net/gh/xiaoji235/airport-free/v2ray/naidounode.txt", 
        "https://node.clashnode.cc/uploads/2025/10/0-20251002.txt",
        
        # 其他可能的 GitHub Pages 代理形式
        "https://vpn-client.github.io/files/config.yaml",
        "https://free-nodes.example.com/uploads/2025/09/nodes.txt",
        "https://sub-hub.net/2025/10/subscription.yaml",
        "https://clash-proxy.site/raw/config.yml",
        
        # 标准地址（应该保持不变）
        "https://raw.githubusercontent.com/barry-far/V2ray-config/main/Sub4.txt",
        "https://example.com/normal/path/file.txt"
    ]
    
    print("🔥 测试智能 GitHub 地址转换功能:")
    print("=" * 100)
    
    for original_url in test_cases:
        print(f"原始地址: {original_url}")
        
        # 检测 GitHub 信息
        username, repo, branch, path = _detect_github_info_from_url(original_url)
        if username:
            print(f"  检测到: user={username}, repo={repo}, branch={branch}, path={path}")
        else:
            print("  未检测到 GitHub 信息")
        
        # 转换测试
        converted_url = canonicalize_url(original_url)
        
        if original_url != converted_url:
            print(f"✅ 转换成功: {converted_url}")
        else:
            print("ℹ️  无需转换")
        print("-" * 100)

if __name__ == "__main__":
    test_smart_github_conversion()