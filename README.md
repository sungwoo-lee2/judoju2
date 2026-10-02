# Leader Finder v18 · KRX + NAVER 시장탐색

## 배포
압축 해제 후 기존 GitHub 파일 교체 → Commit → Render Deploy latest commit.
Build: pip install -r requirements.txt
Start: uvicorn app:app --host 0.0.0.0 --port $PORT
기존 KRX_API_KEY 유지. 추가로 Render Environment에 NAVER_CLIENT_ID, NAVER_CLIENT_SECRET을 입력하세요. API HUB 인증 정보의 Client ID/Client Secret입니다. 클라우드 계정 Access Key가 아닙니다. 값은 GitHub나 화면 코드에 넣지 않습니다.

## 첫 페이지
뉴스·관심도 탭이 첫 화면입니다. 설정 완료 시 국내 증시 기사를 자동 검색합니다. 종목/주제 검색, 섹터 바로검색, KRX TOP20별 관련 기사, 수주·실적·투자·리스크 단어 분류, 모임 기사 저장/취소, 저장함과 발표용 목록 복사를 지원합니다.
주도주 관련 기사는 검색 결과로서 관련성을 사람이 원문으로 확인해야 합니다. 분류는 단순 단어 일치이며 호재/악재 또는 추천 판단이 아닙니다. 발행일은 API가 제공한 기사 제공시간입니다. 출처는 원문 도메인입니다. 같은 원문 URL을 중복 제거합니다. 저장함은 해당 브라우저 localStorage에 저장되며 다른 회원/브라우저와 공유되지 않습니다.

관심도: 종목 최대5개를 한 요청에서 최근30일 비교, 날짜별 그래프/수치 표시. 실제 검색 횟수가 아닌 상대값이며 요청이 다른 그래프 간 직접 비교하지 않습니다. TOP5 종목 자동 입력 버튼 제공.
네이버 시장탐색은 KRX 후보점수 70%와 네이버 최신 기사량 30%를 결합한 규칙 기반 신호입니다. 생성형 AI나 OpenAI API를 사용하지 않습니다. 기사 제목은 모멘텀 참고자료이며 투자 추천이나 호재·악재 판정이 아닙니다. 네이버 한도와 과금은 API HUB 계정 정책을 적용하고, 10분 서버 메모리 캐시로 반복 조회를 줄입니다.

API HUB 공식 문서:
https://api.ncloud-docs.com/docs/naver-api-hub-search-news
https://api.ncloud-docs.com/docs/en/naver-api-hub-search-trend
뉴스: GET https://naverapihub.apigw.ntruss.com/search/v1/news
트렌드: POST https://naverapihub.apigw.ntruss.com/search-trend/v1/search
인증: X-NCP-APIGW-API-KEY-ID / X-NCP-APIGW-API-KEY

검증: python -m unittest test_krx_api test_history test_naver (14건). 첫 화면 템플릿 렌더, 네이버 시장탐색 API 모의 응답 통합 검사, JS 문법 검사 완료. 실제 키 호출/Render 배포는 미검증.

# Leader Finder v14 KRX 과거 데이터

기존 파일을 교체하고 Commit 후 Render Deploy latest commit. Build/Start와 KRX_API_KEY는 기존대로 유지합니다.

화면의 과거 데이터 수집에서 시작·종료일 지정 후 불러오기. 기본 최근 60일, 2010-01-04부터 어제까지 지원. 코스피·코스닥 각 날짜의 전체 종목 저장. 최근 날짜부터 진행하며 중단 후 동일 기간 재요청 시 저장된 날짜를 재사용합니다. 오류와 진행률은 화면에 표시. 완료 후 후보 스냅샷 재계산. CSV 다운로드 지원. 긴 기간은 API 호출 제한·속도에 따라 시간이 오래 걸릴 수 있으며 오류 시 재요청하세요.

10·20일선은 원종가 평균. 거래대금 배수는 당일 / 직전 20거래일 평균. 20일선 상승은 직전 20일선 비교. 부족한 자료는 빈 값 유지. 52주 고점은 250개 시장일 자료가 있을 때 고가 최댓값으로 계산. 기업행사 미조정 원종가이므로 수정주가 차트와 다를 수 있습니다. 외국인/기관 수급은 제공되지 않습니다.

저장: 기본 data/krx_history.sqlite3. Render 무료 서비스에서는 재배포/재시작으로 로컬 데이터가 소실될 수 있습니다. 장기 보관 시 영구 디스크를 연결하고 KRX_HISTORY_DB=/var/data/krx_history.sqlite3 지정. CSV 백업도 가능합니다. SQLite 작업은 단일 uvicorn 프로세스 기준. 서버 종료 시 작업 중단되지만 저장된 날짜는 보존되며 재요청으로 이어갑니다. 기존 Supabase 설정은 이 SQLite 파일을 보존하지 않습니다.

검증: python -m unittest test_krx_api test_history. 테스트는 모의 응답으로 인증헤더·실패처리·날짜검증·캐시·이동평균·거래대금 배수 검증. 실제 인증 호출·Render 배포는 별도 확인 필요.


## v18 자동 과거 데이터 수집
서버 실행 시 최근 400일의 KOSPI·KOSDAQ 자료를 백그라운드에서 수집합니다. 휴장일을 감안해 52주 고점 계산에 필요한 약 250거래일을 확보하는 범위입니다.
기존 저장 날짜는 재사용하고 매시간 다시 확인하여 빠진 날짜·지연 공시를 조회합니다.
수집 후 스캔과 이동평균을 갱신합니다. 기본 활성화이며 AUTO_HISTORY=0으로 끌 수 있습니다.
KRX_API_KEY가 필요합니다. API 실패는 화면 진행 상태에 표시하고 다음 주기에 재시도합니다.
무료 서버가 정지된 동안은 실행하지 않으며 재시작하면 다시 수집합니다.
로컬 DB는 재배포 시 사라질 수 있습니다. 자동 수집이 영구 저장을 제공하는 것은 아닙니다.
기존 KRX_HISTORY_DB에 영구 디스크 경로를 지정하면 저장분을 재사용할 수 있습니다.
