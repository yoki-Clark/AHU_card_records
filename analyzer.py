import pandas as pd
import numpy as np
import re
import unicodedata
from datetime import datetime


# ================= 辅助函数：终端绝对对齐算法 =================
def get_display_width(s):
    """计算字符串在终端中的实际显示宽度（全角字符算2个单位）"""
    s = str(s)
    width = 0
    for char in s:
        if unicodedata.east_asian_width(char) in ('F', 'W', 'A'):
            width += 2
        else:
            width += 1
    return width


def pad_with_fullwidth(s, max_len):
    """使用中文全角空格强制对齐，无视终端字体英文宽度偏差"""
    s = str(s)
    current_len = get_display_width(s)
    padding_needed = max_len - current_len

    # 全角空格补宽(每个占2单位宽度)，剩下的奇数用英文空格补
    full_spaces = padding_needed // 2
    half_spaces = padding_needed % 2

    return s + chr(12288) * full_spaces + ' ' * half_spaces


def print_aligned_table(df):
    """接管 DataFrame 打印，实现终端绝对对齐"""
    str_df = df.copy().fillna('-').astype(str)
    cols = [df.index.name if df.index.name else "索引"] + str_df.columns.tolist()
    str_df = str_df.reset_index()
    str_df.columns = cols

    # 获取每一列的最大所需宽度
    widths = [
        max([get_display_width(str(val)) for val in str_df.iloc[:, i].tolist()] + [get_display_width(cols[i])]) + 4 for
        i in range(len(cols))]

    # 打印表头
    header = "".join([pad_with_fullwidth(cols[i], widths[i]) for i in range(len(cols))])
    print(header)
    print("-" * (sum(widths) - 4))

    # 打印数据行
    for row in str_df.itertuples(index=False):
        row_str = "".join([pad_with_fullwidth(str(val), widths[i]) for i, val in enumerate(row)])
        print(row_str)


# ================= 数据分析核心逻辑 =================
def extract_base_canteen(location_name):
    if pd.isna(location_name): return None
    canteen_keywords = ['桔园', '榴园', '蕙园', '梅园', '桂园', '梧桐园']
    for keyword in canteen_keywords:
        if keyword in location_name: return f"{keyword}食堂"
    if "食堂" in location_name: return re.sub(r'[一二三四五]楼|餐厅', '', location_name)
    return None


def get_meal_period(dt):
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
    hour, minute = dt.hour, dt.minute
    return (hour - 4) * 60 + minute if hour >= 4 else (hour + 20) * 60 + minute


def minutes_to_time_str(logical_minutes):
    if pd.isna(logical_minutes): return "-"
    total_mins = (int(logical_minutes) + 4 * 60) % (24 * 60)
    return f"{total_mins // 60:02d}:{total_mins % 60:02d}"


def analyze_normalized_trend(df, time_col, period_name, n=4):
    """经过【有效日均】清洗的动态趋势分析"""
    # 按照周期进行聚合，求当期总支出和当期实际在校天数
    grouped = df.groupby(time_col).agg(
        总支出=('金额(元)', 'sum'),
        有效天数=('日期', 'nunique')
    )
    # 计算排除了离校空白期后的日均支出
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


