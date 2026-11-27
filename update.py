#!/usr/bin/env python3
"""고교회(CHTF) 2026 한국어 가이드 데이터 갱신.

공식 전시기업 시스템과 포럼 페이지를 다시 수집해서 이전 수집본과 비교하고,
site/data.json 을 다시 만든다.

  python3 -I update.py            # 수집 + 비교 + 빌드
  python3 -I update.py --build    # 수집 없이 빌드만 (번역 반영 후)

번역 우선순위: i18n/ko.json (사람/LLM 검수 번역) > i18n/llm_ko.json (i18n/llm_translate.py, Claude) > i18n/mt_cache.json·mt_long.json (기계번역).
ko.json 에 없는 문자열은 기계번역으로 임시 표시하고 i18n/pending.json 에 모아 둔다.
"""
import concurrent.futures as cf
import datetime as dt
import hashlib
import html
import json
import math
import os
import re
import sys
import time
from collections import Counter
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
NAV_API = "https://dh.whte.cn/"
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


def clean_text(t):
    t = html.unescape(re.sub(r"<br\s*/?>|</p>", "\n", t or "", flags=re.I))
    t = re.sub(r"<[^>]+>", "", t).replace("\r", "")
    return re.sub(r"\n{3,}", "\n\n", "\n".join(line.strip() for line in t.split("\n"))).strip()


DETAIL_KEYS = ("companyProfile", "companyProfileEn", "typeProduct", "site", "tel", "email",
               "companyAddress", "companyAddressEn", "supplyAndDemand", "pic", "logo")


def fetch_detail(cid):
    """기업 상세(소개·주력 제품·연락처). 담당자 이름·휴대폰은 개인정보라 받지 않는다."""
    d = post_form("serveCatalogue/getMoreByIdFocusCata", {"serveCatalogueId": cid}).get("data") or {}
    return {k: clean_text(d.get(k)) if isinstance(d.get(k), str) else "" for k in DETAIL_KEYS}


def fetch_products(cid):
    rows, page = [], 1
    while True:
        data = post_form("serveProduct/getByServeCatalogueId", {"serveCatalogueId": cid, "page": page, "rows": 100})
        chunk = data.get("rows") or []
        rows.extend(chunk)
        if len(rows) >= int(data["total"]) or not chunk:
            break
        page += 1
    if len(rows) != int(data["total"]) or len({r["serveProductId"] for r in rows}) != len(rows):
        raise ValueError("공식 제품 목록이 일부만 반환됨")
    products = []
    for r in rows:
        name = (r.get("productName") or r.get("productNameEn") or "").strip()
        if not name:
            continue
        pic = (r.get("pic") or "").split(",", 1)[0].strip()
        spec = (r.get("productSpec") or "").strip()
        pics = [u.strip() for u in (r.get("pic") or "").split(",") if u.strip().startswith("https://")]
        products.append([name, r["serveProductId"], (r.get("productNameEn") or "").strip(),
                         pic if pic.startswith("https://") else "", spec if len(spec) <= 100 and "<" not in spec else "",
                         clean_text(r.get("productData")), pics[:8]])
    return products


def product_name(row):
    return row if isinstance(row, str) else row[0]


def refresh_products(new, prods):
    refetch = [
        cid for cid, r in new.items()
        if str(cid) not in prods or len(prods[str(cid)]) != (r.get("productCount") or 0)
        or any(isinstance(p, str) or len(p) < 7 for p in prods[str(cid)])
    ]
    with cf.ThreadPoolExecutor(8) as pool:
        for cid, res in zip(refetch, pool.map(lambda c: _safe(fetch_products, c), refetch)):
            if res is not None:
                before = prods.get(str(cid), [])
                prods[str(cid)] = res
                if [product_name(p) for p in before] != [product_name(p) for p in res]:
                    yield cid


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


def nav_hall(name):
    match = re.fullmatch(r"(\d+)号展?馆", name)
    return int(match.group(1)) if match else None


