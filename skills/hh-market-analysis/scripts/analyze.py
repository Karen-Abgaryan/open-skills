#!/usr/bin/env python3
"""Statistics and L2 integrity checks over one or more hh.ru harvest exports.

Input: JSON files produced by ``window.__hh.harvest`` — objects shaped
``{"meta": {...}, "rows": [...]}``. Several files are merged and deduplicated by
hash, which is how a synonym union (skill A OR skill B OR ...) is assembled,
since the server only ever intersects.

Output: a markdown block covering sample integrity, salary cohorts, percentiles,
optional classification, and a spot-check table of resume links.

    python3 analyze.py dwh.json etl.json --classify grade --spot-check 10
    python3 analyze.py msu.json --rules rules_msu.py --dimension faculty --cards cards.json

Dimensions beyond grade come from a rules module rather than from edits to this
file. The module declares ``DIMENSIONS = {name: [(pattern, label), ...]}``, tried
top to bottom so specific rules must precede general ones, and optionally
``SOURCES`` (which text a dimension reads), ``MISSING`` and ``UNMATCHED`` (its
own labels for an empty and an unrecognised value). A missing value always keeps
its own label instead of being folded into "other".
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

# Cleaning bounds. Expectations of 10 RUB occur; so do placeholder millions.
DEFAULT_MIN = 15_000
DEFAULT_MAX = 2_000_000

# Percentiles are meaningless on a handful of values; below this the skill
# reports raw numbers instead of a median.
PERCENTILE_GATE = 50

SENIOR = re.compile(
    r"(?<![A-Za-zА-Яа-яЁё])(?:senior|sr\.|старш|ведущ|главн|lead|тимлид|team\s+lead|principal)",
    re.IGNORECASE,
)
# Kept apart from the senior markers on purpose: an architect is a separate
# career branch rather than a grade, and folding it in inflates the senior band.
ARCHITECT = re.compile(r"(?<![A-Za-zА-Яа-яЁё])(?:архитектор|architect)", re.IGNORECASE)
JUNIOR = re.compile(
    r"(?<![A-Za-zА-Яа-яЁё])(?:junior|jr\.|младш|стажер|стажёр|intern|trainee)",
    re.IGNORECASE,
)


def percentile(values: list[float], p: float) -> float | None:
    """Linear-interpolation percentile on a sorted copy. p in 0..100."""
    if not values:
        return None
    s = sorted(values)
    if len(s) == 1:
        return float(s[0])
    k = (len(s) - 1) * (p / 100.0)
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return float(s[lo] + (s[hi] - s[lo]) * (k - lo))


def summarize(values: list[float]) -> dict:
    return {
        "n": len(values),
        "p25": percentile(values, 25),
        "median": percentile(values, 50),
        "p75": percentile(values, 75),
        "p90": percentile(values, 90),
    }


def load(paths: list[Path]) -> tuple[list[dict], list[dict], dict]:
    """Merge exports, dedup by hash, and count the overlap between sources."""
    metas, by_hash, hits = [], {}, Counter()
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        # browser_evaluate --filename writes the returned string as JSON, so a
        # harvest saved that way arrives wrapped in a second layer of encoding.
        if isinstance(payload, str):
            payload = json.loads(payload)
        meta = payload.get("meta", {}) if isinstance(payload, dict) else {}
        rows = payload.get("rows", payload) if isinstance(payload, dict) else payload
        meta = dict(meta)
        meta["source"] = path.name
        meta["rowsInFile"] = len(rows)
        metas.append(meta)
        for row in rows:
            h = row.get("hash")
            if not h:
                continue
            hits[h] += 1
            by_hash.setdefault(h, row)
    overlap = sum(1 for c in hits.values() if c > 1)
    return list(by_hash.values()), metas, {"overlappingHashes": overlap}


def load_cards(paths: list[Path], rows: list[dict]) -> dict:
    """Attach card exports (``window.__hh.harvestCards``) to rows by hash.

    Cards are capped at 500 views a day, so a run normally covers a fraction of
    the sample. Rows without one keep an explicit "not opened" label rather than
    dropping out of the denominator."""
    cards: dict[str, dict] = {}
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, str):
            payload = json.loads(payload)
        items = payload.get("cards", payload.get("results", payload)) \
            if isinstance(payload, dict) else payload
        for card in items:
            h = card.get("hash")
            if h:
                cards[h] = card
    attached = 0
    for row in rows:
        card = cards.get(row.get("hash"))
        if card:
            row["card"] = card
            attached += 1
    return {"cardsLoaded": len(cards), "attached": attached, "rows": len(rows)}


def split_cohorts(rows: list[dict]) -> dict[str, list[dict]]:
    """Stated / predicted-only / nothing. These three must never be pooled:
    hh's estimate runs about 0.68 of what candidates ask for."""
    stated, predicted_only, none = [], [], []
    for row in rows:
        if (row.get("salary") or {}).get("amount") is not None:
            stated.append(row)
        elif (row.get("predictedSalary") or {}).get("amount") is not None:
            predicted_only.append(row)
        else:
            none.append(row)
    return {"stated": stated, "predicted_only": predicted_only, "none": none}


