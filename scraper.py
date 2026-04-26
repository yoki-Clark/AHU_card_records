import requests
import csv
import time
import random
import os
import json
from datetime import datetime
from playwright.sync_api import sync_playwright

CONFIG_FILE = 'headers_config.json'
TARGET_PAGE_URL = "https://wvpn.ahu.edu.cn/"
TEST_URL = 'https://ycard.ahu.edu.cn/berserker-search/search/personal/turnover?size=1&current=1&synAccessSource=h5'

# 新增：食堂名称映射字典
CANTEEN_MAPPING = {
    "北一区": "桔园",
    "北二区": "榴园",
    "北三区": "蕙园",
    "南一区": "梅园",
    "南二区": "桂园",
    "南三区": "梧桐园"
}


def print_log(msg):
    """带时间戳的日志输出"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def save_config(headers):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(headers, f, indent=4)


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def test_headers_validity(headers):
    """验证 Headers 是否有效，并返回具体错误信息"""
    try:
        resp = requests.get(TEST_URL, headers=headers, timeout=5)
        if resp.status_code == 200:
            res_json = resp.json()
            if res_json.get('success'):
                return True, "验证成功"
            else:
                return False, f"接口返回非成功状态: {res_json}"
        else:
            return False, f"HTTP状态码异常: {resp.status_code}"
    except Exception as e:
        return False, f"网络错误: {e}"


def auto_capture_and_validate():
    final_captured = {}
    print_log("准备启动 Playwright 浏览器实例...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        state = {"found": False}

        def get_full_cookie_string():
            cookies = context.cookies()
            return "; ".join([f"{c['name']}={c['value']}" for c in cookies])

        def try_verify_and_save(cookie_str, auth_token, ua, source=""):
            print_log(f"[{source}] 正在向服务器发送鉴权测试请求...")

            temp_h = {
                "Accept": "*/*",
                "Accept-Encoding": "gzip, deflate, br, zstd",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Connection": "keep-alive",
                "Host": "ycard.ahu.edu.cn",
                "synAccessSource": "h5",
                "Cookie": cookie_str,
                "synjones-auth": auth_token if "bearer" in auth_token.lower() else f"bearer {auth_token}",
                "User-Agent": ua
            }

            is_valid, msg = test_headers_validity(temp_h)
            if is_valid:
                print_log(f"[{source}] ✅ 验证成功！即将接管爬虫程序。")
                final_captured.update(temp_h)
                state["found"] = True
                return True
            else:
                print_log(f"[{source}] ❌ 验证失败: {msg}")
                return False

        def on_request(request):
            if state["found"]: return
            if "ycard.ahu.edu.cn" in request.url:
                h = request.all_headers()

                if "berserker-search" in request.url:
                    print_log(f"[网络嗅探] 捕获到账单 API 请求: {request.url}")

                if "synjones-auth" in h:
                    print_log("[网络嗅探] 发现 synjones-auth 请求头！")
                    cookie_str = get_full_cookie_string()
                    try_verify_and_save(cookie_str, h['synjones-auth'], h.get('user-agent', ''), "网络嗅探")

        context.on("request", on_request)
        print_log("正在打开目标网页...")
        page.goto(TARGET_PAGE_URL)

        loop_count = 0

        while not state["found"]:
            loop_count += 1
            print_log(f"--- 轮询探测 第 {loop_count} 次 ---")

            try:
                for current_page in context.pages:
                    current_url = current_page.url
                    print_log(f"探测到活动标签页 URL: {current_url}")

                    if "campus-card/billing/list" in current_url:
                        print_log("✓ 在某标签页中匹配到目标 URL，提取页面数据...")
                        cookie_str = get_full_cookie_string()

                        extracted_data = current_page.evaluate("""() => {
                            return {
                                local_auth: localStorage.getItem('synjones-auth'),
                                session_auth: sessionStorage.getItem('synjones-auth'),
                                local_token: localStorage.getItem('token'),
                                session_token: sessionStorage.getItem('token')
                            };
                        }""")

                        auth_val = extracted_data['local_auth'] or extracted_data['session_auth'] or extracted_data[
                            'local_token'] or extracted_data['session_token']

                        if auth_val and cookie_str:
                            print_log("✓ 发现 Cookie 和疑似 Auth Token，准备测试...")
                            ua = current_page.evaluate("navigator.userAgent")
                            if try_verify_and_save(cookie_str, auth_val, ua, "本地存储"):
                                break
            except Exception as e:
                print_log(f"轮询过程中页面发生状态变动 (可能页面被关闭): {e}")

            if not state["found"]:
                page.wait_for_timeout(2000)

        browser.close()

    save_config(final_captured)
    return final_captured


def replace_canteen_name(text):
    """替换文本中的食堂区域名称，并处理空值"""
    if text is None:
        return text
    for old_name, new_name in CANTEEN_MAPPING.items():
        text = text.replace(old_name, new_name)
    return text


def crawl_campus_card(mode, headers, output_file='campus_card_records.csv'):
    header_row = ['交易时间', '交易类型', '金额(元)', '余额(元)', '商户/地点', '详情描述', '流水号', '订单状态']

    existing_rows = []
    latest_order_id = None

    if mode == '2':
        if os.path.exists(output_file):
            with open(output_file, 'r', encoding='utf-8-sig') as f:
                reader = csv.reader(f)
                next(reader, None)
                for row in reader:
                    existing_rows.append(row)
                    if not latest_order_id and len(row) >= 7:
                        latest_order_id = row[6]

    new_rows = []
    current_page = 1
    stop_crawling = False

    while not stop_crawling:
        print_log(f"正在爬取第 {current_page} 页...")
        params = {"size": 8, "current": current_page, "synAccessSource": "h5"}
        try:
            resp = requests.get('https://ycard.ahu.edu.cn/berserker-search/search/personal/turnover', headers=headers, params=params, timeout=10)
            data = resp.json()
            if data.get('success'):
                records = data['data']['records']
                if not records:
                    print_log(f"第 {current_page} 页无数据，爬取自然结束。")
                    break
                for item in records:
                    oid = str(item.get('orderId'))
                    if mode == '2' and latest_order_id and oid == latest_order_id:
                        stop_crawling = True
                        break

                    # 新增：在此处对“商户/地点”和“详情描述”进行名称映射替换
                    to_merchant = replace_canteen_name(item.get('toMerchant'))
                    resume = replace_canteen_name(item.get('resume'))

                    new_rows.append([
                        item.get('jndatetimeStr'), item.get('turnoverType'),
                        item.get('tranamt', 0) / 100.0, item.get('cardBalance', 0) / 100.0,
                        to_merchant, resume, oid, item.get('payName')
                    ])
            else:
                print_log(f"终止爬取：响应异常 {data.get('msg')}")
                break
        except Exception as e:
            print_log(f"终止爬取：请求发生错误 {e}")
            break

        if stop_crawling: break
        current_page += 1
        time.sleep(random.uniform(1.0, 2.0))

    with open(output_file, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(header_row)
        writer.writerows(new_rows)
        writer.writerows(existing_rows)
    print_log(f"任务结束。新增 {len(new_rows)} 条记录。")


def run_scraper(mode, output_file='campus_card_records.csv'):
    final_headers = load_config()
    if final_headers:
        is_valid, msg = test_headers_validity(final_headers)
        if is_valid:
            print_log(">>> 检测到有效的本地配置，跳过登录环节。")
        else:
            print_log(f">>> 本地配置已失效 ({msg})，准备启动浏览器捕获环境...")
            final_headers = auto_capture_and_validate()
    else:
        print_log(">>> 未找到本地配置文件，准备启动浏览器捕获环境...")
        final_headers = auto_capture_and_validate()

    crawl_campus_card(mode, final_headers, output_file)


if __name__ == "__main__":
    while True:
        choice = input("1.全量爬取 2.增量爬取: ").strip()
        if choice in ['1', '2']: break

    run_scraper(choice)
