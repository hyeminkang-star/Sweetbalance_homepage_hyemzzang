#!/usr/bin/env python3
"""리뷰·매출·트렌드 파일을 읽어 신제품 기획용 분석 결과(analysis.json, analysis_summary.md)를 만든다.

사용법:
    python analyze_data.py <데이터폴더> [--out <결과폴더>] [--category 샐러드]
"""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import pandas as pd

# 컬럼 이름 후보. 크롤링 파일의 컬럼명이 다르면 여기에 추가한다. (소문자·공백 제거 후 비교)
COLUMN_ALIASES = {
    "text": ["리뷰", "리뷰내용", "리뷰본문", "내용", "본문", "후기", "후기내용", "review", "content", "text", "comment", "코멘트"],
    "rating": ["평점", "별점", "점수", "rating", "score", "stars"],
    "product": ["제품명", "상품명", "제품", "상품", "품목", "품목명", "product", "productname", "item", "itemname", "메뉴", "메뉴명"],
    "date": ["작성일", "날짜", "일자", "등록일", "리뷰일", "date", "createdat", "작성일자"],
    "channel": ["채널", "판매처", "쇼핑몰", "몰", "플랫폼", "channel", "site", "store"],
    "category": ["카테고리", "분류", "category", "유형"],
    "revenue": ["매출", "매출액", "판매금액", "판매액", "revenue", "sales", "금액", "실적"],
    "quantity": ["판매량", "수량", "판매수량", "qty", "quantity", "units"],
    "target": ["목표", "목표매출", "목표액", "target", "goal"],
    "achievement": ["목표달성률", "달성률", "달성율", "achievement", "achievementrate"],
    "period": ["월", "기간", "년월", "month", "period", "yyyymm"],
    "keyword": ["키워드", "검색어", "keyword", "term", "트렌드"],
    "volume": ["검색량", "언급량", "검색수", "언급수", "volume", "count", "지수", "ratio", "검색지수"],
    "growth": ["증감률", "증가율", "성장률", "growth", "변화율", "전월대비"],
    "source": ["출처", "source", "url", "링크"],
    "ingredients": ["재료", "원재료", "주재료", "ingredients"],
    "price": ["가격", "판매가", "정가", "price"],
    "kcal": ["kcal", "칼로리", "열량"],
    "alias": ["별칭", "다른이름", "alias", "aliases"],
}

# 식품 리뷰 속성 사전: 속성 -> (긍정 표현, 부정 표현, 중립 키워드)
ATTRIBUTES = {
    "맛": (["맛있", "존맛", "꿀맛", "고소", "감칠", "담백", "상큼", "맛나"], ["맛없", "싱겁", "너무짜", "짜서", "짜요", "짜다", "느끼", "비리", "밍밍", "별로", "니맛"], ["맛", "소스", "드레싱", "간"]),
    "식감": (["아삭", "쫀득", "부드럽", "촉촉", "바삭", "탱글"], ["눅눅", "질기", "퍽퍽", "물러", "딱딱", "시들", "숨죽"], ["식감", "채소", "야채"]),
    "양·포만감": (["든든", "배부르", "양많", "푸짐", "포만감좋"], ["양적", "양이적", "부족", "배고프", "허기", "적어"], ["양", "포만감", "한끼"]),
    "가격": (["가성비", "저렴", "착한가격", "합리적"], ["비싸", "가격대비", "부담", "창렬"], ["가격", "할인", "쿠폰"]),
    "건강·다이어트": (["건강", "다이어트", "저칼로리", "저당", "고단백", "단백질", "칼로리낮", "살빠"], ["칼로리높", "달아", "너무달", "당이많"], ["칼로리", "kcal", "단백질", "당", "식단"]),
    "편의·배송": (["간편", "편하", "빠른배송", "새벽배송", "전자레인지", "먹기편"], ["배송늦", "파손", "샜", "새서", "터져", "녹아", "불편"], ["배송", "포장", "용기", "보관"]),
    "신선도·품질": (["신선해", "신선하", "싱싱", "깨끗", "품질좋"], ["상했", "시들", "이물질", "머리카락", "냄새", "유통기한"], ["신선도", "품질", "유통기한"]),
    "재료·구성": (["재료가", "구성좋", "토핑많", "듬뿍"], ["토핑적", "구성아쉽", "빈약", "재료가적"], ["닭가슴살", "연어", "두부", "계란", "아보카도", "단호박", "고구마", "퀴노아", "현미", "곤약", "버섯", "치즈", "토마토", "리코타", "새우", "소고기", "오리"]),
}

