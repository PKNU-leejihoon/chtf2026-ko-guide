#!/usr/bin/env python3
"""mirror/pages.json 으로 한국어 정적 페이지(site/p/)를 만든다."""
import html, json, os, re, shutil, sys
ROOT = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(ROOT)
sys.path.insert(0, REPO)
import update as U  # 번역 캐시 유틸 재사용
OUT = os.path.join(REPO, "site", "p")
CJK = re.compile("[一-鿿]")
SEC = {"about": "고교회 소개", "expo": "전시·전문전", "forum": "포럼·행사", "visit": "참관 안내", "exhibit": "참가사 안내", "sponsor": "협찬·제휴", "media": "뉴스·미디어", "etc": "기타"}
ORDER = ["visit", "forum", "expo", "about", "media", "exhibit", "sponsor", "etc"]
e = lambda s: html.escape(str(s or ""), quote=True)
ko = U.load(os.path.join(REPO, "i18n", "ko.json"), {})
mt = U.load(os.path.join(REPO, "i18n", "mt_cache.json"), {})
imgs = U.load(os.path.join(ROOT, "img_map.json"), {})
stats = {"ko": 0, "mt": 0}


U16 = '<p class="tn"><b>번역자 주.</b> 16세 미만 입장 안내가 공식 페이지끼리 다릅니다. 입장 안내는 "16세 미만 사절", 입장권 공지는 "보호자 동반과 면책 동의서 서명 시 무료 입장"이라고 적고 있습니다. 미성년자와 함께 간다면 남측 등록홀 관람객 서비스 창구에 먼저 확인하세요.</p>'
NOTES = {"canguanzhiyin-gonggao": U16, "canguanzhiyin-ruchangxuzhiX": U16}


def slug(u):
    p = re.sub(r"\W+", "-", U.urllib.parse.urlparse(u).path.strip("/")).strip("-")
    return p or "home"


def tr(s):
    if not s or not CJK.search(s):
        return s or ""
    if s in ko:
        stats["ko"] += 1
        return ko[s]
    stats["mt"] += 1
    return mt.get(s) or s


def hidden(s):
    return s.lstrip().startswith("<") and s not in ko


def strings(pages, meets):
    out = []
    for p in pages:
        out.append(p["title"])
        for b in p["blocks"]:
            if b["t"] in ("p", "h", "li", "a") and hidden(b["x"]):
                continue
            if b["t"] in ("p", "h", "li", "a"):
                out.append(b["x"])
            elif b["t"] == "card":
                out += [b["x"], b.get("s", "")]
            elif b["t"] == "table":
                out += [c for r in b["rows"] for c in r]
    for m in meets:
        out += [U_clean(m.get(k)) for k in ("meetname", "location", "charge", "roomname", "class_name")]
    return [s for s in dict.fromkeys(out) if s and CJK.search(s)]


def U_clean(s):
    return re.sub(r"\s+", " ", (s or "").replace("<br>", " ")).strip()


HEAD = re.compile(r"^(?:[一二三四五六七八九十]+[、.．]|[（(][一二三四五六七八九十]+[)）]|第[一二三四五六七八九十]+[章节部分])")


def link(h, known):
    k = h.split("#")[0].rstrip("/")
    return ("../p/" + known[k] + ".html", False) if k in known else (h, True)


def img_tag(src, alt=""):
    local = imgs.get(src)
    if local:
        return f'<img src="../{e(local)}" alt="{e(alt)}" loading="lazy">'
    return f'<img src="{e(src)}" alt="{e(alt)}" loading="lazy" referrerpolicy="no-referrer">'


