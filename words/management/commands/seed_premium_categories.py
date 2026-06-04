import time
import json
from django.core.management.base import BaseCommand
from words.models import Word, WordSense, Phonetic, Example, Category
from vocab.ai_service import get_client

class Command(BaseCommand):
    help = 'Seeds premium word categories (TOEIC, IELTS, TOEFL, GRE, Slangs) with curated word lists.'

    def handle(self, *args, **kwargs):
        client = get_client()
        if not client:
            self.stdout.write(self.style.ERROR("GEMINI_API_KEY is not set. Cannot run premium seeder."))
            return

        # 1. New categories definition with static lists
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
                    'tariff', 'unanimous', 'venture', 'warranty', 'yield', 
                    'terminate', 'stimulate', 'speculate', 'solvent', 'recruitment', 
                    'quota', 'propel', 'predecessor', 'payroll', 'accumulate', 
                    'adhere', 'administer', 'advertise', 'advocate', 'affiliate', 
                    'alleviate', 'amend', 'appraise', 'approve', 'arbitrate', 
                    'assert', 'assign', 'audit', 'authorize', 'benefit', 
                    'budget', 'collaborate', 'compensate', 'comply', 'conclude', 
                    'conduct', 'confirm', 'consent', 'coordinate', 'curtail', 
                    'decrease', 'deduct', 'defray', 'demolish', 'depreciate', 
                    'designate', 'deteriorate', 'disclose', 'discrepancy', 'disrupt', 
                    'distribute', 'diversify', 'dividend', 'dominate', 'drastic', 
                    'durable', 'efficiency', 'eligible', 'emphasize', 'encounter', 
                    'enterprise', 'entrepreneur', 'estimate', 'exceed'
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
                    'credulous', 'dearth', 'decorum', 'deference', 'delineate', 
                    'demagogue', 'depravity', 'deprecate', 'deride', 'desecrate', 
                    'desiccate', 'despondent', 'despot', 'destitute', 'desultory', 
                    'deterrent', 'devious', 'didactic', 'diffident', 'digression', 
                    'diligence', 'disavow', 'discern', 'disconsolate', 'discordant', 
                    'discrepancy', 'discursive', 'disgain', 'disingenuous', 'disinterested', 
                    'disparage', 'disparate', 'disparity', 'dispassionate', 'dispel', 
                    'disperse', 'disrepute', 'dissemble', 'disseminate', 'dissension', 
                    'dissipate', 'dissonance', 'persuade', 'prohibit', 'contradict', 
                    'diminish', 'enhance', 'integrate', 'manifest', 'refute', 
                    'transform', 'undermine', 'validate', 'empirical', 'hypothesis', 
                    'interpretation', 'methodology', 'phenomenon', 'perspective', 'significance', 
                    'subsequent', 'sustainable', 'vulnerable'
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
                    'available', 'aware', 'benefit', 'bias', 'bond', 
                    'brief', 'capable', 'capacity', 'category', 'cause', 
                    'cease', 'challenge', 'channel', 'chapter', 'chart', 
                    'chemical', 'circumstance', 'cite', 'civil', 'clarify', 
                    'classic', 'clause', 'code', 'coherent', 'coincide', 
                    'collapse', 'colleague', 'commence', 'comment', 'commission', 
                    'commit', 'commodity', 'communicate', 'community', 'compatible', 
                    'compensate', 'compile', 'complement', 'complex', 'component', 
                    'compound', 'comprehensive', 'comprise', 'compute', 'conceive', 
                    'concentrate', 'concept', 'conclude', 'concrete', 'condition', 
                    'conduct', 'confer', 'confine', 'confirm', 'conflict', 
                    'conform', 'consent', 'consequent', 'considerable', 'consist', 
                    'constant', 'constitute', 'constrain', 'construct', 'consult'
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
                    'burnish', 'buttress', 'cacophonous', 'capricious', 'castigation', 
                    'catalyst', 'caustic', 'chicanery', 'coalesce', 'cogent', 
                    'commensurate', 'compendium', 'complaisant', 'compliant', 'conciliatory', 
                    'condone', 'confound', 'connoisseur', 'contention', 'contentious', 
                    'contrite', 'conundrum', 'convoluted', 'craven', 'credulous', 
                    'decorum', 'deference', 'delineate', 'demur', 'deride', 
                    'derivative', 'desiccate', 'desultory', 'diatribe', 'dichotomy', 
                    'diffident', 'dilate', 'dilatory', 'dilettante', 'dirge', 
                    'disabuse', 'discern', 'discrepant', 'disingenuous', 'disinterested', 
                    'disparage', 'disparate', 'dissemble', 'disseminate', 'dissolution', 
                    'dissonance', 'distend', 'divest', 'dogmatic', 'dolt', 
                    'dupe', 'ebullient', 'efficacious', 'effrontery', 'elegy', 
                    'elicit', 'eloquent', 'embellish', 'empirical', 'emulate'
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
                    'squad', 'goals', 'fit', 'drip', 'finna', 
                    'gonna', 'wanna', 'bae', 'boujee', 'period', 
                    'bet', 'bruh', 'yeet'
                ]
            }
        }

        # 2. Create categories and associate words
        new_categories = {}
        all_words_to_enrich = set()

        self.stdout.write("Initializing categories and mapping words...")
        for cat_name, cat_info in categories_def.items():
            cat_obj, created = Category.objects.get_or_create(
                name=cat_name,
                defaults={
                    'description': cat_info['description'],
                    'color': cat_info['color'],
                    'order': cat_info['order']
                }
            )
            if not created:
                # Update attributes if category already exists
                cat_obj.description = cat_info['description']
                cat_obj.color = cat_info['color']
                cat_obj.order = cat_info['order']
                cat_obj.save()
            new_categories[cat_name] = cat_obj

            words_list = cat_info['words']
            for word_text in words_list:
                if not word_text:
                    continue
                word_obj, word_created = Word.objects.get_or_create(
                    text=word_text,
                    defaults={'source': 'AI_BATCH'}
                )
                word_obj.categories.add(cat_obj)
                
                # If newly created or not enriched yet, add to enrichment set
                if word_created or word_obj.source != 'AI_BATCH' or not word_obj.senses.exists():
                    all_words_to_enrich.add(word_obj)

        self.stdout.write(self.style.WARNING(f"Total unique words needing AI enrichment: {len(all_words_to_enrich)}"))

        # 3. Batch enrich words
        words_to_enrich = list(all_words_to_enrich)
        total = len(words_to_enrich)
        batch_size = 20
        success_count = 0
        fail_count = 0

        for i in range(0, total, batch_size):
            batch = words_to_enrich[i:i+batch_size]
            word_texts = [w.text for w in batch]
            word_dict = {w.text: w for w in batch}
            
            self.stdout.write(f"[{i+1}/{total}] Processing batch of {len(batch)} words: {', '.join(word_texts[:5])}...")
            
            prompt = f"""請扮演專業的英文字典編輯。
以下是 {len(batch)} 個英文單字/短語：
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

        # 4. Delete old demo categories (TOEIC 金榜 900, GRE 殺手級字彙, 美劇日常俚語)
        old_cat_names = ['TOEIC 金榜 900', 'GRE 殺手級字彙', '美劇日常俚語']
        for old_name in old_cat_names:
            try:
                old_cat = Category.objects.get(name=old_name)
                # Keep words, just delete the category relations and the category itself
                old_cat.delete()
                self.stdout.write(self.style.SUCCESS(f"Deleted old category '{old_name}'"))
            except Category.DoesNotExist:
                pass

        self.stdout.write(self.style.SUCCESS("All premium categories successfully populated and old categories deleted!"))
