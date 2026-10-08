"""Claude API로 (1) 웹 트렌드 키워드를 찾고 (2) 신제품 콘셉트 후보와 요약 보고서를 만든다."""
import json
import re

import anthropic

DEFAULT_MODEL = "claude-opus-5-5"
MODEL_CHOICES = {
    "claude-opus-5-5": "Claude Opus 5.5 (권장, 품질 우선)",
    "claude-sonnet-5-5": "Claude Sonnet 5.5 (더 빠르고 저렴)",
}
# 안전 필터가 요청을 거절하면 서버가 대체 모델로 다시 실행한다
FALLBACK_BETA = "server-side-fallback-2026-07-01"

SYSTEM_PROMPT = """당신은 스윗밸런스(샐러드·저당·고단백 간편식 브랜드)의 상품기획 보조입니다.
고객 리뷰·매출·트렌드 데이터를 근거로 신제품 콘셉트 후보를 제안합니다.

반드시 지킬 것:
- 모든 콘셉트는 아래 제공된 리뷰 중 실제로 그 콘셉트를 뒷받침하는 리뷰 ID(R0001 형식)를 1개 이상 evidence_review_ids에 넣습니다. 목록에 없는 ID는 절대 쓰지 않습니다. 뒷받침하는 리뷰가 없으면 그 콘셉트는 만들지 않습니다.
- 트렌드 키워드는 제공된 트렌드 목록에 있는 것만 trend_keywords에 넣고, trend_source에는 그 키워드의 출처를 그대로 옮깁니다. 트렌드 근거가 없으면 trend_keywords는 빈 배열, trend_source는 빈 문자열, trend 점수는 1~2점입니다.
- related_products에는 제공된 제품 목록의 제품명을 그대로 씁니다.
- 숫자(매출, 달성률, 리뷰 수)는 제공된 데이터에 있는 값만 씁니다. 추측한 수치를 쓰지 않습니다.
- 발상 방식(approach)을 골고루 섞습니다: 잘 팔리는 제품 확장 / 불만 해결 / 바라는 점 실현 / 트렌드 결합 / 미충족 상황.
- 비슷한 콘셉트를 반복하지 말고 서로 구별되게 만듭니다.

점수(각 1~5 정수):
- need 고객니즈: 근거 리뷰가 많고 같은 요청이 반복되면 5, 리뷰 1건뿐이면 1
- sales 매출연관: 연결된 제품의 매출·목표달성률이 상위면 5, 매출 데이터와 연결 없으면 1
- trend 트렌드: 출처 있는 트렌드와 직접 연결되면 5, 근거 없으면 1
- differentiation 차별성: 현재 라인업에 비슷한 제품이 없으면 5, 거의 같으면 1
- feasibility OEM가능: 일반 OEM 공정(샐러드·도시락·랩 조립, 소스 배합)으로 바로 가능하면 5, 새 설비·특수 원료가 필요하면 1

보고서(report)는 팀장님께 공유할 요약입니다. findings는 데이터에서 보인 사실 3가지를 숫자와 함께 씁니다."""

SCORE_SCHEMA = {"type": "integer", "enum": [1, 2, 3, 4, 5]}
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "concepts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "category": {"type": "string"},
                    "one_liner": {"type": "string"},
                    "target": {"type": "string"},
                    "key_ingredients": {"type": "string"},
                    "price_range": {"type": "string"},
                    "approach": {"type": "string", "enum": ["잘 팔리는 제품 확장", "불만 해결", "바라는 점 실현", "트렌드 결합", "미충족 상황"]},
                    "rationale": {"type": "string"},
                    "evidence_review_ids": {"type": "array", "items": {"type": "string"}},
                    "related_products": {"type": "array", "items": {"type": "string"}},
                    "trend_keywords": {"type": "array", "items": {"type": "string"}},
                    "trend_source": {"type": "string"},
                    "risks": {"type": "string"},
                    "scores": {
                        "type": "object",
                        "properties": {k: SCORE_SCHEMA for k in ("need", "sales", "trend", "differentiation", "feasibility")},
                        "required": ["need", "sales", "trend", "differentiation", "feasibility"],
                        "additionalProperties": False,
                    },
                },
                "required": ["name", "category", "one_liner", "target", "key_ingredients", "price_range", "approach", "rationale",
                             "evidence_review_ids", "related_products", "trend_keywords", "trend_source", "risks", "scores"],
                "additionalProperties": False,
            },
        },
        "report": {
            "type": "object",
            "properties": {
                "headline": {"type": "string"},
                "findings": {"type": "array", "items": {"type": "string"}},
                "next_steps": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["headline", "findings", "next_steps"],
            "additionalProperties": False,
        },
    },
    "required": ["concepts", "report"],
    "additionalProperties": False,
}


