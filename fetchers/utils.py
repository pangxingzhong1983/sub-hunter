import re, requests

UA = {"User-Agent":"sub-hunter/1.0"}

def http_get(url, timeout=15):
    return requests.get(url, headers=UA, timeout=timeout)

def extract_links(text:str):
    # 抽取 http/https，并筛选订阅相关后缀/路径
    urls = re.findall(r"https?://[^\s)\"'>]+", text)
    keep = []
    for u in urls:
        lu = u.lower()
        if any(x in lu for x in [".yaml",".yml",".txt","/sub","=sub"]):
            keep.append(u.strip())
    return keep
