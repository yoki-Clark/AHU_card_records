import sys
import os
import scraper
import analyzer

DATA_FILE = 'campus_card_records.csv'


def print_separator():
    print("=" * 50)


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

        choice = input("请输入选项数字并回车: ").strip()

        if choice == '1':
            print("\n>>> 启动增量爬取...")
            scraper.run_scraper(mode='2', output_file=DATA_FILE)
        elif choice == '2':
            print("\n>>> 启动全量爬取...")
            scraper.run_scraper(mode='1', output_file=DATA_FILE)
        elif choice == '3':
            print("\n>>> 启动数据分析...")
            if not os.path.exists(DATA_FILE):
                print(f"❌ 错误：未找到数据文件 {DATA_FILE}，请先执行爬取任务！")
            else:
                analyzer.run_analysis(DATA_FILE)
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
