import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from datetime import datetime
import pandas as pd
from app.data_utils import (get_display_width, pad_with_fullwidth,
                            extract_base_canteen, replace_canteen_name, classify_canteen)
from app.analyzer import get_meal_period, get_logical_day_minutes, minutes_to_time_str


class TestDisplayWidth(unittest.TestCase):
    def test_ascii_only(self):
        self.assertEqual(get_display_width("hello"), 5)

    def test_chinese_only(self):
        self.assertEqual(get_display_width("你好"), 4)

    def test_mixed(self):
        self.assertEqual(get_display_width("hello你好"), 9)

    def test_empty(self):
        self.assertEqual(get_display_width(""), 0)

    def test_number(self):
        self.assertEqual(get_display_width("123"), 3)


class TestPadWithFullwidth(unittest.TestCase):
    def test_no_padding_needed(self):
        result = pad_with_fullwidth("你好", 4)
        self.assertEqual(get_display_width(result), 4)

    def test_padding_ascii(self):
        result = pad_with_fullwidth("ab", 6)
        self.assertEqual(get_display_width(result), 6)

    def test_padding_chinese(self):
        result = pad_with_fullwidth("你好", 8)
        self.assertEqual(get_display_width(result), 8)


class TestExtractBaseCanteen(unittest.TestCase):
    def test_known_canteen(self):
        self.assertEqual(extract_base_canteen("桔园食堂一楼"), "桔园食堂")

    def test_another_canteen(self):
        self.assertEqual(extract_base_canteen("榴园食堂二楼"), "榴园食堂")

    def test_generic_canteen(self):
        self.assertEqual(extract_base_canteen("某某食堂餐厅"), "某某食堂")

    def test_non_canteen(self):
        self.assertIsNone(extract_base_canteen("超市"))

    def test_none_input(self):
        self.assertIsNone(extract_base_canteen(None))

    def test_nan_input(self):
        import numpy as np
        self.assertIsNone(extract_base_canteen(float('nan')))

    def test_all_six_canteens(self):
        for c in ['桔园', '榴园', '蕙园', '梅园', '桂园', '梧桐园']:
            self.assertIsNotNone(extract_base_canteen(f"{c}食堂"))


class TestClassifyCanteen(unittest.TestCase):
    def test_known_canteen(self):
        self.assertEqual(classify_canteen("桔园食堂一楼"), "桔园食堂")

    def test_non_canteen(self):
        self.assertEqual(classify_canteen("超市"), "其他")

    def test_none_input(self):
        self.assertEqual(classify_canteen(None), "其他")

    def test_nan_input(self):
        import numpy as np
        self.assertEqual(classify_canteen(float('nan')), "其他")


class TestMealPeriod(unittest.TestCase):
    def test_breakfast_early(self):
        self.assertEqual(get_meal_period(datetime(2024, 1, 1, 5, 0)), '早餐')

    def test_breakfast_late(self):
        self.assertEqual(get_meal_period(datetime(2024, 1, 1, 9, 59)), '早餐')

    def test_lunch(self):
        self.assertEqual(get_meal_period(datetime(2024, 1, 1, 12, 0)), '午餐')

    def test_lunch_boundary(self):
        self.assertEqual(get_meal_period(datetime(2024, 1, 1, 14, 59)), '午餐')

    def test_dinner(self):
        self.assertEqual(get_meal_period(datetime(2024, 1, 1, 18, 0)), '晚餐')

    def test_late_night_dinner(self):
        self.assertEqual(get_meal_period(datetime(2024, 1, 1, 1, 0)), '晚餐')

    def test_other_afternoon(self):
        self.assertEqual(get_meal_period(datetime(2024, 1, 1, 16, 0)), '其他时段')

    def test_other_dawn(self):
        self.assertEqual(get_meal_period(datetime(2024, 1, 1, 4, 30)), '其他时段')


class TestLogicalDayMinutes(unittest.TestCase):
    def test_morning(self):
        self.assertEqual(get_logical_day_minutes(datetime(2024, 1, 1, 8, 0)), 4 * 60)

    def test_late_night(self):
        self.assertEqual(get_logical_day_minutes(datetime(2024, 1, 1, 1, 0)), 21 * 60)

    def test_noon(self):
        self.assertEqual(get_logical_day_minutes(datetime(2024, 1, 1, 12, 0)), 8 * 60)


class TestMinutesToTimeStr(unittest.TestCase):
    def test_morning(self):
        mins = get_logical_day_minutes(datetime(2024, 1, 1, 8, 0))
        self.assertEqual(minutes_to_time_str(mins), "08:00")

    def test_midnight(self):
        mins = get_logical_day_minutes(datetime(2024, 1, 1, 0, 0))
        self.assertEqual(minutes_to_time_str(mins), "00:00")

    def test_nan(self):
        import numpy as np
        self.assertEqual(minutes_to_time_str(float('nan')), "-")


class TestReplaceCanteenName(unittest.TestCase):
    def test_beiyiqu(self):
        self.assertEqual(replace_canteen_name("北一区"), "桔园")

    def test_beierqu(self):
        self.assertEqual(replace_canteen_name("北二区"), "榴园")

    def test_no_match(self):
        self.assertEqual(replace_canteen_name("超市"), "超市")

    def test_empty(self):
        self.assertIsNone(replace_canteen_name(None))

    def test_multiple_replace(self):
        self.assertEqual(replace_canteen_name("北一区北二区"), "桔园榴园")

    def test_all_canteens(self):
        for old, new in {
            "北一区": "桔园", "北二区": "榴园", "北三区": "蕙园",
            "南一区": "梅园", "南二区": "桂园", "南三区": "梧桐园"
        }.items():
            self.assertEqual(replace_canteen_name(old), new)


if __name__ == '__main__':
    unittest.main()
