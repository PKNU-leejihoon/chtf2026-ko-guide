#!/usr/bin/env python3
"""고교회(CHTF) 2026 한국어 가이드 데이터 갱신.

공식 전시기업 시스템과 포럼 페이지를 다시 수집해서 이전 수집본과 비교하고,
site/data.json 을 다시 만든다.

  python3 -I update.py            # 수집 + 비교 + 빌드
  python3 -I update.py --build    # 수집 없이 빌드만 (번역 반영 후)

번역 우선순위: i18n/ko.json (사람/LLM 검수 번역) > i18n/mt_cache.json (기계번역).
ko.json 에 없는 문자열은 기계번역으로 임시 표시하고 i18n/pending.json 에 모아 둔다.
"""
import concurrent.futures as cf
import datetime as dt
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(ROOT, "raw")
I18N = os.path.join(ROOT, "i18n")
SITE = os.path.join(ROOT, "site")
KST = dt.timezone(dt.timedelta(hours=9))

API = "https://c.zhenweiexpo.com/eip-web-business/api/set/"
# 공식 전시기업 사이트(e.chtf.com)의 공개 프런트엔드가 쓰는 값과 같다.
API_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Origin": "https://e.chtf.com",
    "Referer": "https://e.chtf.com/",
    "pid": "1150",
    "siteToken": "5fcde12cdf513bda1db985eb9cf12603",
}
PROJECT = "1150"
EVENT_INDEX = "https://www.chtf.com/luntanjihuodong/gaoxinluntan"
CJK = re.compile("[一-鿿]")
NAV_API = "https://s.whte.cn/Cs/"
NAV_PROJECT = 12  # 공식 부스 내비게이션의 2026년 프로젝트 (https://s.whte.cn/zwzl/chtf/?id=12)
SHOW_PAGES = {
    "guozhizhognqi": "国之重器、科技巨头产业链", "guojichengguo": "国际科技成果、省市科技成果",
    "keyanyuan": "科研院所高校、产教融合、全国重点实验室及生物技术", "shenzhenkejichengguo": "粤科技",
    "rengongzhineng": "人工智能产业链", "jiqirenchanye": "机器人产业链", "bandaoti": "半导体与集成电路产业",
    "zhinengzhizao": "AI 算力产业与数据中心", "dianzixiaofei": "消费电子", "dikongjingji": "低空经济与通用航空",
    "syht": "亚洲航天展", "kuajingdianshang": "亚洲氢能产业展", "shengwujishu": "生物技术与化学工程",
    "gaoduanyiliao": "高端医疗器械", "chunengdianchi": "储能及电池工业",
    "guangchuchongdianzhuang": "亚洲光储充及充电桩产业", "shuzinengyuan": "智慧电力与数字能源",
    "shuiwuyuhuanjing": "水务与环境、C³未来建筑大会", "shizhenggongcheng": "市政工程", "guidao": "轨道交通",
    "zhihuigangkou": "智慧港口", "yazhouxincailiaochanyezhan": "亚洲新材料产业展", "alsh": "亚洲生命科学与健康产业展",
}


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save(path, obj, compact=False):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        if compact:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def post_form(endpoint, fields, tries=4):
    boundary = "----chtf" + hashlib.md5(str(time.time()).encode()).hexdigest()
    body = b""
    for k, v in fields.items():
        body += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    body += f"--{boundary}--\r\n".encode()
    headers = dict(API_HEADERS, **{"Content-Type": f"multipart/form-data; boundary={boundary}"})
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(API + endpoint, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=90) as r:
                d = json.loads(r.read().decode("utf-8"))
            if d.get("state") != 1:
                raise RuntimeError(d.get("msg"))
            return d
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 + i * 2)
    raise RuntimeError(f"{endpoint} 실패: {last}")


def get_text(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=45) as r:
                return r.read().decode("utf-8", "ignore")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2)
    raise RuntimeError(f"{url} 실패: {last}")


