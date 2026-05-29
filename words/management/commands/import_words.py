"""
Management command: import_words
用法：
    python manage.py import_words
    python manage.py import_words --file path/to/custom.json
    python manage.py import_words --clear   # 清空後重新匯入

JSON 格式（每筆）：
{
  "text": "abundant",
  "difficulty": 2,
  "source": "TOEIC",
  "phonetic": "əˈbʌndənt",
  "senses": [
    {
      "part_of_speech": "adj",
      "definition": "existing in large quantities",
      "translation": "豐富的",
      "order": 0,
      "examples": [
        {"sentence": "...", "translation": "..."}
      ]
    }
  ]
}
"""

import json
import os
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from words.models import Word, WordSense, Example, Phonetic


DEFAULT_DATA_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    'data', 'toeic_words.json'
)


class Command(BaseCommand):
    help = '從 JSON 檔案匯入單字到官方字庫（防重複匯入）'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file', '-f',
            type=str,
            default=DEFAULT_DATA_FILE,
            help='JSON 資料檔路徑（預設：words/data/toeic_words.json）'
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='匯入前先清空官方字庫（危險！）'
        )

    def handle(self, *args, **options):
        filepath = options['file']

        if not os.path.exists(filepath):
            raise CommandError(f'找不到資料檔：{filepath}')

        with open(filepath, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                raise CommandError(f'JSON 解析錯誤：{e}')

        if not isinstance(data, list):
            raise CommandError('JSON 格式錯誤：頂層應為陣列（list）')

        if options['clear']:
            self.stdout.write(self.style.WARNING('清空官方字庫中...'))
            Word.objects.all().delete()
            self.stdout.write(self.style.SUCCESS('字庫已清空。'))

        created_count = 0
        skipped_count = 0
        error_count = 0

        self.stdout.write(f'開始匯入 {len(data)} 筆單字...')

        for idx, entry in enumerate(data, 1):
            try:
                self._import_word(entry)
                created_count += 1
                self.stdout.write(f'  [{idx:>3}] OK {entry.get("text", "?")}', ending='\r')
            except WordAlreadyExists:
                skipped_count += 1
                self.stdout.write(f'  [{idx:>3}] -- {entry.get("text", "?")} (skip)', ending='\r')
            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(f'\n  [{idx:>3}] ERR {entry.get("text", "?")} : {e}')
                )

        self.stdout.write('')  # 換行
        self.stdout.write(self.style.SUCCESS(
            f'\n匯入完成：新增 {created_count} 筆，'
            f'跳過 {skipped_count} 筆（已存在），'
            f'錯誤 {error_count} 筆。'
        ))

    @transaction.atomic
    def _import_word(self, entry):
        text = entry.get('text', '').strip().lower()
        if not text:
            raise ValueError('缺少單字文字（text）')

        # 防重複匯入
        if Word.objects.filter(text=text).exists():
            raise WordAlreadyExists()

        word = Word.objects.create(
            text=text,
            difficulty=entry.get('difficulty', 1),
            source=entry.get('source', 'TOEIC'),
        )

        # 音標
        phonetic_str = entry.get('phonetic', '')
        if phonetic_str:
            Phonetic.objects.create(
                word=word,
                notation=phonetic_str,
                notation_type='IPA',
            )

        # 義項與例句
        for sense_data in entry.get('senses', []):
            sense = WordSense.objects.create(
                word=word,
                part_of_speech=sense_data.get('part_of_speech', 'n'),
                definition=sense_data.get('definition', ''),
                translation=sense_data.get('translation', ''),
                order=sense_data.get('order', 0),
            )
            for ex_data in sense_data.get('examples', []):
                Example.objects.create(
                    sense=sense,
                    sentence=ex_data.get('sentence', ''),
                    translation=ex_data.get('translation', ''),
                )


class WordAlreadyExists(Exception):
    pass
