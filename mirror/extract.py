#!/usr/bin/env python3
"""공식 사이트의 올해 페이지를 받아 본문 블록으로 정리한다 (mirror/pages.json)."""
import concurrent.futures as cf, hashlib, json, os, re, subprocess, sys, time
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup, NavigableString, Tag

ROOT = os.path.dirname(os.path.abspath(__file__))
BASE = "https://www.chtf.com"
CACHE = os.path.join(ROOT, ".cache")
os.makedirs(CACHE, exist_ok=True)
CJK = re.compile("[一-鿿]")
SECTIONS = [
    ("about", "고교회 소개", ["liaojiegaojiaohui/zynr", "liaojiegaojiaohui/zhanqu", "liaojiegaojiaohui/xuanchuance", "liaojiegaojiaohui/baogao", "liaojiegaojiaohui/lianxiwomen", "liaojiegaojiaohui/gongshi", "liaojiegaojiaohui/video"]),
    ("expo", "전시·전문전", ["zhanlanyuzhanshi"]),
    ("forum", "포럼·행사", ["luntanjihuodong"]),
    ("visit", "참관 안내", ["canguanzhiyin"]),
    ("exhibit", "참가사 안내", ["canzhanzhiyin"]),
    ("sponsor", "협찬·제휴", ["guanggaohezuo/zzhz", "guanggaohezuo/zanzhuhezuo", "guanggaohezuo/gongyingshangzhengji"]),
    ("media", "미디어", ["meitizhiyin"]),
    ("etc", "기타", ["awardList"]),
]
SHOW_SLUGS = {"guozhizhognqi","guojichengguo","keyanyuan","shenzhenkejichengguo","rengongzhineng","jiqirenchanye","bandaoti","zhinengzhizao","dianzixiaofei","dikongjingji","syht","kuajingdianshang","shengwujishu","gaoduanyiliao","chunengdianchi","guangchuchongdianzhuang","shuzinengyuan","shuiwuyuhuanjing","shizhenggongcheng","guidao","zhihuigangkou","yazhouxincailiaochanyezhan","alsh"}
SKIP = ("liaojiegaojiaohui/zynr/licheng", "liaojiegaojiaohui/video", "canguanzhiyin/dzccpzn", "canguanzhiyin/menpiao_1", "canguanzhiyin/piaozheng", "canzhanzhiyin/piaozheng", "guanggaohezuo/gongyingshangzhengji", "luntanjihuodong/zhaongguogaoxinjishuluntan/")
OLD_AID = 1090
OLD_FORUM = {"caiguoduijiehui","kms","pingjiang","wy","xmpdqthd","zhuanyejishuluntan_1076","baigonghui"}


def fetch(u):
    n = os.path.join(CACHE, hashlib.md5(u.encode()).hexdigest() + ".html")
    if os.path.exists(n) and time.time() - os.path.getmtime(n) < 6 * 3600:
        return open(n, encoding="utf-8", errors="ignore").read()
    if os.environ.get("MIRROR_OFFLINE"):
        return ""
    for i in range(2):
        r = subprocess.run(["curl", "-sL", "--compressed", "-m", "40", "-A", "Mozilla/5.0", u], capture_output=True)
        if r.returncode == 0 and r.stdout:
            s = r.stdout.decode("utf-8", "ignore")
            open(n, "w", encoding="utf-8").write(s)
            return s
        time.sleep(1 + i)
    return ""


def norm(u):
    p = urlparse(u)
    return BASE + p.path + ("?" + p.query if p.query else "")


def in_scope(u, title):
    path = urlparse(u).path.strip("/")
    if not path or "/english" in u or title.startswith(("删", "隐藏")) or "index_" in path:
        return None
    m = re.search(r"/(20\d{2})\d{2}/", "/" + path + "/")
    if m and int(m.group(1)) < 2026:
        return None
    parts = path.split("/")
    if any(path.startswith(x) for x in SKIP):
        return None
    if parts[0] == "zhanlanyuzhanshi" and len(parts) > 1 and parts[1] not in SHOW_SLUGS:
        return None
    if parts[0] == "luntanjihuodong" and len(parts) > 1 and parts[1] in OLD_FORUM:
        return None
    if "第二十七届" in title or "第二十六届" in title or "2025" in title[:6]:
        return None
    if parts[0] == "liaojiegaojiaohui" and "video" in parts and len(parts) > 2 and not m:
        return None
    for key, name, pre in SECTIONS:
        for x in pre:
            if path == x or path.startswith(x + "/"):
                return key
    return None