def run_analysis(file_path):
    print("正在加载数据并执行综合分析...\n")
    try:
        df = pd.read_csv(file_path)
    except Exception as e:
        print(f"读取文件失败: {e}")
        return

    if df.empty: return

    df['金额(元)'] = pd.to_numeric(df['金额(元)'], errors='coerce')
    df['余额(元)'] = pd.to_numeric(df['余额(元)'], errors='coerce')
    df['交易时间'] = pd.to_datetime(df['交易时间'], errors='coerce')
    df = df.dropna(subset=['交易时间', '金额(元)'])
    df = df.sort_values(by='交易时间').reset_index(drop=True)

    expense_mask = df['交易类型'].isin(['消费', '二维码支付'])
    expenses_df = df[expense_mask].copy()

    if expenses_df.empty:
        print("未找到有效的消费记录。\n")
        return

    expenses_df['日期'] = expenses_df['交易时间'].dt.date
    expenses_df['星期数值'] = expenses_df['交易时间'].dt.dayofweek
    expenses_df['是否周末'] = expenses_df['星期数值'].apply(lambda x: '周末' if x >= 5 else '工作日')
    expenses_df['年月'] = expenses_df['交易时间'].dt.to_period('M')
    expenses_df['年周'] = expenses_df['交易时间'].dt.to_period('W-SUN')
    expenses_df['逻辑相对分钟数'] = expenses_df['交易时间'].apply(get_logical_day_minutes)
    expenses_df['主食堂名称'] = expenses_df['商户/地点'].apply(extract_base_canteen)
    expenses_df['餐段'] = expenses_df['交易时间'].apply(get_meal_period)

    # ================= 0. 离校期断点检测与全局概览 =================
    df['距上笔交易_天'] = df['交易时间'].diff().dt.total_seconds() / 86400
    GAP_THRESHOLD_DAYS = 3.0
    gaps = df[df['距上笔交易_天'] > GAP_THRESHOLD_DAYS]['距上笔交易_天']

    total_absolute_days = (df['交易时间'].max().date() - df['交易时间'].min().date()).days + 1
    total_absence_days = gaps.sum() if not gaps.empty else 0
    effective_days = max(total_absolute_days - total_absence_days, 1)

    recharge_mask = df['交易类型'] == '充值'
    recharge_df = df[recharge_mask]
    avg_recharge_per_txn = recharge_df['金额(元)'].mean() if not recharge_df.empty else 0
    total_expense = expenses_df['金额(元)'].sum()
    avg_expense_per_txn = expenses_df['金额(元)'].mean()

    print("================ 【全局概览与数据有效性】 ================")
    print(f"日历绝对时间跨度：{total_absolute_days} 天")
    print(f"剔除离校期：约 {total_absence_days:.1f} 天 (基于>{GAP_THRESHOLD_DAYS}天无交易判定)")
    print(f"实际有效在校天数：{effective_days:.1f} 天")
    print(f"累计总消费：{total_expense:.2f} 元")
    print(f"真实在校日均消费：{(total_expense / effective_days):.2f} 元/天")
    print(f"单笔平均消费：{avg_expense_per_txn:.2f} 元/笔")
    print(f"单笔平均充值：{avg_recharge_per_txn:.2f} 元/笔")
    print("\n")

    # ================= 1. 动态周期分析 (月度/周度环比) =================
    print("================ 【动态消费趋势分析】 ================")
    analyze_normalized_trend(expenses_df, '年月', '月度', n=4)
    print("")
    analyze_normalized_trend(expenses_df, '年周', '周度', n=5)
    print("\n")

    # ================= 2. 扩维：周一至周日分布对比 =================
    print("================ 【一周时间线（周一至周日）规律分布】 ================")

    # 第一步：计算每一天（日历维度）的消费总额和笔数
    daily_stats = expenses_df.groupby('日期').agg(
        单日总额=('金额(元)', 'sum'),
        单日笔数=('金额(元)', 'count'),
        星期数值=('星期数值', 'first')
    ).reset_index()

    # 第二步：按星期几去平均，得出“真实的均值”
    wd_group = daily_stats.groupby('星期数值').agg(
        日均支出=('单日总额', 'mean'),
        日均笔数=('单日笔数', 'mean'),
        样本天数=('日期', 'count')
    ).reset_index()

    # 第三步：计算星期维度的最常去地点（过滤空值）
    loc_df = expenses_df.dropna(subset=['商户/地点'])
    top_locs = loc_df.groupby('星期数值')['商户/地点'].apply(
        lambda x: x.mode()[0] if not x.empty else '-'
    ).reset_index(name='当日常客地点')

    wd_group = wd_group.merge(top_locs, on='星期数值', how='left')

    # 格式化收尾
    weekday_map = {0: '周一', 1: '周二', 2: '周三', 3: '周四', 4: '周五', 5: '周六', 6: '周日'}
    wd_group['星期'] = wd_group['星期数值'].map(weekday_map)
    wd_group['单笔均价'] = (wd_group['日均支出'] / wd_group['日均笔数']).round(2)

    wd_group = wd_group[['星期', '日均支出', '日均笔数', '单笔均价', '当日常客地点', '样本天数']]
    wd_group['日均支出'] = wd_group['日均支出'].round(2).astype(str) + " 元"
    wd_group['日均笔数'] = wd_group['日均笔数'].round(1).astype(str) + " 笔"
    wd_group['单笔均价'] = wd_group['单笔均价'].astype(str) + " 元"

    print_aligned_table(wd_group.set_index('星期'))
    print("\n")

    # ================= 3. 基础极值分析 =================
    max_expense = expenses_df.loc[expenses_df['金额(元)'].idxmax()]
    print("================ 【金额极值】 ================")
    print(f"最高单笔消费：{max_expense['金额(元)']} 元 ({max_expense['交易时间']} @ {max_expense['商户/地点']})")

    if not recharge_df.empty:
        max_recharge = recharge_df.loc[recharge_df['金额(元)'].idxmax()]
        print(f"最高单笔充值：{max_recharge['金额(元)']} 元 ({max_recharge['交易时间']})")
    print("\n")

    # ================= 4. 作息与消费时间分析 =================
    if not expenses_df.empty:
        earliest_idx = expenses_df['逻辑相对分钟数'].idxmin()
        latest_idx = expenses_df['逻辑相对分钟数'].idxmax()
        earliest_record = expenses_df.loc[earliest_idx]
        latest_record = expenses_df.loc[latest_idx]

        print("================ 【作息与消费时间】 ================")
        print(f"一天中最早的消费：{earliest_record['交易时间'].strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   -> 金额: {earliest_record['金额(元)']}元, 地点: {earliest_record['商户/地点']}")
        print(f"一天中最晚的消费 (熬夜极限)：{latest_record['交易时间'].strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   -> 金额: {latest_record['金额(元)']}元, 地点: {latest_record['商户/地点']}")

    canteen_df = expenses_df.dropna(subset=['主食堂名称'])
    if not canteen_df.empty:
        weekend_canteen = canteen_df[canteen_df['是否周末'] == '周末']
        workday_canteen = canteen_df[canteen_df['是否周末'] == '工作日']
        first_meal_wd = workday_canteen.groupby('日期')['逻辑相对分钟数'].min().mean()
        first_meal_we = weekend_canteen.groupby('日期')['逻辑相对分钟数'].min().mean()
        print(f"工作日首餐时间平均：{minutes_to_time_str(first_meal_wd)}")
        print(f"周末首餐时间平均：{minutes_to_time_str(first_meal_we)}")
    print("\n")

    # ================= 5. 资金燃烧率与充值习惯 =================
    print("================ 【财务习惯与资金续航】 ================")
    if len(recharge_df) > 1:
        recharge_df_copy = recharge_df.copy()
        recharge_df_copy['充值前余额'] = recharge_df_copy['余额(元)'] - recharge_df_copy['金额(元)']
        avg_trigger_balance = recharge_df_copy['充值前余额'].mean()
        print(f"财务习惯：平均在卡内余额剩余 {avg_trigger_balance:.2f} 元时触发充值。")

        total_recharge_amt = recharge_df_copy['金额(元)'].sum()
        if total_recharge_amt > 0:
            days_per_100 = (100 / total_expense) * effective_days
            print(f"充值续航：在校期间，平均每 100 元可支撑 {days_per_100:.1f} 天。")
    else:
        print("充值记录不足，无法计算资金续航。")
    print("\n")

    # ================= 6. 食堂三餐综合报表 =================
    if not canteen_df.empty:
        print("================ 【食堂三餐综合统计表】 ================")
        pivot_avg = pd.pivot_table(canteen_df, values='金额(元)', index='主食堂名称', columns='餐段',
                                   aggfunc='mean').round(2)
        pivot_count = pd.pivot_table(canteen_df, values='金额(元)', index='主食堂名称', columns='餐段', aggfunc='count',
                                     fill_value=0)

        for meal in ['早餐', '午餐', '晚餐']:
            if meal not in pivot_avg.columns: pivot_avg[meal] = np.nan
            if meal not in pivot_count.columns: pivot_count[meal] = 0

        total_count = canteen_df.groupby('主食堂名称').size()
        total_avg = canteen_df.groupby('主食堂名称')['金额(元)'].mean().round(2)

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
                avg_time_str = minutes_to_time_str(avg_logic_mins)
                print(f"[{meal}] 最常去食堂: {fav_canteen:<6} | 平均就餐时间: {avg_time_str}")
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
        print("\n")

    else:
        print("未识别到清晰的食堂消费数据。\n")

    # ================= 7. 非食堂消费汇总 =================
    non_canteen_df = expenses_df[expenses_df['主食堂名称'].isna()]
    if not non_canteen_df.empty:
        print("================ 【非食堂消费明细汇总】 ================")
        nc_stats = non_canteen_df.groupby('商户/地点')['金额(元)'].agg(['count', 'mean', 'sum']).round(2)
        nc_stats.columns = ['总次数', '平均金额(元)', '累计金额(元)']
        nc_stats = nc_stats.sort_values(by='累计金额(元)', ascending=False)
        print_aligned_table(nc_stats)
    else:
        print("无非食堂消费记录。")


if __name__ == "__main__":
    run_analysis()
