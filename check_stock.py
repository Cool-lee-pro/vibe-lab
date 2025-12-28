import requests
from bs4 import BeautifulSoup
import os

# 환경 변수에서 슬랙 URL 가져오기
SLACK_URL = os.environ.get('SLACK_WEBHOOK_URL')
TARGET_URL = "https://www.ddpdesignstore.org/goods/goods_view.php?goodsNo=1000001412"

def check_stock():
    # 1. 페이지 데이터 가져오기 (봇 차단 방지를 위해 Headers 추가)
    headers = {'User-Agent': 'Mozilla/5.0'}
    response = requests.get(TARGET_URL, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # 2. '해치(+3000)' 옵션의 품절 여부 확인
    # 해당 사이트의 옵션 리스트는 보통 select 태그 내부에 있습니다.
    options = soup.find_all('option')
    
    for opt in options:
        text = opt.get_text()
        if "해치(+3000)" in text:
            if "품절" not in text:
                send_slack(f"✅ [재입고 알림] 해치(+3000) 옵션의 품절이 풀렸습니다!\n바로 확인하세요: {TARGET_URL}")
                return
            else:
                print("아직 품절 상태입니다.")
                return

def send_slack(msg):
    requests.post(SLACK_URL, json={"text": msg})

if __name__ == "__main__":
    check_stock()