def extract_amounts(rows: list[dict], field: str, currency: str,
                    lo: float, hi: float) -> tuple[list[float], dict]:
    """Pull one salary field, keeping only the requested currency and dropping
    out-of-range values. Everything discarded is counted, not hidden."""
    kept, dropped_currency, dropped_range = [], Counter(), []
    for row in rows:
        money = row.get(field) or {}
        amount, cur = money.get("amount"), money.get("currency")
        if amount is None:
            continue
        if cur != currency:
            dropped_currency[cur] += 1
            continue
        if amount < lo or amount > hi:
            dropped_range.append(amount)
            continue
        kept.append(float(amount))
    return kept, {
        "droppedOtherCurrency": sum(dropped_currency.values()),
        "otherCurrencies": dict(dropped_currency),
        "droppedOutOfRange": len(dropped_range),
        "outOfRangeValues": sorted(dropped_range)[:10],
    }


def classify_grade(row: dict) -> str:
    current = " ".join(filter(None, [
        row.get("title") or "",
        (row.get("positions") or [{}])[0].get("position") or "",
    ]))
    past = " ".join(
        p.get("position") or "" for p in (row.get("positions") or [])[1:]
    )
    if ARCHITECT.search(current):
        return "architect_current"
    if SENIOR.search(current):
        return "senior_current"
    if SENIOR.search(past) or ARCHITECT.search(past):
        return "senior_past_only"
    if JUNIOR.search(current):
        return "junior"
    return "no_marker"


# ------------------------------------------------------- custom dimensions --

NO_CARD = "Карточка не вскрыта"
DEFAULT_MISSING = "Значение не указано"
DEFAULT_UNMATCHED = "Не классифицировано"

# Text a dimension is matched against. Card sources exist only for resumes whose
# card was opened, which is what forces the two-denominator reporting below.
CARD_SOURCES = {"faculty", "specialty", "university"}


def source_text(row: dict, source: str) -> str:
    positions = row.get("positions") or []
    card = row.get("card") or {}
    education = card.get("education") or []
    if source == "title":
        return row.get("title") or ""
    if source == "current_position":
        return (positions[0].get("position") or "") if positions else ""
    if source == "positions":
        return " ".join(p.get("position") or "" for p in positions)
    if source == "companies":
        return " ".join(p.get("company") or "" for p in positions)
    if source == "skills":
        return " ".join(row.get("keySkills") or [])
    if source == "area":
        return row.get("areaName") or ""
    if source == "faculty":
        return " ".join(e.get("organization") or "" for e in education)
    if source == "specialty":
        return " ".join(e.get("result") or "" for e in education)
    if source == "university":
        return " ".join(e.get("name") or "" for e in education)
    if source == "title_and_position":
        head = row.get("title") or ""
        return f"{head} {positions[0].get('position') or ''}" if positions else head
    raise SystemExit(f"unknown source '{source}' — see SOURCE keys in analyze.py")


