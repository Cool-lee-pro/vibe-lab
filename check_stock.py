import requests
from bs4 import BeautifulSoup
import os
import re

# 환경 변수에서 슬랙 URL 가져오기
SLACK_URL = os.environ.get('SLACK_WEBHOOK_URL')
TARGET_URL = "https://www.ddpdesignstore.org/goods/goods_view.php?goodsNo=1000001412"

def check_stock():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    try:
        response = requests.get(TARGET_URL, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 1. 디자인 옵션 박스만 타겟팅 (item_add_option_box 내부의 select 찾기)
        option_box = soup.find('div', class_='item_add_option_box')
        if not option_box:
            send_slack("⚠️ 디자인 옵션 박스를 찾을 수 없습니다. 사이트 구조를 확인해주세요.")
            return

        options = option_box.find_all('option')
        
        all_options_status = []
        heachi_status_msg = ""
        
        for opt in options:
            # 텍스트 추출 및 여러 줄 공백/줄바꿈 하나로 합치기
            text = " ".join(opt.get_text().split())
            
            # 기본 선택 문구("= 옵션 : 가격 =") 제외
            if "=" in text or not text:
                continue
                
            # 전체 옵션 리스트 빌드 (불필요한 공백 제거 처리)
            all_options_status.append(f"• {text}")
            
            # 해치 옵션 판별
            if "해치" in text:
                if "품절" not in text:
                    heachi_status_msg = "✅ [재입고 완료!] 드디어 해치(+3000) 구매가 가능합니다!"
                else:
                    heachi_status_msg = "ℹ️ [재고 확인] 해치는 아직 품절 상태입니다."

        # 2. 메시지 구성
        status_report = "\n".join(all_options_status)
        final_message = f"{heachi_status_msg}\n\n*현재 옵션 전체 현황:*\n{status_report}\n\n바로가기: {TARGET_URL}"
        
        if all_options_status:
            send_slack(final_message)
        else:
            send_slack("⚠️ 옵션 리스트를 불러오지 못했습니다.")

    except Exception as e:
        send_slack(f"❌ 에러 발생: {str(e)}")

def send_slack(msg):
    payload = {"text": msg}
    requests.post(SLACK_URL, json=payload)

if __name__ == "__main__":
    check_stock()
