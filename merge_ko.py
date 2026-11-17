#!/usr/bin/env python3
"""i18n/batches/<name>.txt (idx\t원문) 와 <name>.ko.txt (idx\t번역) 를 짝지어 i18n/ko.json 에 합친다."""
import glob, json, os, sys
R = os.path.dirname(os.path.abspath(__file__))
kop = os.path.join(R, "i18n", "ko.json")
ko = json.load(open(kop, encoding="utf-8")) if os.path.exists(kop) else {}
added = 0
for kf in sorted(glob.glob(os.path.join(R, "i18n", "batches", "*.ko.txt"))):
    sf = kf.replace(".ko.txt", ".txt")
    src = {}
    for line in open(sf, encoding="utf-8"):
        i, s = line.rstrip("\n").split("\t", 1)
        src[i] = s
    for line in open(kf, encoding="utf-8"):
        if "\t" not in line:
            continue
        i, t = line.rstrip("\n").split("\t", 1)
        if i in src and t.strip():
            if ko.get(src[i]) != t.strip():
                added += 1
            ko[src[i]] = t.strip()
    missing = [i for i in src if src[i] not in ko]
    if missing:
        print(os.path.basename(kf), "누락", len(missing), missing[:10], file=sys.stderr)
json.dump(ko, open(kop, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
print("ko.json", len(ko), "변경", added)
