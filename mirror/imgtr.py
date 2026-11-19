#!/usr/bin/env python3
"""이미지 속 중국어를 한국어로 바꾼다.
  blocks: OCR 결과(JSON lines)를 문단 블록으로 묶는다
  apply : 번역이 있는 블록만 지우고 다시 쓴다. 번역이 없는 글자(로고 등)는 그대로 둔다.
"""
import json, re, sys
import cv2, numpy as np
from PIL import Image, ImageDraw, ImageFont
FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
CJK = re.compile("[一-鿿]")


def group(lines, W):
    lines = sorted(lines, key=lambda l: (l["y"], l["x"]))
    blocks = []
    for l in lines:
        best = None
        for b in reversed(blocks[-8:]):
            p = b["lines"][-1]
            gap = l["y"] - (p["y"] + p["h"])
            ratio = max(l["h"], p["h"]) / max(1, min(l["h"], p["h"]))
            ov = min(l["x"] + l["w"], p["x"] + p["w"]) - max(l["x"], p["x"])
            if -0.35 * p["h"] <= gap <= 0.95 * p["h"] and ratio < 1.16 and ov > 0.45 * min(l["w"], p["w"]) and p["w"] > 0.55 * max(b["W"], 1):
                best = b
                break
        if best is None:
            blocks.append({"lines": [l], "W": l["w"]})
        else:
            best["lines"].append(l)
            best["W"] = max(best["W"], l["w"])
    out = []
    for b in blocks:
        L = b["lines"]
        x0, y0 = min(l["x"] for l in L), min(l["y"] for l in L)
        x1, y1 = max(l["x"] + l["w"] for l in L), max(l["y"] + l["h"] for l in L)
        text = "".join(l["t"] if not (i and re.search(r"[A-Za-z0-9]$", L[i-1]["t"]) and re.match(r"[A-Za-z0-9]", l["t"])) else " " + l["t"] for i, l in enumerate(L))
        lefts = [l["x"] for l in L]; mids = [l["x"] + l["w"] / 2 for l in L]
        center = (np.std(mids) < np.std(lefts) * 0.6) if len(L) > 1 else abs((x0 + x1) / 2 - W / 2) < W * 0.025
        out.append({"t": text, "x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0, "lh": float(np.median([l["h"] for l in L])), "n": len(L), "c": float(np.mean([l["c"] for l in L])), "center": bool(center), "boxes": [[l["x"], l["y"], l["w"], l["h"]] for l in L]})
    return out


def font(sz, bold):
    return ImageFont.truetype(FONT, int(sz), index=6 if bold else 2)


def wrap(d, s, f, maxw):
    lines, cur = [], ""
    for tok in re.findall(r"\S+\s*|\s+", s):
        if d.textlength((cur + tok).rstrip(), font=f) <= maxw:
            cur += tok
            continue
        if cur:
            lines.append(cur.rstrip()); cur = ""
        while d.textlength(tok.rstrip(), font=f) > maxw and len(tok) > 1:
            k = len(tok)
            while k > 1 and d.textlength(tok[:k], font=f) > maxw:
                k -= 1
            lines.append(tok[:k]); tok = tok[k:]
        cur = tok
    if cur.strip():
        lines.append(cur.rstrip())
    return lines


def apply(path, blocks, tr, out, quality=82):
    img = cv2.imread(path)
    if img is None:
        pil = Image.open(path).convert("RGB"); img = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
    H, W = img.shape[:2]
    todo = [b for b in blocks if tr.get(b["t"])]
    styles = []
    for b in todo:
        pad = max(2, int(b["lh"] * 0.12))
        x0, y0 = max(0, int(b["x"] - pad * 3)), max(0, int(b["y"] - pad * 3))
        x1, y1 = min(W, int(b["x"] + b["w"] + pad * 3)), min(H, int(b["y"] + b["h"] + pad * 3))
        crop = img[y0:y1, x0:x1].copy()
        mask_box = np.zeros(crop.shape[:2], np.uint8)
        for bx, by, bw, bh in b["boxes"]:
            cv2.rectangle(mask_box, (int(bx - pad - x0), int(by - pad - y0)), (int(bx + bw + pad - x0), int(by + bh + pad - y0)), 255, -1)
        ring = crop[mask_box == 0]
        if len(ring) < 20:
            ring = crop.reshape(-1, 3)
        bg = np.median(ring, axis=0)
        flat = float(np.mean(np.std(ring, axis=0)))
        diff = np.abs(crop.astype(int) - bg).sum(axis=2)
        inside = diff[mask_box > 0]
        th = max(45, np.percentile(inside, 70) * 0.55)
        tx = crop[(mask_box > 0) & (diff >= np.percentile(inside, 92))]
        color = np.median(tx, axis=0) if len(tx) else 255 - bg
        if flat < 7:
            crop[mask_box > 0] = bg
        else:
            m = ((diff > th) & (mask_box > 0)).astype(np.uint8) * 255
            m = cv2.dilate(m, np.ones((5, 5), np.uint8), iterations=1) & mask_box
            crop = cv2.inpaint(crop, m, 3, cv2.INPAINT_TELEA)
        img[y0:y1, x0:x1] = crop
        sw = float(np.count_nonzero(diff[mask_box > 0] > th)) / max(1, np.count_nonzero(mask_box))
        styles.append((b, tuple(int(v) for v in color[::-1]), sw > 0.30))
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    d = ImageDraw.Draw(pil)
    for b, color, bold in styles:
        s = tr[b["t"]]
        maxw = max(b["w"], 10)
        if b["n"] == 1 and b["center"]:
            maxw = min(W * 0.96, b["w"] * 1.12)
        elif b["n"] == 1:
            maxw = min(W - b["x"] - 4, b["w"] * 1.2)
        sz = min(b["lh"] * 0.86, b["h"]); best = None
        while sz >= max(9, b["lh"] * 0.42):
            f = font(sz, bold); L = wrap(d, s, f, maxw); lh = sz * 1.32
            if len(L) * lh <= b["h"] + b["lh"] * 0.35:
                best = (f, L, lh); break
            sz -= max(0.5, sz * 0.04)
        while best is None and sz >= 9:  # 줄바꿈으로 옆 글자를 덮지 않도록 더 줄인다
            f = font(sz, bold); L = wrap(d, s, f, maxw); lh = sz * 1.25
            if len(L) * lh <= b["h"] + b["lh"] * 0.35:
                best = (f, L, lh)
            sz -= 0.5
        if best is None:
            f = font(max(9, b["lh"] * 0.42), bold); L = wrap(d, s, f, maxw); best = (f, L, f.size * 1.22)
        f, L, lh = best
        total = len(L) * lh
        y = b["y"] + max(0, (b["h"] - total) / 2) if b["n"] == 1 or b["center"] else b["y"]
        for ln in L:
            w = d.textlength(ln, font=f)
            x = b["x"] + (b["w"] - w) / 2 if b["center"] else b["x"]
            d.text((max(1, x), y + (lh - f.size) / 2 - f.size * 0.08), ln, font=f, fill=color)
            y += lh
    pil.save(out, "JPEG", quality=quality, optimize=True, progressive=True)
    return len(todo)
