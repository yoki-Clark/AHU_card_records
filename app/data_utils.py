"""Shared data loading, constants, and formatting utilities."""
import os
import re
import unicodedata
from enum import Enum

import pandas as pd

# ==================== Constants ====================

CONFIG_DIR = 'config'
CONFIG_PATTERN = re.compile(r'^config_[A-Za-z0-9_]+\.json$')

CANTEEN_KEYWORDS = ['桔园', '榴园', '蕙园', '梅园', '桂园', '梧桐园']

CANTEEN_MAPPING = {
    "北一区": "桔园",
    "北二区": "榴园",
    "北三区": "蕙园",
    "南一区": "梅园",
    "南二区": "桂园",
    "南三区": "梧桐园"
}

EXPENSE_TYPES = ['消费', '二维码支付']

COL = {
    'amount': '金额(元)',
    'balance': '余额(元)',
    'time': '交易时间',
    'type': '交易类型',
    'merchant': '商户/地点',
    'description': '详情描述',
    'order_id': '流水号',
    'status': '订单状态',
}


class CrawlMode(Enum):
    FULL = '1'
    INCREMENTAL = '2'


# ==================== Terminal Formatting ====================

def get_display_width(s):
    s = str(s)
    width = 0
    for char in s:
        if unicodedata.east_asian_width(char) in ('F', 'W', 'A'):
            width += 2
        else:
            width += 1
    return width


def pad_with_fullwidth(s, max_len):
    s = str(s)
    current_len = get_display_width(s)
    padding_needed = max_len - current_len
    full_spaces = padding_needed // 2
    half_spaces = padding_needed % 2
    return s + chr(12288) * full_spaces + ' ' * half_spaces


def print_aligned_table(df):
    str_df = df.copy().fillna('-').astype(str)
    cols = [df.index.name if df.index.name else "索引"] + str_df.columns.tolist()
    str_df = str_df.reset_index()
    str_df.columns = cols

    widths = [
        max([get_display_width(str(val)) for val in str_df.iloc[:, i].tolist()] + [get_display_width(cols[i])]) + 4
        for i in range(len(cols))
    ]

    header = "".join([pad_with_fullwidth(cols[i], widths[i]) for i in range(len(cols))])
    print(header)
    print("-" * (sum(widths) - 4))

    for row in str_df.itertuples(index=False):
        row_str = "".join([pad_with_fullwidth(str(val), widths[i]) for i, val in enumerate(row)])
        print(row_str)


# ==================== Data Loading ====================

def load_and_prepare_expenses(file_path, extra_columns=None):
    """Load CSV, clean types, filter expenses, return (full_df, expenses_df).

    extra_columns: optional list of column names to compute on expenses_df.
    Returns the raw full df and the filtered expense-only df.
    Callers can add their own module-specific columns afterward.
    """
    df = pd.read_csv(file_path)

    if df.empty:
        return df, pd.DataFrame()

    df[COL['amount']] = pd.to_numeric(df[COL['amount']], errors='coerce')
    df[COL['balance']] = pd.to_numeric(df[COL['balance']], errors='coerce')
    df[COL['time']] = pd.to_datetime(df[COL['time']], errors='coerce')
    df = df.dropna(subset=[COL['time'], COL['amount']])
    df = df.sort_values(by=COL['time']).reset_index(drop=True)

    expense_mask = df[COL['type']].isin(EXPENSE_TYPES)
    expenses_df = df[expense_mask].copy()

    if expenses_df.empty:
        return df, expenses_df

    expenses_df['日期'] = expenses_df[COL['time']].dt.date
    expenses_df['星期数值'] = expenses_df[COL['time']].dt.dayofweek
    expenses_df['是否周末'] = expenses_df['星期数值'].apply(lambda x: '周末' if x >= 5 else '工作日')
    expenses_df['年月'] = expenses_df[COL['time']].dt.to_period('M')

    return df, expenses_df


def classify_canteen(name):
    """Classify a merchant name into a canteen category."""
    if pd.isna(name):
        return '其他'
    for kw in CANTEEN_KEYWORDS:
        if kw in str(name):
            return f'{kw}食堂'
    if '食堂' in str(name):
        return '其他食堂'
    return '其他'


def extract_base_canteen(location_name):
    """Extract canteen name from a location string. Returns None if not a canteen."""
    if pd.isna(location_name):
        return None
    for keyword in CANTEEN_KEYWORDS:
        if keyword in location_name:
            return f"{keyword}食堂"
    if "食堂" in location_name:
        return re.sub(r'[一二三四五]楼|餐厅', '', location_name)
    return None


def replace_canteen_name(text):
    """Replace internal canteen codes with human-readable names."""
    if not text:
        return text
    for old_name, new_name in CANTEEN_MAPPING.items():
        if old_name in text:
            text = text.replace(old_name, new_name)
    return text


# ==================== Logging ====================

def print_log(msg):
    from datetime import datetime
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
