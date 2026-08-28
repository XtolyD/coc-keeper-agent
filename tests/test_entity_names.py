# -*- coding: utf-8 -*-
import pytest

from coc_keeper.chunker import is_monster_name, is_stat_line
from coc_keeper.build_chunks import _is_skill_item, _split_table_region

# 金标：真名应识别为实体名
TRUE_NAMES = [
    "拜亚基", "钻地魔虫", "星之彩", "食尸鬼", "修格斯", "阿萨托斯", "深潜者",
    "古老者", "夜魇", "乔乔人", "巨乌贼", "鲨鱼", "蛇", "人面鼠",
    "猎食时光之屑的庭达罗斯猎犬", "不应存世的尼约格萨", "夏塔克鸟",
    "无形眷族", "妖鬼", "格拉基之仆", "诺弗·刻", "伊斯之伟大种族",
    "庭达罗斯的猎犬", "恐怖猎手", "罗伊格尔", "无面的夜魇", "潜沙怪",
    "蛇人", "元祖蛇人", "外神仆役", "夏盖妖虫", "寄蚀心灵的夏盖妖虫",
    "修格斯主宰", "克苏鲁的星之眷族", "星之精", "阿布霍斯", "阿特拉克·纳克亚",
    "芭丝特", "昌格纳·方庚", "克图格亚", "伟大的克苏鲁", "赛伊格亚", "道罗斯",
    "埃霍尔特", "加塔诺托亚", "格拉基", "伊塔库亚", "黄印", "诺登斯",
    "奈亚拉托提普", "尼约格萨", "兰-提格斯", "莎布-尼古拉斯", "修德梅尔",
    "撒托古亚", "图尔兹查Tulzscha", "乌波·萨斯拉", "伊戈罗纳克", "伊波·兹特尔",
    "伊格", "犹格·索托斯", "佐斯·奥摩格", "木乃伊", "吸血鬼", "狼人", "丧尸",
    "尼罗鳄", "老鼠", "蛇毒", "巨型乌贼", "黄蜂和蜜蜂群", "旧日支配者",
    "星之彩生命猎食者", "混种深潜者", "黑山羊幼崽", "食尸鬼王子", "独眼巨人",
    "马", "狗", "狼", "黑熊", "鸟", "鳄鱼", "狮子", "巨型蝙蝠", "兀鹫", "鼠群",
]

# 金标：噪声/数据行不应识别为实体名
NOISE_NAMES = [
    "特殊能力", "攻击", "教团", "其他特性", "人类形态", "怪物形态", "战斗",
    "魔法值", "属性平均值掷骰", "平均掷骰", "伤害", "移动",
    "闪避 33% (16/6)", "躲避25%（12/5）", "CON N/A", "STR 90 （5D6×5）",
    "HP：14", "属性 平均 掷骰", "平均伤害加成：1D6", "每回合攻击：2次",
    "造成严重伤害", "性5点", "点伤害+中毒效果", "14.1 神话生物",
    "14.2 神话中的邪神", "《穿越银匙之门》", "克制魔法", "超越怪物",
]


def test_is_monster_name_true_positive():
    for n in TRUE_NAMES:
        assert is_monster_name(n, width=70, page_width=612), f"应识别为怪物名: {n}"


def test_is_monster_name_false_positive():
    for n in NOISE_NAMES:
        assert not is_monster_name(n, width=70, page_width=612), f"不应识别为怪物名: {n}"


def test_is_stat_line():
    assert is_stat_line("STR 90 （5D6×5）")
    assert is_stat_line("CON N/A")
    assert is_stat_line("闪避 33% (16/6)")
    assert is_stat_line("躲避25%（12/5）")
    assert not is_stat_line("拜亚基")
    assert not is_stat_line("钻地魔虫")


def test_monster_name_bounds():
    # 过长 / 含句读 / 含书名号 不应通过
    assert not is_monster_name("这是一个非常非常长的怪物名不适合作为实体名", 70, 612)
    assert not is_monster_name("拜亚基，星骏", 70, 612)   # 含逗号
    assert not is_monster_name("《穿越银匙之门》", 70, 612)  # 书名号


def test_skill_item_detection():
    # 技能条目：名称（基础值）
    assert _is_skill_item("会计（05%）")
    assert _is_skill_item("考古学（01%）")
    assert _is_skill_item("闪避（一半DEX）")
    assert _is_skill_item("格斗（各种各样）")
    # 非技能条目：专业化子项（无括号百分比）、正文长句、项目符号
    assert not _is_skill_item("理发")
    assert not _is_skill_item("莫里斯舞蹈")
    assert not _is_skill_item("允许从过去的文化中鉴定一件古董的年代以及辨别它")
    assert not _is_skill_item("技能：聆听50%，侦查50%")


def test_split_table_region():
    # 含强表头（实体 发音）的页才切出表格区
    lines = ["正文第一行内容较长一些", "实体  发音  实体  发音", "Abhoth 阿布霍斯 Mi-Go 米-戈", "Atlach-Nacha"]
    pre, tab, post = _split_table_region(lines)
    assert pre == ["正文第一行内容较长一些"]
    assert len(tab) >= 2          # 表头 + 表格单元格行（含 `Atlach-Nacha`）
    assert "实体" in tab[0]
    # 无表头则整页为正文
    pre2, tab2, post2 = _split_table_region(["普通正文一行内容较长", "另一行没有表格特征"])
    assert tab2 == []


def test_monster_name_rejects_sentence_fragment_punctuation():
    # 以句末标点结尾的断句残块不是实体名（原有漏洞：｡/）未排除）。
    for frag in ("的舞者)｡", "别的书｡", "物｡", "｡", "过来查看……", "你在恐惧中醒了过来……"):
        assert not is_monster_name(frag)


def test_monster_name_keeps_real_names_ending_in_letter():
    # 真怪物名（含中英混合、汉字结尾）不受影响。
    for name in ("拜亚基", "食尸鬼", "深潜者", "修格斯", "图尔兹查Tulzscha", "旧日支配者"):
        assert is_monster_name(name)
