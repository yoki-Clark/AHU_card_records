import requests
import csv
import time
import random
import os
import json
import glob
from datetime import datetime
from playwright.sync_api import sync_playwright

TARGET_PAGE_URL = "https://wvpn.ahu.edu.cn/"
TEST_URL = 'https://ycard.ahu.edu.cn/berserker-search/search/personal/turnover?size=1&current=1&synAccessSource=h5'

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


def get_windows_browsers():
    """检索 Windows 系统中常见的 Chrome 和 Edge 浏览器路径"""
    browsers = []
    paths = {
        "Chrome": [
            os.environ.get('PROGRAMFILES', '') + r"\Google\Chrome\Application\chrome.exe",
            os.environ.get('PROGRAMFILES(X86)', '') + r"\Google\Chrome\Application\chrome.exe",
            os.environ.get('LOCALAPPDATA', '') + r"\Google\Chrome\Application\chrome.exe"
        ],
        "Edge": [
            os.environ.get('PROGRAMFILES(X86)', '') + r"\Microsoft\Edge\Application\msedge.exe",
            os.environ.get('PROGRAMFILES', '') + r"\Microsoft\Edge\Application\msedge.exe"
        ]
    }
    for name, path_list in paths.items():
        for p in path_list:
            if p and os.path.exists(p):
                browsers.append((name, p))
                break
    return browsers


def scan_local_users():
    """扫描本地已经存在的用户配置文件"""
    users = []
    for file_path in glob.glob('config_*.json'):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if 'user_id' in data and 'user_name' in data:
                    users.append({
                        'file': file_path,
                        'user_id': data['user_id'],
                        'user_name': data['user_name'],
                        'headers': data.get('headers', {})
                    })
        except Exception:
            continue
    return users


