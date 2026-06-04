import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from words.models import Word, WordSense, Example

fixes = [
    {
        'word': 'ethics',
        'ipa_us': 'ˈeθɪks',
        'senses': [
            {
                'pos': 'n',
                'translation': '倫理學；道德規範',
                'definition': 'the study of what is morally right and wrong, or a set of beliefs about what is morally right and wrong',
                'example': 'She studied ethics at university.',
                'example_trans': '她在大學研讀倫理學。',
            }
        ]
    },
    {
        'word': 'goods',
        'ipa_us': 'ɡʊdz',
        'senses': [
            {
                'pos': 'n',
                'translation': '商品；貨物',
                'definition': 'things that are made to be sold; movable property',
                'example': 'The store sells a wide range of goods.',
                'example_trans': '這家商店出售各種各樣的商品。',
            }
        ]
    },
    {
        'word': 'repairperson',
        'ipa_us': 'rɪˈpɛrˌpɜrsən',
        'senses': [
            {
                'pos': 'n',
                'translation': '維修人員',
                'definition': 'a person whose job is to repair things',
                'example': 'The repairperson fixed the washing machine.',
                'example_trans': '維修人員修好了洗衣機。',
            }
        ]
    },
]

from words.models import Phonetic
from vocab.views import _ipa_to_kk

for fix in fixes:
    try:
        w = Word.objects.get(text=fix['word'])
        # Clear old senses and phonetics
        w.senses.all().delete()
        w.phonetics.all().delete()

        # Add phonetics
        ipa = fix['ipa_us']
        if ipa:
            Phonetic.objects.create(word=w, notation=ipa, notation_type='IPA')
            kk = _ipa_to_kk(ipa)
            if kk:
                Phonetic.objects.create(word=w, notation=kk, notation_type='KK')

        # Add senses
        for idx, s in enumerate(fix['senses'], 1):
            sense = WordSense.objects.create(
                word=w,
                part_of_speech=s['pos'],
                translation=s['translation'],
                definition=s['definition'],
                order=idx
            )
            if s.get('example'):
                Example.objects.create(
                    sense=sense,
                    sentence=s['example'],
                    translation=s['example_trans']
                )
        print(f"✓ Fixed: {fix['word']}")
    except Word.DoesNotExist:
        print(f"✗ Not found: {fix['word']}")
    except Exception as e:
        print(f"✗ Error ({fix['word']}): {e}")
