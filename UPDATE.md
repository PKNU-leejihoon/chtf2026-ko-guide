# 고교회 2026 한국어 가이드 갱신 절차

페이지: GitHub Pages (README 참고)
폴더: /Users/ijihun/Downloads/iotx/chtf-guide

## 1. 수집·비교
```
cd /Users/ijihun/Downloads/iotx/chtf-guide && python3 -I update.py
```
마지막 줄 JSON 요약을 본다. `changes`에 바뀐 건수, `pending_translations`에 검수 번역이 없는 문자열 수가 나온다.
변경 내역은 raw/changes.json 마지막 항목에 있다.

## 2. 새 문자열 번역 (pending_translations > 0일 때)
i18n/pending.json의 문자열을 i18n/batches/uNNNN.txt(`번호<TAB>원문`)로 만들고,
같은 번호로 i18n/batches/uNNNN.ko.txt(`번호<TAB>번역`)를 쓴 뒤
`python3 -I merge_ko.py && python3 -I update.py --build`.

번역 규칙:
- 기업명: `브랜드 중국어 발음 + 업종 (지역)` 예) 深圳市工业人快速成型技术有限公司 → 궁예런 쾌속조형기술 (선전).
  법인 접미사(有限公司 등) 생략, 深圳=선전, 广东=광둥, 알려진 브랜드는 통용 이름(화웨이, CATL, DEEP Robotics 등).
  대학·연구소·관공서는 의미 번역(예: 남방과학기술대학).
- 제품명: 자연스러운 한국어, 모델명 유지. 具身智能=체화지능, 灵巧手=로봇 손, 减速器=감속기, 储能=ESS/에너지저장,
  液冷=액체냉각, 算力=연산/컴퓨팅, 无人机=드론, 低空=저고도, 物联网=IoT, 舵机=서보.

## 3. 행사 페이지가 바뀐 경우 (event_added / event_changed)
해당 URL을 읽고, 일정·장소·연사가 바뀌었으면 site/index.html의 `EVENTS` 배열을 고친다.
새 행사가 배울 거리가 있으면 같은 형식으로 추가한다. (이미지로만 된 일정은 이미지를 내려받아 읽는다.)

## 4. 배포
웹사이트는 GitHub Pages로 배포한다. main 브랜치에 push하면 GitHub Actions가 site/를 배포하고,
Actions가 행사 기간에는 20분마다(평소 3시간마다) 1번 단계(수집·비교·기계번역 임시 반영·빌드)를 자동으로 실행해 바뀐 것이 있으면 커밋·배포한다.
2·3번(검수 번역, 행사 내용 수정)은 사람이 하거나 Claude에게 맡긴 뒤 `git pull --rebase && git push`.

## 공식 안내 한글판 (`site/p/`)

- `mirror/extract.py`: 공식 사이트의 올해 페이지와 뉴스·공지 목록(2쪽 이후 포함)을 `mirror/pages.json`으로 모읍니다. 응답이 없던 페이지는 이전 내용을 유지하고, 결과가 이전의 80% 미만이면 중단합니다.
- `mirror/build.py`: `i18n/ko.json`(손번역) → `i18n/mt_cache.json`(임시 기계번역) 순으로 문구를 바꿔 `site/p/`를 만듭니다. 손번역이 필요한 문구는 `mirror/pending.json`에 남습니다.
- 둘 다 GitHub Actions가 행사 기간에는 20분마다(평소 3시간마다) 실행합니다.
- 기업 상세(`raw/details.json`)는 새 기업은 바로, 기존 기업은 오래된 순으로 매번 300곳씩 다시 받습니다. 소개문·제품 설명 같은 긴 글의 기계번역은 `i18n/mt_long.json`에 쌓입니다.

### 이미지 속 글자 (macOS에서만)

OCR에 macOS Vision을 쓰므로 Actions에서는 돌지 않습니다. 새 이미지는 번역 전까지 공식 원본을 그대로 보여 줍니다.

1. 이미지 내려받기·OCR: `mirror/bin/ocr_boxes`(소스 `mirror/ocr_boxes.swift`)로 `mirror/img_work/blocks.json` 생성
2. 번역: `mirror/img_ko.json`에 `원문 블록 → 한국어` 추가 (로고·매체명은 비워 두면 원문 유지)
3. 렌더링: `mirror/.venv/bin/python -I mirror/render_img.py` → `site/img/*.jpg`, `mirror/img_map.json`
4. `python3 -I mirror/build.py --no-mt` 후 커밋