def save_user_config(user_id, user_name, headers):
    file_path = f"config_{user_id}.json"
    data = {
        "user_id": user_id,
        "user_name": user_name,
        "headers": headers,
        "update_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    return file_path


def test_headers_validity(headers):
    """验证 Headers 是否有效"""
    try:
        resp = requests.get(TEST_URL, headers=headers, timeout=5)
        if resp.status_code == 200:
            try:
                res_json = resp.json()
            except ValueError:
                return False, "接口返回非 JSON 数据 (可能被 SSO 拦截)"

            if res_json.get('success'):
                return True, "验证成功"
            else:
                return False, f"接口返回非成功状态: {res_json}"
        else:
            return False, f"HTTP状态码异常: {resp.status_code}"
    except Exception as e:
        return False, f"网络错误: {e}"


def capture_new_user():
    """启动浏览器，引导登录，提取身份并嗅探鉴权"""
    browsers = get_windows_browsers()
    if not browsers:
        print_log("未能在默认路径找到 Chrome 或 Edge，将尝试使用 Playwright 默认的 Chromium。")
        exec_path = None
    else:
        saved_browser = get_saved_browser()
        if saved_browser:
            exec_path = saved_browser
            print_log(f"已找到上次使用的浏览器: {exec_path}")
        else:
            print("\n--- 请选择要用于登录的浏览器 ---")
            for idx, (b_name, b_path) in enumerate(browsers):
                print(f"{idx + 1}. {b_name} ({b_path})")
            print("--------------------------------")
            while True:
                b_choice = input(f"请输入序号 (1-{len(browsers)}): ").strip()
                if b_choice.isdigit() and 1 <= int(b_choice) <= len(browsers):
                    exec_path = browsers[int(b_choice) - 1][1]
                    print_log(f"已选择浏览器: {browsers[int(b_choice) - 1][0]}")
                    save_browser_config(exec_path)  # 保存用户选择的浏览器
                    break

    final_captured = {}
    user_name = "未知用户"
    user_id = "Unknown"

    print_log("准备启动浏览器实例...")

    with sync_playwright() as p:
        if exec_path:
            browser = p.chromium.launch(executable_path=exec_path, headless=False)
        else:
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
                if "synjones-auth" in h:
                    cookie_str = get_full_cookie_string()
                    try_verify_and_save(cookie_str, h['synjones-auth'], h.get('user-agent', ''), "网络嗅探")

        context.on("request", on_request)
        print_log("正在打开统一身份认证网页，请手动完成登录操作...")
        page.goto(TARGET_PAGE_URL)

        # 1. 监测登录状态并获取身份标识
        try:
            print_log("等待获取用户信息节点 (最大等待时长 5 分钟)...")
            # 修复点：只要节点存在于 DOM，不要求一定是可见状态
            page.wait_for_selector('#user-btn-01 > span', state='attached', timeout=300000)

            # 修复点：使用 text_content() 无视 CSS 隐藏强制读取文本
            raw_name = page.locator('#user-btn-01 > span').text_content()

            # 学号节点可能也存在相同问题，同步修改并增加容错
            page.wait_for_selector('#email', state='attached', timeout=5000)
            raw_email = page.locator('#email').text_content()

            user_name = raw_name.strip() if raw_name else "未知用户"
            raw_email_str = raw_email.strip() if raw_email else "Unknown"

            user_id = raw_email_str.split('@')[0] if '@' in raw_email_str else raw_email_str

            print_log(f"识别到登录用户: {user_name} (学号: {user_id})")
        except Exception as e:
            print_log(f"等待登录状态超时或提取身份节点失败: {e}")
            browser.close()
            return None, None, None

        # 2. 自动点击目标按钮并接管新标签页
        try:
            print_log("尝试自动点击并跳转到校园卡页面...")
            with context.expect_page(timeout=10000) as new_page_info:
                # 修复点：使用 force=True 强制触发点击，防止元素因折叠状态被阻挡
                page.locator('#card_info > a:nth-child(2)').click(force=True)
            card_page = new_page_info.value
            card_page.wait_for_load_state()
            print_log("已成功接管校园卡新标签页。为确保生成鉴权，将自动导向账单明细页...")

            card_page.goto("https://ycard.ahu.edu.cn/campus-card/billing/list")
        except Exception as e:
            print_log(f"自动点击或接管新标签页发生异常，将依赖轮询: {e}")

        # 3. 轮询等待嗅探结果
        loop_count = 0
        while not state["found"] and loop_count < 15:
            loop_count += 1
            print_log(f"--- 轮询嗅探鉴权凭证 第 {loop_count}/15 次 ---")

            try:
                for current_page in context.pages:
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
                        ua = current_page.evaluate("navigator.userAgent")
                        if try_verify_and_save(cookie_str, auth_val, ua, "本地存储"):
                            break
            except Exception:
                pass

            if not state["found"]:
                page.wait_for_timeout(2000)

        browser.close()

    if final_captured:
        save_user_config(user_id, user_name, final_captured)
        return user_id, user_name, final_captured
    return None, None, None


def replace_canteen_name(text):
    if not text:
        return text
    for old_name, new_name in CANTEEN_MAPPING.items():
        if old_name in text:
            text = text.replace(old_name, new_name)
    return text


def crawl_campus_card(mode, headers, user_name, output_file=None):
    if output_file is None:
        output_file = f"{user_name}_records.csv"
    header_row = ['交易时间', '交易类型', '金额(元)', '余额(元)', '商户/地点', '详情描述', '流水号', '订单状态']

    existing_rows = []
    latest_order_id = None

    if mode == '2' and os.path.exists(output_file):
        with open(output_file, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                existing_rows.append(row)
                if not latest_order_id and len(row) >= 7 and row[6].strip():
                    latest_order_id = row[6].strip()

    new_rows = []
    current_page = 1
    stop_crawling = False
    max_retries = 3

    while not stop_crawling:
        print_log(f"正在爬取第 {current_page} 页...")
        params = {"size": 8, "current": current_page, "synAccessSource": "h5"}

        retry_count = 0
        success = False
        while retry_count < max_retries:
            try:
                resp = requests.get('https://ycard.ahu.edu.cn/berserker-search/search/personal/turnover',
                                    headers=headers, params=params, timeout=10)
                data = resp.json()
                success = True
                break
            except Exception as e:
                retry_count += 1
                print_log(f"第 {current_page} 页请求失败 ({e})，正在重试 {retry_count}/{max_retries}...")
                time.sleep(2)

        if not success:
            print_log("连续重试失败，终止爬取。")
            break

        if data and data.get('success'):
            records = data.get('data', {}).get('records', [])
            if not records:
                print_log(f"第 {current_page} 页无数据，爬取自然结束。")
                break

            for item in records:
                oid = str(item.get('orderId'))
                if mode == '2' and latest_order_id and oid == latest_order_id:
                    stop_crawling = True
                    break

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

        if stop_crawling:
            break

        current_page += 1
        time.sleep(random.uniform(1.0, 2.0))

    if not new_rows:
        print_log(f"[{user_name}] 没有获取到新数据，文件无需更新。")
        return

    temp_output_file = output_file + '.temp'
    try:
        with open(temp_output_file, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(header_row)
            writer.writerows(new_rows)
            writer.writerows(existing_rows)

        os.replace(temp_output_file, output_file)
        print_log(f"[{user_name}] 任务结束。新增 {len(new_rows)} 条记录，已保存至 {output_file}。")
    except Exception as e:
        print_log(f"写入文件时发生错误: {e}")
        if os.path.exists(temp_output_file):
            os.remove(temp_output_file)


def get_saved_browser():
    config_file = 'browser_config.json'
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                path = data.get('browser_path')
                if path and os.path.exists(path):
                    return path
        except Exception:
            pass
    return None


def save_browser_config(path):
    config_file = 'browser_config.json'
    data = {'browser_path': path}
    with open(config_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)


def run_manager():
    while True:
        mode = input("1.全量爬取 2.增量爬取: ").strip()
        if mode in ['1', '2']:
            break

    local_users = scan_local_users()

    print("\n========= 用户选择 =========")
    if local_users:
        for idx, u in enumerate(local_users):
            print(f"{idx + 1}. 使用已有配置: {u['user_name']} (学号: {u['user_id']})")
        print(f"{len(local_users) + 1}. 登录新用户 (或配置已失效需要重新登录)")
    else:
        print("1. 登录新用户 (未检测到本地配置)")
    print("============================")

    user_headers = None
    target_user_name = None

    while True:
        choice = input("请输入对应的序号: ").strip()
        if not choice.isdigit():
            continue

        choice = int(choice)
        if local_users and 1 <= choice <= len(local_users):
            selected = local_users[choice - 1]
            print_log(f"正在校验 {selected['user_name']} 的本地配置...")
            is_valid, msg = test_headers_validity(selected['headers'])
            if is_valid:
                print_log("✅ 配置有效，准备拉取数据。")
                user_headers = selected['headers']
                target_user_name = selected['user_name']
                break
            else:
                print_log(f"❌ 配置已失效 ({msg})，请选择登录新用户进行更新。")

        elif choice == (len(local_users) + 1) if local_users else choice == 1:
            u_id, u_name, u_headers = capture_new_user()
            if u_headers:
                user_headers = u_headers
                target_user_name = u_name
                break
            else:
                print_log("捕获配置失败，程序退出。")
                return

    if user_headers and target_user_name:
        crawl_campus_card(mode, user_headers, target_user_name)


def run_scraper(mode, output_file, user_name):
    local_users = scan_local_users()
    selected = None
    for u in local_users:
        if u['user_name'] == user_name:
            selected = u
            break
    if not selected:
        print_log(f"未找到用户 {user_name} 的配置")
        return
    is_valid, msg = test_headers_validity(selected['headers'])
    if is_valid:
        user_headers = selected['headers']
        target_user_name = selected['user_name']
    else:
        print_log(f"配置失效: {msg}")
        return
    crawl_campus_card(mode, user_headers, target_user_name, output_file)


if __name__ == "__main__":
    run_manager()
