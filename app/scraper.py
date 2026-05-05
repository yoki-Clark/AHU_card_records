import csv
import glob
import json
import os
import random
import re
import shutil
import time
from datetime import datetime

import requests
from playwright.sync_api import sync_playwright

from app import crypto_utils
from app.data_utils import (CONFIG_DIR, CONFIG_PATTERN, CANTEEN_MAPPING,
                            CrawlMode, print_log, replace_canteen_name)

TARGET_PAGE_URL = "https://wvpn.ahu.edu.cn/"
TEST_URL = ('https://ycard.ahu.edu.cn/berserker-search/search/personal/turnover'
            '?size=1&current=1&synAccessSource=h5')

CHECKPOINT_FILE = '.crawl_checkpoint.json'

# ==================== Page Selectors (configurable) ====================
# These selectors target elements on the SSO portal. If the portal UI changes,
# update these constants rather than hunting through the code.
SELECTOR_USER_NAME = '#user-btn-01 > span'
SELECTOR_USER_EMAIL = '#email'
SELECTOR_CARD_LINK = '#card_info > a:nth-child(2)'
SELECTOR_CARD_LINK_FALLBACK = 'text=校园卡'

# ==================== Browser Detection ====================

BROWSER_PATHS = {
    "Chrome": [
        os.environ.get('PROGRAMFILES', '') + r"\Google\Chrome\Application\chrome.exe",
        os.environ.get('PROGRAMFILES(X86)', '') + r"\Google\Chrome\Application\chrome.exe",
        os.environ.get('LOCALAPPDATA', '') + r"\Google\Chrome\Application\chrome.exe",
    ],
    "Edge": [
        os.environ.get('PROGRAMFILES(X86)', '') + r"\Microsoft\Edge\Application\msedge.exe",
        os.environ.get('PROGRAMFILES', '') + r"\Microsoft\Edge\Application\msedge.exe",
    ]
}


def _find_browser_path():
    for name, path_list in BROWSER_PATHS.items():
        for p in path_list:
            if p and os.path.exists(p):
                return name, p
    for exe in ('chrome', 'google-chrome', 'chromium', 'msedge', 'microsoft-edge'):
        found = shutil.which(exe)
        if found and os.path.exists(found):
            return "Browser", found
    return None, None


def _select_browser():
    saved = _get_saved_browser()
    if saved:
        print_log(f"已找到上次使用的浏览器: {saved}")
        return saved

    name, path = _find_browser_path()
    if path:
        print_log(f"自动检测到浏览器: {name} ({path})")
        _save_browser_config(path)
        return path

    print_log("未能在默认路径找到 Chrome 或 Edge，将尝试使用 Playwright 默认的 Chromium。")
    return None


# ==================== Config File Management ====================

def _is_valid_config_filename(filename):
    return bool(CONFIG_PATTERN.match(filename))


def scan_local_users():
    users = []
    pattern = os.path.join(CONFIG_DIR, 'config_*.json')
    for file_path in glob.glob(pattern):
        basename = os.path.basename(file_path)
        if not _is_valid_config_filename(basename):
            continue
        try:
            data = crypto_utils.load_user_config(file_path)
            if 'user_id' in data and 'user_name' in data:
                users.append({
                    'user_id': data['user_id'],
                    'user_name': data['user_name'],
                    'headers': data.get('headers', {})
                })
        except Exception as e:
            print_log(f"警告: 跳过损坏的配置文件 {file_path}: {e}")
            continue
    return users


