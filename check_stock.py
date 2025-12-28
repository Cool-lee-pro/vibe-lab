import requests
from bs4 import BeautifulSoup
import os

# 환경 변수에서 슬랙 URL 가져오기
SLACK_URL = os.environ.get('SLACK_WEBHOOK_URL')
TARGET_URL = "https://www.ddpdesignstore.org/goods/goods_view.php?goodsNo=1000001412"

def check_stock():
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(TARGET_URL, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 디자인 옵션 select 태그 찾기
        options = soup.find_all('option')
        
        all_options_status = []
        heachi_status_msg = ""
        
        for opt in options:
            text = opt.get_text().strip()
            # 기본 선택 문구 제외
            if "=" in text or not text:
                continue
                
            # 전체 옵션 리스트 빌드 (참고용)
            all_options_status.append(f"• {text}")
            
            # 해치 옵션 특화 로직
            if "해치" in text:
                if "품절" not in text:
                    heachi_status_msg = f"✅ [재입고 완료!] 드디어 해치(+3000) 구매가 가능합니다!"
                else:
                    heachi_status_msg = f"ℹ️ [재고 확인] 해치는 아직 품절 상태입니다."

        # 슬랙 메시지 구성
        status_report = "\n".join(all_options_status)
        final_message = f"{heachi_status_msg}\n\n*현재 옵션 전체 현황:*\n{status_report}\n\n바로가기: {TARGET_URL}"
        
        if all_options_status:
            send_slack(final_message)
        else:
            send_slack("⚠️ 옵션 정보를 읽어오지 못했습니다. 사이트 구조를 확인해주세요.")

    except Exception as e:
        send_slack(f"❌ 에러 발생: {str(e)}")

def send_slack(msg):
    payload = {"text": msg}
    requests.post(SLACK_URL, json=payload)

if __name__ == "__main__":
    check_stock()
