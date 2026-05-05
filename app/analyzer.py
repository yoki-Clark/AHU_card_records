"""Campus card expense analysis — 7-section textual report."""
import numpy as np
import pandas as pd
from datetime import datetime

from app.data_utils import (COL, EXPENSE_TYPES, load_and_prepare_expenses,
                            extract_base_canteen, print_aligned_table)

__all__ = [
    'get_meal_period',
    'get_logical_day_minutes',
    'minutes_to_time_str',
    'analyze_normalized_trend',
    'run_analysis',
]

# ==================== Helpers ====================

def get_meal_period(dt):
    hour = dt.hour
    if 5 <= hour < 10:
        return '早餐'
    if 10 <= hour < 15:
        return '午餐'
    if hour >= 17 or hour < 4:
        return '晚餐'
    return '其他时段'


def get_logical_day_minutes(dt):
    hour, minute = dt.hour, dt.minute
    return (hour - 4) * 60 + minute if hour >= 4 else (hour + 20) * 60 + minute


def minutes_to_time_str(logical_minutes):
    if pd.isna(logical_minutes):
        return "-"
    total_mins = (int(logical_minutes) + 4 * 60) % (24 * 60)
    return f"{total_mins // 60:02d}:{total_mins % 60:02d}"


# ==================== Trend Analysis (shared helper) ====================

def analyze_normalized_trend(df, time_col, period_name, n=4):
    grouped = df.groupby(time_col).agg(
        总支出=(COL['amount'], 'sum'),
        有效天数=('日期', 'nunique')
    )
    grouped['有效日均(元/天)'] = (grouped['总支出'] / grouped['有效天数']).round(2)

    if len(grouped) < 2:
        print(f"数据跨度不足以进行{period_name}对比。")
        return

    recent = grouped.tail(n)
    print(f"--- 近期连续 {len(recent)} {period_name} 【有效日均支出】趋势 ---")

    for i in range(len(recent)):
        period_str = str(recent.index[i])
        val = recent['有效日均(元/天)'].iloc[i]
        days = recent['有效天数'].iloc[i]
        if i == 0:
            print(f"[{period_str}] 日均: {val:>6.2f} 元 (基于{days:>2}天有效数据)")
        else:
            prev_val = recent['有效日均(元/天)'].iloc[i - 1]
            change = (val - prev_val) / prev_val if prev_val != 0 else 0
            sign = "+" if change > 0 else ""
            print(f"[{period_str}] 日均: {val:>6.2f} 元 (基于{days:>2}天有效数据) | 环比: {sign}{change:>6.1%}")

    completed_periods = grouped.iloc[:-1]
    if not completed_periods.empty:
        avg_completed = completed_periods['有效日均(元/天)'].mean()
        print(f"\n*(注：为避免最新一期未结束导致数据不准，均值计算已剔除最后一期)*")
        print(f"历史完整期平均支出：{avg_completed:.2f} 元/天")


# ==================== Section Methods ====================

def _section_overview(df, expenses_df, gaps, holiday_gaps,
                      effective_days, total_expense, recharge_df, gap_threshold, holiday_threshold):
    total_absence_days = gaps['距上笔交易_天'].sum() if not gaps.empty else 0
    total_holiday_days = holiday_gaps['距上笔交易_天'].sum() if not holiday_gaps.empty else 0
    avg_recharge_per_txn = recharge_df[COL['amount']].mean() if not recharge_df.empty else 0
    avg_expense_per_txn = expenses_df[COL['amount']].mean()

    print("================ 【全局概览与数据有效性】 ================")
    print(f"日历绝对时间跨度：{(df[COL['time']].max().date() - df[COL['time']].min().date()).days + 1} 天")
    print(f"短时离校 (>{gap_threshold}天且≤{holiday_threshold}天)：约 {total_absence_days - total_holiday_days:.1f} 天")
    print(f"长假/假期 (>{holiday_threshold}天)：约 {total_holiday_days:.1f} 天")
    if not holiday_gaps.empty:
        print("假期时段：")
        for _, row in holiday_gaps.iterrows():
            start_date = row[COL['time']] - pd.Timedelta(days=row['距上笔交易_天'])
            print(f"  {start_date.date()} ~ {row[COL['time']].date()} ({row['距上笔交易_天']:.1f} 天)")
    print(f"实际有效在校天数：{effective_days:.1f} 天")
    print(f"累计总消费：{total_expense:.2f} 元")
    print(f"真实在校日均消费：{(total_expense / effective_days):.2f} 元/天")
    print(f"单笔平均消费：{avg_expense_per_txn:.2f} 元/笔")
    print(f"单笔平均充值：{avg_recharge_per_txn:.2f} 元/笔")
    print("\n")