class AIError(Exception):
    pass


def make_client(api_key=None):
    # api_key가 없으면 환경변수 ANTHROPIC_API_KEY를 쓴다
    return anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()


def _call(client, log, **kwargs):
    """스트리밍으로 호출하고 최종 메시지를 돌려준다. API 오류는 한국어 메시지로 바꾼다."""
    try:
        with client.beta.messages.stream(betas=[FALLBACK_BETA], fallbacks="default", **kwargs) as stream:
            msg = stream.get_final_message()
    except anthropic.AuthenticationError as e:
        raise AIError("API 키가 올바르지 않습니다. Claude Console(console.anthropic.com)에서 발급한 키인지 확인해 주세요.") from e
    except anthropic.PermissionDeniedError as e:
        raise AIError(f"이 API 키로는 해당 모델/기능을 쓸 수 없습니다: {e.message}") from e
    except anthropic.RateLimitError as e:
        raise AIError("요청 한도를 넘었습니다. 1~2분 뒤 다시 실행해 주세요.") from e
    except anthropic.BadRequestError as e:
        raise AIError(f"요청 오류: {e.message}") from e
    except anthropic.APIStatusError as e:
        raise AIError(f"Claude API 서버 오류({e.status_code}). 잠시 뒤 다시 실행해 주세요.") from e
    except anthropic.APIConnectionError as e:
        raise AIError("Claude API에 연결할 수 없습니다. 인터넷 연결을 확인해 주세요.") from e
    if msg.stop_reason == "refusal":
        raise AIError("Claude가 이 요청을 처리하지 않았습니다(안전 필터). 데이터에 민감한 내용이 있는지 확인해 주세요.")
    u = msg.usage
    log(f"  사용량: 입력 {u.input_tokens:,} 토큰 / 출력 {u.output_tokens:,} 토큰")
    return msg


def _text(msg):
    return "".join(b.text for b in msg.content if b.type == "text")


def search_trends(client, model, category=None, log=print):
    """웹 검색으로 최근 식품 트렌드 키워드를 찾는다. 실제 검색 결과에 있는 URL을 출처로 단 것만 남긴다."""
    topic = f"'{category}' 카테고리 중심의 " if category else ""
    prompt = (f"한국 간편식·샐러드·건강식 시장에서 최근 3개월 {topic}식품 트렌드 키워드를 웹 검색으로 5~10개 찾아 주세요. "
              "뉴스·업계 리포트 등 확인 가능한 출처가 있는 것만 고릅니다. 출처를 못 찾은 키워드는 넣지 않습니다.\n"
              "마지막에 아래 형식의 JSON 배열만 ```json 코드 블록으로 출력하세요.\n"
              '[{"keyword": "키워드", "why": "한 줄 근거", "source_url": "검색 결과의 실제 URL", "source_title": "기사/페이지 제목"}]')
    messages = [{"role": "user", "content": prompt}]
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 8, "user_location": {"type": "approximate", "country": "KR"}}]
    seen_urls = set()
    msg = None
    for _ in range(4):  # 검색이 길어지면 pause_turn으로 멈추므로 이어서 실행
        msg = _call(client, log, model=model, max_tokens=32000, thinking={"type": "adaptive"},
                    output_config={"effort": "medium"}, tools=tools, messages=messages)
        for b in msg.content:
            if b.type == "web_search_tool_result" and isinstance(b.content, list):
                seen_urls.update(r.url for r in b.content if getattr(r, "url", None))
        if msg.stop_reason != "pause_turn":
            break
        messages.append({"role": "assistant", "content": msg.content})
    text = _text(msg)
    m = re.search(r"```json\s*(\[.*?\])\s*```", text, re.S) or re.search(r"(\[\s*\{.*\}\s*\])", text, re.S)
    if not m:
        log("  트렌드 검색 결과를 읽지 못해 트렌드 없이 진행합니다.")
        return []
    try:
        items = json.loads(m.group(1))
    except json.JSONDecodeError:
        log("  트렌드 검색 결과 형식이 잘못돼 트렌드 없이 진행합니다.")
        return []
    kept = [t for t in items if t.get("keyword") and t.get("source_url") in seen_urls]
    dropped = len(items) - len(kept)
    if dropped:
        log(f"  검색 결과에서 확인되지 않은 출처 {dropped}건은 제외했습니다.")
    return [{"keyword": t["keyword"], "volume": None, "growth": None, "periods": [],
             "sources": [f"{t.get('source_title', '')} {t['source_url']}".strip()], "why": t.get("why", ""),
             "review_mentions": 0, "from_web": True} for t in kept]


