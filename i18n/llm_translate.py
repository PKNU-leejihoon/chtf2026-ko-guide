#!/usr/bin/env python3
"""기업 소개·주력 제품·키워드·제품명·제품 설명을 Claude(claude CLI, Haiku)로 다시 번역해 i18n/llm_ko.json에 쌓는다.

  python3 -I i18n/llm_translate.py [동시 실행 수=8]

기업 단위로 묶어 보내서 회사 이름·용어가 한 기업 안에서 일관되게 한다. 이미 번역된 문자열은 건너뛰므로
중간에 멈춰도 다시 실행하면 이어서 한다. 빌드(update.py)는 ko.json > llm_ko.json > 기계번역 순으로 쓴다.
"""
import concurrent.futures as cf
import json
import os
import re
import subprocess
import sys
import tempfile
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "i18n", "llm_ko.json")
HAN = re.compile("[一-鿿]")
RULES = """중국 선전 하이테크 박람회(CHTF) 참가 기업 자료를 한국 관람객(공대생·엔지니어)이 읽을 한국어로 옮긴다.
규칙:
- 원문에 충실하게. 정보를 더하거나 빼거나 요약하지 않는다. 숫자·단위·모델명·줄바꿈·목록 기호는 그대로 둔다.
- 한국 엔지니어가 쓰는 자연스러운 문장으로. 직역 투와 과장된 구호는 담백하게 풀어 쓴다.
- 일반 어휘는 한국어. 한국어로 옮기면 뜻이 흐려지는 업계 용어는 업계에서 통용되는 표기를 쓴다(예: 로봇 핸드, 액추에이터, 서보, Embodied AI, BMS, eVTOL, SoC, LiDAR, AGV).
- 고유명사(회사·브랜드·대학·지명)는 공식 영문명을 알면 영문, 모르면 Pinyin으로. 아래 회사 정보의 이름을 그 회사 이름으로 쓴다.
- 한자는 절대 출력하지 않는다. 중국 정책 용어는 뜻을 풀어 쓴다(예: 专精特新 小巨人 → 국가 지정 강소기업 '작은 거인').
- 제품명은 짧은 제품명으로 옮긴다(모델명 유지).
입력은 '### 번호' 줄로 구분된 글들이다. 출력도 같은 번호의 '### 번호' 줄 다음에 번역만 쓴다. 다른 말은 쓰지 않는다."""


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def clean(src, out):
    """괄호 속 한자 병기는 지우고, 그래도 한자가 남거나 길이가 원문과 너무 다르면 버린다."""
    out = re.sub(r"\s*[（(][^()（）]*[一-鿿][^()（）]*[)）]", "", out).strip()
    out = re.sub("[​-‍﻿]", "", out)
    if not out or HAN.search(out):
        return None
    ratio = len(out) / max(1, len(src))
    return out if len(src) < 20 or .6 <= ratio <= 4.5 else None


def ask(ctx, items):
    body = "\n".join(f"### {i + 1}\n{t}" for i, t in enumerate(items))
    prompt = f"{RULES}\n\n회사 정보: {ctx}\n\n번역할 글:\n{body}"
    with tempfile.TemporaryDirectory() as cwd:  # 프로젝트 설정이 끼어들지 않도록 빈 폴더에서 실행
        r = subprocess.run(["claude", "-p", "--model", "haiku", "--output-format", "text"], input=prompt,
                           capture_output=True, text=True, timeout=600, cwd=cwd)
    parts = re.split(r"^###\s*(\d+)\s*$", r.stdout, flags=re.M)
    res = {int(n): t.strip() for n, t in zip(parts[1::2], parts[2::2])}
    if not res:
        raise ValueError(f"응답 형식 오류: {r.stdout[:200]} {r.stderr[:200]}")
    return [res.get(i + 1) for i in range(len(items))]


NAMES = os.path.join(ROOT, "i18n", "llm_names.json")
NAME_RULES = """중국 박람회 참가 기업의 이름을 한국 관람객용 '표시 이름'으로 정한다.
- 공식 영문명이 있으면 그 영문 브랜드를 짧게 쓴다(Co., Ltd., Technology Co. 같은 법인 꼬리와 지역명은 뺀다). 예: Beijing Inspire Technology Co.,Ltd. → Inspire Robots(널리 쓰는 브랜드명을 알면 그것), Shenzhen Hongkai Industrial Technology Co., Ltd. → Hongkai Technology
- 영문명이 없으면 Pinyin 브랜드 + 업종을 영어로. 예: 杭州炬坤机器人有限公司 → Jukun Robotics
- 대학·연구소·정부 기관은 공식 영문명. 예: 浙江大学 → Zhejiang University
- 한자 금지. 한 줄에 하나.
입력은 '### 번호' 줄 다음에 '원문 | 영문명'. 출력은 '### 번호' 줄 다음에 표시 이름만."""


