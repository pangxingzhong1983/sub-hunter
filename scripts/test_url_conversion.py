#!/usr/bin/env python3
"""
测试 GitHub Pages 地址转换功能
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main_extract_fast import _convert_github_pages_to_raw, canonicalize_url

def test_github_pages_conversion():
    """测试 GitHub Pages 地址转换"""
    
    test_cases = [
        "https://vpn-client.github.io/uploads/2025/09/1-20250930.txt",
        "https://free-v2raynode.github.io/uploads/2025/09/2-20250929.txt",
        "https://tuijianjiedian.github.io/uploads/2025/09/3-20250930.txt",
        "https://freev2raynodes.github.io/uploads/2025/09/2-20250929.txt",
        # 非 GitHub Pages 地址（应该保持不变）
        "https://raw.githubusercontent.com/barry-far/V2ray-config/main/Sub4.txt",
        "https://example.com/path/to/file.txt"
    ]
    
    print("🔥 测试 GitHub Pages 地址转换功能:")
    print("=" * 80)
    
    for original_url in test_cases:
        converted_url = _convert_github_pages_to_raw(original_url)
        canonicalized_url = canonicalize_url(original_url)
        
        print(f"原始地址: {original_url}")
        print(f"转换结果: {converted_url}")
        print(f"标准化后: {canonicalized_url}")
        
        if original_url != converted_url:
            print("✅ 转换成功")
        else:
            print("ℹ️  无需转换")
        print("-" * 80)

if __name__ == "__main__":
    test_github_pages_conversion()