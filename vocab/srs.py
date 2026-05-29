"""
SM-2 間隔重複演算法實作
參考：https://www.supermemo.com/en/archives1990-2015/english/ol/sm2

Quality 評分定義（使用者輸入）：
    0 = Again   — 完全忘記，立刻重複
    1 = Hard    — 記得但非常困難
    2 = Good    — 記得，有點費力
    3 = Easy    — 輕鬆記得

內部轉換為 SM-2 的 0-5 標準：
    Again → 1
    Hard  → 3
    Good  → 4
    Easy  → 5
"""

from datetime import date, timedelta
from math import ceil


# 使用者介面的四個按鈕
QUALITY_AGAIN = 0
QUALITY_HARD = 1
QUALITY_GOOD = 2
QUALITY_EASY = 3

# 對應到 SM-2 原始的 0-5 分
_SM2_MAP = {
    QUALITY_AGAIN: 1,
    QUALITY_HARD:  3,
    QUALITY_GOOD:  4,
    QUALITY_EASY:  5,
}

# 熟練度閾值（interval 天數）
MASTERY_THRESHOLDS = {
    0: 0,    # 生疏：interval < 3
    1: 3,    # 學習中：3 <= interval < 14
    2: 14,   # 熟悉：14 <= interval < 60
    3: 60,   # 精通：interval >= 60
}


def _compute_mastery(interval: int) -> int:
    """根據 interval 計算熟練度等級"""
    if interval >= 60:
        return 3
    elif interval >= 14:
        return 2
    elif interval >= 3:
        return 1
    return 0


def review_card(card, quality: int) -> dict:
    """
    對一張 SRSCard 執行 SM-2 演算法更新。

    Args:
        card: SRSCard 物件
        quality: 0=Again, 1=Hard, 2=Good, 3=Easy

    Returns:
        dict，包含更新後的關鍵數值（方便 view 使用）
    """
    q = _SM2_MAP.get(quality, 4)   # 轉換為 SM-2 原始分
    today = date.today()

    if q < 3:
        # 答錯：重置，明天再複習
        card.repetitions = 0
        card.interval = 1
    else:
        # 答對
        if card.repetitions == 0:
            if quality == QUALITY_EASY:
                card.interval = 4
            elif quality == QUALITY_GOOD:
                card.interval = 2
            else:
                card.interval = 1
        elif card.repetitions == 1:
            card.interval = 6
        else:
            card.interval = ceil(card.interval * card.ease_factor)
        card.repetitions += 1

    # 更新難易係數（EF），最低不得低於 1.3
    card.ease_factor = max(
        1.3,
        card.ease_factor + 0.1 - (5 - q) * (0.08 + (5 - q) * 0.02)
    )

    card.last_reviewed = today
    card.next_review = today + timedelta(days=card.interval)
    card.mastery_level = _compute_mastery(card.interval)
    card.save()

    return {
        'interval': card.interval,
        'ease_factor': round(card.ease_factor, 2),
        'next_review': card.next_review,
        'mastery_level': card.mastery_level,
        'passed': q >= 3,
    }


def get_due_cards(user):
    """
    取得使用者今日待複習的 SRSCard queryset，
    按到期時間（最久未複習的優先）排序。
    """
    from vocab.models import SRSCard
    return (
        SRSCard.objects
        .filter(user_vocab__user=user, next_review__lte=date.today())
        .select_related('user_vocab', 'user_vocab__word')
        .order_by('next_review', 'last_reviewed')
    )


def get_new_cards_today(user, limit=20):
    """
    取得使用者尚未有 SRS 卡的新單字（剛加入字庫但還沒開始複習）。
    自動為這些單字建立 SRSCard。
    """
    from vocab.models import UserVocab, SRSCard
    entries_without_card = (
        UserVocab.objects
        .filter(user=user)
        .exclude(srs_card__isnull=False)[:limit]
    )
    cards = []
    for entry in entries_without_card:
        card, _ = SRSCard.objects.get_or_create(user_vocab=entry)
        cards.append(card)
    return cards
