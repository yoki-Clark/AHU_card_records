# AHU Campus Card Records Scraper and Analyzer

这是一个用于爬取安徽大学（AHU）校园一卡通消费记录的 Python 项目。通过 Playwright 模拟登录智慧安大系统，自动获取一卡通流水数据，并提供数据分析和可视化功能。

## 项目结构

```
AHU_card_records/
├── app/
│   ├── main.py             # CLI 交互入口，用户/数据文件选择菜单
│   ├── scraper.py          # 浏览器自动化登录 + API 分页爬取
│   ├── analyzer.py         # pandas/numpy 数据分析引擎
│   ├── visualizer.py       # matplotlib 可视化图表生成（并行）
│   ├── crypto_utils.py     # 认证配置加密/解密工具
│   └── data_utils.py       # 共享常量、CSV 加载、终端格式化、日志
├── config/
│   ├── browser_config.json # 浏览器路径持久化
│   └── config_{学号}.json  # 用户认证配置（敏感字段加密存储）
├── tests/
│   ├── test_core.py        # 核心逻辑单元测试
│   └── test_crypto.py      # 加密加解密循环测试
├── charts/                 # 可视化图表输出目录
├── run.py                  # 程序入口
├── requirements.txt        # Python 依赖清单
└── {姓名}_records.csv      # 爬取的消费流水数据（根目录）
```

## 主要功能

- **数据爬取** (app/scraper.py)：
  - 支持全量爬取和增量爬取两种模式
  - Playwright 浏览器自动化登录并捕获认证令牌
  - 认证信息本地加密存储，支持多用户配置
  - 全量爬取支持断点续传（崩溃后自动恢复进度）
  - 反反爬机制（随机延时、重试逻辑）
  - 智能食堂名称映射（北一区→桔园等）

- **数据分析** (app/analyzer.py)：
  - 全局概览：有效在校天数（自动识别假期/离校）、日均消费
  - 动态周期分析：月度、周度环比趋势
  - 星期分布：各星期日均支出、笔数、常去地点
  - 作息分析：最早/最晚消费时间、工作日 vs 周末首餐时间
  - 财务习惯：充值触发余额、资金续航、预算预测
  - 食堂统计：三餐×食堂 pivot 表、食堂忠诚度月度变化
  - 非食堂消费汇总
  - 离校期自动检测（区分短假与长假/寒暑假）

- **可视化** (app/visualizer.py)：
  - 月度有效日均消费趋势折线图
  - 食堂消费金额/次数占比饼图
  - 星期日均消费/笔数对比柱状图
  - 星期×小时消费时段热力图
  - 输出保存至 `charts/` 目录

## 依赖环境

- Python 3.7+
- 外部库 (`pip install -r requirements.txt`)：
  - `requests` — HTTP 请求
  - `playwright` — 浏览器自动化
  - `pandas` — 数据分析
  - `numpy` — 数值计算
  - `matplotlib` — 图表生成
  - `cryptography` — 配置加密

## 安装步骤

1. 克隆项目
2. 安装依赖：`pip install -r requirements.txt`
3. 安装浏览器：`playwright install`
4. 运行测试（可选）：`pytest tests/ -v`

## 使用方法

```bash
python run.py
```

菜单选项：
- `[1] 增量爬取` — 仅爬取新数据（推荐）
- `[2] 全量爬取` — 重新获取所有数据（支持断点续传）
- `[3] 数据分析` — 终端输出综合分析报告
- `[4] 可视化` — 输出图表到 `charts/` 目录

首次登录：登录智慧安大账号，点击左侧**「余额」**（不要点「一卡通」），等待程序自动捕获。

## 配置与数据文件

| 文件 | 说明 |
|------|------|
| `config/browser_config.json` | 浏览器路径配置 |
| `config/config_{学号}.json` | 用户认证配置（token/cookie 加密存储） |
| `{姓名}_records.csv` | 消费记录，UTF-8 BOM 编码兼容 Excel |
| `.encryption_key` / `.encryption_salt` | 加密密钥（自动生成，勿删除） |
| `.crawl_checkpoint.json` | 全量爬取断点信息（自动清理） |

## CSV 数据格式

交易时间, 交易类型, 金额(元), 余额(元), 商户/地点, 详情描述, 流水号, 订单状态

## 注意事项

- 爬取会自动添加随机延时，避免被服务器限制
- 认证 token 已加密存储，但请勿将 config 文件分享给他人
- 全量爬取崩溃后重新运行会自动从断点继续
- 本项目仅供学习和个人使用，请遵守安徽大学相关规定
