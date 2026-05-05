#!/usr/bin/env python3
from app.data_utils import setup_logging
from app.main import main_menu

if __name__ == '__main__':
    setup_logging()
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\n\n程序被强制终止，退出。")