def _section_trend(expenses_df):
    print("================ 【动态消费趋势分析】 ================")
    analyze_normalized_trend(expenses_df, '年月', '月度', n=4)
    print("")
    analyze_normalized_trend(expenses_df, '年周', '周度', n=5)
    print("\n")


def _section_weekday(expenses_df, daily_stats):
    print("================ 【一周时间线（周一至周日）规律分布】 ================")

    wd_group = daily_stats.groupby('星期数值').agg(
        日均支出=('单日总额', 'mean'),
        日均笔数=('单日笔数', 'mean'),
        样本天数=('日期', 'count')
    ).reset_index()

    loc_df = expenses_df.dropna(subset=[COL['merchant']])
    top_locs = loc_df.groupby('星期数值')[COL['merchant']].apply(
        lambda x: x.mode()[0] if not x.empty else '-'
    ).reset_index(name='当日常客地点')

    wd_group = wd_group.merge(top_locs, on='星期数值', how='left')

    weekday_map = {0: '周一', 1: '周二', 2: '周三', 3: '周四', 4: '周五', 5: '周六', 6: '周日'}
    wd_group['星期'] = wd_group['星期数值'].map(weekday_map)
    wd_group['单笔均价'] = (wd_group['日均支出'] / wd_group['日均笔数']).round(2)

    wd_group = wd_group[['星期', '日均支出', '日均笔数', '单笔均价', '当日常客地点', '样本天数']]
    wd_group['日均支出'] = wd_group['日均支出'].round(2).astype(str) + " 元"
    wd_group['日均笔数'] = wd_group['日均笔数'].round(1).astype(str) + " 笔"
    wd_group['单笔均价'] = wd_group['单笔均价'].astype(str) + " 元"

    print_aligned_table(wd_group.set_index('星期'))
    print("\n")


def _section_extremes(expenses_df, recharge_df):
    max_expense = expenses_df.loc[expenses_df[COL['amount']].idxmax()]
    print("================ 【金额极值】 ================")
    print(f"最高单笔消费：{max_expense[COL['amount']]} 元 "
          f"({max_expense[COL['time']]} @ {max_expense[COL['merchant']]})")

    if not recharge_df.empty:
        max_recharge = recharge_df.loc[recharge_df[COL['amount']].idxmax()]
        print(f"最高单笔充值：{max_recharge[COL['amount']]} 元 ({max_recharge[COL['time']]})")
    print("\n")


def _section_daily_rhythm(expenses_df, canteen_df):
    earliest_idx = expenses_df['逻辑相对分钟数'].idxmin()
    latest_idx = expenses_df['逻辑相对分钟数'].idxmax()
    earliest_record = expenses_df.loc[earliest_idx]
    latest_record = expenses_df.loc[latest_idx]

    print("================ 【作息与消费时间】 ================")
    print(f"一天中最早的消费：{earliest_record[COL['time']].strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   -> 金额: {earliest_record[COL['amount']]}元, 地点: {earliest_record[COL['merchant']]}")
    print(f"一天中最晚的消费 (熬夜极限)：{latest_record[COL['time']].strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   -> 金额: {latest_record[COL['amount']]}元, 地点: {latest_record[COL['merchant']]}")

    if not canteen_df.empty:
        weekend_canteen = canteen_df[canteen_df['是否周末'] == '周末']
        workday_canteen = canteen_df[canteen_df['是否周末'] == '工作日']
        first_meal_wd = workday_canteen.groupby('日期')['逻辑相对分钟数'].min().mean()
        first_meal_we = weekend_canteen.groupby('日期')['逻辑相对分钟数'].min().mean()
        print(f"工作日首餐时间平均：{minutes_to_time_str(first_meal_wd)}")
        print(f"周末首餐时间平均：{minutes_to_time_str(first_meal_we)}")
    print("\n")


