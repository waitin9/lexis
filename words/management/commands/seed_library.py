import time
import sys
from django.core.management.base import BaseCommand
from words.models import Word, WordSense, Phonetic, Example, Category
from vocab.ai_service import expand_official_word

class Command(BaseCommand):
    help = 'Seeds the database with categorized word libraries'

    def handle(self, *args, **kwargs):
        # 1. 建立分類
        categories = {
            'TOEIC 金榜 900': Category.objects.get_or_create(
                name='TOEIC 金榜 900', 
                defaults={'description': '多益高頻核心單字，職場與商務必備', 'color': '#3498db', 'order': 1}
            )[0],
            'GRE 殺手級字彙': Category.objects.get_or_create(
                name='GRE 殺手級字彙', 
                defaults={'description': '留學考試、進階學術文章必考艱澀單字', 'color': '#e74c3c', 'order': 2}
            )[0],
            '美劇日常俚語': Category.objects.get_or_create(
                name='美劇日常俚語', 
                defaults={'description': '道地美國人天天掛在嘴邊的生活用語', 'color': '#f1c40f', 'order': 3}
            )[0]
        }

        self.stdout.write(self.style.SUCCESS('成功建立字庫分類！'))

        # 2. 定義各分類要匯入的單字清單 (Demo 數量)
        seed_data = {
            'TOEIC 金榜 900': ['implement', 'revenue', 'negotiate', 'strategy', 'evaluate', 'compile', 'comprehensive', 'allocate', 'fluctuate', 'productivity'],
            'GRE 殺手級字彙': ['meticulous', 'ephemeral', 'ubiquitous', 'obfuscate', 'cacophony', 'enigma', 'paradigm', 'alacrity', 'sycophant', 'mitigate'],
            '美劇日常俚語': ['ghosting', 'flex', 'lit', 'salty', 'sus', 'vibe', 'spill', 'tea', 'cringe', 'hype']
        }

        total_words = sum(len(words) for words in seed_data.values())
        self.stdout.write(f'準備匯入 {total_words} 個單字，將呼叫 AI 進行精準解析...')

        count = 0
        for cat_name, words in seed_data.items():
            category = categories[cat_name]
            for text in words:
                word_obj = Word.objects.filter(text=text).first()
                if not word_obj:
                    self.stdout.write(f'正在解析: {text} ...')
                    data = expand_official_word(text)
                    if data:
                        try:
                            word_obj = Word.objects.create(text=data['word'], source='AI_SEED')
                            Phonetic.objects.create(word=word_obj, notation=data['ipa_us'], notation_type='IPA')
                            sense = WordSense.objects.create(
                                word=word_obj,
                                part_of_speech=data['part_of_speech'],
                                definition=data['definition'],
                                translation=data['translation'],
                                order=1
                            )
                            if data.get('example_sentence'):
                                Example.objects.create(
                                    sense=sense,
                                    sentence=data['example_sentence'],
                                    translation=data.get('example_translation', '')
                                )
                            self.stdout.write(self.style.SUCCESS(f'  [OK] 成功匯入: {text}'))
                        except Exception as e:
                            self.stdout.write(self.style.ERROR(f'  [FAIL] 寫入失敗 {text}: {e}'))
                    else:
                        self.stdout.write(self.style.ERROR(f'  [FAIL] AI 解析失敗: {text}'))
                    # 避免打爆 API，稍微等待
                    time.sleep(1)
                
                # 建立分類關聯
                if word_obj:
                    word_obj.categories.add(category)
                    count += 1

        self.stdout.write(self.style.SUCCESS(f'字庫初始化完成！共關聯了 {count} 個單字。'))
