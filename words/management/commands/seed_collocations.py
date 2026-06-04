from django.core.management.base import BaseCommand
from words.models import Word, WordSense, Collocation, WordConfusable, Phonetic


class Command(BaseCommand):
    help = 'Seeds the database with high-quality TOEIC collocations and confusing word pairs'

    def handle(self, *args, **options):
        self.stdout.write('開始載入搭配詞與混淆詞題庫數據...')

        # 輔助函數：安全創建單字、音標與主要義項，以防資料庫尚未包含該詞
        def get_or_create_word(text, pos, translation, definition, phonetic_notation=""):
            word_obj, created = Word.objects.get_or_create(
                text=text,
                defaults={'difficulty': 2, 'source': 'CHALLENGE_SEED'}
            )
            if created:
                WordSense.objects.create(
                    word=word_obj,
                    part_of_speech=pos,
                    translation=translation,
                    definition=definition,
                    order=1
                )
                if phonetic_notation:
                    Phonetic.objects.create(
                        word=word_obj,
                        notation=phonetic_notation,
                        notation_type='IPA'
                    )
                self.stdout.write(f"  已建立基礎單字: {text}")
            return word_obj

        # 1. 建立搭配詞數據 (Collocations)
        collocations_data = [
            {
                'word': 'contract',
                'word_pos': 'n', 'word_trans': '合約，契約', 'word_def': 'an official written agreement', 'word_phonetic': 'ˈkɒntrækt',
                'phrase': 'draw up a contract',
                'missing_part': 'draw up',
                'translation': '擬定合約',
                'distractors': ['make', 'do', 'perform']
            },
            {
                'word': 'contract',
                'word_pos': 'n', 'word_trans': '合約，契約', 'word_def': 'an official written agreement', 'word_phonetic': 'ˈkɒntrækt',
                'phrase': 'sign a contract',
                'missing_part': 'sign',
                'translation': '簽署合約',
                'distractors': ['write', 'do', 'take']
            },
            {
                'word': 'negotiate',
                'word_pos': 'v', 'word_trans': '談判，協商', 'word_def': 'to try to reach an agreement by discussion', 'word_phonetic': 'nɪˈɡəʊʃɪeɪt',
                'phrase': 'negotiate a deal',
                'missing_part': 'negotiate',
                'translation': '洽談交易',
                'distractors': ['do', 'perform', 'make']
            },
            {
                'word': 'implement',
                'word_pos': 'v', 'word_trans': '實施，執行', 'word_def': 'to start using a plan or system', 'word_phonetic': 'ˈɪmplɪment',
                'phrase': 'implement a strategy',
                'missing_part': 'implement',
                'translation': '實施策略',
                'distractors': ['do', 'make', 'perform']
            },
            {
                'word': 'revenue',
                'word_pos': 'n', 'word_trans': '收益，營收', 'word_def': 'money that a company receives from its business', 'word_phonetic': 'ˈrevənjuː',
                'phrase': 'generate revenue',
                'missing_part': 'generate',
                'translation': '創造營收',
                'distractors': ['make', 'build', 'do']
            },
            {
                'word': 'deficit',
                'word_pos': 'n', 'word_trans': '赤字，虧損', 'word_def': 'the amount by which money spent is more than money received', 'word_phonetic': 'ˈdefɪsɪt',
                'phrase': 'run a deficit',
                'missing_part': 'run',
                'translation': '面臨赤字',
                'distractors': ['make', 'perform', 'do']
            },
            {
                'word': 'residence',
                'word_pos': 'n', 'word_trans': '住宅，居住地', 'word_def': 'a home; the state of living in a place', 'word_phonetic': 'ˈrezɪdəns',
                'phrase': 'take up residence',
                'missing_part': 'take up',
                'translation': '定居，開始居住',
                'distractors': ['make', 'do', 'establish_temp']
            },
            {
                'word': 'proposal',
                'word_pos': 'n', 'word_trans': '提案，建議', 'word_def': 'a formal plan or suggestion', 'word_phonetic': 'prəˈpəʊzl',
                'phrase': 'submit a proposal',
                'missing_part': 'submit',
                'translation': '遞交提案',
                'distractors': ['do', 'make', 'perform']
            },
            {
                'word': 'agreement',
                'word_pos': 'n', 'word_trans': '協定，一致同意', 'word_def': 'the state of sharing the same opinion', 'word_phonetic': 'əˈɡriːmənt',
                'phrase': 'reach an agreement',
                'missing_part': 'reach',
                'translation': '達成協議',
                'distractors': ['arrive', 'touch', 'get_at']
            },
            {
                'word': 'agenda',
                'word_pos': 'n', 'word_trans': '議程，待辦清單', 'word_def': 'a list of matters to be discussed at a meeting', 'word_phonetic': 'əˈdʒendə',
                'phrase': 'set the agenda',
                'missing_part': 'set',
                'translation': '設定議程',
                'distractors': ['make', 'write', 'build']
            }
        ]

        col_count = 0
        for col_item in collocations_data:
            word_obj = get_or_create_word(
                text=col_item['word'],
                pos=col_item['word_pos'],
                translation=col_item['word_trans'],
                definition=col_item['word_def'],
                phonetic_notation=col_item['word_phonetic']
            )
            # 建立搭配詞
            col_obj, created = Collocation.objects.get_or_create(
                word=word_obj,
                phrase=col_item['phrase'],
                defaults={
                    'missing_part': col_item['missing_part'],
                    'translation': col_item['translation'],
                    'distractors': col_item['distractors']
                }
            )
            if created:
                col_count += 1

        self.stdout.write(self.style.SUCCESS(f"成功導入 {col_count} 個搭配詞題目！"))

        # 2. 建立混淆配對數據 (Confusables)
        confusables_data = [
            {
                'w1': 'complement', 'w1_pos': 'v', 'w1_trans': '補充，補足', 'w1_def': 'to make something seem better or complete', 'w1_phonetic': 'ˈkɒmplɪment',
                'w2': 'compliment', 'w2_pos': 'v', 'w2_trans': '稱讚，恭維', 'w2_def': 'to praise or express admiration for someone', 'w2_phonetic': 'ˈkɒmplɪment',
                'exp': 'complement (v. 補充，相輔相成) ↔ compliment (v. 稱讚，恭維)'
            },
            {
                'w1': 'assess', 'w1_pos': 'v', 'w1_trans': '評估，估價', 'w1_def': 'to judge the number, value, or quality of something', 'w1_phonetic': 'əˈses',
                'w2': 'access', 'w2_pos': 'n', 'w2_trans': '使用權，通道', 'w2_def': 'the method or possibility of getting near to a place or person', 'w2_phonetic': 'ˈækses',
                'exp': 'assess (v. 評估，估量) ↔ access (n. 使用權，通道)'
            },
            {
                'w1': 'personal', 'w1_pos': 'adj', 'w1_trans': '個人的，私人的', 'w1_def': 'relating or belonging to a single person', 'w1_phonetic': 'ˈpɜːsənl',
                'w2': 'personnel', 'w2_pos': 'n', 'w2_trans': '全體員工，人事部門', 'w2_def': 'the people who are employed in an organization', 'w2_phonetic': 'ˌpɜːsəˈnel',
                'exp': 'personal (adj. 個人的，私人的) ↔ personnel (n. 全體員工，人事處)'
            },
            {
                'w1': 'advice', 'w1_pos': 'n', 'w1_trans': '建議，忠告', 'w1_def': 'an opinion or a suggestion about what somebody should do', 'w1_phonetic': 'ədˈvaɪs',
                'w2': 'advise', 'w2_pos': 'v', 'w2_trans': '建議，向...提出勸告', 'w2_def': 'to tell somebody what you think they should do', 'w2_phonetic': 'ədˈvaɪz',
                'exp': 'advice (n. 名詞忠告，不可數) ↔ advise (v. 動詞建議，及物動詞)'
            },
            {
                'w1': 'accept', 'w1_pos': 'v', 'w1_trans': '接受，同意', 'w1_def': 'to take willingly something that is offered', 'w1_phonetic': 'əkˈsept',
                'w2': 'except', 'w2_pos': 'prep', 'w2_trans': '除了...之外', 'w2_def': 'not including; but not', 'w2_phonetic': 'ɪkˈsept',
                'exp': 'accept (v. 接受，認可) ↔ except (prep. 除了...之外，不包含)'
            }
        ]

        conf_count = 0
        for conf_item in confusables_data:
            word1 = get_or_create_word(
                text=conf_item['w1'], pos=conf_item['w1_pos'],
                translation=conf_item['w1_trans'], definition=conf_item['w1_def'],
                phonetic_notation=conf_item['w1_phonetic']
            )
            word2 = get_or_create_word(
                text=conf_item['w2'], pos=conf_item['w2_pos'],
                translation=conf_item['w2_trans'], definition=conf_item['w2_def'],
                phonetic_notation=conf_item['w2_phonetic']
            )

            # 建立雙向混淆關係
            _, c1 = WordConfusable.objects.get_or_create(
                word=word1,
                confusable=word2,
                defaults={'explanation': conf_item['exp']}
            )
            _, c2 = WordConfusable.objects.get_or_create(
                word=word2,
                confusable=word1,
                defaults={'explanation': conf_item['exp']}
            )
            if c1 or c2:
                conf_count += 1

        self.stdout.write(self.style.SUCCESS(f"成功導入 {conf_count} 組混淆辨析對決題目！"))
        self.stdout.write(self.style.SUCCESS("題庫種子資料導入完成！"))