def nav_code(code, hall):
    code = code.strip().upper()
    if hall and re.fullmatch(r"[A-Z]+\d+(?:-[A-Z0-9]+)*", code):
        return f"{hall}-{code}"
    if hall and re.match(fr"^{hall}[A-Z]", code):
        return f"{hall}-{code[len(str(hall)):]}"
    return code


def fetch_nav():
    """공식 부스 내비게이션에 입력된 부스. 주최 측이 전시 직전까지 채워 넣는 데이터다."""
    halls = []
    for a in nav_get(f"plan/listAreaByProjectId?projectId={NAV_PROJECT}") or []:
        rows = nav_get(f"plan/pagePlan?areaId={a['id']}").get("data") or []
        hall = nav_hall(a.get("areaName") or "")
        codes = Counter(nav_code(x.get("planBooth") or "", hall) for x in rows)
        named = []
        booths = [[x["id"], x["leftX"], x["topY"], x["width"], x["height"], (x.get("planBooth") or "").strip(),
                   str(x.get("catalogueId") or ""), (x.get("planName") or x.get("jcName") or "").strip()]
                  for x in rows if all(isinstance(x.get(k), int) for k in ("leftX", "topY", "width", "height"))]
        for x in rows:
            name = (x.get("planName") or x.get("jcName") or "").strip()
            if not name:
                continue
            code = (x.get("planBooth") or "").strip()
            named.append({"booth": code, "name": name, "cid": str(x.get("catalogueId") or ""),
                          "id": x["id"] if code and codes[nav_code(code, hall)] == 1 else None})
        halls.append({"id": a["id"], "name": a.get("areaName") or "", "total": len(rows), "named": named, "booths": booths,
                      "checkedAt": dt.datetime.now(KST).isoformat(timespec="minutes")})
    return halls


# 공식 홀 도면(imgDt)에서 홀 외곽선의 픽셀 범위. 도면 이미지가 바뀌면 다시 잰다.
# shortcut: 11/27 도면 기준으로 한 번 측정한 값, 주최 측이 도면을 교체하면 재측정 필요
HALL_RECT = {5: [112, 176, 1587, 2877], 6: [369, 211, 1409, 2227], 7: [112, 197, 1587, 2898],
             8: [405, 246, 1505, 2103], 9: [275, 189, 1345, 2265], 10: [378, 148, 1448, 2225],
             11: [112, 136, 1587, 2893], 12: [369, 211, 1409, 2227], 13: [273, 191, 1343, 2267],
             14: [369, 211, 1409, 2227], 15: [269, 185, 1339, 2261], 16: [112, 129, 1587, 2913]}


def hall_geo(hall):
    """도면 좌상·우상·좌하 모서리의 [위도, 경도]. 도면 아래쪽은 항상 중앙 통로 쪽 정문이다.
    짝수 홀(동쪽 줄)은 도면 왼쪽이 북쪽, 홀수 홀(서쪽 줄)은 왼쪽이 남쪽 (도면 옆 '通往N号馆' 표기로 확인)."""
    s = open(os.path.join(SITE, "venue.js"), encoding="utf-8").read()
    pts = json.loads(s[s.index("{"):s.rindex("}") + 1]).get(f"hall-{hall}", [None, None])[1]
    if not pts:
        return None
    lat0, lon0 = pts[0]
    kx, ky = 111320 * math.cos(math.radians(lat0)), 110574
    P = [((b - lon0) * kx, (a - lat0) * ky) for a, b in pts]
    best = None
    for (x1, y1), (x2, y2) in zip(P, P[1:]):
        t = math.atan2(y2 - y1, x2 - x1)
        c, n = math.cos(t), math.sin(t)
        u = [x * c + y * n for x, y in P]
        v = [-x * n + y * c for x, y in P]
        size = (max(u) - min(u)) * (max(v) - min(v))
        if best is None or size < best[0]:
            best = (size, t, min(u), max(u), min(v), max(v))
    _, t, u0, u1, v0, v1 = best
    if u1 - u0 < v1 - v0:  # u를 긴 변(동서 방향)으로
        t, u0, u1, v0, v1 = t - math.pi / 2, -v1, -v0, u0, u1
    if math.cos(t) < 0:  # u가 동쪽을 향하게
        t, u0, u1, v0, v1 = t + math.pi, -u1, -u0, -v1, -v0
    c, n = math.cos(t), math.sin(t)

    def geo(u, v):
        x, y = u * c - v * n, u * n + v * c
        return [round(lat0 + y / ky, 6), round(lon0 + x / kx, 6)]
    if hall % 2 == 0:  # 위=동, 왼쪽=북
        return [geo(u1, v1), geo(u1, v0), geo(u0, v1)]
    return [geo(u0, v0), geo(u0, v1), geo(u1, v0)]  # 위=서, 왼쪽=남


