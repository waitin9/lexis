import urllib.request
from django.core.management.base import BaseCommand
from words.models import Word, WordSense, Category
from deep_translator import GoogleTranslator

class Command(BaseCommand):
    help = 'Seeds a massive amount of words from public datasets'

    def handle(self, *args, **kwargs):
        self.stdout.write("Downloading 10000 English words dataset...")
        url = "https://raw.githubusercontent.com/first20hours/google-10000-english/master/google-10000-english-no-swears.txt"
        
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            response = urllib.request.urlopen(req)
            data = response.read().decode('utf-8')
            words_list = [w.strip() for w in data.split('\n') if len(w.strip()) > 3]
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to download: {e}"))
            return

        # 分配分類
        categories = {
            '🔥 日常高頻 1000 詞 (A1)': {'start': 0, 'end': 1000, 'desc': '最常見的生活單字，聽說讀寫必備', 'color': '#2ecc71'},
            '🚀 職場進階 1000 詞 (B1)': {'start': 1000, 'end': 2000, 'desc': '工作與商務場合高頻出現的單字', 'color': '#3498db'},
            '🎓 學術挑戰 1000 詞 (C1)': {'start': 2000, 'end': 3000, 'desc': '留學、外商、高階閱讀必背單字', 'color': '#9b59b6'},
        }

        translator = GoogleTranslator(source='en', target='zh-TW')

        total_added = 0

        for cat_name, cat_data in categories.items():
            cat_obj, _ = Category.objects.get_or_create(
                name=cat_name, 
                defaults={'description': cat_data['desc'], 'color': cat_data['color']}
            )
            
            target_words = words_list[cat_data['start']:cat_data['end']]
            self.stdout.write(f"Processing category... ({len(target_words)} words)")
            
            # 批次處理
            batch_size = 50
            for i in range(0, len(target_words), batch_size):
                batch = target_words[i:i+batch_size]
                
                # 過濾掉資料庫中已存在的單字
                existing_words = set(Word.objects.filter(text__in=batch).values_list('text', flat=True))
                new_words = [w for w in batch if w not in existing_words]
                
                if not new_words:
                    # 把已存在的單字綁定到分類
                    for w in existing_words:
                        word_obj = Word.objects.get(text=w)
                        word_obj.categories.add(cat_obj)
                    continue

                try:
                    # 批次翻譯
                    translations = translator.translate_batch(new_words)
                    
                    # 建立資料庫記錄
                    for idx, text in enumerate(new_words):
                        trans = translations[idx] if idx < len(translations) else "暫無翻譯"
                        
                        word_obj = Word.objects.create(text=text, source='MASSIVE_SEED')
                        WordSense.objects.create(
                            word=word_obj,
                            part_of_speech='unknown',
                            translation=trans,
                            definition='',
                            order=1
                        )
                        word_obj.categories.add(cat_obj)
                        total_added += 1
                        
                    self.stdout.write(f"  [OK] Batch {i//batch_size + 1}: Imported {len(new_words)} words")
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"  [FAIL] Batch error: {e}"))

        self.stdout.write(self.style.SUCCESS(f'Massive seeder finished! Added {total_added} new words.'))
