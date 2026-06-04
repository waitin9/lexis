from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import date, timedelta
from words.models import Word


class UserProfile(models.Model):
    """使用者學習統計與個人設定"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    streak = models.IntegerField(default=0)          # 連續學習天數
    last_study_date = models.DateField(null=True, blank=True)
    total_reviews = models.IntegerField(default=0)   # 累計複習次數
    total_learned = models.IntegerField(default=0)   # 累計學會的單字數
    theme = models.CharField(max_length=50, default='deep-space')  # 主題設定
    phonetic_pref = models.CharField(max_length=20, default='kk')  # 'kk', 'ipa', 'hide'
    daily_target = models.IntegerField(default=20)                 # 每日新探索上限
    auto_pronounce = models.BooleanField(default=False)            # 是否自動朗讀發音
    pronunciation_pref = models.CharField(max_length=10, choices=[('US', '美音'), ('UK', '英音')], default='US') # 發音偏好 (美音/英音)
    particle_effect = models.BooleanField(default=True)            # 是否啟用背景粒子特效
    card_border_style = models.CharField(max_length=20, default='default') # 'default', 'platinum'
    show_gold_badge = models.BooleanField(default=False)
    background_effect = models.CharField(max_length=50, default='none')
    user_badge = models.CharField(max_length=50, default='none')
    challenges_played = models.IntegerField(default=0)
    coins = models.IntegerField(default=100)
    unlocked_items = models.TextField(default="theme:deep-space,theme:aurora,border:default,effect:none")

    def get_badge_info(self):
        """獲取當前啟用頭銜的顯示名稱與樣式"""
        badges = {
            'sprout': {'emoji': '👶', 'name': '幼嫩萌芽', 'class': 'badge-sprout'},
            'novice': {'emoji': '🧭', 'name': '冒險新手', 'class': 'badge-novice'},
            'iron': {'emoji': '🛡️', 'name': '鋼鐵意志', 'class': 'badge-iron'},
            'star': {'emoji': '⭐', 'name': '勤奮之星', 'class': 'badge-star'},
            'walker': {'emoji': '🚶', 'name': '溫故行者', 'class': 'badge-walker'},
            'start': {'emoji': '🚀', 'name': '挑戰起點', 'class': 'badge-start'},
            'time-traveler': {'emoji': '⏳', 'name': '時間旅者', 'class': 'badge-time'},
            'wisdom': {'emoji': '💡', 'name': '智慧啟蒙', 'class': 'badge-wisdom'},
            'master': {'emoji': '👑', 'name': '黃金學習者', 'class': 'badge-master'},
            'sage': {'emoji': '🧙', 'name': '單字賢者', 'class': 'badge-sage'},
            'survivor': {'emoji': '🩸', 'name': '浴血倖存者', 'class': 'badge-survivor'},
            'explorer': {'emoji': '🧭', 'name': '新詞探索家', 'class': 'badge-explorer'},
        }
        return badges.get(self.user_badge, None)

    def __str__(self):
        return f"{self.user.username}'s profile"

    def update_streak(self):
        """每次完成複習後呼叫，自動維護 streak"""
        today = date.today()
        if self.last_study_date is None:
            self.streak = 1
        elif self.last_study_date == today:
            pass  # 今天已學過，不重複計算
        elif self.last_study_date == today - timedelta(days=1):
            self.streak += 1
        else:
            self.streak = 1  # 中斷了，重置
        self.last_study_date = today
        self.save()


class UserVocab(models.Model):
    """使用者加入個人字庫的單字（官方 + 自建）"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='vocab_entries')
    # 官方字庫的單字（可為空，代表是使用者自建單字）
    word = models.ForeignKey(Word, on_delete=models.CASCADE, null=True, blank=True, related_name='user_vocabs')
    # 使用者自建單字的欄位（當 word 為空時使用）
    custom_text = models.CharField(max_length=100, blank=True)
    custom_phonetic = models.CharField(max_length=100, blank=True)
    custom_part_of_speech = models.CharField(max_length=50, blank=True)
    custom_definition = models.TextField(blank=True)
    custom_translation = models.CharField(max_length=300, blank=True)
    custom_example = models.TextField(blank=True)
    # 共用欄位
    ai_mnemonic = models.TextField(blank=True)  # AI 生成的專屬迷因記憶鉤子
    note = models.TextField(blank=True)   # 個人記憶備註
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # 避免同一使用者重複加入同一官方單字
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'word'],
                condition=models.Q(word__isnull=False),
                name='unique_user_official_word'
            )
        ]

    def __str__(self):
        return f"{self.user.username} - {self.display_text}"

    @property
    def display_text(self):
        if self.word:
            return self.word.text
        return self.custom_text

    @property
    def display_translation(self):
        if self.word:
            primary = self.word.senses.order_by('order').first()
            return primary.translation if primary else ''
        return self.custom_translation

    @property
    def display_definition(self):
        if self.word:
            primary = self.word.senses.order_by('order').first()
            return primary.definition if primary else ''
        return self.custom_definition

    @property
    def display_example(self):
        if self.word:
            primary = self.word.senses.order_by('order').first()
            if primary:
                ex = primary.examples.first()
                return ex.sentence if ex else ''
        return self.custom_example

    @property
    def is_custom(self):
        return self.word is None