def save_user_config(user_id, user_name, headers):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    file_path = os.path.join(CONFIG_DIR, f"config_{user_id}.json")
    data = {
        "user_id": user_id,
        "user_name": user_name,
        "headers": crypto_utils.encrypt_headers(headers),
        "update_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    return file_path


# ==================== Auth Validation ====================

BASE_HEADERS = {
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Connection": "keep-alive",
    "Host": "ycard.ahu.edu.cn",
    "synAccessSource": "h5",
}


def test_headers_validity(headers):
    try:
        resp = requests.get(TEST_URL, headers=headers, timeout=5)
        if resp.status_code == 200:
            try:
                res_json = resp.json()
            except ValueError:
                return False, "接口返回非 JSON 数据 (可能被 SSO 拦截)"
            if res_json.get('success'):
                return True, "验证成功"
            return False, f"接口返回非成功状态: {res_json}"
        return False, f"HTTP状态码异常: {resp.status_code}"
    except Exception as e:
        return False, f"网络错误: {e}"


# ==================== User Identity Extraction ====================

def _extract_user_identity(page):
    print_log("等待获取用户信息节点 (最大等待时长 5 分钟)...")
    page.wait_for_selector(SELECTOR_USER_NAME, state='attached', timeout=300000)

    raw_name = page.locator(SELECTOR_USER_NAME).text_content()
    page.wait_for_selector(SELECTOR_USER_EMAIL, state='attached', timeout=5000)
    raw_email = page.locator(SELECTOR_USER_EMAIL).text_content()

    user_name = raw_name.strip() if raw_name else "未知用户"
    raw_email_str = raw_email.strip() if raw_email else "Unknown"
    user_id = raw_email_str.split('@')[0] if '@' in raw_email_str else raw_email_str

    print_log(f"识别到登录用户: {user_name} (学号: {user_id})")
    return user_name, user_id


# ==================== Auth Token Sniffing ====================

def _setup_auth_verify(context, page, on_capture):
    def _get_cookies():
        cookies = context.cookies()
        return "; ".join([f"{c['name']}={c['value']}" for c in cookies])

    def _try_verify(cookie_str, auth_token, ua, source=""):
        print_log(f"[{source}] 正在向服务器发送鉴权测试请求...")
        temp_h = {**BASE_HEADERS}
        temp_h["Cookie"] = cookie_str
        auth_lower = auth_token.lower()
        temp_h["synjones-auth"] = auth_token if auth_lower.startswith("bearer ") else f"bearer {auth_token}"
        temp_h["User-Agent"] = ua

        is_valid, msg = test_headers_validity(temp_h)
        if is_valid:
            print_log(f"[{source}] 验证成功！即将接管爬虫程序。")
            on_capture(temp_h)
            return True
        print_log(f"[{source}] 验证失败: {msg}")
        return False

    def _on_request(request):
        if "ycard.ahu.edu.cn" in request.url:
            h = request.all_headers()
            if "synjones-auth" in h:
                _try_verify(_get_cookies(), h['synjones-auth'],
                           h.get('user-agent', ''), "网络嗅探")

    context.on("request", _on_request)

    def poll_storage():
        for current_page in context.pages:
            cookie_str = _get_cookies()
            try:
                extracted = current_page.evaluate("""() => {
                    return {
                        local_auth: localStorage.getItem('synjones-auth'),
                        session_auth: sessionStorage.getItem('synjones-auth'),
                        local_token: localStorage.getItem('token'),
                        session_token: sessionStorage.getItem('token')
                    };
                }""")
                auth_val = (extracted['local_auth'] or extracted['session_auth'] or
                           extracted['local_token'] or extracted['session_token'])
                if auth_val and cookie_str:
                    ua = current_page.evaluate("navigator.userAgent")
                    return _try_verify(cookie_str, auth_val, ua, "本地存储")
            except Exception:
                pass
        return False

    return poll_storage


# ==================== Main Capture Flow ====================

def capture_new_user():
    exec_path = _select_browser()
    captured_headers = {}

    print_log("准备启动浏览器实例...")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=exec_path if exec_path else None,
            headless=False
        )

        context = browser.new_context()
        page = context.new_page()

        def _on_headers_captured(headers):
            captured_headers.update(headers)

        poll_storage = _setup_auth_verify(context, page, _on_headers_captured)

        print_log("正在打开统一身份认证网页，请手动完成登录操作...")
        page.goto(TARGET_PAGE_URL)

        try:
            user_name, user_id = _extract_user_identity(page)
        except Exception as e:
            print_log(f"等待登录状态超时或提取身份节点失败: {e}")
            browser.close()
            return None, None, None

        try:
            print_log("尝试自动点击并跳转到校园卡页面...")
            try:
                card_link = page.locator(SELECTOR_CARD_LINK)
            except Exception:
                card_link = page.locator(SELECTOR_CARD_LINK_FALLBACK)
            with context.expect_page(timeout=10000) as new_page_info:
                card_link.click(force=True)
            card_page = new_page_info.value
            card_page.wait_for_load_state()
            print_log("已成功接管校园卡新标签页。为确保生成鉴权，将自动导向账单明细页...")
            card_page.goto("https://ycard.ahu.edu.cn/campus-card/billing/list")
        except Exception as e:
            print_log(f"自动点击或接管新标签页发生异常，将依赖轮询: {e}")

        for i in range(15):
            if captured_headers:
                break
            print_log(f"--- 轮询嗅探鉴权凭证 第 {i + 1}/15 次 ---")
            poll_storage()
            if not captured_headers:
                page.wait_for_timeout(2000)

        browser.close()

    if captured_headers:
        save_user_config(user_id, user_name, captured_headers)
        return user_id, user_name, captured_headers
    return None, None, None