def nav_public(nav, exhibitors, tr=lambda s: s, names=None):
    names = names or {}
    companies = {str(x[0]): x for x in exhibitors}
    # 지도 부스에 기업 id가 빠져 있어도 중국어 회사명이 같으면 같은 기업으로 잇는다
    norm = lambda t: re.sub(r"[\s（）()·\-]", "", t or "")
    by_cn, by_code = {}, {}
    for x in exhibitors:
        by_cn.setdefault(norm(x[3]), str(x[0]))
        for c in re.split(r"\s*[,，、/]\s*", (x[4] or "").upper()):
            if c:
                by_code.setdefault(c, set()).add(str(x[0]))

    def link(cid, name, code):
        """기업 id → 같은 중국어 회사명 → 같은 부스 번호이면서 회사명 핵심 글자가 60% 이상 겹치는 기업 순으로 잇는다."""
        if cid in companies:
            return cid
        if norm(name) in by_cn:
            return by_cn[norm(name)]
        ids = by_code.get(code, ())
        if len(ids) == 1:
            other = next(iter(ids))
            core = lambda t: set(re.sub(r"有限责任公司|股份有限公司|有限公司|股份|集团|公司|科技|技术|^.{2,3}?[省市]|"
                                        r"深圳|北京|上海|广东|广州|东莞|苏州|杭州|浙江|江苏", "", norm(t)))
            a, b = core(name), core(companies[other][3])
            if a and b and len(a & b) >= .6 * min(len(a), len(b)):
                return other
        return cid
    result = []
    for area in nav:
        hall = nav_hall(area["name"])
        targets = {}
        for booth in area["named"]:
            company = companies.get(booth["cid"])
            code = nav_code(booth["booth"], hall)
            if (company and hall in company[5] and isinstance(booth.get("id"), int)
                    and code.startswith(f"{hall}-")
                    and code in re.split(r"\s*[,，、/]\s*", company[4].upper().strip())):
                targets.setdefault(code, []).append([company[0], booth["id"]])
        result.append({"name": area["name"], "total": area["total"], "named": len(area["named"]),
                       "hall": hall, "id": area["id"], "checkedAt": area.get("checkedAt"),
                       "targets": {code: entries[0] for code, entries in targets.items() if len(entries) == 1},
                       "r": HALL_RECT.get(hall), "g": hall_geo(hall) if hall in HALL_RECT else None,
                       # [부스 id, x, y, w, h, 부스 번호, 기업 id(없으면 0), 기업 id가 없을 때만 한글·중국어 이름]
                       "b": [[i, x, y, w, h, nav_code(code, hall), int(cid) if cid in companies else 0,
                              *(["", ""] if cid in companies else [names.get(name) or tr(name), name])]
                             for i, x, y, w, h, code, cid, name in
                             [(*b[:6], link(b[6], b[7], nav_code(b[5], hall)), b[7]) for b in area.get("booths", [])]]})
    return result


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


# 번역기가 자주 틀리게 옮기는 업계 용어 (번역 결과에서 바로잡는다)
KO_FIX = {"민첩한 손": "로봇 손", "손재주 있는 손": "로봇 손", "손재주가 있는 손": "로봇 손", "능숙한 손": "로봇 손",
          "구현된 지능": "체화 지능", "구체화된 지능": "체화 지능", "구현 지능": "체화 지능"}


