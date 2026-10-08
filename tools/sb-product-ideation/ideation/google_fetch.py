"""구글 시트 / 구글 드라이브 파일 링크를 엑셀·CSV로 내려받는다.

'링크가 있는 모든 사용자'에게 보기 권한이 공유된 파일만 받을 수 있다(로그인 없이 받기 때문).
"""
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SHEET_RE = re.compile(r"docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)")
FILE_RE = re.compile(r"drive\.google\.com/file/d/([a-zA-Z0-9_-]+)")
OPEN_ID_RE = re.compile(r"[?&]id=([a-zA-Z0-9_-]+)")
FOLDER_RE = re.compile(r"drive\.google\.com/drive/(?:u/\d+/)?folders/")

SHARE_HELP = ("구글 파일을 열고 오른쪽 위 [공유] → 일반 액세스를 '링크가 있는 모든 사용자(뷰어)'로 바꾼 뒤 다시 시도해 주세요. "
              "회사 정책상 외부 공유가 막혀 있으면, 파일을 엑셀로 다운로드해서 PC 폴더에 넣어 주세요.")


class GoogleFetchError(Exception):
    pass


def export_url(link):
    """링크 종류를 보고 (다운로드 URL, 기본 확장자)를 돌려준다."""
    link = link.strip()
    if FOLDER_RE.search(link):
        raise GoogleFetchError("구글 드라이브 '폴더' 링크는 지원하지 않습니다. 폴더 안 파일의 링크를 각각 넣어 주세요.")
    m = SHEET_RE.search(link)
    if m:
        # 구글 시트: 모든 탭을 엑셀 하나로 받는다
        return f"https://docs.google.com/spreadsheets/d/{m.group(1)}/export?format=xlsx", ".xlsx"
    m = FILE_RE.search(link) or (OPEN_ID_RE.search(link) if "drive.google.com" in link else None)
    if m:
        # 드라이브에 올린 엑셀/CSV 파일
        return f"https://drive.google.com/uc?export=download&id={m.group(1)}", ".xlsx"
    raise GoogleFetchError(f"구글 시트나 구글 드라이브 파일 링크가 아닙니다: {link}")


def _filename_from_headers(headers):
    cd = headers.get("Content-Disposition", "") or ""
    m = re.search(r"filename\*=UTF-8''([^;]+)", cd)
    if m:
        return urllib.parse.unquote(m.group(1))
    m = re.search(r'filename="?([^";]+)"?', cd)
    return m.group(1) if m else None


def download(link, dest_dir, label=None, timeout=60):
    """링크를 dest_dir에 저장하고 저장된 경로를 돌려준다. label이 있으면 파일명 앞에 붙인다(예: '리뷰')."""
    url, default_ext = export_url(link)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (sb-product-ideation)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            ctype = resp.headers.get("Content-Type", "")
            name = _filename_from_headers(resp.headers)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 404):
            raise GoogleFetchError(f"파일을 열 수 없습니다(HTTP {e.code}). {SHARE_HELP}") from e
        raise GoogleFetchError(f"다운로드 실패(HTTP {e.code}): {link}") from e
    except urllib.error.URLError as e:
        raise GoogleFetchError(f"인터넷 연결을 확인해 주세요: {e.reason}") from e

    # 공유가 안 된 파일은 엑셀 대신 로그인 화면(HTML)이 온다
    if "text/html" in ctype or data[:15].lstrip().lower().startswith((b"<!doctype html", b"<html")):
        raise GoogleFetchError(f"로그인이 필요한 파일이라 받을 수 없습니다. {SHARE_HELP}")

    if not name:
        name = "구글파일" + default_ext
    if not Path(name).suffix:
        name += ".csv" if "csv" in ctype else default_ext
    if Path(name).suffix.lower() not in (".xlsx", ".xlsm", ".xls", ".csv"):
        raise GoogleFetchError(f"엑셀/CSV 파일이 아닙니다({name}). 리뷰·매출 데이터는 구글 시트나 엑셀/CSV로 넣어 주세요.")
    name = re.sub(r'[\\/:*?"<>|]', "_", name)
    if label:
        name = f"{label}_{name}"
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / name
    i = 2
    while path.exists():
        path = dest / f"{Path(name).stem}_{i}{Path(name).suffix}"
        i += 1
    path.write_bytes(data)
    return path
