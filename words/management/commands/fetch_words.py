"""
Management command: fetch_words
從 Free Dictionary API 抓取單字資料並匯入資料庫

用法：
    python manage.py fetch_words                     # 從 word_list.txt 抓全部
    python manage.py fetch_words --limit 100         # 只抓前 100 個
    python manage.py fetch_words --file my_list.txt  # 指定清單檔案
    python manage.py fetch_words --delay 0.3         # 設定請求間隔（秒）
"""

import time
import json
import urllib.request
import urllib.error
import urllib.parse
import os
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from words.models import Word, WordSense, Example, Phonetic

DEFAULT_LIST_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    'data', 'word_list.txt'
)

API_BASE = 'https://api.dictionaryapi.dev/api/v2/entries/en/'

POS_MAP = {
    'noun': 'n', 'verb': 'v', 'adjective': 'adj', 'adverb': 'adv',
    'preposition': 'prep', 'conjunction': 'conj', 'pronoun': 'pron',
    'exclamation': 'phrase', 'abbreviation': 'n',
}

DIFFICULTY_MAP = {
    1: ['simple', 'basic', 'common'],
    2: ['standard'],
    3: ['advanced'],
}


class Command(BaseCommand):
    help = '從 Free Dictionary API 批次抓取單字定義並匯入資料庫'

    def add_arguments(self, parser):
        parser.add_argument('--file', '-f', type=str, default=DEFAULT_LIST_FILE,
                            help='單字清單文字檔（每行一個單字）')
        parser.add_argument('--limit', '-l', type=int, default=None,
                            help='最多抓幾個單字（預設全部）')
        parser.add_argument('--delay', type=float, default=0.4,
                            help='每次請求間隔秒數（預設 0.4，避免被封）')
        parser.add_argument('--difficulty', type=int, default=2,
                            help='預設難度（1-5，預設 2）')
        parser.add_argument('--overwrite', action='store_true',
                            help='若單字已存在，覆寫其資料')

    def handle(self, *args, **options):
        filepath = options['file']
        if not os.path.exists(filepath):
            raise CommandError(f'找不到清單檔：{filepath}')

        with open(filepath, 'r', encoding='utf-8') as f:
            words = [line.strip().lower() for line in f if line.strip() and not line.startswith('#')]

        # 去重
        seen = set()
        unique_words = []
        for w in words:
            if w not in seen:
                seen.add(w)
                unique_words.append(w)
        words = unique_words

        if options['limit']:
            words = words[:options['limit']]

        total = len(words)
        self.stdout.write(f'準備抓取 {total} 個單字（間隔 {options["delay"]}s）...\n')

        created = skipped = failed = not_found = 0

        for idx, word_text in enumerate(words, 1):
            # 已存在且不覆寫
            exists = Word.objects.filter(text=word_text).exists()
            if exists and not options['overwrite']:
                skipped += 1
                self.stdout.write(f'  [{idx:>4}/{total}] SKIP  {word_text}', ending='\r')
                continue

            # 呼叫 API
            result = self._fetch_from_api(word_text)

            if result is None:
                not_found += 1
                self.stdout.write(f'  [{idx:>4}/{total}] 404   {word_text}', ending='\r')
            elif result == 'error':
                failed += 1
                self.stdout.write(f'  [{idx:>4}/{total}] ERR   {word_text}', ending='\r')
            else:
                try:
                    if exists and options['overwrite']:
                        Word.objects.filter(text=word_text).delete()
                    self._save_word(word_text, result, options['difficulty'])
                    created += 1
                    self.stdout.write(f'  [{idx:>4}/{total}] OK    {word_text}', ending='\r')
                except Exception as e:
                    failed += 1
                    self.stdout.write(f'\n  [{idx:>4}/{total}] SAVE_ERR {word_text}: {e}')

            time.sleep(options['delay'])

        self.stdout.write(f'\n\n完成！新增 {created} / 跳過 {skipped} / 找不到 {not_found} / 錯誤 {failed}\n')

    def _fetch_from_api(self, word: str):
        """呼叫 Free Dictionary API，回傳原始資料或 None/error"""
        url = API_BASE + urllib.parse.quote(word)
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Lexis-Fetcher/1.0'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            return 'error'
        except Exception:
            return 'error'

    @transaction.atomic
    def _save_word(self, word_text: str, api_data: list, default_difficulty: int):
        """解析 API 回應並儲存到資料庫"""
        word_obj = Word.objects.create(
            text=word_text,
            difficulty=default_difficulty,
            source='TOEIC',
        )

        audio_saved = False
        sense_order = 0
        seen_pos = set()

        for entry in api_data:
            # 音標（每個單字只存一次）
            if not audio_saved:
                for ph in entry.get('phonetics', []):
                    notation = ph.get('text', '').strip('/')
                    if notation:
                        Phonetic.objects.create(
                            word=word_obj,
                            notation=notation,
                            notation_type='IPA',
                        )
                        audio_saved = True
                        break

            # 義項
            for meaning in entry.get('meanings', []):
                raw_pos = meaning.get('partOfSpeech', 'noun')
                pos = POS_MAP.get(raw_pos, 'n')

                # 同一詞性只保留一個義項（取第一個最主要的定義）
                pos_key = pos
                if pos_key in seen_pos:
                    continue
                seen_pos.add(pos_key)

                definitions = meaning.get('definitions', [])
                if not definitions:
                    continue

                first_def = definitions[0]
                definition_text = first_def.get('definition', '')
                if not definition_text:
                    continue

                sense = WordSense.objects.create(
                    word=word_obj,
                    part_of_speech=pos,
                    definition=definition_text,
                    translation='',  # API 不提供中文，使用者加入字庫後可自行補充
                    order=sense_order,
                )
                sense_order += 1

                # 例句（最多 2 個）
                ex_count = 0
                for defn in definitions[:3]:
                    if ex_count >= 2:
                        break
                    example_text = defn.get('example', '')
                    if example_text:
                        Example.objects.create(
                            sense=sense,
                            sentence=example_text,
                            translation='',
                        )
                        ex_count += 1
