import json
from django.core.management.base import BaseCommand
from words.models import Category, Word, WordSense, Example, Phonetic

PREMIUM_DATA = {
    "TOEIC 金榜 900": [
        {"word": "implement", "ipa": "ˈɪmplɪmənt", "pos": "verb", "translation": "實施，貫徹", "definition": "To put a decision, plan, agreement, etc. into effect.", "example": "The company will implement the new policy next month.", "example_trans": "公司下個月將實施新政策。"},
        {"word": "strategy", "ipa": "ˈstrætədʒi", "pos": "noun", "translation": "策略", "definition": "A plan of action designed to achieve a long-term or overall aim.", "example": "We need a new marketing strategy.", "example_trans": "我們需要一個新的行銷策略。"},
        {"word": "revenue", "ipa": "ˈrɛvənu", "pos": "noun", "translation": "收入，收益", "definition": "Income, especially when of a company or organization and of a substantial nature.", "example": "Tax revenues have fallen this year.", "example_trans": "今年稅收有所下降。"},
        {"word": "executive", "ipa": "ɪɡˈzɛkjətɪv", "pos": "noun", "translation": "高階主管", "definition": "A person with senior managerial responsibility in a business organization.", "example": "The executive decided to launch the product early.", "example_trans": "這位高階主管決定提早發布產品。"},
        {"word": "negotiation", "ipa": "nɪˌɡoʊʃiˈeɪʃən", "pos": "noun", "translation": "談判，協商", "definition": "Discussion aimed at reaching an agreement.", "example": "The negotiation between the two companies was successful.", "example_trans": "兩家公司之間的談判很成功。"},
        {"word": "compliance", "ipa": "kəmˈplaɪəns", "pos": "noun", "translation": "遵守，服從", "definition": "The action or fact of complying with a wish or command.", "example": "The company is in compliance with all regulations.", "example_trans": "公司遵守所有規定。"},
        {"word": "productivity", "ipa": "ˌproʊdʌkˈtɪvɪti", "pos": "noun", "translation": "生產力", "definition": "The effectiveness of productive effort, especially in industry.", "example": "We must increase productivity to stay competitive.", "example_trans": "我們必須提高生產力以保持競爭力。"},
        {"word": "collaborate", "ipa": "kəˈlæbəreɪt", "pos": "verb", "translation": "合作", "definition": "Work jointly on an activity, especially to produce or create something.", "example": "The two teams will collaborate on the new project.", "example_trans": "這兩個團隊將合作進行新專案。"},
        {"word": "appraisal", "ipa": "əˈpreɪzəl", "pos": "noun", "translation": "評估，考核", "definition": "An act of assessing something or someone.", "example": "Employees receive an annual performance appraisal.", "example_trans": "員工每年接受一次績效考核。"},
        {"word": "initiative", "ipa": "ɪˈnɪʃətɪv", "pos": "noun", "translation": "主動性，新措施", "definition": "The ability to assess and initiate things independently.", "example": "She took the initiative to organize the meeting.", "example_trans": "她主動組織了這次會議。"}
    ],
    "GRE 殺手級字彙": [
        {"word": "ephemeral", "ipa": "ɪˈfɛmərəl", "pos": "adjective", "translation": "短暫的", "definition": "Lasting for a very short time.", "example": "Fashions are ephemeral.", "example_trans": "流行時尚是短暫的。"},
        {"word": "cacophony", "ipa": "kəˈkɑfəni", "pos": "noun", "translation": "刺耳的聲音", "definition": "A harsh, discordant mixture of sounds.", "example": "A cacophony of alarms began to ring.", "example_trans": "一陣刺耳的警報聲響起。"},
        {"word": "obsequious", "ipa": "əbˈsikiəs", "pos": "adjective", "translation": "奉承的，諂媚的", "definition": "Obedient or attentive to an excessive or servile degree.", "example": "They were served by obsequious waiters.", "example_trans": "他們由諂媚的侍者服務。"},
        {"word": "alacrity", "ipa": "əˈlækrɪti", "pos": "noun", "translation": "敏捷，樂意", "definition": "Brisk and cheerful readiness.", "example": "She accepted the invitation with alacrity.", "example_trans": "她欣然接受了邀請。"},
        {"word": "ubiquitous", "ipa": "juˈbɪkwɪtəs", "pos": "adjective", "translation": "無所不在的", "definition": "Present, appearing, or found everywhere.", "example": "Smartphones have become ubiquitous.", "example_trans": "智慧型手機已經無所不在。"},
        {"word": "esoteric", "ipa": "ˌɛsəˈtɛrɪk", "pos": "adjective", "translation": "深奧的，秘傳的", "definition": "Intended for or likely to be understood by only a small number of people with a specialized knowledge or interest.", "example": "He has an esoteric collection of old books.", "example_trans": "他收藏了一些深奧的古書。"},
        {"word": "ameliorate", "ipa": "əˈmiljəˌreɪt", "pos": "verb", "translation": "改善", "definition": "Make (something bad or unsatisfactory) better.", "example": "Steps have been taken to ameliorate the situation.", "example_trans": "已經採取措施來改善局勢。"},
        {"word": "fastidious", "ipa": "fæˈstɪdiəs", "pos": "adjective", "translation": "挑剔的，一絲不苟的", "definition": "Very attentive to and concerned about accuracy and detail.", "example": "He is fastidious about keeping the house clean.", "example_trans": "他對保持房屋清潔非常挑剔。"},
        {"word": "capricious", "ipa": "kəˈprɪʃəs", "pos": "adjective", "translation": "反覆無常的", "definition": "Given to sudden and unaccountable changes of mood or behavior.", "example": "She is a capricious and unpredictable boss.", "example_trans": "她是一個反覆無常且不可預測的老闆。"},
        {"word": "sycophant", "ipa": "ˈsɪkəfənt", "pos": "noun", "translation": "馬屁精", "definition": "A person who acts obsequiously toward someone important in order to gain advantage.", "example": "The boss was surrounded by sycophants.", "example_trans": "老闆周圍都是馬屁精。"}
    ],
    "美劇日常俚語": [
        {"word": "ghosting", "ipa": "ˈɡoʊstɪŋ", "pos": "noun", "translation": "不告而別（斷聯）", "definition": "The practice of ending a personal relationship with someone by suddenly and without explanation withdrawing from all communication.", "example": "I thought we had a good date, but he ended up ghosting me.", "example_trans": "我以為我們約會得很愉快，但他最後卻跟我斷聯了。"},
        {"word": "binge", "ipa": "bɪndʒ", "pos": "verb", "translation": "狂歡，狂看", "definition": "Indulge in an activity, especially eating, drinking, or watching television, to excess.", "example": "I plan to binge-watch the entire new season this weekend.", "example_trans": "我打算這週末狂看整季新劇。"},
        {"word": "salty", "ipa": "ˈsɔlti", "pos": "adjective", "translation": "惱羞成怒的，酸葡萄的", "definition": "Feeling or showing resentment towards someone or something.", "example": "He was salty because he lost the game.", "example_trans": "他因為輸了比賽而惱羞成怒。"},
        {"word": "flex", "ipa": "flɛks", "pos": "verb", "translation": "炫耀", "definition": "To show off or boast.", "example": "He bought a new car just to flex on his friends.", "example_trans": "他買了一輛新車只是為了在朋友面前炫耀。"},
        {"word": "spill", "ipa": "spɪl", "pos": "verb", "translation": "爆料（八卦）", "definition": "To disclose confidential or juicy information (often used in 'spill the tea').", "example": "Come on, spill the tea! What happened at the party?", "example_trans": "快點，爆料一下！派對上發生了什麼事？"},
        {"word": "shook", "ipa": "ʃʊk", "pos": "adjective", "translation": "震驚的", "definition": "Emotionally or physically disturbed; shocked.", "example": "When I saw the plot twist, I was completely shook.", "example_trans": "看到劇情的反轉，我整個人都震驚了。"},
        {"word": "basic", "ipa": "ˈbeɪsɪk", "pos": "adjective", "translation": "毫無特色的，大眾款的", "definition": "Having tastes, interests, or attitudes regarded as mainstream or conventional.", "example": "Drinking pumpkin spice lattes is so basic.", "example_trans": "喝南瓜拿鐵真的很沒特色（很跟風）。"},
        {"word": "lowkey", "ipa": "ˈloʊki", "pos": "adverb", "translation": "暗自地，有點", "definition": "To some extent, secretly, or modestly.", "example": "I lowkey want to stay home tonight.", "example_trans": "我今晚其實有點想待在家。"},
        {"word": "savage", "ipa": "ˈsævɪdʒ", "pos": "adjective", "translation": "毫不留情的，超派", "definition": "Fierce, violent, or uncontrolled, often used to describe a ruthless comeback.", "example": "Her reply to his comment was absolutely savage.", "example_trans": "她對他留言的回覆簡直毫不留情。"},
        {"word": "fomo", "ipa": "ˈfoʊmoʊ", "pos": "noun", "translation": "錯失恐懼症", "definition": "Fear Of Missing Out; anxiety that an exciting or interesting event may currently be happening elsewhere.", "example": "I went to the party just because I had major FOMO.", "example_trans": "我去參加派對只是因為我有嚴重的錯失恐懼症。"}
    ]
}

