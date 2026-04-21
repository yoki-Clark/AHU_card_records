import pandas as pd
import numpy as np
import re
from datetime import datetime


def extract_base_canteen(location_name):
    """提取基础食堂名称"""
    if pd.isna(location_name):
        return None

    canteen_keywords = ['桔园', '榴园', '蕙园', '梅园', '桂园', '梧桐园']
    for keyword in canteen_keywords:
        if keyword in location_name:
            return f"{keyword}食堂"

    if "食堂" in location_name:
        return re.sub(r'[一二三四五]楼|餐厅', '', location_name)

    return None


def get_meal_period(dt):
    """根据时间界定三餐"""
    hour = dt.hour
    if 5 <= hour < 10:
        return '早餐'
    elif 10 <= hour < 15:
        return '午餐'
    elif hour >= 17 or hour < 4:
        return '晚餐'
    else:
        return '其他时段'


def get_logical_day_minutes(dt):
    """
    计算基于凌晨 4 点起点的相对分钟数。
    04:00 -> 0分钟
    23:59 -> 1199分钟
    次日 03:59 -> 1439分钟
    """
    hour = dt.hour
    minute = dt.minute
    if hour >= 4:
        return (hour - 4) * 60 + minute
    else:
        return (hour + 20) * 60 + minute


def minutes_to_time_str(logical_minutes):
    """将基于 4 点的相对分钟数还原为 24小时制时间字符串"""
    if pd.isna(logical_minutes):
        return "-"
    total_mins = (int(logical_minutes) + 4 * 60) % (24 * 60)
    hour = total_mins // 60
    minute = total_mins % 60
    return f"{hour:02d}:{minute:02d}"


def run_analysis(file_path):
    print("正在加载数据并进行深度分析...\n")
    try:
        df = pd.read_csv(file_path)
    except Exception as e:
        print(f"读取文件失败: {e}")
        return

    if df.empty:
        print("记录为空，无法分析。")
        return

    # 数据预处理
    df['金额(元)'] = pd.to_numeric(df['金额(元)'], errors='coerce')
    df['交易时间'] = pd.to_datetime(df['交易时间'], errors='coerce')
    df = df.dropna(subset=['交易时间', '金额(元)'])

    expense_mask = df['交易类型'].isin(['消费', '二维码支付'])
    expenses_df = df[expense_mask].copy()

    if expenses_df.empty:
        print("未找到有效的消费记录。\n")
        return

    # ================= 1. 基础极值分析 =================
    max_expense = expenses_df.loc[expenses_df['金额(元)'].idxmax()]
    print("================ 【金额极值】 ================")
    print(f"💰 最高单笔消费：{max_expense['金额(元)']} 元 ({max_expense['交易时间']} @ {max_expense['商户/地点']})")

    recharge_mask = df['交易类型'] == '充值'
    recharge_df = df[recharge_mask]
    if not recharge_df.empty:
        max_recharge = recharge_df.loc[recharge_df['金额(元)'].idxmax()]
        print(f"💳 最高单笔充值：{max_recharge['金额(元)']} 元 ({max_recharge['交易时间']})")
    print("\n")

    # ================= 2. 熬夜与早起极限时间分析 =================
    expenses_df['逻辑相对分钟数'] = expenses_df['交易时间'].apply(get_logical_day_minutes)
    earliest_idx = expenses_df['逻辑相对分钟数'].idxmin()
    latest_idx = expenses_df['逻辑相对分钟数'].idxmax()

    earliest_record = expenses_df.loc[earliest_idx]
    latest_record = expenses_df.loc[latest_idx]

    print("================ 【作息与消费时间】 ================")
    print(f"🌅 一天中最早的消费：{earliest_record['交易时间'].strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   -> 金额: {earliest_record['金额(元)']}元, 地点: {earliest_record['商户/地点']}")
    print(f"🦉 一天中最晚的消费 (熬夜极限)：{latest_record['交易时间'].strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   -> 金额: {latest_record['金额(元)']}元, 地点: {latest_record['商户/地点']}")
    print("\n")

    # 数据标记准备
    expenses_df['主食堂名称'] = expenses_df['商户/地点'].apply(extract_base_canteen)
    expenses_df['餐段'] = expenses_df['交易时间'].apply(get_meal_period)
    canteen_df = expenses_df.dropna(subset=['主食堂名称'])

    # ================= 3. 食堂三餐综合报表 =================
    if not canteen_df.empty:
        print("================ 【食堂三餐综合统计表】 ================")
        # 生成透视表获取均值和次数
        pivot_avg = pd.pivot_table(canteen_df, values='金额(元)', index='主食堂名称', columns='餐段',
                                   aggfunc='mean').round(2)
        pivot_count = pd.pivot_table(canteen_df, values='金额(元)', index='主食堂名称', columns='餐段', aggfunc='count',
                                     fill_value=0)

        # 补全列
        for meal in ['早餐', '午餐', '晚餐']:
            if meal not in pivot_avg.columns: pivot_avg[meal] = np.nan
            if meal not in pivot_count.columns: pivot_count[meal] = 0

        # 计算总计数据
        total_count = canteen_df.groupby('主食堂名称').size()
        total_avg = canteen_df.groupby('主食堂名称')['金额(元)'].mean().round(2)

        # 组装最终报表
        canteen_summary = pd.DataFrame({
            '早均(元)': pivot_avg['早餐'],
            '早次数': pivot_count['早餐'].astype(int),
            '中均(元)': pivot_avg['午餐'],
            '中次数': pivot_count['午餐'].astype(int),
            '晚均(元)': pivot_avg['晚餐'],
            '晚次数': pivot_count['晚餐'].astype(int),
            '总次数': total_count,
            '总均(元)': total_avg
        }).fillna('-')

        print(canteen_summary.to_string())
        print("\n")

        # ================= 4. 三餐视角统筹分析 =================
        print("================ 【三餐偏好与时间规律】 ================")
        for meal in ['早餐', '午餐', '晚餐']:
            meal_df = canteen_df[canteen_df['餐段'] == meal]
            if not meal_df.empty:
                fav_canteen = meal_df['主食堂名称'].value_counts().idxmax()
                avg_logic_mins = meal_df['逻辑相对分钟数'].mean()
                avg_time_str = minutes_to_time_str(avg_logic_mins)
                print(f"[{meal}] 最常去食堂: {fav_canteen:<6} | 平均就餐时间: {avg_time_str}")
        print("\n")
    else:
        print("🍽️ 未识别到清晰的食堂消费数据。\n")

    # ================= 5. 非食堂消费汇总 =================
    non_canteen_df = expenses_df[expenses_df['主食堂名称'].isna()]
    if not non_canteen_df.empty:
        print("================ 【非食堂消费明细汇总】 ================")
        nc_stats = non_canteen_df.groupby('商户/地点')['金额(元)'].agg(['count', 'mean']).round(2)
        nc_stats.columns = ['总次数', '平均金额(元)']
        nc_stats = nc_stats.sort_values(by='总次数', ascending=False)
        print(nc_stats.to_string())
    else:
        print("📦 无非食堂消费记录。")

    print("\n分析结束，按任意键返回主菜单...")
    input()


if __name__ == "__main__":
    run_analysis('campus_card_records.csv')
