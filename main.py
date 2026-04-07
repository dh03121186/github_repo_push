import requests
from bs4 import BeautifulSoup
import hmac
import hashlib
import base64
import time
import os
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ===================== 配置项 =====================
FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK")
FEISHU_SECRET = os.getenv("FEISHU_SECRET")
# FEISHU_WEBHOOK = "https://open.feishu.cn/open-apis/bot/v2/hook/cd3d9413-1398-4426-966b-79b233d466c7  "
# FEISHU_SECRET = "Pku9PTgNiLVawOp0ZWQgib"

# ==================================================

def create_session():
    """创建带重试机制的Session，修复SSL问题"""
    session = requests.Session()
    retry = Retry(connect=3, backoff_factor=0.5)
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    return session


def get_github_trending():
    """抓取 GitHub Trending 热门项目（已修复SSL）"""
    url = "https://github.com/trending"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    session = create_session()
    # 关键：关闭SSL证书验证 + 忽略警告
    requests.packages.urllib3.disable_warnings()
    resp = session.get(url, headers=headers, timeout=20, verify=False)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    repos = []
    articles = soup.select("article.Box-row")[:10]  # 取前10个

    for article in articles:
        # 项目名称
        name_tag = article.select_one("h2 a")
        name = name_tag.get_text(strip=True).replace("\n", "").replace(" ", "")

        # 描述
        desc_tag = article.select_one("p.col-9")
        desc = desc_tag.get_text(strip=True) if desc_tag else "无描述"

        # 语言
        lang_tag = article.select_one("span[itemprop='programmingLanguage']")
        lang = lang_tag.get_text(strip=True) if lang_tag else "未知"

        # 星标
        star_tag = article.select_one("a[href*='/stargazers']")
        stars = star_tag.get_text(strip=True) if star_tag else "0"

        # 今日星标
        today_star = article.select_one("span.d-inline-block.float-sm-right")
        today = today_star.get_text(strip=True) if today_star else "0"

        # 链接
        url = f"https://github.com/{name}"

        repos.append({
            "name": name,
            "desc": desc,
            "lang": lang,
            "stars": stars,
            "today": today,
            "url": url
        })

    return repos


def gen_feishu_sign(secret: str, timestamp: int) -> str:
    """生成飞书签名（安全校验）"""
    string = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        string.encode("utf-8"),
        digestmod=hashlib.sha256
    ).digest()
    return base64.b64encode(hmac_code).decode()


def send_to_feishu(repos):
    timestamp = int(time.time())
    sign = gen_feishu_sign(FEISHU_SECRET, timestamp)

    today = datetime.now().strftime("%Y-%m-%d")

    # 构建卡片内容
    elements = []

    # 标题模块
    elements.append({
        "tag": "div",
        "text": {
            "tag": "plain_text",
            "content": f"🔥 GitHub 每日热门项目 · {today}"
        }
    })

    # 分割线
    elements.append({"tag": "hr"})

    # 循环添加项目
    for idx, repo in enumerate(repos, 1):
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**{idx}. {repo['name']}**\n"
                           f"📝 {repo['desc']}\n"
                           f"🔧 语言：{repo['lang']}　⭐ 总星：{repo['stars']}　🌟 今日：{repo['today']}"
            }
        })
        # 跳转按钮
        elements.append({
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "text": {
                        "tag": "plain_text",
                        "content": "前往项目"
                    },
                    "url": repo['url'],
                    "type": "default"
                }
            ]
        })
        elements.append({"tag": "hr"})

    # 卡片结构
    card = {
        "config": {"wide_screen_mode": True},
        "elements": elements
    }

    payload = {
        "timestamp": timestamp,
        "sign": sign,
        "msg_type": "interactive",
        "card": card
    }

    r = requests.post(FEISHU_WEBHOOK, json=payload, timeout=10)
    return r.json()


if __name__ == "__main__":
    print("开始抓取 GitHub Trending...")
    repos = get_github_trending()
    print(f"抓取完成，共 {len(repos)} 个项目")

    print("推送至飞书...")
    result = send_to_feishu(repos)
    print("推送结果：", result)