# ---------------------------------------------------------------- 수집
def fetch_exhibitors():
    rows, page = [], 1
    while True:
        d = post_form("serveCatalogue/selectByTypeFocusCata", {"projectId": PROJECT, "page": page, "rows": 100})
        chunk = d.get("rows") or []
        rows += chunk
        if len(chunk) < 100:
            break
        page += 1
    uniq = {r["serveCatalogueId"]: r for r in rows}
    return list(uniq.values())


def fetch_products(cid):
    d = post_form("serveProduct/getByServeCatalogueId", {"serveCatalogueId": cid, "page": 1, "rows": 20})
    return [(r.get("productName") or "").strip() for r in (d.get("rows") or []) if (r.get("productName") or "").strip()]


def page_main_text(raw):
    t = re.sub(r"<!--.*?-->|<script.*?</script>|<style.*?</style>", "", raw, flags=re.S)
    t = re.sub(r"<img[^>]*src=\"([^\"]+)\"[^>]*>", r" [IMG \1] ", t)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    t = re.sub(r"\s+", " ", t)
    i = t.rfind("首页 >")
    j = t.find("参观预登记", i)
    return t[i:j] if i >= 0 else t


def fetch_events():
    raw = get_text(EVENT_INDEX)
    found = {}
    # 상단 메뉴에는 지난해 제목이 남아 있어서, 뒤쪽(사이드바) 제목이 앞의 것을 덮어쓰게 한다
    for href, title in re.findall(r'<a[^>]+href="(/?luntanjihuodong/[^"#]+)"[^>]*>\s*([^<]{2,80}?)\s*</a>', raw):
        url = "https://www.chtf.com/" + href.lstrip("/").rstrip("/")
        found[url] = title.strip()
    items = [{"url": u, "title": t} for u, t in found.items() if not u.endswith("zhutiluxian")]
    # 전문전 페이지. 대부분 포스터 이미지라서 이미지 주소까지 비교 대상에 들어간다
    items += [{"url": f"https://www.chtf.com/zhanlanyuzhanshi/{k}", "title": v, "kind": "show"} for k, v in SHOW_PAGES.items()]
    for it in items:
        try:
            body = page_main_text(get_text(it["url"]))
            it["hash"] = hashlib.sha1(body.encode()).hexdigest()[:12]
            it["len"] = len(body)
        except Exception as e:  # noqa: BLE001
            it["hash"], it["err"] = None, str(e)
    return items