def _pick_reviews(a, max_reviews):
    """AI에게 보낼 리뷰를 고른다: 바라는 점 → 불만 → 속성 대표 → 나머지(긴 글 우선)."""
    rv = {r["id"]: r for r in a["reviews"]}
    order = list(a["wishes"]) + list(a["complaints"])
    for v in a["attributes"].values():
        order += v["negative_examples"] + v["positive_examples"]
    for s in a["situations"]:
        order += s["examples"]
    order += [r["id"] for r in sorted(a["reviews"], key=lambda r: -len(r["text"]))]
    picked, seen = [], set()
    for i in order:
        if i not in seen and i in rv:
            seen.add(i)
            picked.append(rv[i])
        if len(picked) >= max_reviews:
            break
    return sorted(picked, key=lambda r: r["id"])


def generate_concepts(client, model, a, summary_md, n_concepts=50, max_reviews=1500, log=print):
    reviews = _pick_reviews(a, max_reviews)
    if len(reviews) < len(a["reviews"]):
        log(f"  리뷰 {len(a['reviews']):,}건 중 {len(reviews):,}건(요청·불만·대표 리뷰 우선)을 AI에게 전달합니다.")
    review_lines = "\n".join(
        "\t".join([r["id"], r["product"] or "-", "" if r["rating"] is None else f"{r['rating']:g}", r["text"][:500].replace("\n", " ")])
        for r in reviews)
    products = [{k: p.get(k) for k in ("product", "review_count", "avg_rating", "low_rating_count", "revenue", "achievement_pct",
                                       "top_attributes", "top_negative_attributes")} | {"master": p.get("master") or {}}
                for p in a["products"]]
    trends = [{"keyword": t["keyword"], "volume": t.get("volume"), "growth": t.get("growth"),
               "why": t.get("why", ""), "source": ", ".join(t.get("sources", []))} for t in a["trends"]]
    user = (f"# 분석 요약\n{summary_md}\n\n"
            f"# 제품 목록(JSON)\n{json.dumps(products, ensure_ascii=False, default=str)}\n\n"
            f"# 트렌드 목록(JSON)\n{json.dumps(trends, ensure_ascii=False) if trends else '없음'}\n\n"
            f"# 리뷰 (ID\\t제품\\t평점\\t본문)\n{review_lines}\n\n"
            f"# 요청\n위 데이터를 근거로 신제품 콘셉트 후보 {n_concepts}개와 요약 보고서를 만들어 주세요.")
    msg = _call(client, log, model=model, max_tokens=64000, thinking={"type": "adaptive"},
                output_config={"effort": "high", "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
                system=SYSTEM_PROMPT, messages=[{"role": "user", "content": user}])
    if msg.stop_reason == "max_tokens":
        raise AIError("결과가 너무 길어 중간에 잘렸습니다. 콘셉트 개수를 줄여서 다시 실행해 주세요.")
    try:
        return json.loads(_text(msg))
    except json.JSONDecodeError as e:
        raise AIError("AI 응답을 읽지 못했습니다. 다시 실행해 주세요.") from e
