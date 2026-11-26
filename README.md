# 고교회 2026 관람 노트

제28회 중국 국제 하이테크 성과 교역회(CHTF, 2026.11.26–28, 선전 국제회의전시센터)를 위한 **비공식** 한국어 가이드입니다.
공식 사이트(www.chtf.com)와 공식 전시기업 시스템(e.chtf.com)에 공개된 정보를 정리·번역했습니다.

- `site/` 배포되는 정적 페이지. `data.json`은 기업·부스 데이터, `products.json`은 제품 검색을 열 때 읽는 공식 제품 식별자·사진·모델 데이터입니다.
- `update.py` 공식 데이터 수집·비교·빌드. GitHub Actions가 3시간마다 실행하고 바뀐 것이 있으면 커밋·배포합니다.
- 감시 대상: 공식 전시기업 시스템, 포럼·전문전 페이지 43개, 공식 부스 내비게이션
- `i18n/ko.json` 검수 번역 사전. 여기에 없는 새 문자열은 기계번역(`i18n/mt_cache.json`)으로 임시 표시되고 `i18n/pending.json`에 모입니다.
- `merge_ko.py`, `UPDATE.md` 새 문자열 번역 반영 절차

로컬 실행:
```
python3 -I update.py          # 수집 + 빌드
python3 -I update.py --build  # 빌드만
cd site && python3 -m http.server
```