def render_blocks(p, known):
    out, ul = [], False
    title = p["title"]
    def close():
        nonlocal ul
        if ul:
            out.append("</ul>"); ul = False
    for i, b in enumerate(p["blocks"]):
        t = b["t"]
        if t != "li":
            close()
        if t in ("p", "h", "li", "a") and hidden(b["x"]):
            continue
        if t in ("p", "h") and b["x"] == title and i < 3:
            continue
        if t == "li":
            if not ul:
                out.append("<ul>"); ul = True
            out.append(f"<li>{e(tr(b['x']))}</li>")
        elif t == "h" or (t == "p" and len(b["x"]) < 40 and HEAD.match(b["x"])):
            out.append(f"<h2>{e(tr(b['x']))}</h2>")
        elif t == "p":
            out.append(f"<p>{e(tr(b['x']))}</p>")
        elif t == "a":
            h, ext = link(b["href"], known)
            if "index_" in h:
                continue
            out.append(f'<p><a href="{e(h)}"{" target=_blank rel=noopener" if ext else ""}>{e(tr(b["x"]))}{" ↗" if ext else ""}</a></p>')
        elif t == "img":
            out.append(f"<figure>{img_tag(b['src'], b.get('alt'))}</figure>")
        elif t == "video":
            out.append(f'<p><a href="{e(b["src"])}" target="_blank" rel="noopener">영상 보기 ↗</a></p>')
        elif t == "table":
            rows = "".join("<tr>" + "".join(f"<td>{e(tr(c))}</td>" for c in r) + "</tr>" for r in b["rows"])
            out.append(f'<div class="tw"><table>{rows}</table></div>')
        elif t == "card":
            h, ext = link(b["href"], known)
            pic = img_tag(b["img"]) if b.get("img") else ""
            out.append(f'<a class="card" href="{e(h)}"{" target=_blank rel=noopener" if ext else ""}>{pic}<span><b>{e(tr(b["x"]))}</b>{("<small>"+e(b["d"])+"</small>") if b.get("d") else ""}{("<em>"+e(tr(b["s"]))+"</em>") if b.get("s") else ""}</span></a>')
    close()
    return "\n".join(out)


CSS = """:root{--bg:#f3f5f8;--s:#fff;--i:#122033;--m:#5a6779;--l:#d8dee7;--a:#0f6fd6;--c:#e9eef5;color-scheme:light}
@media (prefers-color-scheme:dark){:root{--bg:#0d141d;--s:#151f2b;--i:#e6edf5;--m:#9aa8b8;--l:#2a3848;--a:#4c9cf0;--c:#1f2b39;color-scheme:dark}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--i);font:16px/1.75 "IBM Plex Sans KR","Apple SD Gothic Neo","Malgun Gothic",system-ui,sans-serif}
a{color:var(--a)}.w{max-width:860px;margin:0 auto;padding-left:max(16px,env(safe-area-inset-left));padding-right:max(16px,env(safe-area-inset-right))}
header{background:var(--s);border-bottom:1px solid var(--l)}header .w{max-width:1100px;display:flex;gap:6px 18px;align-items:center;flex-wrap:wrap;padding-block:12px}
header b{font-size:1.05rem}header a{text-decoration:none;color:var(--m);font-size:.9rem;font-weight:600}header a.h{color:var(--i)}
main{padding-block:26px 56px}h1{font-size:1.65rem;line-height:1.35;margin:4px 0 8px;text-wrap:balance}h2{font-size:1.14rem;margin:30px 0 8px;line-height:1.4}
.meta{font-size:.82rem;color:var(--m);display:flex;gap:6px 14px;flex-wrap:wrap;margin-bottom:22px}p{margin:10px 0}ul{padding-left:1.2em}figure{margin:16px 0}img{max-width:100%;height:auto;display:block;border-radius:6px}.tn{background:var(--c);border:1px solid var(--l);border-radius:8px;padding:10px 12px;font-size:.9rem}
.tw{overflow-x:auto;margin:14px 0;background:var(--s);border:1px solid var(--l);border-radius:8px}table{border-collapse:collapse;width:100%;font-size:.88rem;line-height:1.5}td{border-bottom:1px solid var(--l);padding:8px 10px;vertical-align:top;min-width:72px}tr:first-child td{font-weight:700;background:var(--c)}
.card{display:grid;grid-template-columns:120px minmax(0,1fr);gap:12px;background:var(--s);border:1px solid var(--l);border-radius:8px;padding:10px;margin:8px 0;text-decoration:none;color:inherit}.card span{display:flex;flex-direction:column;gap:2px;min-width:0}.card small{color:var(--m)}.card em{font-style:normal;font-size:.86rem;color:var(--m)}.card b{line-height:1.4}
.grp{margin-top:26px}.list{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:6px 18px;list-style:none;padding:0}
.sc td{min-width:0}.tag{display:inline-block;background:var(--c);border-radius:4px;padding:0 6px;font-size:.76rem;color:var(--m)}
footer{border-top:1px solid var(--l);color:var(--m);font-size:.8rem}footer .w{padding-block:16px 28px}"""


