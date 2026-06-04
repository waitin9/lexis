import os
import sys
import django
import time
import json

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from words.models import Word, WordSense, Phonetic, Example, Category
from vocab.models import UserVocab, SRSCard, ReviewLog, UserWordStatus, UserProfile
from django.contrib.auth.models import User
from vocab.ai_service import get_client

def reset_and_seed():
    client = get_client()
    if not client:
        print("ERROR: GEMINI_API_KEY is not set.")
        return

    print("Step 1: Deleting learning history for all users...")
    ReviewLog.objects.all().delete()
    SRSCard.objects.all().delete()
    UserVocab.objects.all().delete()
    UserWordStatus.objects.all().delete()
    
    # Reset UserProfiles
    for profile in UserProfile.objects.all():
        profile.streak = 0
        profile.last_study_date = None
        profile.total_reviews = 0
        profile.total_learned = 0
        profile.save()
    print("  -> User progress reset completed.")

    print("Step 2: Cleaning up existing categories and words...")
    Category.objects.all().delete()
    Word.objects.all().delete()
    print("  -> Old categories and words deleted.")

    # 3. New premium categories definition
    categories_def = {
        '多益職場商務 (TOEIC)': {
            'description': '多益高頻核心單字，職場與商務溝通必備',
            'color': '#3498db',
            'order': 1,
            'words': [
                'implement', 'revenue', 'negotiate', 'strategy', 'evaluate', 
                'compile', 'comprehensive', 'allocate', 'fluctuate', 'productivity', 
                'merger', 'acquire', 'agenda', 'consult', 'contract', 
                'deficit', 'delegate', 'dispatch', 'endorse', 'franchise', 
                'invoice', 'liability', 'logistics', 'monopoly', 'nominate', 
                'outsource', 'patent', 'portfolio', 'precautious', 'prospective', 
                'reconcile', 'redundant', 'remuneration', 'retail', 'subsidiary', 
                'tariff', 'unanimous', 'venture', 'warranty', 'yield'
            ]
        },
        '雅思學術挑戰 (IELTS)': {
            'description': '雅思考試必背單字，涵蓋學術與日常討論',
            'color': '#2ecc71',
            'order': 2,
            'words': [
                'meticulous', 'ephemeral', 'ubiquitous', 'obfuscate', 'cacophony', 
                'enigma', 'paradigm', 'alacrity', 'sycophant', 'mitigate', 
                'aesthetic', 'altruism', 'ambivalent', 'anomaly', 'apathy', 
                'arbitrary', 'assiduous', 'audacious', 'austere', 'benevolent', 
                'capricious', 'censor', 'charlatan', 'coalesce', 'cogent', 
                'collusion', 'complacent', 'concede', 'condone', 'connoisseur', 
                'consensus', 'contentious', 'conundrum', 'copious', 'corroborate', 
                'credulous', 'dearth', 'decorum', 'deference', 'delineate'
            ]
        },
        '托福留學必備 (TOEFL)': {
            'description': '托福聽力與閱讀高頻詞，涵蓋校園與學術學科',
            'color': '#9b59b6',
            'order': 3,
            'words': [
                'absorb', 'accumulate', 'adapt', 'adjacent', 'affect', 
                'aggregate', 'albeit', 'allocate', 'alter', 'alternative', 
                'ambiguous', 'analyze', 'anticipate', 'apparent', 'appendix', 
                'appreciate', 'approach', 'appropriate', 'approximate', 'arbitrary', 
                'area', 'aspect', 'assemble', 'assess', 'assign', 
                'assist', 'assume', 'assure', 'attach', 'attain', 
                'attitude', 'attribute', 'author', 'authority', 'automate', 
                'available', 'aware', 'benefit', 'bias', 'bond'
            ]
        },
        'GRE 殺手學術彙編 (GRE)': {
            'description': 'GRE/GMAT 高難度字彙，邏輯與學術閱讀必載',
            'color': '#e74c3c',
            'order': 4,
            'words': [
                'aberrant', 'abjure', 'abscond', 'accolade', 'acerbic', 
                'acumen', 'admonish', 'adulterate', 'aesthetic', 'aggrandize', 
                'alacrity', 'amalgamate', 'ameliorate', 'anachronism', 'anomalous', 
                'antipathy', 'antithesis', 'apocryphal', 'appease', 'approbation', 
                'arduous', 'artless', 'ascetic', 'assuage', 'attenuate', 
                'audacious', 'austere', 'autonomous', 'aver', 'banal', 
                'belie', 'beneficent', 'bombastic', 'boorish', 'burgeon', 
                'burnish', 'buttress', 'cacophonous', 'capricious', 'castigation'
            ]
        },
        '美劇日常流行俚語 (Slangs)': {
            'description': '美國人日常生活最常講的口語、流行語與俚語',
            'color': '#f1c40f',
            'order': 5,
            'words': [
                'ghosting', 'flex', 'lit', 'salty', 'sus', 
                'vibe', 'cringe', 'hype', 'no cap', 'periodt', 
                'slay', 'extra', 'lowkey', 'highkey', 'shook', 
                'simp', 'tea', 'cap', 'clout', 'cancelled', 
                'snack', 'stan', 'gucci', 'snatched', 'fire', 
                'basic', 'savage', 'shady', 'fam', 'bro', 
                'squad', 'goals', 'fit', 'drip', 'yeet'
            ]
        }
    }

    # Create Categories and link Word structures
    print("Step 3: Seeding new premium categories...")
    all_words_to_enrich = set()
    for cat_name, cat_info in categories_def.items():
        cat_obj = Category.objects.create(
            name=cat_name,
            description=cat_info['description'],
            color=cat_info['color'],
            order=cat_info['order']
        )
        print(f"  Category created: {cat_name}")

        for word_text in cat_info['words']:
            word_obj, created = Word.objects.get_or_create(
                text=word_text,
                defaults={'source': 'AI_BATCH'}
            )
            word_obj.categories.add(cat_obj)
            all_words_to_enrich.add(word_obj)

    print(f"Step 4: Batch enriching {len(all_words_to_enrich)} premium words via Gemini...")
    words_to_enrich = list(all_words_to_enrich)
    total = len(words_to_enrich)
    batch_size = 20
    success_count = 0
    fail_count = 0

    for i in range(0, total, batch_size):
        batch = words_to_enrich[i:i+batch_size]
        word_texts = [w.text for w in batch]
        word_dict = {w.text: w for w in batch}
        
        print(f"[{i+1}/{total}] Processing batch of {len(batch)} words: {', '.join(word_texts[:5])}...")
        
        prompt = f"""請扮演專業的英文字典編輯。
以下是 {len(batch)} 個英文單字：
{json.dumps(word_texts)}

請回傳一個嚴格的 JSON Array，每個元素包含：
- "word": 單字本身 (必須與給定的單字完全一致)
- "ipa_us": 美式音標 (不含斜線)
- "senses": 一個 Array，包含該單字最常見的 1 到 3 個義項 (不同詞性或明顯不同的意思)。
  每個義項包含：
  - "part_of_speech": 詞性簡寫 (n, v, adj, adv, prep, conj, pron, phrase)
  - "translation": 繁體中文翻譯
  - "definition": 英文解釋
  - "example_sentence": 英文例句
  - "example_translation": 例句翻譯

請務必回傳嚴格的 JSON Array 格式。不允許 Markdown code blocks。"""

        success = False
        retries = 5
        backoff = 60

        while not success and retries > 0:
            try:
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt,
                    config={
                        'response_mime_type': 'application/json',
                        'temperature': 0.1,
                    },
                )
                
                results = json.loads(response.text)
                if not isinstance(results, list):
                    raise ValueError("AI did not return a list")
                
                for item in results:
                    w_text = item.get('word', '').lower()
                    if w_text in word_dict:
                        word = word_dict[w_text]
                        
                        # Clear old data
                        word.senses.all().delete()
                        word.phonetics.all().delete()
                        
                        # Add Phonetic
                        if item.get('ipa_us'):
                            Phonetic.objects.create(word=word, notation=item['ipa_us'], notation_type='IPA')
                            
                        # Add Senses
                        senses_data = item.get('senses', [])
                        order = 1
                        for s_data in senses_data:
                            sense = WordSense.objects.create(
                                word=word,
                                part_of_speech=s_data.get('part_of_speech', 'unknown')[:10],
                                translation=s_data.get('translation', ''),
                                definition=s_data.get('definition', ''),
                                order=order
                            )
                            order += 1
                            if s_data.get('example_sentence'):
                                Example.objects.create(
                                    sense=sense,
                                    sentence=s_data['example_sentence'],
                                    translation=s_data.get('example_translation', '')
                                )
                        
                        # Mark as processed
                        word.source = 'AI_BATCH'
                        word.save()
                        success_count += 1
                        
                print(f"  -> Batch success!")
                success = True
                
            except Exception as e:
                err_msg = str(e)
                if 'RESOURCE_EXHAUSTED' in err_msg or '429' in err_msg:
                    print(f"  -> Rate limited, waiting {backoff}s before retry... Error: {e}")
                    time.sleep(backoff)
                    backoff *= 2
                    retries -= 1
                else:
                    fail_count += len(batch)
                    print(f"  -> Batch failed: {e}")
                    break
        
        if not success and retries == 0:
            fail_count += len(batch)
            print(f"  -> Batch failed after maximum retries.")

        time.sleep(5) # Avoid rate limits

    print(f"\nSeeding complete! Successfully enriched {success_count} words. Failed: {fail_count}.")

if __name__ == "__main__":
    reset_and_seed()
