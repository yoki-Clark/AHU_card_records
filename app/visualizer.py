import os
from concurrent.futures import ThreadPoolExecutor

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from app.data_utils import load_and_prepare_expenses, classify_canteen, COL

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'WenQuanYi Micro Hei', 'Noto Sans CJK SC', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

OUTPUT_DIR = 'charts'


def _ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def _prepare_visualization_data(expenses_df):
    """Add visualization-specific columns to the expenses dataframe."""
    expenses_df['小时'] = expenses_df[COL['time']].dt.hour
    expenses_df['消费类别'] = expenses_df[COL['merchant']].apply(classify_canteen)
    return expenses_df


# ==================== Chart Functions ====================

def _chart_monthly_trend(expenses_df):
    monthly = expenses_df.groupby('年月').agg(
        总支出=(COL['amount'], 'sum'),
        有效天数=('日期', 'nunique')
    )
    monthly['有效日均'] = monthly['总支出'] / monthly['有效天数']

    fig, ax = plt.subplots(figsize=(12, 5))
    x_labels = [str(m) for m in monthly.index]
    ax.plot(x_labels, monthly['有效日均'], marker='o', linewidth=2, color='#2c7bb6')
    ax.fill_between(range(len(x_labels)), monthly['有效日均'], alpha=0.15, color='#2c7bb6')
    ax.axhline(y=monthly['有效日均'].mean(), color='#d7191c', linestyle='--',
              linewidth=1, label=f"均值: {monthly['有效日均'].mean():.2f} 元/天")
    ax.set_title('月度有效日均消费趋势', fontsize=14, fontweight='bold')
    ax.set_ylabel('有效日均消费 (元)')
    ax.legend()
    ax.grid(axis='y', alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    path = os.path.join(OUTPUT_DIR, 'monthly_trend.png')
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  [OK] 月度趋势图 -> {path}")


def _chart_canteen_pie(expenses_df):
    canteen = expenses_df[expenses_df['消费类别'] != '其他'].copy()
    if canteen.empty:
        print("  [跳过] 无食堂数据，跳过饼图。")
        return
    counts = canteen.groupby('消费类别').agg(
        消费总额=(COL['amount'], 'sum'),
        消费次数=(COL['amount'], 'count')
    ).sort_values('消费总额', ascending=False)

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    colors = ['#2c7bb6', '#abd9e9', '#fdae61', '#d7191c', '#5e3c99', '#b2abd2', '#33a02c']

    axes[0].pie(counts['消费总额'], labels=counts.index, autopct='%1.1f%%',
               startangle=90, colors=colors[:len(counts)])
    axes[0].set_title('各食堂消费金额占比', fontsize=13, fontweight='bold')

    axes[1].pie(counts['消费次数'], labels=counts.index, autopct='%1.1f%%',
               startangle=90, colors=colors[:len(counts)])
    axes[1].set_title('各食堂消费次数占比', fontsize=13, fontweight='bold')

    fig.tight_layout()
    path = os.path.join(OUTPUT_DIR, 'canteen_pie.png')
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  [OK] 食堂占比图 -> {path}")


def _chart_weekday_comparison(expenses_df):
    daily = expenses_df.groupby('日期').agg(
        单日总额=(COL['amount'], 'sum'),
        单日笔数=(COL['amount'], 'count'),
        星期数值=('星期数值', 'first'),
    ).reset_index()

    wd_group = daily.groupby('星期数值').agg(
        日均支出=('单日总额', 'mean'),
        日均笔数=('单日笔数', 'mean')
    ).reindex(range(7))

    weekday_labels = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
    colors = ['#2c7bb6' if i < 5 else '#d7191c' for i in range(7)]

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    axes[0].bar(weekday_labels, wd_group['日均支出'], color=colors)
    axes[0].set_title('星期日均消费金额', fontsize=13, fontweight='bold')
    axes[0].set_ylabel('日均消费 (元)')
    axes[0].axhline(y=wd_group['日均支出'].mean(), color='gray', linestyle='--', linewidth=1)
    axes[0].grid(axis='y', alpha=0.3)

    axes[1].bar(weekday_labels, wd_group['日均笔数'], color=colors)
    axes[1].set_title('星期日均消费笔数', fontsize=13, fontweight='bold')
    axes[1].set_ylabel('日均笔数')
    axes[1].axhline(y=wd_group['日均笔数'].mean(), color='gray', linestyle='--', linewidth=1)
    axes[1].grid(axis='y', alpha=0.3)

    fig.tight_layout()
    path = os.path.join(OUTPUT_DIR, 'weekday_comparison.png')
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  [OK] 星期对比图 -> {path}")


def _chart_hourly_heatmap(expenses_df):
    heatmap_data = expenses_df.groupby(['星期数值', '小时']).agg(
        消费总额=(COL['amount'], 'sum')
    ).reset_index()

    pivot = heatmap_data.pivot(index='星期数值', columns='小时', values='消费总额').fillna(0)
    pivot = pivot.reindex(index=range(7), fill_value=0)
    for h in range(24):
        if h not in pivot.columns:
            pivot[h] = 0
    pivot = pivot[sorted(pivot.columns)]

    weekday_labels = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

    fig, ax = plt.subplots(figsize=(14, 4))
    im = ax.imshow(pivot.values, cmap='YlOrRd', aspect='auto')

    ax.set_xticks(range(24))
    ax.set_xticklabels([f'{h}:00' for h in range(24)], rotation=45, fontsize=8)
    ax.set_yticks(range(7))
    ax.set_yticklabels(weekday_labels, fontsize=10)
    ax.set_xlabel('小时')
    ax.set_title('消费时段热力图 (按星期 × 小时)', fontsize=14, fontweight='bold')

    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label('累计消费金额 (元)')

    fig.tight_layout()
    path = os.path.join(OUTPUT_DIR, 'hourly_heatmap.png')
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  [OK] 时段热力图 -> {path}")


_CHART_FUNCTIONS = [_chart_monthly_trend, _chart_canteen_pie,
                    _chart_weekday_comparison, _chart_hourly_heatmap]


def run_visualization(file_path):
    print("正在加载数据并生成可视化图表...\n")
    try:
        df, expenses_df = load_and_prepare_expenses(file_path)
    except Exception as e:
        print(f"读取文件失败: {e}")
        return

    if expenses_df.empty:
        print("未找到有效的消费记录。")
        return

    _ensure_output_dir()
    _prepare_visualization_data(expenses_df)

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(fn, expenses_df) for fn in _CHART_FUNCTIONS]
        for future in futures:
            future.result()

    print(f"\n所有图表已保存至 {OUTPUT_DIR}/ 目录。")


if __name__ == "__main__":
    run_visualization()
