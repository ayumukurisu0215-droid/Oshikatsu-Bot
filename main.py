import os
import requests
import json
from bs4 import BeautifulSoup
import google.generativeai as genai
from supabase import create_client, Client
from linebot import LineBotApi
from linebot.models import TextSendMessage

# --- 設定 (環境変数から読み込む) ---
TARGET_URL = os.environ["TARGET_URL"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
LINE_CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
LINE_USER_ID = os.environ["LINE_USER_ID"]

# --- 1. スクレイピング部 ---
def fetch_text_from_url(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")
        # 余計なタグを消す
        for tag in soup(["script", "style"]):
            tag.decompose()
        # テキストだけ取得して先頭3000文字を返す
        return soup.get_text(separator="\n", strip=True)[:3000]
    except Exception as e:
        print(f"Error fetching URL: {e}")
        return None

# --- 2. AI解析部 ---
def analyze_with_gemini(text):
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("models/gemini-2.5-flash")
    
    prompt = f"""
    以下のWebサイトのテキストから、「グッズ発売」や「チケット申込」に関する情報を抽出してください。
    過去の日付のものは無視して、未来のイベントだけを抽出してください。
    
    出力は以下のJSON形式のみで返してください（Markdown記法は不要）:
    [
        {{"event_name": "イベント名やグッズ名", "date": "日付(YYYY-MM-DD)", "details": "詳細一言"}}
    ]
    
    もし新しい情報がなければ空のリスト [] を返してください。
    
    テキスト:
    {text}
    """
    
    response = model.generate_content(prompt)
    try:
        # JSON部分だけを取り出すクリーニング処理
        cleaned_text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(cleaned_text)
    except:
        return []

# --- 3. データベース & LINE通知部 ---
def main():
    print("処理開始...")
    
    # DB接続
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    # LINE接続
    line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)

    # テキスト取得
    text = fetch_text_from_url(TARGET_URL)
    if not text:
        return

    # AI解析
    events = analyze_with_gemini(text)
    
    for event in events:
        event_name = event["event_name"]
        date = event["date"]
        
        # --- 重複チェック (記憶部) ---
        # DBから同じイベント名があるか検索
        response = supabase.table("notifications").select("*").eq("event_name", event_name).execute()
        
        if len(response.data) > 0:
            print(f"スキップ: {event_name} は通知済みです。")
            continue
        
        # --- LINE通知 ---
        message = f"📢 推し活速報！\n\n【{event_name}】\n📅 日付: {date}\n🔗 {TARGET_URL}"
        line_bot_api.push_message(LINE_USER_ID, TextSendMessage(text=message))
        print(f"通知送信: {event_name}")
        
        # --- DBに記録 ---
        supabase.table("notifications").insert({"event_name": event_name}).execute()

if __name__ == "__main__":
    main()