def load_rules(path: Path):
    """Import a rules module by path. Only DIMENSIONS is required."""
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot import rules module {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    dims = getattr(module, "DIMENSIONS", None)
    if not isinstance(dims, dict) or not dims:
        raise SystemExit(f"{path} defines no DIMENSIONS = {{name: [(pattern, label), ...]}}")
    compiled = {
        name: [(re.compile(pat, re.IGNORECASE), label) for pat, label in rules]
        for name, rules in dims.items()
    }
    return {
        "dimensions": compiled,
        "sources": getattr(module, "SOURCES", {}),
        "missing": getattr(module, "MISSING", {}),
        "unmatched": getattr(module, "UNMATCHED", {}),
        "name": path.name,
    }


def classify_dimension(row: dict, dim: str, rules: dict) -> tuple[str, str | None]:
    """Label plus the pattern that produced it — the attribution is what makes a
    general rule stealing from a specific one visible in the spot-check table."""
    source = rules["sources"].get(dim, dim if dim in CARD_SOURCES else "title_and_position")
    if source in CARD_SOURCES and not row.get("card"):
        return NO_CARD, None
    text = source_text(row, source).strip()
    if not text:
        return rules["missing"].get(dim, DEFAULT_MISSING), None
    for pattern, label in rules["dimensions"][dim]:
        if pattern.search(text):
            return label, pattern.pattern
    return rules["unmatched"].get(dim, DEFAULT_UNMATCHED), None


def dimension_block(rows: list[dict], dim: str, rules: dict, currency: str,
                    lo: float, hi: float) -> list[str]:
    source = rules["sources"].get(dim, dim if dim in CARD_SOURCES else "title_and_position")
    card_based = source in CARD_SOURCES
    opened = sum(1 for r in rows if r.get("card"))
    total = len(rows)

    groups: dict[str, list[dict]] = {}
    for row in rows:
        label, _ = classify_dimension(row, dim, rules)
        groups.setdefault(label, []).append(row)

    out = [f"## Измерение «{dim}»", "",
           f"Разметка выгрузки по правилам `{rules['name']}`, источник — `{source}`. "
           "Серверного фильтра для этого признака нет.", ""]
    if card_based:
        share = 100 * opened / total if total else 0
        out += [f"Признак живёт только в карточке, вскрыто {opened} из {total} ({share:.1f}%). "
                "Доли приводятся дважды: от всей выборки и от вскрытой части — одна без "
                "другой читается как утверждение о пуле.", "",
                "| Значение | n | % выборки | % вскрытых | n с ЗП | p25 | Медиана | p75 |",
                "|---|---|---|---|---|---|---|---|"]
    else:
        out += ["| Значение | n | % выборки | n с ЗП | p25 | Медиана | p75 |",
                "|---|---|---|---|---|---|---|"]

    for label, group in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        vals, _ = extract_amounts(group, "salary", currency, lo, hi)
        s = summarize(vals)
        # The project's publication rule: percentiles from 50 values, a bare
        # median from 10, nothing below that.
        if s["n"] >= PERCENTILE_GATE:
            cells = (f"{s['p25']:,.0f} | {s['median']:,.0f} | {s['p75']:,.0f}").replace(",", " ")
        elif s["n"] >= 10:
            cells = ("— | " + f"{s['median']:,.0f}".replace(",", " ") + " | —")
        else:
            cells = "— | — | —"
        pct = f"{100 * len(group) / total:.1f}" if total else "—"
        if card_based:
            of_opened = "—" if label == NO_CARD else (
                f"{100 * len(group) / opened:.1f}" if opened else "—")
            out.append(f"| {label} | {len(group)} | {pct} | {of_opened} | {s['n']} | {cells} |")
        else:
            out.append(f"| {label} | {len(group)} | {pct} | {s['n']} | {cells} |")

    out += ["", "Перцентили — от 50 значений с зарплатой, одна медиана — от 10, ниже — "
            "прочерк. Отсутствие значения остаётся отдельной категорией и в знаменателе.", ""]
    return out


def integrity(rows: list[dict], metas: list[dict], merge: dict) -> list[str]:
    """L2: everything checkable from data already collected — no extra requests."""
    out = ["## L2 — целостность выборки", ""]
    out.append("| Источник | totalResults | Страниц | Сырых строк | Дублей в файле | Уникальных |")
    out.append("|---|---|---|---|---|---|")
    for m in metas:
        out.append(
            f"| {m.get('tag') or m.get('source')} | {m.get('totalResults')} | "
            f"{m.get('pagesFetched')}/{m.get('pagesRequested')} | {m.get('rawRows')} | "
            f"{m.get('duplicates')} | {m.get('uniqueRows')} |"
        )
    out.append("")

    unique = len(rows)
    out.append(f"- Уникальных резюме после слияния: **{unique}** "
               f"(пересечение источников: {merge['overlappingHashes']})")

    flags = []
    for m in metas:
        total, fetched, requested = m.get("totalResults"), m.get("pagesFetched"), m.get("pagesRequested")
        if m.get("capHit"):
            flags.append(f"**{m.get('source')}: totalResults={total} превышает потолок "
                         f"max_search_result — хвост выборки недостижим, перцентили описывают "
                         f"только доступную часть. Нужна нарезка по зарплате.**")
        if fetched is not None and requested is not None and fetched < requested:
            flags.append(f"**{m.get('source')}: собрано {fetched} из {requested} страниц "
                         f"— причина: {m.get('stoppedReason')}**")
        if m.get("droppedParams"):
            names = ", ".join(d["param"] for d in m["droppedParams"])
            flags.append(f"**{m.get('source')}: параметры молча отброшены бэкендом: {names} (L0)**")
        if total is not None and fetched is not None:
            coverage = min(total, fetched * 100)
            if total > 0:
                flags.append(f"{m.get('source')}: покрытие популяции ≈ "
                             f"{100 * coverage / total:.1f}% ({coverage} из {total})")

    perm = Counter(r.get("permission") for r in rows)
    if set(perm) - {"view_without_contacts"}:
        flags.append(f"Уровни доступа в выборке: {dict(perm)}")

    missing_hash = sum(1 for r in rows if not r.get("hash"))
    if missing_hash:
        flags.append(f"**Записей без hash (не дедуплицируются): {missing_hash}**")

    out.extend(f"- {f}" for f in flags)
    out.append("")
    return out


def spot_check_table(rows: list[dict], n: int, seed: int | None,
                     rules: dict | None = None, dims: list[str] | None = None) -> list[str]:
    """Random resume links with the parsed values beside them, so the operator
    can open a few and confirm the parse matches what the page shows."""
    rng = random.Random(seed)
    sample = rng.sample(rows, min(n, len(rows)))
    dims = dims or []
    out = [
        "## Точечная проверка — открыть и сверить вручную", "",
        f"Случайные {len(sample)} из {len(rows)} записей. Рядом с каждой ссылкой — значения, "
        "которые из неё разобрал сбор. Открыть карточку, сверить заявленную зарплату, "
        "должность и регион. Расхождение означает ошибку разбора, а не шум данных.", "",
    ]
    head = "| # | Ссылка | Должность | Заявлено | Оценка hh | Регион | Стаж, мес | Статус поиска |"
    rule = "|---|---|---|---|---|---|---|---|"
    if rules and dims:
        out += ["Столбцы разметки показывают и метку, и сработавшее правило: если частное "
                "правило перехвачено общим, это видно здесь и больше нигде.", ""]
        for d in dims:
            head += f" {d} |"
            rule += "---|"
    out += [head, rule]

    def show(money: dict) -> str:
        if not money or money.get("amount") is None:
            return "—"
        return f"{money['amount']} {money.get('currency') or ''}".strip()

    for i, r in enumerate(sample, 1):
        line = (
            f"| {i} | {r.get('url')} | {r.get('title') or '—'} | "
            f"{show(r.get('salary'))} | "
            f"{show(r.get('predictedSalary'))} | "
            f"{r.get('areaName') or '—'} | {r.get('totalExperienceMonths') if r.get('totalExperienceMonths') is not None else '—'} | "
            f"{r.get('jobSearchStatus') or '—'} |"
        )
        for d in dims if rules else []:
            label, pattern = classify_dimension(r, d, rules)
            line += f" {label}{f' ← `{pattern}`' if pattern else ''} |"
        out.append(line)
    out.append("")
    return out


def stats_block(title: str, values: list[float], note: str = "") -> list[str]:
    s = summarize(values)
    out = [f"**{title}** — n = {s['n']}"]
    if note:
        out.append(f"  {note}")
    if s["n"] == 0:
        out.append("  Нет значений.")
    elif s["n"] < 10:
        out.append(f"  Ниже 10 значений — перцентили не считаются. Сырые значения: "
                   f"{', '.join(f'{v:,.0f}'.replace(',', ' ') for v in sorted(values))}")
    elif s["n"] < PERCENTILE_GATE:
        out.append(f"  n < {PERCENTILE_GATE}: перцентили ориентировочные, публиковать с оговоркой. "
                   f"p25 {s['p25']:,.0f} · медиана {s['median']:,.0f} · p75 {s['p75']:,.0f}"
                   .replace(",", " "))
    else:
        out.append(f"  p25 {s['p25']:,.0f} · **медиана {s['median']:,.0f}** · "
                   f"p75 {s['p75']:,.0f} · p90 {s['p90']:,.0f}".replace(",", " "))
    out.append("")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path, help="harvest JSON exports")
    ap.add_argument("--currency", default="RUR")
    ap.add_argument("--min", dest="lo", type=float, default=DEFAULT_MIN)
    ap.add_argument("--max", dest="hi", type=float, default=DEFAULT_MAX)
    ap.add_argument("--classify", choices=["grade"], help="classify the export by job titles")
    ap.add_argument("--rules", type=Path, help="python module declaring DIMENSIONS")
    ap.add_argument("--dimension", action="append", default=[],
                    help="dimension from --rules to report; repeatable, default all")
    ap.add_argument("--cards", type=Path, action="append", default=[],
                    help="card export from harvestCards, joined by hash; repeatable")
    ap.add_argument("--spot-check", type=int, default=10, help="rows to list for manual checking")
    ap.add_argument("--seed", type=int, default=None, help="fix the spot-check sample")
    ap.add_argument("--out", type=Path, help="write markdown here instead of stdout")
    args = ap.parse_args(argv)

    rows, metas, merge = load(args.files)
    if not rows:
        print("No rows found in the given files.", file=sys.stderr)
        return 1

    rules = load_rules(args.rules) if args.rules else None
    dims: list[str] = []
    if rules:
        dims = args.dimension or list(rules["dimensions"])
        unknown = [d for d in dims if d not in rules["dimensions"]]
        if unknown:
            raise SystemExit(f"--dimension {', '.join(unknown)} not in {args.rules}: "
                             f"declared are {', '.join(rules['dimensions'])}")
    elif args.dimension:
        raise SystemExit("--dimension needs --rules")

    cards_meta = load_cards(args.cards, rows) if args.cards else None

    doc: list[str] = ["# Анализ выгрузки hh.ru", ""]
    doc += integrity(rows, metas, merge)
    if cards_meta:
        doc += [f"- Карточек прикреплено к выборке: **{cards_meta['attached']}** из "
                f"{cards_meta['rows']} записей (в файлах карточек — {cards_meta['cardsLoaded']}). "
                "Разрезы по карточным признакам опираются на эту подвыборку.", ""]

    cohorts = split_cohorts(rows)
    total = len(rows)
    doc += ["## Зарплатные когорты", "",
            "| Когорта | Кол-во | Доля |", "|---|---|---|"]
    for key, label in [("stated", "Заявлено соискателем"),
                       ("predicted_only", "Только оценка hh"),
                       ("none", "Нет данных")]:
        n = len(cohorts[key])
        doc.append(f"| {label} | {n} | {100 * n / total:.1f}% |")
    doc += ["", f"Доля без зарплатных данных — {100 * len(cohorts['none']) / total:.1f}% — "
            "это факт о рынке, а не дефект выборки. Указывать в отчёте.", ""]

    stated_vals, stated_drop = extract_amounts(cohorts["stated"], "salary",
                                               args.currency, args.lo, args.hi)
    pred_vals, pred_drop = extract_amounts(rows, "predictedSalary",
                                           args.currency, args.lo, args.hi)

    doc += ["## Зарплаты", ""]
    doc += stats_block(f"Заявлено соискателем ({args.currency})", stated_vals)
    doc += stats_block(f"Оценка hh, predictedSalary ({args.currency})", pred_vals,
                        note="Отдельный справочный показатель. Не подставлять вместо пропуска — "
                             "отношение к заявленному около 0.68.")

    span = f"{args.lo:,.0f}–{args.hi:,.0f}".replace(",", " ")
    doc += ["**Очистка**", "",
            f"- Отброшено вне диапазона {span}: "
            f"{stated_drop['droppedOutOfRange']} заявленных, "
            f"{pred_drop['droppedOutOfRange']} оценок"]
    if stated_drop["outOfRangeValues"]:
        doc.append(f"- Примеры отброшенных значений: {stated_drop['outOfRangeValues']}")
    doc += [f"- Отброшено в иной валюте: {stated_drop['droppedOtherCurrency']} "
            f"{stated_drop['otherCurrencies'] or ''}", ""]

    if args.classify == "grade":
        labels = {
            "senior_current": "Маркер грейда в текущей должности",
            "senior_past_only": "Маркер только в прошлых должностях",
            "architect_current": "Архитектор (отдельная ветка, не грейд)",
            "junior": "Junior-маркер",
            "no_marker": "Без маркера",
        }
        groups: dict[str, list[dict]] = {k: [] for k in labels}
        for row in rows:
            groups[classify_grade(row)].append(row)
        doc += ["## Грейд по названиям должностей", "",
                "Классификация выгрузки, а не серверный фильтр: фильтра по грейду нет, "
                "а `title` и `shortExperience[].position` лежат прямо в выдаче.", "",
                "| Класс | Кол-во | n с ЗП | p25 | Медиана | p75 |", "|---|---|---|---|---|---|"]
        for key, label in labels.items():
            group = groups[key]
            vals, _ = extract_amounts(group, "salary", args.currency, args.lo, args.hi)
            s = summarize(vals)
            if s["n"] >= 10:
                cells = (f"{s['p25']:,.0f} | {s['median']:,.0f} | {s['p75']:,.0f}").replace(",", " ")
            else:
                cells = "— | — | —"
            doc.append(f"| {label} | {len(group)} | {s['n']} | {cells} |")
        doc += ["", "Ниже 10 значений с зарплатой перцентили не приводятся. "
                "Немонотонный градиент между классами означает, что словарь маркеров шумит.", ""]

    for dim in dims:
        doc += dimension_block(rows, dim, rules, args.currency, args.lo, args.hi)

    if args.spot_check > 0:
        doc += spot_check_table(rows, args.spot_check, args.seed, rules, dims)

    text = "\n".join(doc)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out} ({len(rows)} unique rows)")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