def names(workers):
    ex = load(os.path.join(ROOT, "raw", "exhibitors.json"), [])
    done = load(NAMES, {})
    todo = [r for r in ex if (r.get("companyName") or "").strip() not in done and HAN.search(r.get("companyName") or "")]
    batches = [todo[i:i + 60] for i in range(0, len(todo), 60)]

    def run(batch):
        body = "\n".join(f"### {i + 1}\n{r['companyName'].strip()} | {(r.get('companyNameEn') or '').strip() or '없음'}"
                         for i, r in enumerate(batch))
        with tempfile.TemporaryDirectory() as cwd:
            out = subprocess.run(["claude", "-p", "--model", "haiku", "--output-format", "text"],
                                 input=f"{NAME_RULES}\n\n{body}", capture_output=True, text=True, timeout=600, cwd=cwd).stdout
        parts = re.split(r"^###\s*(\d+)\s*$", out, flags=re.M)
        got = {int(n): t.strip().splitlines()[0].strip() for n, t in zip(parts[1::2], parts[2::2]) if t.strip()}
        return [(r["companyName"].strip(), got.get(i + 1)) for i, r in enumerate(batch)]

    with cf.ThreadPoolExecutor(workers) as pool:
        for res in pool.map(run, batches):
            for cn, name in res:
                if name and not HAN.search(name) and len(name) <= 80:
                    done[cn] = name
    with open(NAMES, "w", encoding="utf-8") as f:
        json.dump(done, f, ensure_ascii=False, indent=0)
    print("이름", len(done), flush=True)


def main():
    if "--names" in sys.argv:
        return names(4)
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    det = load(os.path.join(ROOT, "raw", "details.json"), {})
    prods = load(os.path.join(ROOT, "raw", "prod_by_cat.json"), {})
    ex = {str(r["serveCatalogueId"]): r for r in load(os.path.join(ROOT, "raw", "exhibitors.json"), [])}
    data = {str(x[0]): x for x in load(os.path.join(ROOT, "site", "data.json"), {}).get("x", [])}
    done = load(OUT, {})
    lock = threading.Lock()
    jobs = []
    for cid, d in det.items():
        texts = [d.get("companyProfile"), d.get("typeProduct"), d.get("supplyAndDemand")]
        for p in prods.get(cid, []):
            if isinstance(p, list):
                texts += [p[0], p[5] if len(p) > 5 else ""]
        texts = [t for t in dict.fromkeys(texts) if t and HAN.search(t) and t not in done]
        if texts:
            r = ex.get(cid, {})
            ko = load(NAMES, {}).get((r.get("companyName") or "").strip()) or data.get(cid, [None, ""])[1]
            ctx = f"{ko} / 영문명 {r.get('companyNameEn') or '없음'} / 원문 {r.get('companyName', '')}"
            # 한 요청이 너무 길지 않게 6,000자 단위로 나눈다
            batch, size = [], 0
            for t in texts:
                if batch and size + len(t) > 6000:
                    jobs.append((ctx, batch))
                    batch, size = [], 0
                batch.append(t)
                size += len(t)
            jobs.append((ctx, batch))
    total = len(jobs)
    print("요청", total, "문자열", sum(len(b) for _, b in jobs), flush=True)
    finished = [0]

    def run(job):
        ctx, items = job
        for _ in range(2):
            try:
                res = ask(ctx, items)
                break
            except Exception as e:  # noqa: BLE001
                err = e
        else:
            print("실패", ctx[:40], err, flush=True)
            return
        with lock:
            for s, t in zip(items, res):
                t = clean(s, t) if isinstance(t, str) else None
                if t:
                    done[s] = t
            finished[0] += 1
            if finished[0] % 25 == 0 or finished[0] == total:
                tmp = OUT + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(done, f, ensure_ascii=False, indent=0)
                os.replace(tmp, OUT)
                print("진행", finished[0], "/", total, flush=True)

    with cf.ThreadPoolExecutor(workers) as pool:
        list(pool.map(run, jobs))
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(done, f, ensure_ascii=False, indent=0)
    os.replace(tmp, OUT)
    print("완료", len(done), flush=True)


if __name__ == "__main__":
    main()
