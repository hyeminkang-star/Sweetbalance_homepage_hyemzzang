# 신제품 아이디어 발굴 스킬 (sb-product-ideation)

PC에 저장한 리뷰 크롤링 파일·매출·트렌드 데이터를 근거로 신제품 콘셉트 후보를 뽑는 Claude 스킬입니다.
숫자 집계와 엑셀 작성은 파이썬 스크립트가, 콘셉트 발상은 Claude가 합니다.

## 설치 (Claude 데스크톱 / Cowork)

1. 이 폴더의 `sb-product-ideation.skill` 파일을 내려받습니다.
2. Claude 설정 → 기능(Capabilities) → 스킬에서 파일을 업로드합니다.
3. 데이터 폴더를 연결하고 "신제품 아이디어 뽑아줘"라고 말합니다.

## 데이터 폴더

```
내데이터/
  리뷰/      리뷰 크롤링 .xlsx/.csv
  매출/      제품별 매출·목표(·달성률)
  트렌드/    키워드, 검색량, 증감률, 출처 (선택)
  제품마스터.xlsx  제품명, 재료, 가격, kcal, 카테고리, 별칭 (선택)
```

`examples/sample_data/`에 형식 예시가 있습니다. **예시 파일의 내용은 테스트용으로 지어낸 가짜 데이터**입니다.

## 스크립트만 직접 돌리기

```bash
pip install pandas openpyxl
python scripts/analyze_data.py 내데이터 --out 내데이터/결과
# Claude가 내데이터/결과/concepts.json 작성 (형식: examples/concepts_example.json)
python scripts/build_excel.py 내데이터/결과/analysis.json 내데이터/결과/concepts.json
```

결과 엑셀 시트: 읽어주세요 / 콘셉트 후보(상품팀 검토 칸 포함) / 근거 리뷰 / 제품별 현황 / 속성 분석 / 트렌드

## 바꿀 수 있는 곳

- 컬럼명 인식: `scripts/analyze_data.py`의 `COLUMN_ALIASES`
- 맛·식감 등 속성 사전: 같은 파일의 `ATTRIBUTES`
- 점수 가중치: `scripts/build_excel.py`의 `WEIGHTS`