def _section_finance(expenses_df, recharge_df, effective_days, total_expense):
    print("================ 【财务习惯与资金续航】 ================")
    if len(recharge_df) <= 1:
        print("充值记录不足，无法计算资金续航。")
        print("\n")
        return

    recharge_df_copy = recharge_df.copy()
    recharge_df_copy['充值前余额'] = recharge_df_copy[COL['balance']] - recharge_df_copy[COL['amount']]
    avg_trigger_balance = recharge_df_copy['充值前余额'].mean()
    print(f"财务习惯：平均在卡内余额剩余 {avg_trigger_balance:.2f} 元时触发充值。")

    total_recharge_amt = recharge_df_copy[COL['amount']].sum()
    if total_recharge_amt > 0:
        days_per_100 = (100 / total_expense) * effective_days
        print(f"充值续航：在校期间，平均每 100 元可支撑 {days_per_100:.1f} 天。")

    daily_avg = total_expense / effective_days
    today = datetime.now()
    days_in_month = pd.Period(today.strftime('%Y-%m')).days_in_month
    days_left = days_in_month - today.day
    predicted = daily_avg * days_left
    print(f"\n--- 【预算预测】 ---")
    print(f"参考日均消费：{daily_avg:.2f} 元/天")
    print(f"本月剩余天数：{days_left} 天")
    print(f"预估本月还需：{predicted:.2f} 元")
    if '年周' in expenses_df.columns:
        recent_4w = expenses_df[expenses_df['年周'].isin(expenses_df['年周'].unique()[-4:])]
        if not recent_4w.empty:
            recent_days = recent_4w['日期'].nunique()
            recent_avg = recent_4w[COL['amount']].sum() / max(recent_days, 1)
            print(f"近4周日均消费：{recent_avg:.2f} 元/天")
            print(f"基于近4周趋势预估本月还需：{recent_avg * days_left:.2f} 元")
    print("\n")


def _section_canteen(expenses_df, canteen_df):
    if canteen_df.empty:
        print("未识别到清晰的食堂消费数据。\n")
        return

    print("================ 【食堂三餐综合统计表】 ================")
    pivot_avg = pd.pivot_table(canteen_df, values=COL['amount'], index='主食堂名称',
                               columns='餐段', aggfunc='mean').round(2)
    pivot_count = pd.pivot_table(canteen_df, values=COL['amount'], index='主食堂名称',
                                 columns='餐段', aggfunc='count', fill_value=0)

    for meal in ['早餐', '午餐', '晚餐']:
        if meal not in pivot_avg.columns:
            pivot_avg[meal] = np.nan
        if meal not in pivot_count.columns:
            pivot_count[meal] = 0

    total_count = canteen_df.groupby('主食堂名称').size()
    total_avg = canteen_df.groupby('主食堂名称')[COL['amount']].mean().round(2)

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

    print_aligned_table(canteen_summary)
    print("\n")

    print("================ 【三餐偏好与时间规律】 ================")
    for meal in ['早餐', '午餐', '晚餐']:
        meal_df = canteen_df[canteen_df['餐段'] == meal]
        if not meal_df.empty:
            fav_canteen = meal_df['主食堂名称'].value_counts().idxmax()
            avg_logic_mins = meal_df['逻辑相对分钟数'].mean()
            print(f"[{meal}] 最常去食堂: {fav_canteen:<6} | 平均就餐时间: {minutes_to_time_str(avg_logic_mins)}")
    print("\n")

    print("================ 【饮食轨迹专一度】 ================")
    canteen_counts = canteen_df['主食堂名称'].value_counts(normalize=True)
    top_canteen = canteen_counts.index[0]
    top_ratio = canteen_counts.iloc[0]
    print(f"饮食专一指数：{top_ratio:.1%} 的食堂消费发生在 [{top_canteen}]")
    if top_ratio > 0.6:
        print("数据判断：就餐轨迹高度集中，倾向于固定区域就餐。")
    elif top_ratio < 0.3:
        print("数据判断：就餐轨迹分散，倾向于在多个食堂间切换。")

    # Canteen loyalty over time
    print("\n--- 【食堂忠诚度月度变化】 ---")
    monthly_canteen = canteen_df.groupby(['年月', '主食堂名称']).size().unstack(fill_value=0)
    if len(monthly_canteen) >= 2:
        monthly_share = monthly_canteen.div(monthly_canteen.sum(axis=1), axis=0)
        top3 = canteen_df['主食堂名称'].value_counts().head(3).index.tolist()
        top3 = [c for c in top3 if c in monthly_share.columns]
        loyalty_table = monthly_share[top3].copy()
        loyalty_table.index = [str(idx) for idx in loyalty_table.index]
        loyalty_table = (loyalty_table * 100).round(1).astype(str)
        loyalty_table = loyalty_table.apply(lambda col: col + '%')
        print_aligned_table(loyalty_table)
    print("\n")


