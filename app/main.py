import glob
import os
import sys

from app import scraper, analyzer, visualizer
from app.data_utils import CONFIG_DIR, CONFIG_PATTERN, CrawlMode
from app import crypto_utils


def print_separator():
    print("=" * 50)


def get_available_users():
    """Return list of configured user names, delegating to scraper's scan."""
    return [u['user_name'] for u in scraper.scan_local_users()]


def select_user():
    users = get_available_users()

    print("\n========= 选择用户 =========")
    if users:
        for i, u in enumerate(users):
            print(f"  [{i+1}] {u}")
        print(f"  [{len(users)+1}] 添加新用户")
    else:
        print("  (暂无已配置用户)")
        print(f"  [1] 添加新用户")
    print("============================")

    while True:
        choice = input("请输入用户序号: ").strip()
        if choice.isdigit():
            choice = int(choice)
            if users and 1 <= choice <= len(users):
                return users[choice - 1]
            add_new = (choice == len(users) + 1) if users else (choice == 1)
            if add_new:
                print("\n>>> 启动添加新用户...")
                u_id, u_name, u_headers = scraper.capture_new_user()
                if u_headers and u_name:
                    print(f"✅ 新用户 {u_name} 添加成功！")
                    return u_name
                print("❌ 添加新用户失败，请重试。")
                return None
            print("❌ 无效输入，请重新选择。")
        else:
            print("❌ 无效输入，请重新选择。")


def select_data_file():
    files = glob.glob('*_records.csv')
    if not files:
        print("❌ 未找到数据文件。")
        return None
    print("\n========= 选择数据文件 =========")
    for i, f in enumerate(files):
        print(f"  [{i+1}] {f}")
    print("=================================")
    while True:
        choice = input("请输入文件序号: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(files):
            return files[int(choice) - 1]
        print("❌ 无效输入，请重新选择。")


def main_menu():
    while True:
        print_separator()
        print(" " * 12 + "一卡通数据管理与分析系统")
        print_separator()
        print("请选择操作功能：")
        print("  [1] 增量爬取流水记录 (推荐，仅爬取新数据)")
        print("  [2] 全量爬取流水记录 (耗时较长，重新获取所有数据)")
        print("  [3] 执行一卡通数据分析 (基于本地已有数据)")
        print("  [4] 生成可视化图表 (基于本地已有数据)")
        print("  [0] 退出系统")
        print_separator()

        choice = input("请输入选项数字并回车: ")

        if choice == '1':
            user = select_user()
            if user:
                print(f"\n>>> 启动增量爬取 {user} 的数据...")
                scraper.run_scraper(CrawlMode.INCREMENTAL, f"{user}_records.csv", user)
        elif choice == '2':
            user = select_user()
            if user:
                print(f"\n>>> 启动全量爬取 {user} 的数据...")
                scraper.run_scraper(CrawlMode.FULL, f"{user}_records.csv", user)
        elif choice == '3':
            file_path = select_data_file()
            if file_path:
                print(f"\n>>> 启动数据分析 {file_path}...")
                analyzer.run_analysis(file_path)
        elif choice == '4':
            file_path = select_data_file()
            if file_path:
                print(f"\n>>> 启动可视化生成 {file_path}...")
                visualizer.run_visualization(file_path)
        elif choice == '0':
            print("\n感谢使用，再见！")
            sys.exit(0)
        else:
            print("\n❌ 无效的输入，请重新选择。")


if __name__ == "__main__":
    from app.data_utils import setup_logging
    setup_logging()
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\n\n程序被强制终止，退出。")
        sys.exit(0)
