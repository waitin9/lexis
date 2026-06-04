import os
import sys
import django
import urllib.request
import urllib.parse
import json
import time

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from words.models import Word, WordSense, Phonetic, Example, Category
from vocab.models import UserVocab, SRSCard, ReviewLog, UserWordStatus, UserProfile

def download_words():
    print("Sourcing words from GitHub TKomi/FlashCard-Data (TOEIC Service List)...")
    words_list = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    for i in range(1, 26):
        url = f"https://raw.githubusercontent.com/TKomi/FlashCard-Data/master/tsl/part{i}.json"
        success = False
        retries = 3
        while not success and retries > 0:
            try:
                print(f"  Downloading Part {i}/25 from {url}...")
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=8) as response:
                    data = json.loads(response.read().decode('utf-8'))
                    for item in data:
                        word = item.get('word', '').strip().lower()
                        if word and word not in words_list:
                            words_list.append(word)
                success = True
            except Exception as e:
                retries -= 1
                print(f"    Error downloading Part {i}: {e}. Retries remaining: {retries}")
                time.sleep(1)
                
    print(f"Successfully downloaded {len(words_list)} unique TOEIC words.")
    return words_list

def reset_and_seed():
    # 1. Download words first to make sure network is fine
    words = download_words()
    if not words:
        print("ERROR: No words downloaded. Seeding aborted.")
        return
        
    print("\nStep 1: Deleting learning history for all users...")
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

    print("\nStep 2: Cleaning up existing categories and words...")
    Category.objects.all().delete()
    Word.objects.all().delete()
    print("  -> Old categories and words deleted.")

    print("\nStep 3: Seeding new TOEIC Category...")
    toeic_category = Category.objects.create(
        name="多益核心字庫 (TOEIC)",
        description="官方多益服務字表 (TOEIC Service List，簡稱 TSL)，涵蓋 99% 多益考試高頻商業與職場字彙",
        color="#3498db",
        order=1
    )
    print(f"  Category created: {toeic_category.name}")

    print("\nStep 4: Importing 1,250 words to database...")
    words_to_create = []
    for word_text in words:
        # Check if word is duplicate (should not be based on list set)
        words_to_create.append(Word(
            text=word_text,
            difficulty=2, # Default difficulty for TOEIC
            source='TOEIC_TSL'
        ))
        
    # Bulk create words for speed
    Word.objects.bulk_create(words_to_create)
    
    # Link words to Category (Django bulk_create doesn't do m2m, so we associate them)
    all_inserted_words = list(Word.objects.filter(source='TOEIC_TSL'))
    ThroughModel = Word.categories.through
    relations = [
        ThroughModel(word_id=w.id, category_id=toeic_category.id)
        for w in all_inserted_words
    ]
    ThroughModel.objects.bulk_create(relations)
    
    print(f"Successfully seeded {len(all_inserted_words)} words into '{toeic_category.name}'!")

if __name__ == "__main__":
    reset_and_seed()
