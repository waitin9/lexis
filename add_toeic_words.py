import os
import sys
import django
import json
import time
import argparse
from pydantic import BaseModel, Field
from typing import List

# Setup path and Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from words.models import Word, Category, WordSense, Phonetic, Example
from vocab.ai_service import get_client
from vocab.views import enrich_word_from_api, _ipa_to_kk
from scrape_cambridge_definitions import scrape_word

# Reconfigure standard output for Windows encoding safety
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(errors='replace')

class WordListResult(BaseModel):
    words: List[str] = Field(description="List of unique high-frequency business English/TOEIC words")

def enrich_word_from_cambridge(word_obj):
    """嘗試從劍橋字典網頁直接爬取數據並寫入資料庫"""
    try:
        data, status = scrape_word(word_obj.text)
        if status == "ok" and data and data.get('senses'):
            # 清除舊的釋義與音標
            word_obj.senses.all().delete()
            word_obj.phonetics.all().delete()

            # 儲存音標
            ipa_us = data.get('ipa_us', '')
            if ipa_us:
                Phonetic.objects.create(word=word_obj, notation=ipa_us, notation_type='IPA')
                kk = _ipa_to_kk(ipa_us)
                if kk:
                    Phonetic.objects.create(word=word_obj, notation=kk, notation_type='KK')

            # 儲存釋義與例句
            for o_idx, s_data in enumerate(data['senses'], 1):
                pos = s_data.get('part_of_speech', 'unknown')[:10]
                translation = s_data.get('translation', '').strip()
                # 統一分號
                translation = translation.replace(';', '；').replace(' ；', '；').replace('； ', '；')
                definition = s_data.get('definition', '')

                sense = WordSense.objects.create(
                    word=word_obj,
                    part_of_speech=pos,
                    definition=definition,
                    translation=translation,
                    order=o_idx
                )

                ex_sentence = s_data.get('example_sentence', '')
                ex_trans = s_data.get('example_translation', '')
                if ex_sentence:
                    Example.objects.create(
                        sense=sense,
                        sentence=ex_sentence,
                        translation=ex_trans
                    )
            return True
    except Exception as e:
        print(f"  -> Cambridge scraper exception for '{word_obj.text}': {e}")
    return False

def get_existing_words():
    """獲取目前資料庫中所有已存在的單字"""
    return set(Word.objects.values_list('text', flat=True))

def generate_toeic_words_batch(client, exclude_list, count=100, max_retries=3, delay=20):
    """要求 Gemini API 生成一批高頻多益商務單字"""
    # 限制傳遞給 API 的排除列表大小以節省 token，只挑前 1200 個單字
    partial_exclude = list(exclude_list)[:1200]
    
    prompt = f"""
    Please act as a professional vocabulary specialist for the TOEIC (Test of English for International Communication) exam.
    I have a database that already contains {len(exclude_list)} TOEIC words. Here is the list of existing words to avoid duplication:
    {json.dumps(partial_exclude)}

    Please generate a list of exactly {count} unique, high-frequency TOEIC/business English words that are NOT in the list above.
    
    【Guidelines】:
    1. The words must be highly practical for the TOEIC exam, representing workplace, management, and commercial themes (e.g. finance, contracts, human resources, shipping, office communication, banking, and travel).
    2. Focus on intermediate and advanced words (B2/C1 level, e.g. 'reimburse', 'compliance', 'discrepancy', 'feasibility', 'mandatory', 'incentive'). Avoid overly simple words like 'office', 'computer', 'pencil', 'happy'.
    3. Words must be single English words (no spaces, no hyphens, containing only alphabetic characters).
    4. Only output a valid JSON matching the schema. No markdown wrapping.
    """
    
    for attempt in range(1, max_retries + 1):
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config={
                    'response_mime_type': 'application/json',
                    'response_schema': WordListResult,
                    'temperature': 0.5,
                }
            )
            data = json.loads(response.text)
            raw_words = data.get('words', [])
            # 清理並過濾掉不合法的字
            cleaned_words = []
            for w in raw_words:
                w_clean = w.strip().lower()
                # 檢查是否為純字母單字，且長度大於 2
                if w_clean.isalpha() and len(w_clean) > 2:
                    cleaned_words.append(w_clean)
            return cleaned_words
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
                print(f"  -> [API Rate Limit] 生成新詞列表時遭遇 429 限制，等待 {delay} 秒後重試 ({attempt}/{max_retries})...")
                time.sleep(delay)
                # 逐漸增加延遲時間以分散請求
                delay = int(delay * 1.5)
            else:
                print(f"Error generating batch from Gemini: {e}")
                break
    return []