# ==================== Crawl Checkpoint ====================

def _read_checkpoint_file():
    """Return parsed checkpoint dict, or {} if missing/corrupt."""
    try:
        with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            # Migrate legacy single-user format
            if 'user_name' in data and 'last_page' in data:
                old_user = data.pop('user_name')
                old_page = data.pop('last_page')
                data[old_user] = old_page
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return {}


def _load_checkpoint(user_name):
    """Load the checkpoint page for a specific user. Returns 1 if none found."""
    data = _read_checkpoint_file()
    return data.get(user_name, 1)


def _save_checkpoint(user_name, page_num):
    """Save checkpoint for a user. Supports multiple users in one file."""
    data = _read_checkpoint_file()
    data[user_name] = page_num
    with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f)


def _clear_checkpoint(user_name=None):
    """Clear checkpoint. If user_name is given, remove only that user's entry."""
    if user_name is None:
        try:
            os.remove(CHECKPOINT_FILE)
        except FileNotFoundError:
            pass
        return
    data = _read_checkpoint_file()
    data.pop(user_name, None)
    if data:
        with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f)
    else:
        try:
            os.remove(CHECKPOINT_FILE)
        except FileNotFoundError:
            pass


# ==================== Core Crawling Logic ====================

MAX_RETRIES = 3
PAGE_SIZE = 8
API_URL = 'https://ycard.ahu.edu.cn/berserker-search/search/personal/turnover'


def _fetch_page(page_num, headers):
    """Fetch a single page of records. Returns (data_dict, error_msg)."""
    params = {"size": PAGE_SIZE, "current": page_num, "synAccessSource": "h5"}
    last_error = None

    for retry in range(MAX_RETRIES):
        try:
            resp = requests.get(API_URL, headers=headers, params=params, timeout=10)
            return resp.json(), None
        except Exception as e:
            last_error = str(e)
            if retry < MAX_RETRIES - 1:
                wait_s = min(2 ** retry, 8)  # exponential backoff capped at 8s
                print_log(f"第 {page_num} 页请求失败 ({e})，正在重试 {retry + 1}/{MAX_RETRIES} (等待 {wait_s}s)...")
                time.sleep(wait_s)

    return None, f"连续重试失败: {last_error}"


def _process_record(item):
    """Convert a single API record to a CSV row."""
    return [
        item.get('jndatetimeStr'),
        item.get('turnoverType'),
        item.get('tranamt', 0) / 100.0,
        item.get('cardBalance', 0) / 100.0,
        replace_canteen_name(item.get('toMerchant')),
        replace_canteen_name(item.get('resume')),
        str(item.get('orderId')),
        item.get('payName')
    ]


