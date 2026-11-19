#!/usr/bin/env python3
"""OCR 결과와 mirror/img_ko.json으로 번역 이미지를 만든다(macOS 로컬 전용).
결과: site/img/*.jpg, mirror/img_map.json(원본 URL → site 기준 경로)"""
import json, os, sys, tempfile
import concurrent.futures as cf
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import imgtr
ROOT = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(os.path.dirname(ROOT), "site")
OUT = os.path.join(SITE, "img")
MAXW = 1200


def flat(path):
    im = Image.open(path)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA"); bg = Image.new("RGBA", im.size, "white"); bg.alpha_composite(im); im = bg
    return im.convert("RGB")


def one(a):
    path, blocks, tr = a
    if not any(tr.get(b["t"]) for b in blocks):
        return path, None
    name = os.path.splitext(os.path.basename(path))[0] + ".jpg"
    out = os.path.join(OUT, name)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as t:
        tmp = t.name
    try:
        flat(path).save(tmp)
        imgtr.apply(tmp, blocks, tr, out, 80)
    finally:
        os.unlink(tmp)
    im = Image.open(out)
    if im.width > MAXW:
        im = im.convert("RGB").resize((MAXW, round(im.height * MAXW / im.width)), Image.LANCZOS)
        im.save(out, "JPEG", quality=80, optimize=True, progressive=True)
    return path, "img/" + name


def main():
    W = os.path.join(ROOT, "img_work")
    os.makedirs(OUT, exist_ok=True)
    B = json.load(open(os.path.join(W, "blocks.json")))
    F = json.load(open(os.path.join(W, "files.json")))
    tr = json.load(open(os.path.join(ROOT, "img_ko.json")))
    only = set(sys.argv[1:])
    jobs = [(os.path.join(os.path.dirname(ROOT), f) if not os.path.isabs(f) else f, d["blocks"], tr) for f, d in B.items() if not only or any(x in f for x in only)]
    done = {}
    with cf.ProcessPoolExecutor(6) as ex:
        for p, o in ex.map(one, jobs):
            if o:
                done[os.path.relpath(p, os.path.dirname(ROOT))] = o
    old = {} if not only else json.load(open(os.path.join(ROOT, "img_map.json")))
    for u, f in F.items():
        if f in done:
            old[u] = done[f]
    json.dump(old, open(os.path.join(ROOT, "img_map.json"), "w"), ensure_ascii=False, indent=0)
    print(len(done), "images", len(old), "urls")


if __name__ == "__main__":
    main()
