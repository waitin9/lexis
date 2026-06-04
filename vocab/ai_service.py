import os
import json
from google import genai
from pydantic import BaseModel, Field

# 嘗試載入 .env
from dotenv import load_dotenv
load_dotenv()

def get_client():
    # 每次呼叫時重新載入 .env，讓使用者即使忘了重啟也能立刻生效
    load_dotenv(override=True)
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    return genai.Client(api_key=api_key)

def generate_meme_mnemonic(word_text: str, context: str = "") -> str:
    """
    生成靈魂共鳴法/迷因級的記憶鉤子
    """
    client = get_client()
    if not client:
        return "⚠️ 未設定 GEMINI_API_KEY。請在根目錄建立 .env 檔案並設定 GEMINI_API_KEY=你的金鑰"

    prompt = f"""
    請為英文單字 '{word_text}' 創造一個極度有畫面、具備靈魂共鳴或迷因感的「記憶鉤子」。
    
    【重要限制】：這個單字在這裡的具體翻譯與解釋是「{context}」。
    請你務必、絕對要針對「{context}」這個意思來設計記憶情境，絕對不可以寫成其他的常見意思（例如 rate 有評分和速度的意思，請嚴格根據上下文來寫）！
    
    如果這個單字有明確的字根字首，可以簡單拆解（例如 Pro- 向前），但重點要放在「極度生活化的痛點情境」或「幽默感」。
    不要用死板的造句，要像是一個幽默的老師在對學生講話。
    
    請直接回傳記憶鉤子文字，不要包含多餘的開頭問候。
    """
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        return response.text.strip()
    except Exception as e:
        return f"AI 生成失敗：{str(e)}"

class WordDefinition(BaseModel):
    word: str
    ipa_us: str = Field(description="美式音標 IPA，不含斜線")
    part_of_speech: str = Field(description="詞性簡寫，例如 n, v, adj, adv, prep")
    translation: str = Field(description="繁體中文翻譯（簡短直接）")
    definition: str = Field(description="全英文定義")
    example_sentence: str = Field(description="包含該單字的英文例句")
    example_translation: str = Field(description="例句的繁體中文翻譯")

def expand_official_word(word_text: str) -> dict:
    """
    要求 AI 回傳嚴格 JSON 格式的字典資訊。
    回傳字典：
    {
        "word": "...", "ipa_us": "...", "part_of_speech": "...",
        "translation": "...", "definition": "...", 
        "example_sentence": "...", "example_translation": "..."
    }
    """
    client = get_client()
    if not client:
        print("GEMINI_API_KEY not set")
        return None

    prompt = f"請提供單字 '{word_text}' 的標準字典解析（以最常見的詞性與意思為主）。"
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config={
                'response_mime_type': 'application/json',
                'response_schema': WordDefinition,
                'temperature': 0.1,
            },
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"Error fetching from AI: {e}")
        return None
