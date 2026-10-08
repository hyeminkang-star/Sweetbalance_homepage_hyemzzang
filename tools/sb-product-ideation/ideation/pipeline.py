"""데이터 불러오기 → 분석 → (웹 트렌드) → AI 콘셉트 생성 → 엑셀·보고서 저장까지 한 번에 실행한다."""
import json
from datetime import datetime
from pathlib import Path

from . import ai
from .analyze import analyze, summary_md
from .excel import DISCLAIMER, build_excel
from .google_fetch import GoogleFetchError, download

LINK_TYPES = ["리뷰", "매출", "트렌드", "제품마스터"]


def run(out_root, local_dir=None, google_links=None, api_key=None, model=ai.DEFAULT_MODEL, category=None,
        n_concepts=50, web_trends=True, max_reviews=1500, log=print):
    """google_links: {"리뷰": [링크, ...], "매출": [...], ...}
    돌려주는 값: {"out_dir", "excel", "report", "warnings", "concepts", "analysis"}"""
    links = {k: [l.strip() for l in v if l.strip()] for k, v in (google_links or {}).items()}
    if not local_dir and not any(links.values()):
        raise ValueError("PC 폴더 경로나 구글 링크를 하나 이상 넣어 주세요.")
    out_dir = Path(out_root) / datetime.now().strftime("%Y%m%d_%H%M%S")
    sources = []

    if local_dir:
        local_dir = Path(local_dir).expanduser()
        if not local_dir.is_dir():
            raise ValueError(f"PC 폴더를 찾을 수 없습니다: {local_dir}")
        sources.append(local_dir)

    out_dir.mkdir(parents=True, exist_ok=True)
    if any(links.values()):
        gdir = out_dir / "구글에서_받은_파일"
        for kind, items in links.items():
            for link in items:
                log(f"구글 파일 받는 중({kind}): {link}")
                try:
                    path = download(link, gdir / kind, label=kind)
                except GoogleFetchError as e:
                    raise GoogleFetchError(f"[{kind}] {link}\n{e}") from e
                log(f"  저장: {path.name}")
        sources.append(gdir)

    log("1/4 데이터 분석 중...")
    a = analyze(sources, out_dir, category=category, log=log)
    if not a["reviews"]:
        raise ValueError("리뷰를 한 건도 읽지 못했습니다. 위 '파일 인식 결과'에서 리뷰 파일의 본문 컬럼이 잡혔는지 확인해 주세요.")

    client = ai.make_client(api_key)
    if web_trends and not a["trends"]:
        log("2/4 트렌드 파일이 없어 웹 검색으로 트렌드를 찾는 중...")
        a["trends"] = ai.search_trends(client, model, category, log=log)
        for t in a["trends"]:
            t["review_mentions"] = sum(1 for r in a["reviews"] if t["keyword"] in r["text"])
        log(f"  트렌드 키워드 {len(a['trends'])}개 확보")
    else:
        log("2/4 트렌드: " + ("파일 데이터 사용" if a["trends"] else "웹 검색 끔(트렌드 없이 진행)"))

    log(f"3/4 AI가 콘셉트 후보 {n_concepts}개를 만드는 중... (몇 분 걸릴 수 있습니다)")
    md = summary_md(a)
    result = ai.generate_concepts(client, model, a, md, n_concepts=n_concepts, max_reviews=max_reviews, log=log)
    result["generated_at"] = datetime.now().strftime("%Y-%m-%d")
    result["notes"] = f"모델 {model}, 웹 트렌드 검색 {'사용' if any(t.get('from_web') for t in a['trends']) else '안 함'}"

    log("4/4 엑셀·보고서 저장 중...")
    (out_dir / "analysis.json").write_text(json.dumps(a, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (out_dir / "concepts.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    excel, warnings, concepts = build_excel(a, result, out_dir)
    report = out_dir / f"요약보고서_{datetime.now().strftime('%Y%m%d')}.md"
    report.write_text(report_md(a, result, concepts), encoding="utf-8")
    if warnings:
        log("근거 확인 필요(엑셀에서 빨간색으로 표시):\n" + "\n".join(warnings))
    log(f"완료: {out_dir}")
    return {"out_dir": out_dir, "excel": excel, "report": report, "warnings": warnings, "concepts": concepts, "analysis": a}


def report_md(a, result, concepts, top=5):
    rv = {r["id"]: r for r in a["reviews"]}
    prod = {p["product"]: p for p in a["products"]}
    o = a["overview"]
    rep = result.get("report", {})
    L = [f"# 신제품 콘셉트 후보 요약 ({result.get('generated_at', '')})", "", f"**{rep.get('headline', '')}**", "", f"> {DISCLAIMER}", "",
         "## 분석 데이터", "",
         f"- 리뷰 {o['review_count']:,}건, 제품 {o['product_count']}개, 기간 {' ~ '.join(o['review_period']) if o.get('review_period') else '날짜 정보 없음'}",
         f"- 매출 데이터 {'있음' if o['has_sales'] else '없음'}, 트렌드 {len(a['trends'])}개",
         f"- 파일: {', '.join(f['file'] for f in a['files'])}", "", "## 데이터에서 보인 것", ""]
    L += [f"{i}. {x}" for i, x in enumerate(rep.get("findings", []), 1)]
    L += ["", f"## 추천 TOP {top}", ""]
    for n, c in enumerate([c for c in concepts if c["_valid"]][:top], 1):
        L += [f"### {n}. {c['name']} (총점 {c['_total']})", "", f"{c['one_liner']}", "",
              f"- 타깃: {c['target']}", f"- 핵심 재료: {c['key_ingredients']} / 가격대: {c['price_range']}",
              f"- 발상 방식: {c['approach']} / 근거: {c['rationale']}"]
        ach = [f"{p} 달성률 {prod[p]['achievement_pct']}%" for p in c.get("related_products", [])
               if p in prod and prod[p].get("achievement_pct") is not None]
        if ach:
            L.append(f"- 관련 매출: {', '.join(ach)}")
        if c.get("trend_keywords"):
            L.append(f"- 트렌드: {', '.join(c['trend_keywords'])} ({c.get('trend_source') or '출처 없음'})")
        L.append(f"- 리스크: {c['risks']}")
        L.append("- 근거 리뷰:")
        for i in c["_valid"][:2]:
            r = rv[i]
            L.append(f"  - \"{r['text']}\" ({r['file']} {r['row']}행)")
        L.append("")
    L += ["## 다음 단계", ""] + [f"- {x}" for x in rep.get("next_steps", [])]
    if a["trends"]:
        L += ["", "## 트렌드 출처", ""] + [f"- {t['keyword']}: {', '.join(t.get('sources', []))}" for t in a["trends"]]
    return "\n".join(L) + "\n"