def page(title, body, orig=None, sec=None, depth=""):
    top = f'<header><div class="w"><a class="h" href="../index.html"><b>고교회 2026 관람 노트</b></a><a href="index.html">공식 안내 한글판</a><a href="schedule.html">행사 일정</a><a href="../index.html#find">기업 찾기</a></div></header>'
    meta = ""
    if sec or orig:
        meta = '<div class="meta">' + (f'<a href="index.html#{sec}">{e(SEC[sec])}</a>' if sec else "") + (f'<a href="{e(orig)}" target="_blank" rel="noopener">공식 원문 ↗</a>' if orig else "") + "<span>비공식 번역</span></div>"
    return f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><title>{e(title)} · 고교회 2026 한글판</title><link rel="stylesheet" href="style.css"></head><body>{top}<main class="w"><h1>{e(title)}</h1>{meta}{body}</main><footer><div class="w">비공식 한국어 번역본입니다. 내용과 일정은 공식 사이트(chtf.com)를 기준으로 확인하세요. 등록·신청은 공식 페이지에서만 진행됩니다. 권리자의 삭제 요청은 <a href="https://github.com/PKNU-leejihoon/chtf2026-ko-guide/issues">GitHub Issues</a>로 받습니다.</div></footer></body></html>'


def schedule(meets):
    names = {"2026-11-26": "11월 26일 (목)", "2026-11-27": "11월 27일 (금)", "2026-11-28": "11월 28일 (토)"}
    out = ['<p>공식 동시행사표의 시간·장소·참가 조건을 선전 현지 시각으로 옮겼습니다. 16관 신제품 발표는 <a href="luntanjihuodong-sfsxlyq.html">별도 로드쇼 시간표</a>에서 확인할 수 있습니다. <a href="../index.html#events">추천 포럼·로드쇼</a> · <a href="https://www.chtf.com/live/">공식 생중계</a></p>']
    for d in sorted({m["meet_date"] for m in meets}):
        out.append(f"<h2>{names.get(d, d)}</h2><div class='tw sc'><table><tr><td>시간</td><td>행사</td><td>장소</td><td>참가</td></tr>")
        for m in sorted((x for x in meets if x["meet_date"] == d), key=lambda x: (x["start_time"], x["sort"])):
            n = e(tr(U_clean(m["meetname"])))
            if m.get("more_link"):
                n = f'<a href="{e(U.urllib.parse.urljoin("https://www.chtf.com/", m["more_link"]))}" target="_blank" rel="noopener">{n} ↗</a>'
            out.append(f"<tr><td>{e(m['start_time'])}–{e(m['end_time'])}</td><td>{n}</td><td>{e(tr(U_clean(m['location'])))}</td><td>{e(tr(U_clean(m['charge'])))}</td></tr>")
        out.append("</table></div>")
    return "".join(out)


def main():
    pages = U.load(os.path.join(ROOT, "pages.json"), [])
    meets = U.load(os.path.join(ROOT, "meetings.json"), [])
    S = strings(pages, meets)
    need = [s for s in S if s not in ko and s not in mt]
    if need and "--no-mt" not in sys.argv:
        U.mt_translate(need, mt)
        U.save(os.path.join(REPO, "i18n", "mt_cache.json"), mt)
    U.save(os.path.join(ROOT, "pending.json"), [s for s in S if s not in ko])
    shutil.rmtree(OUT, ignore_errors=True); os.makedirs(OUT)
    open(os.path.join(OUT, "style.css"), "w").write(CSS)
    known = {p["url"].rstrip("/"): slug(p["url"]) for p in pages}
    for p in pages:
        t = tr(p["title"])
        open(os.path.join(OUT, slug(p["url"]) + ".html"), "w", encoding="utf-8").write(page(t, NOTES.get(slug(p["url"]), "") + render_blocks(p, known), p["url"], p["sec"]))
    open(os.path.join(OUT, "schedule.html"), "w", encoding="utf-8").write(page("공식 동시행사 일정", schedule(meets), "https://www.chtf.com/meet/"))
    idx = ['<p>공식 사이트의 올해 안내 페이지와 이미지 속 글자를 한국어로 옮겼습니다. 참관 등록과 참가 신청은 공식 페이지로 연결됩니다. 뉴스 본문은 공식 사이트 밖의 위챗 글이라 제목과 요약만 옮겼고, 로고와 일부 작은 글자는 원문 그대로 둡니다.</p><p><a href="schedule.html"><b>공식 동시행사 일정</b></a> · <a href="luntanjihuodong-sfsxlyq.html">16관 로드쇼</a> · <a href="https://www.chtf.com/live/">공식 생중계</a></p>']
    for s in ORDER:
        L = [p for p in pages if p["sec"] == s]
        if L:
            idx.append(f'<section class="grp" id="{s}"><h2>{SEC[s]}</h2><ul class="list">' + "".join(f'<li><a href="{slug(p["url"])}.html">{e(tr(p["title"]))}</a></li>' for p in L) + "</ul></section>")
    open(os.path.join(OUT, "index.html"), "w", encoding="utf-8").write(page("공식 안내 한글판", "".join(idx)))
    print(json.dumps({"pages": len(pages), "meetings": len(meets), "strings": len(S), "pending_review": sum(1 for s in S if s not in ko)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
