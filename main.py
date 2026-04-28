import sys
import json
import glob
import scraper
import analyzer

# 动态设置数据文件路径
configs = glob.glob('config_*.json')
if configs:
    try:
        with open(configs[0], 'r', encoding='utf-8') as f:
            data = json.load(f)
            user_name = data.get('user_name', 'campus_card')
        DATA_FILE = f"{user_name}_records.csv"
    except Exception:
        DATA_FILE = 'campus_card_records.csv'
else:
    DATA_FILE = 'campus_card_records.csv'


def print_separator():
    print("=" * 50)


def get_available_users():
    configs = glob.glob('config_*.json')
    users = []
    for config in configs:
        try:
            with open(config, 'r', encoding='utf-8') as f:
                data = json.load(f)
                user_name = data.get('user_name')
                if user_name:
                    users.append(user_name)
        except Exception:
            pass
    return users


def select_user():
    users = get_available_users()
    if not users:
        print("❌ 未找到用户配置，请先运行爬虫创建配置。")
        return None
    print("\n========= 选择用户 =========")
    for i, u in enumerate(users):
        print(f"  [{i+1}] {u}")
    print(f"  [{len(users)+1}] 添加新用户")
    print("============================")
    while True:
        choice = input("请输入用户序号: ").strip()
        if choice.isdigit():
            choice = int(choice)
            if 1 <= choice <= len(users):
                return users[choice - 1]
            elif choice == len(users) + 1:
                print("\n>>> 启动添加新用户...")
                u_id, u_name, u_headers = scraper.capture_new_user()
                if u_headers and u_name:
                    print(f"✅ 新用户 {u_name} 添加成功！")
                    return u_name
                else:
                    print("❌ 添加新用户失败，请重试。")
            else:
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
        else:
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
        print("  [0] 退出系统")
        print_separator()

        choice = input("请输入选项数字并回车: ")


        if choice == '1':
            user = select_user()
            if user:
                DATA_FILE = f"{user}_records.csv"
                print(f"\n>>> 启动增量爬取 {user} 的数据...")
                scraper.run_scraper(mode='2', output_file=DATA_FILE, user_name=user)
        elif choice == '2':
            user = select_user()
            if user:
                DATA_FILE = f"{user}_records.csv"
                print(f"\n>>> 启动全量爬取 {user} 的数据...")
                scraper.run_scraper(mode='1', output_file=DATA_FILE, user_name=user)
        elif choice == '3':
            file_path = select_data_file()
            if file_path:
                print(f"\n>>> 启动数据分析 {file_path}...")
                analyzer.run_analysis(file_path)
        elif choice == '0':
            print("\n感谢使用，再见！")
            sys.exit(0)
        else:
            print("\n❌ 无效的输入，请重新选择。")


if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\n\n程序被强制终止，退出。")
        sys.exit(0)