class Command(BaseCommand):
    help = 'Populate premium categories (TOEIC, GRE, Slang) with fully enriched words.'

    def handle(self, *args, **kwargs):
        for cat_name, words in PREMIUM_DATA.items():
            category, created = Category.objects.get_or_create(
                name=cat_name,
                defaults={'description': f'{cat_name} essential vocabulary', 'color': '#6c63ff'}
            )
            
            added_count = 0
            for item in words:
                text = item['word'].lower()
                word_obj, w_created = Word.objects.get_or_create(text=text, defaults={'source': 'Premium'})
                
                # Setup phonetic
                if item['ipa']:
                    Phonetic.objects.get_or_create(word=word_obj, notation_type='IPA', defaults={'notation': item['ipa']})
                
                # Clear existing senses just in case
                if w_created or not word_obj.senses.exists():
                    sense = WordSense.objects.create(
                        word=word_obj,
                        part_of_speech=item['pos'],
                        definition=item['definition'],
                        translation=item['translation'],
                        order=1
                    )
                    
                    if item['example']:
                        Example.objects.create(
                            sense=sense,
                            sentence=item['example'],
                            translation=item['example_trans']
                        )
                
                category.words.add(word_obj)
                added_count += 1
                
            self.stdout.write(self.style.SUCCESS(f'Successfully added {added_count} words to {cat_name}'))
