#!/usr/bin/env python3
"""Analyze and clean an iPhone/iCloud contacts export (.vcf).

Usage:
    python3 contacts_cleanup.py contacts.vcf              # report only
    python3 contacts_cleanup.py contacts.vcf -o clean.vcf  # write cleaned file

Cleaning (all on by default, each can be turned off):
    - merge duplicate contacts (same name, or sharing a phone/email)
    - strip embedded photos larger than --max-photo-kb (default 50)
    - trim notes longer than --max-note-chars (default 500)
"""
import argparse
import re
import sys
from collections import defaultdict


def unfold(text):
    return re.sub(r"\r?\n[ \t]", "", text)


def parse(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        text = unfold(f.read())
    cards = re.findall(r"BEGIN:VCARD\r?\n(.*?)END:VCARD", text, re.S | re.I)
    return [[l for l in c.splitlines() if l.strip()] for c in cards]


def prop(line):
    return line.split(":", 1)[0].split(";", 1)[0].upper()


def value(line):
    return line.split(":", 1)[1] if ":" in line else ""


def digits(s):
    d = re.sub(r"\D", "", s)
    return d[-10:] if len(d) >= 10 else d


def keys(card):
    ks = set()
    for l in card:
        p = prop(l)
        if p == "FN" and value(l).strip():
            ks.add("n:" + re.sub(r"\s+", " ", value(l).strip().lower()))
        elif p == "TEL" and len(digits(value(l))) >= 7:
            ks.add("t:" + digits(value(l)))
        elif p == "EMAIL" and value(l).strip():
            ks.add("e:" + value(l).strip().lower())
    return ks


def merge_duplicates(cards):
    parent = list(range(len(cards)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    seen = {}
    for i, c in enumerate(cards):
        for k in keys(c):
            if k in seen:
                parent[find(i)] = find(seen[k])
            else:
                seen[k] = i
    groups = defaultdict(list)
    for i in range(len(cards)):
        groups[find(i)].append(i)

    merged = []
    for idxs in groups.values():
        out, seen_lines = [], set()
        for i in idxs:
            for l in cards[i]:
                if prop(l) in ("VERSION", "UID", "PRODID", "REV"):
                    if prop(l) == "VERSION" and "VERSION" not in {prop(x) for x in out}:
                        out.append(l)
                    continue
                if prop(l) in ("FN", "N", "BDAY", "PHOTO") and prop(l) in {prop(x) for x in out}:
                    continue
                norm = (prop(l), re.sub(r"\D", "", value(l)) if prop(l) == "TEL" else value(l).strip().lower())
                if norm in seen_lines:
                    continue
                seen_lines.add(norm)
                out.append(l)
        merged.append(out)
    return merged


def photo_kb(card):
    return sum(len(l) for l in card if prop(l) == "PHOTO") * 3 / 4 / 1024


def note_len(card):
    return sum(len(value(l)) for l in card if prop(l) == "NOTE")


def report(cards):
    print(f"Contacts: {len(cards)}")
    photos = [(photo_kb(c), c) for c in cards if photo_kb(c) > 0]
    print(f"With photos: {len(photos)}  (total {sum(p for p, _ in photos) / 1024:.1f} MB)")
    dupes = len(cards) - len(merge_duplicates(cards))
    print(f"Duplicates that would merge away: {dupes}")

    def name(c):
        return next((value(l) for l in c if prop(l) == "FN"), "(no name)")

    print("\nLargest photos:")
    for kb, c in sorted(photos, key=lambda x: -x[0])[:10]:
        print(f"  {kb:8.0f} KB  {name(c)}")
    print("\nLongest notes:")
    for n, c in sorted(((note_len(c), c) for c in cards), key=lambda x: -x[0])[:10]:
        if n:
            print(f"  {n:8d} chars  {name(c)}")


def clean(cards, merge, max_photo_kb, max_note):
    if merge:
        cards = merge_duplicates(cards)
    out = []
    for c in cards:
        new = []
        for l in c:
            if prop(l) == "PHOTO" and len(l) * 3 / 4 / 1024 > max_photo_kb:
                continue
            if prop(l) == "NOTE" and len(value(l)) > max_note:
                head = l.split(":", 1)[0]
                l = head + ":" + value(l)[:max_note]
            new.append(l)
        out.append(new)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("vcf")
    ap.add_argument("-o", "--output")
    ap.add_argument("--no-merge", action="store_true")
    ap.add_argument("--max-photo-kb", type=int, default=50)
    ap.add_argument("--max-note-chars", type=int, default=500)
    a = ap.parse_args()

    cards = parse(a.vcf)
    if not cards:
        sys.exit("No contacts found in file.")
    report(cards)
    if a.output:
        cleaned = clean(cards, not a.no_merge, a.max_photo_kb, a.max_note_chars)
        with open(a.output, "w", encoding="utf-8", newline="") as f:
            for c in cleaned:
                f.write("BEGIN:VCARD\r\n" + "\r\n".join(c) + "\r\nEND:VCARD\r\n")
        print(f"\nWrote {len(cleaned)} contacts to {a.output}")


if __name__ == "__main__":
    main()
