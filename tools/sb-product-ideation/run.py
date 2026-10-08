"""명령어로 실행하기 (화면 없이).

예:
    python run.py --folder "C:/리뷰데이터"
    python run.py --review-link "https://docs.google.com/spreadsheets/d/..." --sales-link "https://..."
API 키는 환경변수 ANTHROPIC_API_KEY 또는 api_key.txt에서 읽습니다.
"""
import argparse
import os
import sys
from pathlib import Path

from ideation import ai
from ideation.pipeline import run

HERE = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser(description="스윗밸런스 신제품 아이디어 발굴")
    ap.add_argument("--folder", help="PC 데이터 폴더")
    ap.add_argument("--review-link", action="append", default=[], help="리뷰 구글 링크 (여러 번 가능)")
    ap.add_argument("--sales-link", action="append", default=[], help="매출 구글 링크")
    ap.add_argument("--trend-link", action="append", default=[], help="트렌드 구글 링크")
    ap.add_argument("--master-link", action="append", default=[], help="제품마스터 구글 링크")
    ap.add_argument("--out", default=str(HERE / "결과"), help="결과 저장 폴더")
    ap.add_argument("--category", help="이 카테고리만 분석 (예: 샐러드)")
    ap.add_argument("--n", type=int, default=50, help="콘셉트 후보 개수")
    ap.add_argument("--model", default=ai.DEFAULT_MODEL, choices=list(ai.MODEL_CHOICES))
    ap.add_argument("--no-web", action="store_true", help="웹 트렌드 검색 끄기")
    ap.add_argument("--max-reviews", type=int, default=1500)
    args = ap.parse_args()

    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key and (HERE / "api_key.txt").exists():
        key = (HERE / "api_key.txt").read_text(encoding="utf-8").strip()
    if not key:
        sys.exit("Claude API 키가 없습니다. 환경변수 ANTHROPIC_API_KEY를 설정하거나 api_key.txt에 넣어 주세요.")

    try:
        res = run(args.out, local_dir=args.folder,
                  google_links={"리뷰": args.review_link, "매출": args.sales_link, "트렌드": args.trend_link, "제품마스터": args.master_link},
                  api_key=key, model=args.model, category=args.category, n_concepts=args.n, web_trends=not args.no_web,
                  max_reviews=args.max_reviews)
    except Exception as e:  # noqa: BLE001
        sys.exit(f"[오류] {e}")
    print(f"\n엑셀: {res['excel']}\n보고서: {res['report']}")


if __name__ == "__main__":
    main()