def _section_noncanteen(expenses_df):
    non_canteen_df = expenses_df[expenses_df['主食堂名称'].isna()]
    if not non_canteen_df.empty:
        print("================ 【非食堂消费明细汇总】 ================")
        nc_stats = non_canteen_df.groupby(COL['merchant'])[COL['amount']].agg(
            ['count', 'mean', 'sum']).round(2)
        nc_stats.columns = ['总次数', '平均金额(元)', '累计金额(元)']
        nc_stats = nc_stats.sort_values(by='累计金额(元)', ascending=False)
        print_aligned_table(nc_stats)
    else:
        print("无非食堂消费记录。")
    print("\n")


# ==================== Main Entry Point ====================

def run_analysis(file_path, gap_threshold=3.0, holiday_threshold=30.0):
    """Load data and produce a 7-section analysis report to stdout."""
    print("正在加载数据并执行综合分析...\n")

    df, expenses_df = load_and_prepare_expenses(file_path)

    if expenses_df.empty:
        print("未找到有效的消费记录。\n")
        return

    # --- Add computed columns to expenses_df ---
    expenses_df['年周'] = expenses_df[COL['time']].dt.to_period('W-SUN')
    expenses_df['逻辑相对分钟数'] = expenses_df[COL['time']].apply(get_logical_day_minutes)
    expenses_df['主食堂名称'] = expenses_df[COL['merchant']].apply(extract_base_canteen)
    expenses_df['餐段'] = expenses_df[COL['time']].apply(get_meal_period)

    # --- Add gap column to full df for overview ---
    df['距上笔交易_天'] = df[COL['time']].diff().dt.total_seconds() / 86400

    # --- Pre-compute shared DataFrames / stats ---
    gaps = df[df['距上笔交易_天'] > gap_threshold]
    holiday_gaps = df[df['距上笔交易_天'] > holiday_threshold]
    total_absolute_days = (df[COL['time']].max().date() - df[COL['time']].min().date()).days + 1
    total_absence_days = gaps['距上笔交易_天'].sum() if not gaps.empty else 0
    effective_days = max(total_absolute_days - total_absence_days, 1)

    recharge_mask = df[COL['type']] == '充值'
    recharge_df = df[recharge_mask]
    total_expense = expenses_df[COL['amount']].sum()

    # Daily stats — used by section 2 (weekday) and available for reuse
    daily_stats = expenses_df.groupby('日期').agg(
        单日总额=(COL['amount'], 'sum'),
        单日笔数=(COL['amount'], 'count'),
        星期数值=('星期数值', 'first')
    ).reset_index()

    # Canteen-only DataFrame — used by sections 4, 6, 7
    canteen_df = expenses_df.dropna(subset=['主食堂名称'])

    # --- Produce report ---
    _section_overview(df, expenses_df, gaps, holiday_gaps,
                      effective_days, total_expense, recharge_df,
                      gap_threshold, holiday_threshold)
    _section_trend(expenses_df)
    _section_weekday(expenses_df, daily_stats)
    _section_extremes(expenses_df, recharge_df)
    _section_daily_rhythm(expenses_df, canteen_df)
    _section_finance(expenses_df, recharge_df, effective_days, total_expense)
    _section_canteen(expenses_df, canteen_df)
    _section_noncanteen(expenses_df)


if __name__ == "__main__":
    run_analysis()