def clean(s):
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ").replace("　", " ")).strip()


def blocks_of(el, base):
    out = []
    def img(t):
        s = t.get("src") or t.get("data-src") or ""
        if s and "/public/images/" not in s:
            out.append({"t": "img", "src": urljoin(base, s), "alt": clean(t.get("alt"))})
    def card(a):
        h = urljoin(base, a.get("href") or "")
        txt = clean(a.get_text(" "))
        d = re.search(r"20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}", txt)
        y = re.search(r"/(20\d{2})\d{2}/", h)
        if (d and int(d.group(0)[:4]) < 2026) or (y and int(y.group(1)) < 2026):
            return
        aid = re.search(r"[?&]aid=(\d+)", h)
        if aid and int(aid.group(1)) < OLD_AID and not re.search(r"第二十八届|第28届|2026", txt.replace(d.group(0) if d else "\0", "")):
            return  # 2026-06-18로 일괄 재등록된 지난 회차 글
        ttl = clean(a.get("title")) or clean((a.select_one(".t1, .tit, .title, .txt, .t2") or a).get_text(" "))
        ex = a.select_one(".tbox .txt")
        im = a.find("img", class_=lambda v: v != "play")
        out.append({"t": "card", "x": ttl[:120], "s": clean(ex.get_text(" ")) if ex else "", "d": d.group(0) if d else "", "href": h,
                    "img": urljoin(base, im.get("src")) if im and im.get("src") else ""})
    def walk(n):
        for c in n.children:
            if isinstance(c, NavigableString):
                x = clean(str(c))
                if x:
                    out.append({"t": "p", "x": x})
                continue
            if not isinstance(c, Tag) or c.name in ("script", "style", "iframe", "form", "input"):
                continue
            if c.name == "li" and c.find("a", recursive=False) and c.find("a", recursive=False).find(["img", "div", "span"]):
                card(c.find("a", recursive=False))
            elif c.name == "img":
                img(c)
            elif c.name == "table":
                rows = []
                for r in c.find_all("tr"):
                    cells = [clean(d.get_text(" ")) for d in r.find_all(["td", "th"])]
                    if any(cells):
                        rows.append(cells)
                if rows:
                    out.append({"t": "table", "rows": rows})
                for i in c.find_all("img"):
                    img(i)
            elif c.name in ("h1", "h2", "h3", "h4", "h5"):
                x = clean(c.get_text(" "))
                if x:
                    out.append({"t": "h", "x": x})
            elif c.name == "video" or c.find("video") is not None:
                v = c if c.name == "video" else c.find("video")
                s = v.get("src") or (v.find("source") or {}).get("src") if v else ""
                if s:
                    out.append({"t": "video", "src": urljoin(base, s)})
            elif c.find(["img", "table", "h1", "h2", "h3", "h4", "h5", "p", "div", "ul", "ol", "li"]) is None:
                x = clean(c.get_text(" "))
                if x:
                    a = c if c.name == "a" else c.find("a")
                    h = a.get("href") if a else None
                    if h and not h.startswith("javascript"):
                        out.append({"t": "a", "x": x, "href": urljoin(base, h)})
                    else:
                        out.append({"t": "li" if c.name == "li" else "p", "x": x})
            else:
                walk(c)
    walk(el)
    return out


PAGER = re.compile(r"^(共\s*\d+\s*页.*|首页|上一页|下一页|末页|尾页|\d{1,3}|\.\.\.|…)$")


def paged(html, u, blocks):
    """목록 페이지의 2쪽 이후에서 올해 카드만 이어 붙이고 쪽 번호는 뺀다."""
    if not re.search(r"index_list_\d+\.html", html):
        return [x for x in blocks if not (x["t"] in ("p", "li") and re.match(r"^共\s*\d+\s*页", x["x"]))]
    out = [x for x in blocks if not (x["t"] in ("p", "li", "a") and PAGER.match(x["x"]))]
    seen = {x["href"] for x in out if x["t"] == "card"}
    for n in range(2, 41):
        pu = urljoin(u, f"index_list_{n}.html")
        t = fetch(pu)
        main = BeautifulSoup(t, "html.parser").select_one(".list-center") if t else None
        if main is None:
            break
        new = [x for x in blocks_of(main, pu) if x["t"] == "card" and x["href"] not in seen]
        if not new:
            break
        seen.update(x["href"] for x in new)
        out += new
        time.sleep(0.2)
    return out