def nav_get(path):
    req = urllib.request.Request(NAV_API + path, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_nav():
    """공식 부스 내비게이션에 입력된 부스. 주최 측이 전시 직전까지 채워 넣는 데이터다."""
    halls = []
    for a in nav_get(f"plan/listAreaByProjectId?projectId={NAV_PROJECT}") or []:
        rows = nav_get(f"plan/pagePlan?areaId={a['id']}").get("data") or []
        named = [{"booth": (x.get("planBooth") or "").strip(), "name": (x.get("planName") or x.get("jcName") or "").strip(),
                  "cid": str(x.get("catalogueId") or "")} for x in rows if x.get("planName") or x.get("jcName")]
        halls.append({"id": a["id"], "name": a.get("areaName") or "", "total": len(rows), "named": named})
    return halls


# ---------------------------------------------------------------- 번역
def mt_translate(strings, cache):
    todo = [s for s in dict.fromkeys(strings) if s and s not in cache]

    def call(lines):
        q = "\n".join(lines)
        url = "https://translate.googleapis.com/translate_a/single?" + urllib.parse.urlencode(
            {"client": "gtx", "sl": "zh-CN", "tl": "ko", "dt": "t", "q": q})
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        d = json.load(urllib.request.urlopen(req, timeout=30))
        return "".join(seg[0] for seg in d[0] if seg[0]).split("\n")

    for i in range(0, len(todo), 40):
        chunk = [s.replace("\n", " ") for s in todo[i:i + 40]]
        try:
            res = call(chunk)
            if len(res) != len(chunk):
                raise ValueError("줄 수 불일치")
            for s, r in zip(todo[i:i + 40], res):
                cache[s] = r.strip()
        except Exception:  # noqa: BLE001
            for s in todo[i:i + 40]:
                try:
                    cache[s] = call([s.replace("\n", " ")])[0].strip()
                except Exception:  # noqa: BLE001
                    pass
        time.sleep(0.3)
    return cache


# ---------------------------------------------------------------- 빌드
CATMAP = {
    "人工智能与机器人": "AI·로봇", "智能制造与自动化": "스마트 제조·자동화", "新材料": "신소재",
    "新型电力、储能、充电": "전력·에너지저장·충전", "低空经济与商业航天": "저고도 경제·상업 우주",
    "消费电子": "소비자 전자", "AI 算力产业与数据中心": "AI 컴퓨팅·데이터센터", "半导体与集成电路": "반도체·IC",
    "医药/生物技术与实验室": "의약·바이오·실험실", "科研院所高校": "연구기관·대학", "新质生产力": "신질 생산력",
    "数字产业": "디지털 산업", "深圳科技成果、未来前沿科技": "선전 기술성과·미래기술",
    "节能环保和绿色低碳": "에너지절약·환경·저탄소", "国之重器科技巨头产业链": "국가 핵심장비·테크 대기업",
    "国际科技与省市科技": "국제·지역 기술성과", "清洁能源、氢能产业": "청정에너지·수소", "水务与环境": "수처리·환경",
    "交通运输与物流科技创新": "교통·물류 기술", "智慧农业与数字乡村": "스마트 농업", "金融服务": "금융 서비스",
    "未来建筑、智能建造": "미래 건축·스마트 건설", "跨境电商": "크로스보더 이커머스", "港口物流交通": "항만·물류·교통",
}


def halls_of(booth):
    out = []
    for part in re.split(r"[,，、/]", booth or ""):
        m = re.match(r"\s*(\d{1,2})(?=\D|$)", part.strip())
        if m and 1 <= int(m.group(1)) <= 20 and int(m.group(1)) not in out:
            out.append(int(m.group(1)))
    return out


def is_korean(r):
    a = (r.get("companyAddressEn") or "") + " " + (r.get("companyAddress") or "")
    b = (r.get("boothNum") or "")
    return ("Korea" in a or "韩国" in a or "首尔" in a or "Siheung" in a
            or b.startswith("14-C301") or b.startswith("10-D6"))


def clean_booth(b):
    return (b or "").strip().rstrip(".").replace("—", "-")


def build(now_iso):
    ex = load(os.path.join(RAW, "exhibitors.json"), [])
    prods = load(os.path.join(RAW, "prod_by_cat.json"), {})
    ko = load(os.path.join(I18N, "ko.json"), {})
    mt = load(os.path.join(I18N, "mt_cache.json"), {})
    changes = load(os.path.join(RAW, "changes.json"), [])
    events_state = load(os.path.join(RAW, "events.json"), {"items": []})

    nav = load(os.path.join(RAW, "nav.json"), [])
    nav_booth = {n["cid"]: n["booth"] for h in nav for n in h.get("named", []) if n.get("cid") and n.get("booth")}

    def tr(s):
        if not s or not CJK.search(s):
            return s
        return ko.get(s) or mt.get(s) or s

    cats, cidx = [], {}

    def cat(n):
        k = CATMAP.get(n.strip(), n.strip())
        if k not in cidx:
            cidx[k] = len(cats)
            cats.append(k)
        return cidx[k]

    X, hall_count, hall_cats, cat_count, kr_halls, nohall = [], {}, {}, {}, set(), 0
    pending = set()
    for r in ex:
        cn = (r.get("companyName") or "").strip()
        en = (r.get("companyNameEn") or "").strip()
        kr = is_korean(r)
        if kr:
            name = ko.get(cn) or (cn if re.search("[가-힣]", cn) else en or cn)
        else:
            name = tr(cn)
            if CJK.search(cn) and cn not in ko:
                pending.add(cn)
        booth = clean_booth(r.get("boothNum")) or nav_booth.get(str(r["serveCatalogueId"]), "")
        hs = halls_of(booth)
        cs = [cat(t["tradeName"]) for t in (r.get("tradeClassList") or [])]
        plist = []
        for p in prods.get(str(r["serveCatalogueId"]), []):
            plist.append([tr(p), p])
            if CJK.search(p) and p not in ko:
                pending.add(p)
        X.append([r["serveCatalogueId"], name, en, cn, booth, hs, cs, 1 if kr else 0, plist, r.get("readNum") or 0])
        if hs:
            for h in hs:
                hall_count[h] = hall_count.get(h, 0) + 1
                hc = hall_cats.setdefault(h, {})
                for c in cs:
                    hc[c] = hc.get(c, 0) + 1
                if kr:
                    kr_halls.add(h)
        else:
            nohall += 1
        for c in cs:
            cat_count[c] = cat_count.get(c, 0) + 1

    # 최근 변경(최근 5회 수집분)을 표시용으로 정리
    names = {x[0]: x for x in X}
    recent = []
    for ch in changes[-5:][::-1]:
        items = []
        for it in ch.get("items", []):
            x = names.get(it.get("id"))
            it = dict(it)
            if x:
                it["name"] = x[1]
                it["booth"] = x[4]
            if it.get("title_cn"):
                it["title"] = tr(it["title_cn"])
            items.append(it)
        recent.append({"at": ch["at"], "items": items[:60], "more": max(0, len(items) - 60)})

    out = {
        "updatedAt": now_iso,
        "checkedAt": load(os.path.join(RAW, "meta.json"), {}).get("checkedAt", now_iso),
        "cats": cats,
        "catCount": [cat_count.get(i, 0) for i in range(len(cats))],
        "hallCount": {str(k): v for k, v in sorted(hall_count.items())},
        "hallCats": {str(h): {str(c): n for c, n in v.items()} for h, v in hall_cats.items()},
        "krHalls": sorted(kr_halls),
        "noHall": nohall,
        "recent": recent,
        "eventPages": [{"url": e["url"], "title": e["title"], "ko": tr(e["title"]), "kind": e.get("kind", "event")} for e in events_state.get("items", [])],
        "nav": {"url": f"https://s.whte.cn/zwzl/chtf/?id={NAV_PROJECT}",
                "halls": [{"name": h["name"], "total": h["total"], "named": len(h["named"])} for h in nav]},
        "x": X,
    }
    save(os.path.join(SITE, "data.json"), out, compact=True)
    save(os.path.join(I18N, "pending.json"), sorted(pending))
    return len(X), len(pending)


def collect():
    now = dt.datetime.now(KST).isoformat(timespec="minutes")
    old = {r["serveCatalogueId"]: r for r in load(os.path.join(RAW, "exhibitors.json"), [])}
    prods = load(os.path.join(RAW, "prod_by_cat.json"), {})
    new_rows = fetch_exhibitors()
    if len(new_rows) < 0.8 * max(1, len(old)):
        raise SystemExit(f"수집 결과가 비정상적으로 적어서 중단: {len(new_rows)}곳 (이전 {len(old)}곳)")
    new = {r["serveCatalogueId"]: r for r in new_rows}
    items = []
    for cid, r in new.items():
        o = old.get(cid)
        if not o:
            items.append({"type": "added", "id": cid})
        elif clean_booth(o.get("boothNum")) != clean_booth(r.get("boothNum")):
            items.append({"type": "booth", "id": cid, "from": clean_booth(o.get("boothNum")), "to": clean_booth(r.get("boothNum"))})
    for cid, o in old.items():
        if cid not in new:
            items.append({"type": "removed", "id": cid, "name_cn": o.get("companyName"), "booth": clean_booth(o.get("boothNum"))})

    # 제품: 새 기업이거나 제품 수가 바뀐 기업만 다시 받는다
    refetch = [cid for cid, r in new.items()
               if str(cid) not in prods or (old.get(cid) or {}).get("productCount") != r.get("productCount")]
    with cf.ThreadPoolExecutor(8) as pool:
        for cid, res in zip(refetch, pool.map(lambda c: _safe(fetch_products, c), refetch)):
            if res is not None:
                if str(cid) in prods and prods[str(cid)] != res and old.get(cid):
                    items.append({"type": "products", "id": cid})
                prods[str(cid)] = res

    # 행사 페이지
    ev_old = {e["url"]: e for e in load(os.path.join(RAW, "events.json"), {"items": []}).get("items", [])}
    try:
        ev_new = fetch_events()
    except Exception as e:  # noqa: BLE001
        print("행사 목록 수집 실패:", e, file=sys.stderr)
        ev_new = list(ev_old.values())
    for e in ev_new:
        o = ev_old.get(e["url"])
        if ev_old and not o:
            items.append({"type": "event_added", "url": e["url"], "title_cn": e["title"]})
        elif o and e.get("hash") and o.get("hash") and o["hash"] != e["hash"]:
            items.append({"type": "event_changed", "url": e["url"], "title_cn": e["title"]})

    nav_old = {h["id"]: h for h in load(os.path.join(RAW, "nav.json"), [])}
    try:
        nav_new = fetch_nav()
        for h in nav_new:
            before = len((nav_old.get(h["id"]) or {}).get("named", []))
            if len(h["named"]) > before:
                items.append({"type": "nav", "hall": h["name"], "from": before, "to": len(h["named"])})
        save(os.path.join(RAW, "nav.json"), nav_new)
    except Exception as e:  # noqa: BLE001
        print("부스 내비게이션 수집 실패:", e, file=sys.stderr)

    save(os.path.join(RAW, "exhibitors.json"), list(new.values()))
    save(os.path.join(RAW, "prod_by_cat.json"), prods)
    save(os.path.join(RAW, "events.json"), {"at": now, "items": ev_new})
    save(os.path.join(RAW, "meta.json"), {"checkedAt": now})
    if items:
        changes = load(os.path.join(RAW, "changes.json"), [])
        changes.append({"at": now, "items": items})
        save(os.path.join(RAW, "changes.json"), changes[-30:])

    # 새 문자열은 기계번역으로 먼저 채운다 (검수 번역은 i18n/ko.json)
    ko = load(os.path.join(I18N, "ko.json"), {})
    mt = load(os.path.join(I18N, "mt_cache.json"), {})
    strings = [r.get("companyName", "").strip() for r in new.values()]
    strings += [p for v in prods.values() for p in v] + [e["title"] for e in ev_new]
    need = [s for s in strings if s and CJK.search(s) and s not in ko and s not in mt]
    if need:
        save(os.path.join(I18N, "mt_cache.json"), mt_translate(need, mt))
    return now, items


def _safe(fn, *a):
    try:
        return fn(*a)
    except Exception as e:  # noqa: BLE001
        print("실패:", a, e, file=sys.stderr)
        return None


def main():
    os.makedirs(RAW, exist_ok=True)
    os.makedirs(SITE, exist_ok=True)
    if "--baseline" in sys.argv:  # 감시 대상을 늘릴 때 '새 항목' 알림 없이 기준선만 저장
        now = dt.datetime.now(KST).isoformat(timespec="minutes")
        save(os.path.join(RAW, "events.json"), {"at": now, "items": fetch_events()})
        save(os.path.join(RAW, "nav.json"), fetch_nav())
        items = []
    elif "--build" in sys.argv:
        now = load(os.path.join(RAW, "meta.json"), {}).get("checkedAt") or dt.datetime.now(KST).isoformat(timespec="minutes")
        items = []
    else:
        now, items = collect()
    n, pend = build(now)
    summary = {
        "at": now, "exhibitors": n, "pending_translations": pend,
        "changes": {t: sum(1 for i in items if i["type"] == t) for t in sorted({i["type"] for i in items})},
    }
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
