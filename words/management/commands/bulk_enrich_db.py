import time
import json
from django.core.management.base import BaseCommand
from words.models import Word, WordSense, Phonetic, Example
from vocab.ai_service import get_client

class Command(BaseCommand):
    help = 'Bulk enrich database words using Gemini AI in batches.'

    def handle(self, *args, **kwargs):
        client = get_client()
        if not client:
            self.stdout.write(self.style.ERROR("GEMINI_API_KEY is not set. Cannot run bulk enrichment."))
            return

        # Prioritize words in UserVocab. First, get list of official word IDs in UserVocab
        from django.db.models import Case, When, Value, BooleanField
        from vocab.models import UserVocab
        user_word_ids = set(UserVocab.objects.filter(word__isnull=False).values_list('word_id', flat=True))

        words_to_enrich = list(
            Word.objects.exclude(source='AI_BATCH')
            .annotate(
                is_user_vocab=Case(
                    When(id__in=user_word_ids, then=Value(True)),
                    default=Value(False),
                    output_field=BooleanField()
                )
            )
            .order_by('-is_user_vocab', 'id')
        )
        total = len(words_to_enrich)
        
        self.stdout.write(self.style.WARNING(f"Found {total} words needing AI enrichment (prioritizing {len(user_word_ids)} words in user vocabulary)."))
        if total == 0:
            self.stdout.write(self.style.SUCCESS("All words are already fully enriched!"))
            return

        batch_size = 20
        success_count = 0
        fail_count = 0

        for i in range(0, total, batch_size):
            batch = words_to_enrich[i:i+batch_size]
            word_texts = [w.text for w in batch]
            word_dict = {w.text: w for w in batch}
            
            self.stdout.write(f"[{i+1}/{total}] Processing batch of {len(batch)} words: {', '.join(word_texts[:5])}...")
            
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
            retries = 3
            backoff = 15

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
                            
                    self.stdout.write(self.style.SUCCESS(f"  -> Batch success!"))
                    success = True
                    
                except Exception as e:
                    err_msg = str(e)
                    if 'RESOURCE_EXHAUSTED' in err_msg or '429' in err_msg:
                        self.stdout.write(self.style.WARNING(f"  -> Rate limited, waiting {backoff}s before retry... Error: {e}"))
                        time.sleep(backoff)
                        backoff *= 2
                        retries -= 1
                    else:
                        fail_count += len(batch)
                        self.stdout.write(self.style.ERROR(f"  -> Batch failed: {e}"))
                        break
            
            if not success and retries == 0:
                fail_count += len(batch)
                self.stdout.write(self.style.ERROR(f"  -> Batch failed after maximum retries."))

            time.sleep(5) # Avoid rate limits

        self.stdout.write(self.style.SUCCESS(f"\\nDone! Successfully enriched {success_count} words. Failed: {fail_count}."))