def main():
    parser = argparse.ArgumentParser(description="增量新增多益高頻單字並解析")
    parser.add_argument('--test', action='store_true', help='執行冒煙測試模式 (僅生成 5 個單字)')
    args = parser.parse_args()
    
    target_count = 5 if args.test else 500
    print(f"=== 開始多益核心字庫增量擴充計畫 (目標數量: {target_count} 字) ===")
    
    client = get_client()
    if not client:
        print("ERROR: 未設定 GEMINI_API_KEY！請先在 .env 檔案中設定。")
        sys.exit(1)
        
    # 1. 取得多益分類
    try:
        toeic_category = Category.objects.get(name="多益核心字庫 (TOEIC)")
    except Category.DoesNotExist:
        # 相容無該分類時的狀況，建立它
        toeic_category = Category.objects.create(
            name="多益核心字庫 (TOEIC)",
            description="官方多益服務字表 (TOEIC Service List)，涵蓋高頻商業與職場字彙",
            color="#6C63FF"
        )
    
    # 2. 獲取去重排除列表
    exclude_list = get_existing_words()
    print(f"當前資料庫中已有 {len(exclude_list)} 個單字，將用於自動去重...")
    
    # 3. 收集目標數量的新詞
    print("\n[第一階段] 開始收集高頻多益新詞 (優先使用本地字表去重)...")
    
    raw_candidates = """
    negotiation prioritize feasibility incentive strategy accommodate achievement administrative advertisement agenda
    agreement allocation analysis announcement application appointment appraisal approval arrangement assembly
    assessment assignment assistance attendance attractor audience authorization baggage bankruptcy benefit
    bidder billing boardroom brochure budget campaign candidate capability capacity career
    cargo caterer certification chairman charter circulation claimant clientele collaboration colleague
    commence commitment committee compensation competence competition competitor compliance complimentary compromise
    conference confidential confirmation conglomerate consensus consent consequence consignment construction consultant
    consumer contractor contribution convene conveyance cooperation corporate correspondence credentials creditor
    deadline debtor decision declaration decline deduction deficit delegation delivery demographic
    departure deposit depreciation description destination evaluation exclusive executive exhibition expansion
    expedition expenditure expense expertise expiration facility factors faculty feedback finance
    fixtures fluctuation forecast foreclosure franchise freight fulfillment funding garment gathering
    generalization government grievance growth guarantee guideline headquarters hospitality implementation implication
    improvement inauguration incentive incorporation indemnity indicator industry inflation infrastructure initiative
    innovation inspection inspector installation institution instruction insurance integration intelligence interaction
    interest internship inventory investment invoice itinerary janitor jeopardy jointure jurisdiction
    justification landmark laundry leaseholder ledger legislation liability liaison licensing limitation
    liquidation litigation lodging logistics lubricant machinery maintenance management mandatory manufacturer
    markdown merchandise merger milestone misconduct negotiate nomination notification obligation obstacle
    occupation occurrence offering operator opportunity optimization orientation outcome outsource overtime
    overview package pamphlet parliament participant partnership passenger patented patronage payment
    penalty pension performance personnel perspective portfolio postage precaution predecessor preference
    premium presentation procedure procurement productivity profession profitability progression prohibition projection
    promotion proposal proprietor prospectus prosperity protocol provision publicity purchase qualification
    quotation realignment reassignment rebound receipt receivables reception recession recipient recommendation
    reconciliation recreation recruitment reduction redundancy referral refinancing refund registration regulation
    reimbursement rejection relocation remittance renegotiation renovation rental reorganization repair replacement
    reporter representation representative reproduction reputation requirement requisition researcher reservation resignation
    resolution resource respondent responsibility restructuring retailer retained retirement retrieval revenue
    revitalization salary satisfaction schedule scholarship screening security segmentation seller seminar
    shipment shipping shortage signature significance solicitation speculative sponsor spokesperson stability
    standardization statement statistic stockholder strategic subscription subsidiary subsidy succession supervisor
    supplier surcharge surplus survey synergy tactic tariff taxation taxpayer tenant
    termination testimonial threshold timetable tolerance tourism transaction transcript transfer transformation
    transition translation transportation treasury trend turnover ultimatum uncertainty underwriter unemployment
    union uniqueness upgrade urgency usage utility vacancy validation valuation value
    variable variance variation vendor venture verification vessel violation visitor volunteer
    voucher warehouse warranty wealth welfare withdrawal workforce workplace workshop yield
    abundant accelerate accomplish accumulate accurate accustom achieve acquire adapt adequate
    adjust administer advance adverse advocate affect afford agenda allocate allowance
    alter alternative ambiguous amend analyze anticipate apparent appeal appoint appreciate
    approach approve approximate arbitrary arise assemble assert assert assess assign assist
    associate assume assure attach attain attempt attend attract attribute auction
    audit authenticate authorize automate available average avoid award backup balance
    bargain barrier base bear behalf benchmark beneficial bias bid bind
    blend block board boost borrow boundary branch brand breach breakthrough
    brief broaden broker browse bulk burden bureau calculate calendar cancel
    candidate canvas capital career carriage carry case cash catalog category
    cater caution cease celebrate center certain certificate chain challenge chamber
    channel charge chart charter check chief chronological circumstance cite citizen
    civil claim clarify class clause clearance clerk client climate climb
    close cluster coach code collaborate collapse colleague collect column combat
    combine comfort command comment commerce commission commit committee commodity common
    communicate community company compare compel compensate compete competent compile complain
    complement complete complex comply component compose compound comprehensive compromise compute
    conceal concede concentrate concept concern concert concession conclude concrete condition
    conduct confer conference confess confidence confidential confine confirm conflict conform
    confront confuse conglomerate congratulate connect consecutive consensus consent conserve consider
    consign consist consistent consolidate consolidate consortium conspicuous conspire constant constitute constrain
    construct consult consume contact contain contaminate contemplate contend content contest
    context contingency continue contract contradict contrary contrast contribute control controversial
    convene convenient convention converge converse convert convey convince cooperate coordinate
    cope copy cordial core corner corporate correct correspond corrupt cosmopolitan
    cost council counsel count counter counteract counterfeit counterpart country couple
    courage course court courtesy covenant cover craft crash create credential
    credit creditor crew crisis criterion critic critical criticize crop cross
    crowd crucial crude cruise crush currency current curriculum curtail curve
    cushion custody custom customer cycle damage danger data date deadline
    deal dealer debate debt decade decay deceive decent decide decision
    declare decline decorate decrease decree dedicate deduct deem deepen default
    defeat defect defend defer deficient deficit define definite deflate deflect
    degrade degree delay delegate delete deliberate delicate deliver demand demolish
    demonstrate demonstrate denounce deny depart department depend depict deplete deplore deposit
    depreciate depress deprive deputy derive descend describe description desert deserve
    design designate desire desk despair despatch despite destination destroy detach
    detail detain detect deter deteriorate determine detour devalue devastate develop
    deviate device devise devote diagnose diagram dial dialogue dictate differ
    differentiate difficult diffuses digest digit dignity dilemma diligent dilute diminish
    dine diploma direct director directory disable disadvantage disagree disappear disappoint
    disapprove disaster disburse discard discern discharge discipline disclose discount discourage
    discover discrepancy discretion discriminate discuss disease disembark disgrace disguise dismiss
    disorder dispatch dispel dispense disperse displace display displease dispose disprove
    displeasure dispute disregard disrupt dissatisfied disseminate dissolve distance distort distract distribute
    district disturb diverge diverse divert divide dividend divorce document domain
    domestic dominant dominate donate donor doom door dose double doubt
    draft drag drain dramatic draw drawer dread drift drill drive
    drop drown dual due dull duplicate durable duration dust duty
    dwell dynamic earn ease echo eclipse ecology economic economical economy
    """
    
    # 清理並分詞
    local_words = [w.strip().lower() for w in raw_candidates.split() if w.strip().isalpha() and len(w.strip()) > 2]
    local_words_set = set(local_words)
    
    new_words_set = set()
    for w in local_words_set:
        if w not in exclude_list:
            new_words_set.add(w)
            if len(new_words_set) >= target_count:
                break
                
    print(f"本地去重後，成功從精選詞庫中挑選出 {len(new_words_set)}/{target_count} 個新單字。")
    
    # 如果不夠，再向 AI 索取補足
    if len(new_words_set) < target_count:
        needed = target_count - len(new_words_set)
        print(f"還差 {needed} 個單字，將向 Gemini API 進行補足索取...")
        attempts = 0
        max_attempts = 5
        batch_request_size = 100
        
        while len(new_words_set) < target_count and attempts < max_attempts:
            attempts += 1
            needed = target_count - len(new_words_set)
            req_size = min(batch_request_size, needed * 2)
            
            print(f"  AI 索取批次 {attempts}: 正在索取 {req_size} 個新字... (已收集 {len(new_words_set)}/{target_count})")
            current_exclude = exclude_list.union(new_words_set)
            batch_words = generate_toeic_words_batch(client, current_exclude, count=req_size)
            
            added_in_batch = 0
            for w in batch_words:
                if w not in current_exclude and w not in new_words_set:
                    new_words_set.add(w)
                    added_in_batch += 1
                    if len(new_words_set) >= target_count:
                        break
            
            print(f"  批次 {attempts} 結束，過濾後新增了 {added_in_batch} 個有效單字。")
            if len(new_words_set) < target_count:
                time.sleep(2.0)
        
    print(f"\n新詞選詞完成！共收集到 {len(new_words_set)} 個符合標準的商務/多益單字。")
    print(list(new_words_set))
    
    # 4. 資料庫寫入與解析
    print("\n[第二階段] 開始寫入資料庫並呼叫劍橋字典解析...")
    success_count = 0
    fail_count = 0
    
    for idx, word_text in enumerate(new_words_set, 1):
        print(f"[{idx}/{target_count}] 正在處理單字: '{word_text}'...")
        
        # 雙重保險：資料庫去重
        if Word.objects.filter(text=word_text).exists():
            print(f"  -> '{word_text}' 已在資料庫中，略過。")
            continue
            
        # 建立 Word 物件
        word_obj = Word.objects.create(
            text=word_text,
            difficulty=3, # 中高階難度
            source='TOEIC_INCREMENTAL'
        )
        word_obj.categories.add(toeic_category)
        
        # 優先呼叫真實劍橋字典解析，失敗時再 fallback 呼叫 Gemini
        try:
            print("  -> 嘗試從真實劍橋字典網頁爬取數據...")
            success = enrich_word_from_cambridge(word_obj)
            
            if not success:
                print("  -> 真實網頁爬取失敗，fallback 使用 Gemini API 解析...")
                success = enrich_word_from_api(word_obj)
                
            if success:
                # 再次驗證釋義是否存在
                if word_obj.senses.exists():
                    primary_sense = word_obj.get_primary_sense()
                    print(f"  -> 成功！音標: /{word_obj.get_phonetic_display()}/, 中文釋義: [{primary_sense.pos_display}] {primary_sense.translation}")
                    success_count += 1
                else:
                    word_obj.delete() # 釋義為空，安全移除防殘存
                    fail_count += 1
                    print(f"  -> 解析失敗：無釋義資料。已將單字 '{word_text}' 移出。")
            else:
                word_obj.delete() # 解析失敗，安全移除
                fail_count += 1
                print(f"  -> 解析失敗：爬蟲與 Gemini 均解析失敗。已將單字 '{word_text}' 移出。")
        except Exception as e:
            word_obj.delete() # 異常，安全移除
            fail_count += 1
            print(f"  -> 解析過程發生異常: {e}。已將單字 '{word_text}' 移出。")
            
        # 每次呼叫後休眠以維護 QPS 速率限制
        time.sleep(0.8)
        
    print(f"\n=== 增量擴充處理完成！ ===")
    print(f"成功寫入且完成劍橋字典解析: {success_count} 字。")
    print(f"解析失敗已移除: {fail_count} 字。")
    print(f"資料庫多益字庫當前總數: {toeic_category.words.count()} 字。")

if __name__ == "__main__":
    main()