def _get_latest_order_id(output_file):
    """Read the first data row from an existing CSV to get the latest order ID."""
    try:
        with open(output_file, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            next(reader, None)
            first_row = next(reader, None)
            if first_row and len(first_row) >= 7 and first_row[6].strip():
                return first_row[6].strip()
    except (FileNotFoundError, StopIteration):
        pass
    return None


def _write_csv(output_file, header_row, new_rows, append_file=None):
    """Write new rows to CSV. If append_file is given, stream its content after new rows."""
    temp_file = output_file + '.temp'
    try:
        with open(temp_file, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(header_row)
            writer.writerows(new_rows)
            # Stream existing rows without loading all into memory
            if append_file and os.path.exists(append_file):
                with open(append_file, 'r', encoding='utf-8-sig') as src:
                    src.readline()  # skip header
                    for line in src:
                        f.write(line)
        os.replace(temp_file, output_file)
    finally:
        try:
            os.remove(temp_file)
        except FileNotFoundError:
            pass


def crawl_campus_card(mode, headers, user_name, output_file=None):
    if output_file is None:
        output_file = f"{user_name}_records.csv"
    header_row = ['交易时间', '交易类型', '金额(元)', '余额(元)', '商户/地点', '详情描述', '流水号', '订单状态']

    latest_order_id = None

    if mode == CrawlMode.INCREMENTAL and os.path.exists(output_file):
        latest_order_id = _get_latest_order_id(output_file)

    new_rows = []
    stop_crawling = False

    if mode == CrawlMode.FULL:
        current_page = _load_checkpoint(user_name)
        if current_page > 1:
            print_log(f"检测到断点记录，从第 {current_page} 页继续爬取...")
    else:
        current_page = 1

    # Hoist the mode check outside the record loop
    is_incremental_match = mode == CrawlMode.INCREMENTAL and latest_order_id

    while not stop_crawling:
        print_log(f"正在爬取第 {current_page} 页...")
        data, error = _fetch_page(current_page, headers)

        if error:
            print_log(error)
            _save_checkpoint(user_name, current_page + 1)
            break

        if not data or not data.get('success'):
            print_log(f"终止爬取：响应异常 {data.get('msg') if data else '无响应'}")
            _save_checkpoint(user_name, current_page + 1)
            break

        records = data.get('data', {}).get('records', [])
        if not records:
            print_log(f"第 {current_page} 页无数据，爬取自然结束。")
            _clear_checkpoint(user_name)
            break

        if is_incremental_match:
            for item in records:
                if str(item.get('orderId')) == latest_order_id:
                    stop_crawling = True
                    break
                new_rows.append(_process_record(item))
        else:
            for item in records:
                new_rows.append(_process_record(item))

        if stop_crawling:
            _clear_checkpoint(user_name)
            break

        if current_page % 10 == 0:
            _save_checkpoint(user_name, current_page + 1)

        current_page += 1
        time.sleep(random.uniform(1.0, 2.0))

    if not new_rows:
        print_log(f"[{user_name}] 没有获取到新数据，文件无需更新。")
        return

    _write_csv(output_file, header_row, new_rows, append_file=output_file)
    print_log(f"[{user_name}] 任务结束。新增 {len(new_rows)} 条记录，已保存至 {output_file}。")


# ==================== Browser Config Persistence ====================

def _get_saved_browser():
    config_file = os.path.join(CONFIG_DIR, 'browser_config.json')
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            path = data.get('browser_path')
            if path and os.path.exists(path):
                return path
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return None


def _save_browser_config(path):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    config_file = os.path.join(CONFIG_DIR, 'browser_config.json')
    with open(config_file, 'w', encoding='utf-8') as f:
        json.dump({'browser_path': path}, f, indent=4)


# ==================== Entry Points ====================

def run_manager():
    while True:
        mode = input("1.全量爬取 2.增量爬取: ").strip()
        if mode in ['1', '2']:
            mode = CrawlMode(mode)
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
                print_log("配置有效，准备拉取数据。")
                user_headers = selected['headers']
                target_user_name = selected['user_name']
                break
            print_log(f"配置已失效 ({msg})，请选择登录新用户进行更新。")

        else:
            expected_new = len(local_users) + 1 if local_users else 1
            if choice != expected_new:
                continue
            u_id, u_name, u_headers = capture_new_user()
            if u_headers:
                user_headers = u_headers
                target_user_name = u_name
                break
            print_log("捕获配置失败，程序退出。")
            return

    if user_headers and target_user_name:
        crawl_campus_card(mode, user_headers, target_user_name)


def run_scraper(mode, output_file, user_name):
    local_users = scan_local_users()
    selected = next((u for u in local_users if u['user_name'] == user_name), None)
    if not selected:
        print_log(f"未找到用户 {user_name} 的配置")
        return
    is_valid, msg = test_headers_validity(selected['headers'])
    if not is_valid:
        print_log(f"配置失效: {msg}")
        return
    crawl_campus_card(mode, selected['headers'], user_name, output_file)


if __name__ == "__main__":
    run_manager()