WISH_PATTERNS = [r"했으면", r"하면\s*좋", r"있으면\s*좋", r"좋겠", r"바랍니다", r"바래요", r"아쉬", r"나왔으면", r"출시", r"추가해", r"늘려", r"줄여", r"옵션", r"다른\s*맛", r"신메뉴"]
SITUATION_WORDS = ["출근", "아침", "점심", "저녁", "야식", "간식", "운동", "헬스", "다이어트", "식단", "회사", "사무실", "도시락", "캠핑", "아이", "부모님", "선물", "자취", "혼밥"]
STOPWORDS = set("그리고 그런데 하지만 너무 정말 진짜 좀 많이 조금 아주 그냥 이거 저거 그거 이번 다음 제품 상품 구매 주문 배송 먹었 먹어 먹고 있어요 있습니다 했어요 합니다 해요 같아요 입니다 이에요 예요 근데 그래서 또 더 잘 다 안 못 것 거 수 때 듯 등 및 저는 제가 저도 우리 저희 ㅎㅎ ㅋㅋ ㅠㅠ 요 네 는 은 이 가 을 를 에 의 도 로 으로 와 과".split())

REVIEW_HINTS = ["리뷰", "review", "후기"]
SALES_HINTS = ["매출", "판매", "sales", "실적"]
TREND_HINTS = ["트렌드", "trend", "검색", "키워드", "datalab"]
MASTER_HINTS = ["마스터", "master", "제품정보", "상품정보"]


def norm(s):
    return re.sub(r"[\s_\-\(\)\[\]/·.]", "", str(s)).lower()


def norm_product(s):
    s = re.sub(r"\(.*?\)|\[.*?\]", "", str(s))
    s = re.sub(r"\d+\s*(g|kg|ml|l|개|팩|입|ea|세트)\b", "", s, flags=re.I)
    return re.sub(r"[\s_\-/·.,]", "", s).lower()


def map_columns(df):
    mapping = {}
    cols = {c: norm(c) for c in df.columns}
    for field, aliases in COLUMN_ALIASES.items():
        al = [norm(a) for a in aliases]
        exact = [c for c, n in cols.items() if n in al]
        partial = [c for c, n in cols.items() if any(a in n for a in al if len(a) >= 2)]
        pick = exact or partial
        if pick:
            mapping[field] = pick[0]
    # 본문 컬럼을 못 찾으면 평균 글자 수가 가장 긴 문자열 컬럼을 고른다
    if "text" not in mapping:
        obj = [c for c in df.columns if df[c].dtype == object and c not in mapping.values()]
        if obj:
            best = max(obj, key=lambda c: df[c].astype(str).str.len().mean())
            if df[best].astype(str).str.len().mean() >= 15:
                mapping["text"] = best
    return mapping


def read_table(path):
    """엑셀은 시트별로, CSV는 인코딩을 바꿔 가며 읽는다. (sheet_name, DataFrame, header_row_offset) 목록."""
    out = []
    if path.suffix.lower() in (".xlsx", ".xlsm", ".xls"):
        sheets = pd.read_excel(path, sheet_name=None, dtype=object)
        for name, df in sheets.items():
            out.append((name, df))
    else:
        for enc in ("utf-8-sig", "cp949", "euc-kr", "utf-16"):
            try:
                out.append((None, pd.read_csv(path, dtype=object, encoding=enc)))
                break
            except (UnicodeDecodeError, UnicodeError):
                continue
            except pd.errors.ParserError:
                out.append((None, pd.read_csv(path, dtype=object, encoding=enc, sep=None, engine="python")))
                break
    return [(n, d.dropna(how="all")) for n, d in out if not d.dropna(how="all").empty]