class SRSCard(models.Model):
    """SM-2 間隔重複卡片狀態"""
    MASTERY_CHOICES = [
        (0, '生疏'),
        (1, '學習中'),
        (2, '熟悉'),
        (3, '精通'),
    ]
    user_vocab = models.OneToOneField(UserVocab, on_delete=models.CASCADE, related_name='srs_card')
    # SM-2 核心參數
    interval = models.IntegerField(default=1)        # 下次複習間隔（天）
    repetitions = models.IntegerField(default=0)     # 連續答對次數
    ease_factor = models.FloatField(default=2.5)     # 難易係數
    next_review = models.DateField(default=date.today)
    last_reviewed = models.DateField(null=True, blank=True)
    mastery_level = models.IntegerField(default=0, choices=MASTERY_CHOICES)

    def __str__(self):
        return f"Card for {self.user_vocab.display_text} (next: {self.next_review})"

    def is_due(self):
        return self.next_review <= date.today()


class UserWordStatus(models.Model):
    """
    追蹤使用者在 Browse 模式中對每個官方字庫單字的狀態。
    讓系統知道哪些字已看過、哪些認識、哪些加入字庫。
    """
    STATUS_KNOWN   = 'known'   # 認識，暫時跳過
    STATUS_ADDED   = 'added'   # 已加入字庫
    STATUS_SKIPPED = 'skipped' # 略過（下次繼續出現）

    STATUS_CHOICES = [
        (STATUS_KNOWN,   '認識'),
        (STATUS_ADDED,   '已加入字庫'),
        (STATUS_SKIPPED, '略過'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='word_statuses')
    word = models.ForeignKey(Word, on_delete=models.CASCADE, related_name='user_statuses')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    seen_at = models.DateTimeField(auto_now=True)
    # 「認識」的單字 30 天後重新浮現確認
    resurface_after = models.DateField(null=True, blank=True)

    class Meta:
        unique_together = ['user', 'word']

    def __str__(self):
        return f"{self.user.username} - {self.word.text}: {self.status}"


class ReviewLog(models.Model):
    """使用者每一次複習的歷程記錄（用於繪製熱力圖）"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='review_logs')
    user_vocab = models.ForeignKey(UserVocab, on_delete=models.CASCADE, related_name='review_logs')
    quality = models.IntegerField()  # 複習掌握度 (0~3)
    created_at = models.DateField(default=date.today) # 複習日期

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} reviewed {self.user_vocab.display_text} on {self.created_at}"