def mt_long(texts, cache, save_to=None, budget=4000):
    """소개문·제품 설명처럼 여러 줄인 긴 글. 줄바꿈을 살리고 여러 글을 한 요청(약 4,000자)에 묶어 보낸다.
    번역이 안 된 글은 저장하지 않는다(반쪽 번역이나 중국어가 한국어 칸에 나가지 않도록)."""
    todo = [t for t in dict.fromkeys(texts) if t and CJK.search(t) and t not in cache]
    url = "https://translate.googleapis.com/translate_a/t?client=dict-chrome-ex&sl=zh-CN&tl=ko"

    def call(qs):
        body = urllib.parse.urlencode([("q", q) for q in qs]).encode()
        req = urllib.request.Request(url, data=body, headers={
            "User-Agent": "Mozilla/5.0", "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"})
        for i in range(5):
            try:
                d = json.load(urllib.request.urlopen(req, timeout=60))
                d = [x[0] if isinstance(x, list) else x for x in (d if isinstance(d, list) else [d])]
                if len(d) != len(qs):
                    raise ValueError("응답 개수 불일치")
                return d
            except urllib.error.HTTPError as e:
                time.sleep(60 if e.code == 429 else 5 * (i + 1))
            except Exception:  # noqa: BLE001
                time.sleep(5 * (i + 1))
        return None

    def tidy(r):
        r = re.sub("[\u200b-\u200d\ufeff]", "", r)
        for k, v in KO_FIX.items():
            r = r.replace(k, v)
        return re.sub(r"[ \t]+\n", "\n", re.sub(r"[ \t]{2,}", " ", r)).strip()

    # 긴 글은 문단 묶음으로 쪼개 보내고 다시 합친다
    pieces = []  # (글 번호, 조각)
    for n, t in enumerate(todo):
        cur = ""
        for para in t.split("\n"):
            if cur and len(cur) + len(para) > budget:
                pieces.append((n, cur))
                cur = ""
            cur += para + "\n"
        pieces.append((n, cur))
    out, failed, batch, size, sent = {}, set(), [], 0, 0

    def flush():
        nonlocal batch, size, sent
        if not batch:
            return
        res = call([q.rstrip("\n") for _, q in batch])
        for k, (n, _) in enumerate(batch):
            if res is None or not res[k].strip():
                failed.add(n)
            else:
                out.setdefault(n, []).append(res[k])
        batch, size = [], 0
        sent += 1
        if save_to and sent % 20 == 0:
            commit()
            save(save_to, cache)
        time.sleep(0.6)

    def commit():
        for n, parts in list(out.items()):
            if n in failed:
                continue
            if sum(1 for m, _ in pieces if m == n) == len(parts):
                r = tidy("\n".join(parts))
                if r and len(CJK.findall(r)) < len(r) * .2:
                    cache[todo[n]] = r
                del out[n]

    for n, q in pieces:
        if size and size + len(q) > budget:
            flush()
        batch.append((n, q))
        size += len(q)
    flush()
    commit()
    if save_to:
        save(save_to, cache)
    return cache


def long_texts(details, prods):
    out = []
    for d in details.values():
        out += [d.get("companyProfile"), d.get("typeProduct"), d.get("supplyAndDemand")]
    for rows in prods.values():
        out += [r[5] for r in rows if isinstance(r, list) and len(r) > 5]
    return [t for t in out if t]