def parse(u):
    t = fetch(u)
    if not t:
        return None
    s = BeautifulSoup(t, "html.parser")
    title = clean(((s.title.get_text() if s.title else "") or "").split("_")[0])
    sec = in_scope(u, title)
    if not sec:
        return None
    main = s.select_one(".list-center") or s.select_one(".article-con")
    if main is None:
        return None
    bc = s.select_one(".breadcrumbs")
    b = []
    for x in blocks_of(main, u):
        if x["t"] in ("p", "h", "li", "a") and "注释代码" in x["x"]:
            break  # 이후는 공식 페이지에서 숨겨 둔 예전 내용
        if x["t"] in ("p", "h", "li") and re.search(r"[-=]{6,}", x["x"]):
            continue
        b.append(x)
    b = paged(t, u, b)
    txt = " ".join(x.get("x", "") for x in b if not x.get("x", "").lstrip().startswith("<")) + " ".join(c for x in b if x["t"] == "table" for r in x["rows"] for c in r)
    if re.search(r"第二十[四五六]届|2024年11月1[4-6]", txt) and not re.search(r"第二十八届|第28届|2026", txt):
        return None
    return {"url": u, "sec": sec, "title": title, "crumb": clean(bc.get_text(" ")) if bc else "", "blocks": b}


def main():
    seeds = os.path.join(ROOT, "urls.json")
    urls = json.load(open(seeds)) if os.path.exists(seeds) else []
    if len(sys.argv) > 1:
        urls += [u for u, v in json.load(open(sys.argv[1]))["pages"].items() if v["st"] == 200 and "/english" not in u]
    # 공식 사이트 메뉴에서 새 페이지를 찾는다
    home = BeautifulSoup(fetch(BASE + "/"), "html.parser")
    for a in home.select("a[href]"):
        u = urljoin(BASE + "/", a["href"]).split("#")[0]
        if urlparse(u).netloc == "www.chtf.com":
            urls.append(u)
    urls = list(dict.fromkeys(u for u in urls if not re.search(r"\.(pdf|jpe?g|png|mp4|docx?|xlsx?)$", u, re.I)))
    path = os.path.join(ROOT, "pages.json")
    prev = {r["url"]: r for r in json.load(open(path))} if os.path.exists(path) else {}

    def safe(u):
        """공식 사이트가 일시적으로 응답하지 않으면 이전 내용을 유지한다."""
        r = parse(u)
        old = prev.get(u)
        if old is None:
            return r
        if not fetch(u) or r is None and not BeautifulSoup(fetch(u), "html.parser").select_one(".list-center, .article-con"):
            return old
        count = lambda x: sum(1 for b in x["blocks"] if b["t"] == "card")
        if r and count(old) >= 10 and count(r) < count(old) * 0.7:
            return old
        return r
    with cf.ThreadPoolExecutor(6) as ex:
        res = [r for r in ex.map(safe, urls) if r and r["blocks"]]
    seen, out = set(), []
    for r in res:
        k = norm(r["url"]).rstrip("/")
        if k not in seen:
            seen.add(k)
            out.append(r)
    out.sort(key=lambda r: r["url"])
    if prev and len(out) < len(prev) * 0.8:
        sys.exit(f"수집 결과가 너무 적어 중단합니다: {len(out)} / {len(prev)}")
    json.dump(out, open(os.path.join(ROOT, "pages.json"), "w", encoding="utf-8"), ensure_ascii=False)
    json.dump([r["url"] for r in out], open(seeds, "w"), ensure_ascii=False, indent=0)
    r = subprocess.run(["curl", "-s", "-m", "40", "-A", "Mozilla/5.0", BASE + "/plus/meetinfo.php?do=select"], capture_output=True)
    d = json.loads(r.stdout.decode("utf-8", "ignore"))
    if d.get("code") == 200 and d.get("date"):
        json.dump(d["date"], open(os.path.join(ROOT, "meetings.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print(len(out), "pages")


if __name__ == "__main__":
    main()
