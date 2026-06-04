from django.db import models


class Category(models.Model):
    """字庫分類（如：TOEIC、GRE、日常會話）"""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    color = models.CharField(max_length=20, default='#6C63FF')  # 供前端 UI 標籤使用顏色
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


class Word(models.Model):
    """官方字庫的單字本體"""
    text = models.CharField(max_length=100, unique=True, db_index=True)
    difficulty = models.IntegerField(default=1)  # 1=easy ... 5=hard
    source = models.CharField(max_length=50, default='TOEIC')  # 資料來源標籤
    categories = models.ManyToManyField(Category, related_name='words', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['text']

    def __str__(self):
        return self.text

    def get_primary_sense(self):
        return self.senses.order_by('order').first()

    def get_related_family_words(self):
        text = self.text.lower()
        if len(text) <= 3:
            return []
        
        # 決定前綴長度 (N)
        if len(text) <= 5:
            prefix_len = 3
        elif len(text) <= 7:
            prefix_len = 4
        else:
            prefix_len = 5
            
        prefix = text[:prefix_len]
        
        # 查詢具有相同前綴的單字，排除本身
        # 限制長度差異在 5 字元以內
        candidates = Word.objects.filter(text__istartswith=prefix).exclude(id=self.id)
        
        valid_candidates = []
        for c in candidates:
            if abs(len(c.text) - len(self.text)) <= 5:
                valid_candidates.append(c)
                
        return valid_candidates

    def get_phonetic_display(self, pref='kk'):
        """根據偏好顯示音標：kk(優先KK), ipa(優先IPA), hide(隱藏)"""
        if pref == 'hide':
            return ""
        
        # 內置 Python 過濾，避免 prefetch_related 快取失效觸發 N+1 資料庫查詢
        phonetics_list = list(self.phonetics.all())
        
        if pref == 'ipa':
            ipa = next((p for p in phonetics_list if p.notation_type == 'IPA'), None)
            if ipa:
                return ipa.notation
            kk = next((p for p in phonetics_list if p.notation_type == 'KK'), None)
            if kk:
                return kk.notation
        else:  # 'kk'
            kk = next((p for p in phonetics_list if p.notation_type == 'KK'), None)
            if kk:
                return kk.notation
            ipa = next((p for p in phonetics_list if p.notation_type == 'IPA'), None)
            if ipa:
                return ipa.notation
        return ""


class WordSense(models.Model):
    """一個單字的某個詞性義項"""
    PART_OF_SPEECH_CHOICES = [
        ('n', 'Noun'),
        ('v', 'Verb'),
        ('adj', 'Adjective'),
        ('adv', 'Adverb'),
        ('prep', 'Preposition'),
        ('conj', 'Conjunction'),
        ('pron', 'Pronoun'),
        ('phrase', 'Phrase'),
    ]
    word = models.ForeignKey(Word, on_delete=models.CASCADE, related_name='senses')
    part_of_speech = models.CharField(max_length=10, choices=PART_OF_SPEECH_CHOICES)
    definition = models.TextField()            # 英文定義
    translation = models.CharField(max_length=300)  # 中文翻譯
    order = models.IntegerField(default=0)    # 義項排序（主要義項優先）

    class Meta:
        ordering = ['order']

    @property
    def pos_display(self):
        mapping = {
            'n': 'n.',
            'v': 'v.',
            'adj': 'adj.',
            'adv': 'adv.',
            'prep': 'prep.',
            'conj': 'conj.',
            'pron': 'pron.',
            'phrase': 'phr.',
        }
        pos = self.part_of_speech.lower().strip()
        if pos.endswith('.'):
            return pos
        full_map = {
            'noun': 'n.', 'verb': 'v.', 'adjective': 'adj.', 'adverb': 'adv.',
            'preposition': 'prep.', 'conjunction': 'conj.', 'pronoun': 'pron.',
            'phrase': 'phr.', 'idiom': 'phr.', 'exclamation': 'phr.',
        }
        if pos in full_map:
            return full_map[pos]
        return mapping.get(pos, f"{pos}.")

    @property
    def pos_class(self):
        mapping = {
            'noun': 'n', 'verb': 'v', 'adjective': 'adj', 'adverb': 'adv',
            'preposition': 'prep', 'conjunction': 'conj', 'pronoun': 'pron',
            'phrase': 'phrase', 'idiom': 'phrase', 'exclamation': 'phrase',
        }
        pos = self.part_of_speech.lower().strip().replace('.', '')
        return mapping.get(pos, pos)

    def __str__(self):
        return f"{self.word.text} ({self.part_of_speech}): {self.translation}"


class Example(models.Model):
    """例句，掛在某個義項下"""
    sense = models.ForeignKey(WordSense, on_delete=models.CASCADE, related_name='examples')
    sentence = models.TextField()
    translation = models.CharField(max_length=500, blank=True)

    def __str__(self):
        return self.sentence[:60]


class Phonetic(models.Model):
    """音標，一個單字可有多個音標（美式/英式）"""
    NOTATION_TYPE = [
        ('IPA', 'IPA'),
        ('KK', 'KK'),
    ]
    word = models.ForeignKey(Word, on_delete=models.CASCADE, related_name='phonetics')
    notation = models.CharField(max_length=100)
    notation_type = models.CharField(max_length=5, choices=NOTATION_TYPE, default='IPA')

    def __str__(self):
        return f"/{self.notation}/ ({self.notation_type})"


class Collocation(models.Model):
    """必考搭配詞，掛在單字本體下"""
    word = models.ForeignKey(Word, on_delete=models.CASCADE, related_name='collocations')
    phrase = models.CharField(max_length=250)              # 完整片語，例如: "draw up a contract"
    missing_part = models.CharField(max_length=100)        # 挖空答案，例如: "draw up"
    translation = models.CharField(max_length=250)         # 中文釋義，例如: "擬定合約"
    distractors = models.JSONField(default=list)           # 干擾選項，例如: ["make", "do"]

    def __str__(self):
        return f"Collocation for {self.word.text}: {self.phrase}"


class WordConfusable(models.Model):
    """天敵混淆字配對，用於精準混淆題挑戰"""
    word = models.ForeignKey(Word, on_delete=models.CASCADE, related_name='confusables')
    confusable = models.ForeignKey(Word, on_delete=models.CASCADE, related_name='confusable_by')
    explanation = models.TextField(blank=True)             # 辨析說明，例如: "personal (個人的) ↔ personnel (員工)"

    class Meta:
        unique_together = ['word', 'confusable']

    def __str__(self):
        return f"{self.word.text} ↔ {self.confusable.text}"