# ---------------------------------------------------------------- 빌드
CATMAP = {
    "人工智能与机器人": "AI·로봇", "智能制造与自动化": "스마트 제조·자동화", "新材料": "신소재",
    "新型电力、储能、充电": "전력·에너지저장·충전", "低空经济与商业航天": "드론·저고도·민간 우주",
    "消费电子": "소비자 가전", "AI 算力产业与数据中心": "AI 컴퓨팅·데이터센터", "半导体与集成电路": "반도체·IC",
    "医药/生物技术与实验室": "의약·바이오·실험실", "科研院所高校": "연구기관·대학", "新质生产力": "첨단 산업 전환",
    "数字产业": "디지털 산업", "深圳科技成果、未来前沿科技": "선전 기술·미래 기술",
    "节能环保和绿色低碳": "에너지 절감·친환경", "国之重器科技巨头产业链": "국가 전략 장비·빅테크",
    "国际科技与省市科技": "해외·중국 지역 기술", "清洁能源、氢能产业": "청정에너지·수소", "水务与环境": "수처리·환경",
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
    nav_booths = {}
    for area in nav:
        hall = nav_hall(area["name"])
        for entry in area["named"]:
            if entry["cid"] and entry["booth"] and hall:
                raw_code = entry["booth"].strip().upper()
                code = nav_code(raw_code, hall)
                nav_booths.setdefault(entry["cid"], {}).setdefault(raw_code, set()).add(code)

    llm = load(os.path.join(I18N, "llm_ko.json"), {})  # i18n/llm_translate.py (Claude) 번역
    llm_names = load(os.path.join(I18N, "llm_names.json"), {})

    def tr(s):
        if not s or not CJK.search(s):
            return s
        return ko.get(s) or llm.get(s) or mt.get(s) or s

    cats, cidx = [], {}

    def cat(n):
        k = CATMAP.get(n.strip(), n.strip())
        if k not in cidx:
            cidx[k] = len(cats)
            cats.append(k)
        return cidx[k]

    X, catalog, hall_count, hall_cats, cat_count, kr_halls, nohall = [], [], {}, {}, {}, set(), 0
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
        # 중국 기업은 한글 음역 대신 영문 브랜드명(i18n/llm_names.json)으로 보여 주고, 한글 이름은 검색용으로 남긴다
        alias = ""
        if not kr and llm_names.get(cn):
            alias, name = (name if name != llm_names[cn] else ""), llm_names[cn]
        booth = clean_booth(r.get("boothNum"))
        if official := nav_booths.get(str(r["serveCatalogueId"])):
            parts = re.split(r"\s*[,，、/]\s*", booth) if booth else list(official)
            for i, part in enumerate(parts):
                matches = official.get(part.upper(), ())
                if len(matches) == 1:
                    parts[i] = next(iter(matches))
            booth = ",".join(parts)
        hs = halls_of(booth)
        cs = [cat(t["tradeName"]) for t in (r.get("tradeClassList") or [])]
        plist = []
        for row in prods.get(str(r["serveCatalogueId"]), []):
            p = product_name(row)
            title = tr(p)
            plist.append([title, p])
            if isinstance(row, list):
                catalog.append([row[1], r["serveCatalogueId"], title, p, *row[2:5]])
            if CJK.search(p) and p not in ko:
                pending.add(p)
        X.append([r["serveCatalogueId"], name, en, cn, booth, hs, cs, 1 if kr else 0, plist, r.get("readNum") or 0, alias])
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
                "halls": nav_public(nav, X, tr, llm_names)},
        "x": X,
    }
    save(os.path.join(SITE, "data.json"), out, compact=True)

    # 기업 상세: 기업마다 site/co/<id>.json (상세 화면을 열 때만 받는다)
    details = load(os.path.join(RAW, "details.json"), {})
    mtl = load(os.path.join(I18N, "mt_long.json"), {})

    rename = {x[0]: (x[10], re.sub(r"\s*\([^)]*\)$", "", x[10]), x[1]) for x in X if x[10]}

    def renamed(cid, text):
        """번역문 속 옛 한글 음역 이름을 표시 이름으로 바꾼다."""
        if cid in rename and text:
            old, short, new = rename[cid]
            text = text.replace(old, new)
            if len(short) >= 3:
                text = text.replace(short, new)
        return text

    def trl(s):
        """번역이 아직 없으면 빈 문자열 → 화면은 '번역 준비 중'과 원문을 보여 준다(중국어를 한국어 칸에 넣지 않는다)."""
        return (ko.get(s) or llm.get(s) or mtl.get(s) or "") if s and CJK.search(s) else (s or "")
    co_dir = os.path.join(SITE, "co")
    os.makedirs(co_dir, exist_ok=True)
    keep = set()
    for r in ex:
        cid = str(r["serveCatalogueId"])
        d = details.get(cid, {})
        rows = [p for p in prods.get(cid, []) if isinstance(p, list)]
        kw = d.get("supplyAndDemand") or ""
        co = {
            "p": renamed(int(cid), trl(d.get("companyProfile"))), "pc": d.get("companyProfile") or "", "pe": "" if d.get("companyProfile") else d.get("companyProfileEn") or "",
            "t": trl(d.get("typeProduct")), "tc": d.get("typeProduct") or "",
            "k": [w.strip() for w in re.split(r"[,，、;；]", trl(kw)) if w.strip()][:20],
            "w": d.get("site") or "", "tel": d.get("tel") or "", "m": d.get("email") or "",
            "a": d.get("companyAddress") or r.get("companyAddress") or "", "ae": d.get("companyAddressEn") or "",
            "img": (d.get("pic") or r.get("pic") or "").split(",")[0], "logo": d.get("logo") or r.get("companyLogo") or "",
            # [제품 id, 한글명, 원문명, 규격, 한글 설명, 원문 설명, 사진들]
            "pr": [[p[1], tr(p[0]), p[0], p[4], renamed(int(cid), trl(p[5])) if len(p) > 5 else "", p[5] if len(p) > 5 else "",
                    p[6] if len(p) > 6 else ([p[3]] if p[3] else [])] for p in rows],
        }
        name = cid + ".json"
        keep.add(name)
        save(os.path.join(co_dir, name), co, compact=True)
    for name in os.listdir(co_dir):
        if name.endswith(".json") and name not in keep:
            os.remove(os.path.join(co_dir, name))
    save(os.path.join(SITE, "products.json"), catalog, compact=True)
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

    # 기업 상세: 새 기업은 바로, 기존 기업은 오래된 순으로 매번 300곳씩 다시 받는다 (약 3시간이면 한 바퀴)
    details = load(os.path.join(RAW, "details.json"), {})
    stale = sorted(new, key=lambda c: (str(c) in details, details.get(str(c), {}).get("_at", "")))[:max(300, sum(str(c) not in details for c in new))]
    with cf.ThreadPoolExecutor(8) as pool:
        for cid, res in zip(stale, pool.map(lambda c: _safe(fetch_detail, c), stale)):
            if res is not None:
                res["_at"] = now
                details[str(cid)] = res
    save(os.path.join(RAW, "details.json"), {k: v for k, v in details.items() if int(k) in new})

    for cid in refresh_products(new, prods):
        if cid in old:
            items.append({"type": "products", "id": cid})

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
        nav_current = {h["id"]: h for h in nav_new}
        if any(nav_current.get(i, {}).get("total", 0) < previous["total"] * .7
               or len(nav_current.get(i, {}).get("named", [])) < len(previous["named"]) * .7
               for i, previous in nav_old.items()):
            raise ValueError("공식 지도 데이터가 크게 줄어 직전 확인본 유지")
        for h in nav_new:
            before = len((nav_old.get(h["id"]) or {}).get("named", []))
            if len(h["named"]) > before:
                items.append({"type": "nav", "hall": h["name"], "from": before, "to": len(h["named"])})
        save(os.path.join(RAW, "nav.json"), nav_new)
    except Exception as e:  # noqa: BLE001
        print("부스 내비게이션 수집 실패:", e, file=sys.stderr)

    save(os.path.join(RAW, "exhibitors.json"), list(new.values()))
    save(os.path.join(RAW, "prod_by_cat.json"), prods, compact=True)
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
    strings += [product_name(p) for cid in new for p in prods.get(str(cid), [])] + [e["title"] for e in ev_new]
    strings += [b[7] for h in load(os.path.join(RAW, "nav.json"), []) for b in h.get("booths", [])]
    need = [s for s in strings if s and CJK.search(s) and s not in ko and s not in mt]
    if need:
        save(os.path.join(I18N, "mt_cache.json"), mt_translate(need, mt))
    mtl_path = os.path.join(I18N, "mt_long.json")
    mt_long(long_texts(details, prods), load(mtl_path, {}), save_to=mtl_path)
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
