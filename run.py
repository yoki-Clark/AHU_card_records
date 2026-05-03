#!/usr/bin/env python3
from app.main import main_menu

if __name__ == '__main__':
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\n\n程序被强制终止，退出。")
