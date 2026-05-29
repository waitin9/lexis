from django.db import models


class Word(models.Model):
    """官方字庫的單字本體"""
    text = models.CharField(max_length=100, unique=True, db_index=True)
    difficulty = models.IntegerField(default=1)  # 1=easy ... 5=hard
    source = models.CharField(max_length=50, default='TOEIC')  # 資料來源標籤
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['text']

    def __str__(self):
        return self.text

    def get_primary_sense(self):
        return self.senses.order_by('order').first()


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