def classify(path, mapping):
    p = norm(str(path))
    for hints, kind in ((REVIEW_HINTS, "review"), (SALES_HINTS, "sales"), (TREND_HINTS, "trend"), (MASTER_HINTS, "master")):
        if any(h in p for h in hints):
            return kind
    if "text" in mapping:
        return "review"
    if "keyword" in mapping:
        return "trend"
    if "revenue" in mapping or "achievement" in mapping:
        return "sales"
    if "product" in mapping and ("ingredients" in mapping or "price" in mapping):
        return "master"
    return None


def to_num(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip().replace(",", "").replace("원", "").replace("%", "")
    m = re.search(r"-?\d+(\.\d+)?", s)
    return float(m.group()) if m else None


def tokens(text):
    words = re.findall(r"[가-힣a-zA-Z]{2,}", text)
    out = []
    for w in words:
        w2 = re.sub(r"(이에요|예요|어요|아요|해요|네요|습니다|입니다|이고|이랑|에서|으로|하고|는데|지만|까지|부터|처럼|보다|이라|라서|은|는|이|가|을|를|에|의|도|로|와|과|요)$", "", w)
        if len(w2) >= 2 and w2 not in STOPWORDS:
            out.append(w2)
    return out


def find_attrs(text):
    t = re.sub(r"\s", "", text)
    hits = {}
    for attr, (pos, neg, neu) in ATTRIBUTES.items():
        p = any(k in t for k in pos)
        n = any(k in t for k in neg)
        if p or n or any(k in t for k in neu):
            hits[attr] = "neg" if n and not p else ("pos" if p and not n else ("mixed" if p and n else "neutral"))
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data_dir")
    ap.add_argument("--out", default=None)
    ap.add_argument("--category", default=None, help="제품명·카테고리에 이 단어가 들어간 것만 분석")
    ap.add_argument("--low-rating", type=float, default=3.0, help="이 점수 이하를 불만 리뷰로 본다")
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    out_dir = Path(args.out) if args.out else data_dir / "결과"
    out_dir.mkdir(parents=True, exist_ok=True)

    files = [p for p in sorted(data_dir.rglob("*")) if p.suffix.lower() in (".xlsx", ".xlsm", ".xls", ".csv")
             and not p.name.startswith(("~$", ".")) and out_dir not in p.parents]
    if not files:
        sys.exit(f"[오류] {data_dir} 안에 엑셀/CSV 파일이 없습니다.")

    reviews, sales_rows, trend_rows, master_rows = [], [], [], []
    file_log = []
    for path in files:
        try:
            tables = read_table(path)
        except Exception as e:  # noqa: BLE001
            file_log.append({"file": str(path.relative_to(data_dir)), "status": f"읽기 실패: {e}"})
            continue
        for sheet, df in tables:
            mapping = map_columns(df)
            kind = classify(path.relative_to(data_dir), mapping)
            label = str(path.relative_to(data_dir)) + (f" [{sheet}]" if sheet and len(tables) > 1 else "")
            file_log.append({"file": label, "kind": kind or "인식 못 함", "rows": len(df),
                             "columns": {k: str(v) for k, v in mapping.items()}, "all_columns": [str(c) for c in df.columns]})
            if kind == "review" and "text" in mapping:
                for idx, r in df.iterrows():
                    text = str(r[mapping["text"]]).strip()
                    if not text or text.lower() == "nan":
                        continue
                    reviews.append({
                        "file": label,
                        "row": int(idx) + 2,  # 엑셀 행 번호(헤더 1행 기준)
                        "product": str(r[mapping["product"]]).strip() if "product" in mapping and pd.notna(r[mapping["product"]]) else "",
                        "rating": to_num(r[mapping["rating"]]) if "rating" in mapping else None,
                        "date": str(r[mapping["date"]])[:10] if "date" in mapping and pd.notna(r[mapping["date"]]) else "",
                        "channel": str(r[mapping["channel"]]) if "channel" in mapping and pd.notna(r[mapping["channel"]]) else "",
                        "category": str(r[mapping["category"]]) if "category" in mapping and pd.notna(r[mapping["category"]]) else "",
                        "text": text,
                    })
            elif kind == "sales" and "product" in mapping:
                for _, r in df.iterrows():
                    if pd.isna(r[mapping["product"]]):
                        continue
                    sales_rows.append({f: (to_num(r[mapping[f]]) if f in ("revenue", "quantity", "target", "achievement") else str(r[mapping[f]]))
                                       for f in ("product", "revenue", "quantity", "target", "achievement", "period", "category") if f in mapping})
            elif kind == "trend" and "keyword" in mapping:
                for _, r in df.iterrows():
                    if pd.isna(r[mapping["keyword"]]):
                        continue
                    trend_rows.append({"keyword": str(r[mapping["keyword"]]).strip(),
                                       "volume": to_num(r[mapping["volume"]]) if "volume" in mapping else None,
                                       "growth": to_num(r[mapping["growth"]]) if "growth" in mapping else None,
                                       "period": str(r[mapping["period"]]) if "period" in mapping and pd.notna(r[mapping["period"]]) else "",
                                       "source": str(r[mapping["source"]]) if "source" in mapping and pd.notna(r[mapping["source"]]) else label})
            elif kind == "master" and "product" in mapping:
                for _, r in df.iterrows():
                    if pd.isna(r[mapping["product"]]):
                        continue
                    master_rows.append({f: str(r[mapping[f]]) for f in ("product", "category", "ingredients", "price", "kcal", "alias")
                                        if f in mapping and pd.notna(r[mapping[f]])})

    if not reviews:
        print("[경고] 리뷰를 한 건도 읽지 못했습니다. 아래 파일별 컬럼을 보고 COLUMN_ALIASES['text']를 고쳐 주세요.")

    # 제품명 정규화(별칭 포함)
    alias_map = {}
    for m in master_rows:
        alias_map[norm_product(m["product"])] = m["product"]
        for a in str(m.get("alias", "")).split(","):
            if a.strip():
                alias_map[norm_product(a)] = m["product"]

    def canon(name):
        return alias_map.get(norm_product(name), name) if name else ""

    master_by = {canon(m["product"]): m for m in master_rows}

    if args.category:
        c = args.category
        cat_of = {k: v.get("category", "") for k, v in master_by.items()}
        reviews = [r for r in reviews if c in r["product"] or c in r["category"] or c in cat_of.get(canon(r["product"]), "")]
        sales_rows = [s for s in sales_rows if c in s.get("product", "") or c in str(s.get("category", "")) or c in cat_of.get(canon(s["product"]), "")]

    for i, r in enumerate(reviews, 1):
        r["id"] = f"R{i:04d}"
        r["product"] = canon(r["product"])
        r["attrs"] = find_attrs(r["text"])

    # 매출 집계(같은 제품 여러 기간이면 합산, 달성률은 평균 또는 매출/목표로 재계산)
    sales = defaultdict(lambda: {"revenue": 0.0, "quantity": 0.0, "target": 0.0, "ach": [], "periods": set(), "has_rev": False})
    for s in sales_rows:
        p = canon(s["product"])
        d = sales[p]
        for f in ("revenue", "quantity", "target"):
            if s.get(f) is not None:
                d[f] += s[f]
                if f == "revenue":
                    d["has_rev"] = True
        if s.get("achievement") is not None:
            d["ach"].append(s["achievement"])
        if s.get("period"):
            d["periods"].add(s["period"])
    sales_out = {}
    for p, d in sales.items():
        ach = (d["revenue"] / d["target"] * 100) if d["target"] and d["has_rev"] else (sum(d["ach"]) / len(d["ach"]) if d["ach"] else None)
        if ach is not None and ach <= 3 and d["ach"] and not d["target"]:
            ach *= 100  # 0.95 같은 비율 표기
        sales_out[p] = {"revenue": d["revenue"] if d["has_rev"] else None, "quantity": d["quantity"] or None,
                        "target": d["target"] or None, "achievement_pct": round(ach, 1) if ach is not None else None,
                        "periods": sorted(d["periods"])}

    # 제품별 요약
    by_prod = defaultdict(list)
    for r in reviews:
        by_prod[r["product"] or "(제품명 없음)"].append(r)
    products = []
    for p in sorted(set(by_prod) | set(sales_out)):
        rs = by_prod.get(p, [])
        ratings = [r["rating"] for r in rs if r["rating"] is not None]
        attr_cnt = Counter()
        neg_cnt = Counter()
        for r in rs:
            for a, pol in r["attrs"].items():
                attr_cnt[a] += 1
                if pol == "neg":
                    neg_cnt[a] += 1
        products.append({
            "product": p, "review_count": len(rs),
            "avg_rating": round(sum(ratings) / len(ratings), 2) if ratings else None,
            "low_rating_count": sum(1 for x in ratings if x <= args.low_rating),
            **(sales_out.get(p) or {}),
            "top_attributes": attr_cnt.most_common(4), "top_negative_attributes": neg_cnt.most_common(3),
            "master": master_by.get(p, {}),
        })
    products.sort(key=lambda x: (x.get("achievement_pct") is None, -(x.get("achievement_pct") or 0), -x["review_count"]))

    # 속성별
    attributes = {}
    for a in ATTRIBUTES:
        rs = [r for r in reviews if a in r["attrs"]]
        pos = [r for r in rs if r["attrs"][a] == "pos"]
        neg = [r for r in rs if r["attrs"][a] == "neg"]
        attributes[a] = {"mentions": len(rs), "positive": len(pos), "negative": len(neg),
                         "positive_examples": [r["id"] for r in sorted(pos, key=lambda r: -len(r["text"]))[:8]],
                         "negative_examples": [r["id"] for r in sorted(neg, key=lambda r: -len(r["text"]))[:8]]}

    wish_re = re.compile("|".join(WISH_PATTERNS))
    wishes = [r["id"] for r in reviews if wish_re.search(r["text"])]
    complaints = [r["id"] for r in sorted((r for r in reviews if r["rating"] is not None and r["rating"] <= args.low_rating),
                                          key=lambda r: (r["rating"], -len(r["text"])))]
    situations = Counter()
    situation_ex = defaultdict(list)
    for r in reviews:
        for w in SITUATION_WORDS:
            if w in r["text"]:
                situations[w] += 1
                if len(situation_ex[w]) < 5:
                    situation_ex[w].append(r["id"])

    uni, bi = Counter(), Counter()
    for r in reviews:
        tk = tokens(r["text"])
        uni.update(set(tk))
        bi.update({f"{a} {b}" for a, b in zip(tk, tk[1:])})

    trend_agg = {}
    for t in trend_rows:
        k = t["keyword"]
        cur = trend_agg.setdefault(k, {"keyword": k, "volume": None, "growth": None, "periods": [], "sources": set()})
        if t["volume"] is not None:
            cur["volume"] = (cur["volume"] or 0) + t["volume"]
        if t["growth"] is not None:
            cur["growth"] = t["growth"]
        if t["period"]:
            cur["periods"].append(t["period"])
        cur["sources"].add(t["source"])
    trends = sorted(({**v, "sources": sorted(v["sources"]), "review_mentions": sum(1 for r in reviews if v["keyword"] in r["text"])}
                     for v in trend_agg.values()), key=lambda x: -(x["growth"] if x["growth"] is not None else (x["volume"] or 0)))

    dates = sorted(r["date"] for r in reviews if r["date"])
    analysis = {
        "generated_at": date.today().isoformat(),
        "data_dir": str(data_dir.resolve()),
        "category_filter": args.category,
        "files": file_log,
        "overview": {"review_count": len(reviews), "product_count": len(products),
                     "review_period": [dates[0], dates[-1]] if dates else None,
                     "avg_rating": round(sum(r["rating"] for r in reviews if r["rating"] is not None) / max(1, sum(1 for r in reviews if r["rating"] is not None)), 2) if any(r["rating"] is not None for r in reviews) else None,
                     "has_sales": bool(sales_out), "has_trends": bool(trends), "has_master": bool(master_rows)},
        "products": products,
        "attributes": attributes,
        "wishes": wishes,
        "complaints": complaints,
        "situations": [{"word": w, "count": c, "examples": situation_ex[w]} for w, c in situations.most_common()],
        "keywords": {"unigrams": uni.most_common(60), "bigrams": [b for b in bi.most_common(80) if b[1] >= 2][:40]},
        "trends": trends,
        "reviews": [{k: r[k] for k in ("id", "file", "row", "product", "rating", "date", "channel", "text")} for r in reviews],
    }
    (out_dir / "analysis.json").write_text(json.dumps(analysis, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (out_dir / "analysis_summary.md").write_text(summary_md(analysis), encoding="utf-8")

    print("=== 파일 인식 결과 ===")
    for f in file_log:
        print(f"- {f['file']}: {f.get('kind', f.get('status'))}, {f.get('rows', '-')}행, 인식 컬럼 {f.get('columns', {})}")
    o = analysis["overview"]
    print(f"\n리뷰 {o['review_count']}건 / 제품 {o['product_count']}개 / 매출 {'있음' if o['has_sales'] else '없음'} / 트렌드 {'있음' if o['has_trends'] else '없음'}")
    print(f"저장: {out_dir / 'analysis.json'}, {out_dir / 'analysis_summary.md'}")


def summary_md(a):
    rv = {r["id"]: r for r in a["reviews"]}

    def q(rid, n=120):
        r = rv[rid]
        t = r["text"] if len(r["text"]) <= n else r["text"][:n] + "…"
        star = f"★{r['rating']:g} " if r["rating"] is not None else ""
        return f"- `{rid}` {star}[{r['product'] or '-'}] \"{t}\" ({r['file']} {r['row']}행)"

    o = a["overview"]
    L = [f"# 데이터 분석 요약 ({a['generated_at']})", ""]
    L += [f"- 리뷰 {o['review_count']}건, 제품 {o['product_count']}개, 평균 평점 {o['avg_rating']}",
          f"- 리뷰 기간: {' ~ '.join(o['review_period']) if o['review_period'] else '날짜 정보 없음'}",
          f"- 매출 데이터 {'있음' if o['has_sales'] else '없음'}, 트렌드 {'있음' if o['has_trends'] else '없음 (웹 검색 보강 필요)'}, 제품마스터 {'있음' if o['has_master'] else '없음'}",
          f"- 카테고리 필터: {a['category_filter'] or '없음'}", "", "## 파일"]
    for f in a["files"]:
        L.append(f"- {f['file']}: {f.get('kind', f.get('status'))} ({f.get('rows', '-')}행) {f.get('columns', '')}")
    L += ["", "## 제품별 (목표달성률 순)", "", "| 제품 | 리뷰 | 평점 | 저평점 | 매출 | 달성률 | 자주 언급 | 부정 많은 속성 |", "|---|---|---|---|---|---|---|---|"]
    for p in a["products"][:40]:
        rev = f"{p['revenue']:,.0f}" if p.get("revenue") else "-"
        ach = f"{p['achievement_pct']}%" if p.get("achievement_pct") is not None else "-"
        L.append(f"| {p['product']} | {p['review_count']} | {p['avg_rating'] or '-'} | {p['low_rating_count']} | {rev} | {ach} | "
                 f"{', '.join(f'{k}({v})' for k, v in p['top_attributes'])} | {', '.join(f'{k}({v})' for k, v in p['top_negative_attributes'])} |")
    L += ["", "## 속성별 긍정/부정", ""]
    for k, v in sorted(a["attributes"].items(), key=lambda x: -x[1]["mentions"]):
        L.append(f"### {k}: 언급 {v['mentions']} / 긍정 {v['positive']} / 부정 {v['negative']}")
        L += [q(i) for i in v["negative_examples"][:3]] + [q(i) for i in v["positive_examples"][:2]]
    L += ["", f"## 바라는 점 리뷰 ({len(a['wishes'])}건, 상위 20)", ""] + [q(i) for i in a["wishes"][:20]]
    L += ["", f"## 불만 리뷰 ({len(a['complaints'])}건, 상위 15)", ""] + [q(i) for i in a["complaints"][:15]]
    L += ["", "## 먹는 상황", ""] + [f"- {s['word']}: {s['count']}건 (예: {', '.join(s['examples'][:3])})" for s in a["situations"][:12]]
    L += ["", "## 자주 나온 표현", "", "단어: " + ", ".join(f"{w}({c})" for w, c in a["keywords"]["unigrams"][:40]),
          "", "2어절: " + ", ".join(f"{w}({c})" for w, c in a["keywords"]["bigrams"][:25])]
    L += ["", "## 트렌드", ""]
    if a["trends"]:
        L += [f"- {t['keyword']}: 수치 {t['volume']}, 증감 {t['growth']}, 리뷰 언급 {t['review_mentions']}건, 출처 {', '.join(t['sources'])}" for t in a["trends"][:30]]
    else:
        L.append("- 트렌드 파일 없음. 웹 검색으로 보강하고 출처 링크를 남길 것.")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
