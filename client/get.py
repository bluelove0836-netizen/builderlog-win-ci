#!/usr/bin/env python3
"""빌더로그 도우미 — 붙여넣기 프롬프트({{ORIGIN}}/start)가 AI(Claude Code·Codex)에게 실행시키는 단일 파일(표준 파이썬만).

  python3 ~/builderlog/get.py login            연결 코드·주소 표시(브라우저에서 이메일 6자리 로그인 뒤 코드 입력)
  python3 ~/builderlog/get.py login --code XXXX-XXXX   MCP login_start 도구가 준 코드로 이 컴퓨터를 붙이고 기다림
  python3 ~/builderlog/get.py login --wait     코드를 넣을 때까지 기다림(약 1분 40초씩, 아직이면 다시 실행)
  python3 ~/builderlog/get.py connect          이 AI 에 빌더로그 원격 MCP 연결(토큰은 파일에서 읽는 중계)
  python3 ~/builderlog/get.py list             팩 목록(이용 중 · 구독 가능 · 최신 버전)
  python3 ~/builderlog/get.py install <팩>     가진 팩(구매·구독)의 전체 패키지 → sha256 확인 → ~/builderlog/<팩>/ → 이 AI 에 CLAUDE.md·AGENTS.md 절차 연결
  python3 ~/builderlog/get.py update [--check] 새 버전 확인·패치(내가 고친 파일·out/·config/·.env 는 그대로, 새 내용은 .new)
  python3 ~/builderlog/get.py buy <팩> [--yearly] [--wait]  결제 페이지(월 990원, --yearly 1년 이용권)를 기본 브라우저로 열기(결제는 사용자가 직접) · --wait 확인되면 바로 설치
  python3 ~/builderlog/get.py schedule on|off  하루 1번 업데이트 확인(macOS launchd · WSL/리눅스 cron) + 다음 대화 때 바뀐 점 알림
  python3 ~/builderlog/get.py news             바뀐 점(아직 안 본 것)
  python3 ~/builderlog/get.py brain <install|status|recall|note|uninstall>   AI 뇌(내 컴퓨터 안 옵시디언 보관함 · MCP 도구 brain_setup·brain_recall·brain_note 와 같은 일)
  python3 ~/builderlog/get.py status · logout · uninstall <팩>
  python3 ~/builderlog/get.py lang en|ko      안내 언어(영어·한국어). 환경 변수 BUILDERLOG_LANG 이 먼저

English: set BUILDERLOG_LANG=en or run `python3 ~/builderlog/get.py lang en` to see every message in English.
  login [--code XXXX-XXXX] [--wait] · connect · list · install <pack> · update [--check] · buy <pack> [--yearly] [--wait]
  schedule on|off · news · status · logout · uninstall <pack> · lang en|ko

토큰·기기 비밀값은 ~/builderlog/.builderlog/ 안 0600 파일에만 두고 화면에 출력하지 않는다. 서버 주소는 {{ORIGIN}} 하나.
게시·결제·로그인 대행은 하지 않는다. Windows 는 WSL(우분투) 안에서 실행한다.
"""
import argparse
import base64
import contextlib
import hashlib
import json
import os
import platform
import random
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

VERSION = "0.5.0"
ORIGIN = (os.environ.get("BUILDERLOG_SERVER") or "{{ORIGIN}}").rstrip("/")
_HERE = Path(__file__).resolve().parent
# 도우미는 자기가 있는 빌더로그 폴더를 쓴다(안내서의 절대 경로로 불려도 같은 곳). 처음 받을 때(.builderlog 없음)는 ~/builderlog
ROOT = Path(os.environ.get("BUILDERLOG_HOME") or (_HERE if (_HERE / ".builderlog").is_dir() else Path.home() / "builderlog")).expanduser()
STATE = ROOT / ".builderlog"
HELPER = ROOT / "get.py"
UA = f"builderlog-get/{VERSION} ({platform.system()})"
# 윈도우 그대로(WSL 없이, 10/29 회장 '파워쉘없이 코덱스나 클코로 바로'): 안내 속 실행 명령은 python3 대신 py -3(없으면 python —
# 윈도우의 python3 는 스토어 바로가기일 수 있다), 경로는 ~ 대신 절대 경로(PowerShell 은 ~ 를 펼치지 않는다)
IS_WIN = os.name == "nt"
PY = ("py -3" if shutil.which("py") else "python") if IS_WIN else "python3"


# 안내 언어(해외 손님 영어, 2026-10-17): 환경 변수 BUILDERLOG_LANG(en·ko) > ~/builderlog/lang(설치 한 줄·`get.py lang` 이 씀) > ko
def _lang():
    v = (os.environ.get("BUILDERLOG_LANG") or "").strip().lower()
    if v not in ("en", "ko"):
        try:
            v = (ROOT / "lang").read_text(encoding="utf-8").strip().lower()
        except OSError:
            v = ""
    return v if v in ("en", "ko") else "ko"


LANG = _lang()
# 서버 요청 머리글: 영어면 Accept-Language: en(서버 message·상태 글이 영어로 온다)
HEADERS = {"User-Agent": UA, **({"Accept-Language": "en"} if LANG == "en" else {})}


def t(ko, en):
    return en if LANG == "en" else ko


def ui_url(url):
    """사용자에게 보여 주거나 여는 빌더로그 화면 주소: 영어면 lang=en 을 붙인다(다른 사이트 주소는 그대로)."""
    if LANG != "en" or not str(url).startswith(ORIGIN) or "lang=" in url:
        return url
    base, _, frag = url.partition("#")
    return base + ("&" if "?" in base else "?") + "lang=en" + ("#" + frag if frag else "")


def install_line():
    if IS_WIN:
        return f"irm {ORIGIN}/{'en/' if LANG == 'en' else ''}install.ps1 | iex"
    return f"curl -fsSL {ORIGIN}/{'en/' if LANG == 'en' else ''}install.sh | bash"
LABEL = "net.builderlog.update"
MARK = "builderlog-update"
NEVER = (".builderlog/", ".venv/", "out/", "config/", ".onboarding/", ".env")  # 사용자 것: 묶음에 없고 패치도 안 건드림
# 출시 서명(ed25519): kid → 공개 열쇠 hex. 서버(src/packages.js)도 이 줄을 읽는다(JSON 모양 유지). 열쇠 교체: 새 kid 를 먼저 넣어 배포 → 출시를 새 kid 로 → 옛 kid 는 REVOKED
RELEASE_KEYS = {"k1": "868197f3d40429d2eb1842470a1c8f2f7994871359c1d158e19a009e5018dad0", "k2": "ddc767e15b8afe113cebfbb5d6343719276cdfdc9be9aa8ecd4ddcdab2a98265"}
REVOKED = []
# 이 날(KST, YYYY-MM-DD)부터 서명 없는 파일은 설치하지 않는다. 비어 있으면 전환 기간(기록만). 서명이 틀린 파일은 언제나 거부.
SIG_REQUIRED_FROM = "2026-11-06"  # 회장 10/16 OK: 첫 서명 출시 뒤 2주 이상, 이 날부터 서명 없는 업데이트 거부


# ── ed25519 검증·서명 문장: begin (client/get.py 와 같은 글자) ──
_P = 2 ** 255 - 19
_Q = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_SQRT_M1 = pow(2, (_P - 1) // 4, _P)


def _ed_add(a, b):
    x = (a[1] - a[0]) * (b[1] - b[0]) % _P
    y = (a[1] + a[0]) * (b[1] + b[0]) % _P
    c = 2 * a[3] * b[3] * _D % _P
    z = 2 * a[2] * b[2] % _P
    e, f, g, h = y - x, z - c, z + c, y + x
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _ed_mul(s, pt):
    out = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            out = _ed_add(out, pt)
        pt = _ed_add(pt, pt)
        s >>= 1
    return out


def _ed_x(y, sign):
    if y >= _P:
        return None
    x2 = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P) % _P
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P:
        x = x * _SQRT_M1 % _P
    if (x * x - x2) % _P:
        return None
    return _P - x if (x & 1) != sign else x


def _ed_point(s):
    y = int.from_bytes(s, "little")
    sign, y = y >> 255, y & ((1 << 255) - 1)
    x = _ed_x(y, sign)
    return None if x is None else (x, y, 1, x * y % _P)


_GY = 4 * pow(5, _P - 2, _P) % _P
_G = (_ed_x(_GY, 0), _GY, 1, _ed_x(_GY, 0) * _GY % _P)


def _ed_hash(*parts):
    return int.from_bytes(hashlib.sha512(b"".join(parts)).digest(), "little") % _Q


def ed25519_verify(public, message, signature):
    """공개 열쇠(32바이트)로 서명(64바이트) 확인. 형식이 틀리면 False."""
    if len(public) != 32 or len(signature) != 64:
        return False
    a, r = _ed_point(public), _ed_point(signature[:32])
    s = int.from_bytes(signature[32:], "little")
    if a is None or r is None or s >= _Q:
        return False
    left, right = _ed_mul(s, _G), _ed_add(r, _ed_mul(_ed_hash(signature[:32], public, message), a))
    return (left[0] * right[2] - right[0] * left[2]) % _P == 0 and (left[1] * right[2] - right[1] * left[2]) % _P == 0


def pkg_message(slug, version, plat, name, size, sha256):
    """판매 ZIP 한 개의 서명 문장. sha256 이 들어 있어 ZIP 전체를 다시 서명하지 않는다."""
    return f"builderlog-pkg-v1\n{slug}\n{version}\n{plat}\n{name}\n{size}\n{sha256}".encode()


def getpy_message(version, sha256):
    """도우미(get.py, 서버 주소가 채워진 그대로) 서명 문장."""
    return f"builderlog-getpy-v1\n{version}\n{sha256}".encode()
# ── ed25519 검증·서명 문장: end ──


class Stop(Exception):
    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


def say(*a):
    print(*a, flush=True)


# ── 파일(비밀값은 0600) ──
def write_private(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def release_ok(what, message, sig, kid):
    """출시 서명 확인. 맞으면 True. 틀림·폐기한 열쇠는 언제나 거부(Stop). 서명 없음(모르는 kid 포함)은 SIG_REQUIRED_FROM 전까지 기록만 하고 False."""
    pub = RELEASE_KEYS.get(kid) if sig and kid not in REVOKED else None
    if pub:
        try:
            ok = ed25519_verify(bytes.fromhex(pub), message, base64.b64decode(sig, validate=True))
        except ValueError:
            ok = False
        if ok:
            return True
    result = "bad-signature" if pub or (sig and kid in REVOKED) else "unsigned"
    required = SIG_REQUIRED_FROM and time.strftime("%Y-%m-%d", time.gmtime(time.time() + 9 * 3600)) >= SIG_REQUIRED_FROM
    STATE.mkdir(parents=True, exist_ok=True)
    with open(STATE / "security.log", "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {what} {result}{' kid=' + str(kid) if kid else ''} {'refused' if result != 'unsigned' or required else 'allowed'}\n")
    if result != "unsigned":
        raise Stop(t(f"{what}: 출시 서명이 맞지 않아 설치하지 않았어요(지금 것은 그대로). 서버 문제일 수 있어요. 고객센터에 알려 주세요.",
                     f"{what}: the release signature does not match, so nothing was installed (your current version stays). This may be a server problem. Please tell hello@builderlog.net."))
    if required:
        raise Stop(t(f"{what}: 출시 서명이 없어 설치하지 않았어요(지금 것은 그대로). 서버 문제일 수 있어요. 고객센터에 알려 주세요.",
                     f"{what}: there is no release signature, so nothing was installed (your current version stays). This may be a server problem. Please tell hello@builderlog.net."))
    return False


def token():
    f = STATE / "token"
    v = f.read_text(encoding="utf-8").strip() if f.is_file() else ""
    return v if v.startswith("blt_") and len(v) == 68 else ""


def device(create=False):
    f = STATE / "device"
    v = f.read_text(encoding="utf-8").strip() if f.is_file() else ""
    if len(v) == 64 and all(c in "0123456789abcdef" for c in v):
        return v
    if not create:
        return ""
    v = os.urandom(32).hex()
    write_private(f, v + "\n")
    return v


def pair_code(secret):
    return hashlib.sha256(("builderlog-code:" + secret).encode()).hexdigest()[:8].upper()


# ── 서버 ──
def api(method, path, body=None, auth=True, timeout=30):
    headers = {**HEADERS, "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if auth:
        tok = token()
        if not tok:
            raise Stop(t(f"로그인이 필요해요: {GET} login", f"Please log in first: {GET} login"), 3)
        headers["Authorization"] = "Bearer " + tok
    req = urllib.request.Request(ORIGIN + path, method=method, headers=headers, data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            data = json.loads(e.read() or b"{}")
        except ValueError:
            data = {}
        if e.code == 401 and auth:
            raise Stop(t(f"로그인이 끊겼어요(다른 컴퓨터 연결로 해제됐거나 로그아웃). 다시: {GET} login",
                         f"You were logged out (another computer took this slot, or you logged out). Log in again: {GET} login"), 3)
        return e.code, data
    except OSError as e:
        raise Stop(t(f"서버({ORIGIN})에 연결하지 못했어요: {e}. 인터넷 연결을 확인해 주세요.", f"Could not reach the server ({ORIGIN}): {e}. Please check your internet connection."))


def fetch(url, dest, timeout=120):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r, open(dest, "wb") as f:
            shutil.copyfileobj(r, f)
    except urllib.error.HTTPError as e:
        raise Stop(t(f"내려받지 못했어요({e.code}). 다시 실행해 주세요.", f"Download failed ({e.code}). Please run it again."))
    except OSError as e:
        raise Stop(t(f"내려받지 못했어요: {e}", f"Download failed: {e}"))


# ── 로그인(기기 코드) ──
def machine_info():
    """연결 확인 화면에 보일 이 컴퓨터 이름·OS(약점 ④). 이름은 hostname 에서 .local 을 뗀 40자, 비밀값 아님."""
    import socket
    host = socket.gethostname()
    label = (host[:-6] if host.endswith(".local") else host)[:40]
    if platform.system() == "Darwin":
        osname = f"macOS {platform.mac_ver()[0]}".strip()
    elif IS_WIN:
        osname = f"Windows {platform.release()}".strip()
    else:
        osname = platform.system()
        with contextlib.suppress(OSError):
            for line in Path("/etc/os-release").read_text().splitlines():
                if line.startswith("PRETTY_NAME="):
                    osname = line.split("=", 1)[1].strip('"')
        if is_wsl():
            osname += " (WSL)"
    return {"label": label, "os": osname[:40]}


def say_name(info):
    say(t(f"이 컴퓨터 이름: {info['label']} — 브라우저 확인 화면에 같은 이름이 보일 때만 [연결]을 누르세요. 누가 코드를 보내 줬다면 누르지 마세요.",
          f"This computer's name: {info['label']}. Press [Link] only if the browser shows the same name. If someone sent you the code, do not press it."))


def cmd_login(a):
    if token() and not a.again:
        code, me = api("GET", "/v1/account")
        if code == 200:
            say(t(f"이미 로그인돼 있어요: {me.get('account')} (다른 계정이면: {GET} login --again)",
                  f"Already logged in: {me.get('account')} (for another account: {GET} login --again)"))
            return 0
    pending = read_json(STATE / "login-pending", {})
    if a.wait:
        if not pending.get("device_code"):
            raise Stop(t(f"먼저 {GET} login 을 실행해 연결 코드를 받으세요.", f"First run {GET} login to get a link code."))
        return wait_login(pending)
    secret = device(create=True)
    if a.code:
        # MCP 한 줄 연결: login_start 도구가 준 코드에 이 컴퓨터를 붙이고, 사용자가 그 코드를 넣을 때까지 기다린다
        info = machine_info()
        code, r = api("POST", "/v1/device/claim", {"code": a.code, "pair": pair_code(secret), "client": detect_client(), **info}, auth=False)
        if code != 200:
            raise Stop(r.get("message") or t(f"로그인을 이어 가지 못했어요({code}).", f"Could not continue the login ({code})."))
        p = {"device_code": r["device_code"], "user_code": r["user_code"], "interval": r.get("interval", 5), "expires_at": time.time() + r.get("expires_in", 600), "uri": r["verification_uri"]}
        write_private(STATE / "login-pending", json.dumps(p))
        say(t(f"이 컴퓨터 준비 완료. 사용자가 {p['uri']} 에서 로그인하고 연결 코드 {p['user_code']} 를 넣으면 이어져요.",
              f"This computer is ready. It continues when the user logs in at {ui_url(p['uri'])} and enters the link code {p['user_code']}."))
        say_name(info)
        return wait_login(p)
    info = machine_info()
    code, r = api("POST", "/v1/device/start", {"pair": pair_code(secret), "client": detect_client(), **info}, auth=False)
    if code == 409 and r.get("code") == "CODE_BUSY":
        # 5분 안에 다시 실행(설치 한 줄을 또 붙임·Ctrl-C 뒤 재실행): 이 컴퓨터가 먼저 시작한 로그인이 아직 열려 있다.
        # 그 요청의 device_code 는 이 컴퓨터의 login-pending(0600)에만 있으니 그걸로 이어서 기다린다(서버는 새 요청을 받지 않아 끼어들기 없음).
        if pending.get("device_code") and str(pending.get("user_code", "")).replace("-", "") == pair_code(secret) and pending.get("expires_at", 0) > time.time() + 10:
            say(t(f"조금 전 로그인을 이어서 기다려요: {pending['uri']} 에서 연결 코드 {pending['user_code']} 를 넣어 주세요.",
                  f"Still waiting for your earlier login: enter the link code {pending['user_code']} at {ui_url(pending['uri'])}."))
            return 0
        raise Stop(t("이 컴퓨터의 이전 로그인이 아직 열려 있어요. 5분 뒤 다시 실행해 주세요.", "An earlier login from this computer is still open. Please run it again in 5 minutes."))
    if code != 200:
        raise Stop(r.get("message") or t(f"로그인을 시작하지 못했어요({code}).", f"Could not start the login ({code})."))
    write_private(STATE / "login-pending", json.dumps({"device_code": r["device_code"], "user_code": r["user_code"], "interval": r.get("interval", 5),
                                                         "expires_at": time.time() + r.get("expires_in", 600), "uri": r["verification_uri"]}))
    say(t("빌더로그 로그인 — 사용자에게 아래 두 줄을 그대로 보여 주세요.", "Builderlog login: show the user these two steps exactly as written."))
    say(t(f"  1) 브라우저에서 {r['verification_uri']} 를 열고 이메일로 온 6자리 코드로 로그인",
          f"  1) Open {ui_url(r['verification_uri'])} in a browser and log in with the 6-digit code sent to your email"))
    say(t(f"  2) 연결 코드 {r['user_code']} 를 넣고 '이 컴퓨터 연결하기' (5분 안)", f"  2) Enter the link code {r['user_code']} and press 'Link this computer' (within 5 minutes)"))
    say_name(info)
    say(t(f"넣은 뒤(또는 바로) 이어서: {GET} login --wait", f"After entering it (or right now), continue with: {GET} login --wait"))
    if not os.environ.get("BUILDERLOG_NO_BROWSER") and a.open:
        try:
            import webbrowser
            webbrowser.open(ui_url(r["verification_uri"]))
        except Exception:
            pass
    return 0


def wait_login(p):
    deadline = min(p["expires_at"], time.time() + float(os.environ.get("BUILDERLOG_WAIT_SECONDS", "100")))
    interval = int(p.get("interval", 5))
    say(t(f"연결 코드 {p['user_code']} 입력을 기다려요({p['uri']})…", f"Waiting for the link code {p['user_code']} ({ui_url(p['uri'])})..."))
    while time.time() < deadline:
        code, r = api("POST", "/v1/device/token", {"device_code": p["device_code"]}, auth=False)
        if code == 200 and r.get("access_token"):
            write_private(STATE / "token", r["access_token"] + "\n")
            (STATE / "login-pending").unlink(missing_ok=True)
            say(t(f"로그인 완료: {r.get('account') or '계정 확인됨'} · 이 컴퓨터가 연결됐어요.", f"Logged in: {r.get('account') or 'account confirmed'}. This computer is connected."))
            return 0
        err = r.get("error")
        if err == "slow_down":
            interval = int(r.get("interval", interval + 2))
        elif err != "authorization_pending":
            (STATE / "login-pending").unlink(missing_ok=True)
            raise Stop(r.get("message") or t(f"로그인이 끝나지 않았어요. 처음부터: {GET} login", f"The login did not finish. Start over: {GET} login"))
        time.sleep(interval)
    if time.time() >= p["expires_at"]:
        (STATE / "login-pending").unlink(missing_ok=True)
        raise Stop(t(f"5분이 지났어요. 처음부터: {GET} login", f"5 minutes have passed. Start over: {GET} login"))
    say(t(f"아직 코드를 넣지 않았어요. 넣은 뒤 다시: {GET} login --wait", f"The code has not been entered yet. After entering it, run: {GET} login --wait"))
    return 4


def cmd_logout(a):
    if token():
        api("POST", "/v1/device/logout", {})
    (STATE / "token").unlink(missing_ok=True)
    say(t("로그아웃했어요(이 컴퓨터의 토큰을 지웠어요). 설치된 기능은 그대로예요.", "Logged out (the token on this computer was deleted). Installed packs stay."))
    return 0


# ── 목록·상태 ──
def cmd_list(a):
    code, r = api("GET", "/v1/features", auth=bool(token()))
    if code != 200:
        raise Stop(r.get("message") or t(f"목록을 받지 못했어요({code}).", f"Could not get the list ({code})."))
    inst = installed()
    say(t(f"빌더로그 팩 — 이용 중인 팩만 설치돼요(설치: {GET} install <팩>)", f"Builderlog packs: only packs you subscribe to can be installed (install: {GET} install <pack>)"))
    for f in r["features"]:
        mine = inst.get(f["id"], {})
        have = f" · {t('설치됨', 'installed')} {mine.get('version')}" + (t(" (새 버전 있음)", " (update available)") if f.get("rev") and mine.get("rev") != f.get("rev") else "") if mine else ""
        ver = f" · {t('최신', 'latest')} {f['version']}" if f.get("version") else ""
        buy = f" · {t('결제 페이지', 'subscribe')}: {GET} buy {f['pack']}" if f.get("buy") else ""
        say(f"- {f['id']:<22} {f['title']} · {f['status']}{ver}{have}{buy}")
    if not r.get("logged_in"):
        say(t(f"(로그인하면 이용 중인 팩이 함께 보여요: {GET} login)", f"(Log in to see your packs here: {GET} login)"))
    return 0


def installed():
    return read_json(STATE / "installed.json", {}) or {}


def cmd_status(a):
    if token():
        code, me = api("GET", "/v1/account")
        if code == 200:
            say(t(f"계정 {me['account']} · 연결된 컴퓨터 {me['devices']['used']}/{me['devices']['limit']}대 · 이용 중인 팩 {', '.join(me['paid']) or '없음'}",
                  f"Account {me['account']} · computers {me['devices']['used']}/{me['devices']['limit']} · your packs: {', '.join(me['paid']) or 'none'}"))
    else:
        say(t(f"로그인 안 됨: {GET} login", f"Not logged in: {GET} login"))
    inst = installed()
    say(t("설치된 기능: ", "Installed: ") + (", ".join(f"{k} {v.get('version')}" for k, v in inst.items()) or t("없음", "none")))
    s = read_json(STATE / "schedule.json", {}) or {}
    say(t("하루 1번 업데이트 확인: ", "Daily update check: ") + (t(f"켜짐({s.get('kind')}, 매일 {s.get('hour', 10)}:{s.get('minute', 0):02d})",
                                                           f"on ({s.get('kind')}, every day at {s.get('hour', 10)}:{s.get('minute', 0):02d})") if s.get("on") else t("꺼짐", "off")))
    if (STATE / "news.md").is_file():
        say(t(f"안 본 업데이트 소식이 있어요: {GET} news", f"You have unread update news: {GET} news"))
    return 0


# ── 설치 ──
def detect_client():
    if os.environ.get("CLAUDECODE") == "1" or os.environ.get("CLAUDE_CODE_ENTRYPOINT"):
        return "claude-code"
    if any(k.startswith("CODEX_") for k in os.environ):
        return "codex"
    return "auto"


def pick_python():
    """install.py 를 돌릴 파이썬(3.10 이상)."""
    cands = [sys.executable, shutil.which("python3.13"), shutil.which("python3.12"), shutil.which("python3.11"), shutil.which("python3.10"),
             "/opt/homebrew/bin/python3", "/usr/local/bin/python3", shutil.which("python3")]
    for c in cands:
        if not c or not Path(c).exists():
            continue
        try:
            out = subprocess.run([c, "-c", "import sys;print(sys.version_info[:2]>=(3,10))"], capture_output=True, text=True, timeout=20).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            continue
        if out == "True":
            return c
    raise Stop(t("파이썬 3.10 이상이 필요해요. macOS: brew install python@3.12 · 윈도우: winget install -e --id Python.Python.3.12 --scope user · 우분투(WSL): sudo apt install python3.12 python3.12-venv — 설치한 뒤 같은 명령을 다시 실행하세요.",
                 "Python 3.10 or newer is needed. macOS: brew install python@3.12 · Windows: winget install -e --id Python.Python.3.12 --scope user · Ubuntu (WSL): sudo apt install python3.12 python3.12-venv. Then run the same command again."))


def safe_members(z):
    for info in z.infolist():
        p = Path(info.filename)
        if p.is_absolute() or ".." in p.parts or (info.external_attr >> 16) & 0o170000 == 0o120000:
            raise Stop(t("설치 파일 구성이 이상해서 멈췄어요. hello@builderlog.net 으로 알려 주세요.", "The install file looks wrong, so it stopped. Please tell hello@builderlog.net."))
    return z.infolist()


def link_kit(dest):
    """설치한 기능(키트)에 이 컴퓨터 연결을 넘긴다: 로그인 때 계정에 묶인 기기 비밀값 + '연결됨' 표시 → 키트의 유료 모듈이 같은 계정 권한으로 열린다."""
    write_private(dest / ".builderlog" / "device", device(create=True) + "\n")
    if token():
        write_private(dest / ".builderlog" / "account.json", json.dumps({"linked_at": int(time.time())}))


def cmd_install(a):
    fid = a.feature.strip()
    if "." in fid:  # 예전 키트의 유료 모듈(<팩>.<모듈>) — 키트 사용자용, 가진 팩일 때만
        code, info = api("POST", "/v1/features/download", {"feature": fid})
        if code != 200:
            raise Stop(info.get("message") or t(f"설치 정보를 받지 못했어요({code}).", f"Could not get install info ({code})."))
        if not info.get("allowed"):
            say(info.get("message"))
            return 2
        return install_module(info, a)
    try:
        info, kept = install_package(fid, a)
    except Stop as e:
        if e.code == 2:  # 가진 팩이 아님 → 구독 안내(결제 페이지 열기 명령)
            say(str(e))
            return 2
        raise
    pack = info["pack"]
    dest = ROOT / pack
    if kept is None:
        say(t(f"이미 최신이에요: {info.get('title', pack)} {info['version']}", f"Already up to date: {info.get('title', pack)} {info['version']}"))
    reg = register(pack, dest, a.client, a.scope)
    inst = installed()
    inst[pack]["skills"] = sorted(set(inst[pack].get("skills", []) + SKILLS.pop(pack, [])))
    write_json(STATE / "installed.json", inst)
    say(t("이 AI 에 연결: ", "Connected to this AI: ") + (", ".join(reg) or t("없음(--client 로 고를 수 있어요)", "none (choose with --client)")))
    say(t(f"다음: \"{trigger(pack)}\" 라고 하면 {show(dest)}/CLAUDE.md(Codex 는 AGENTS.md) 절차대로 진행해요. (새 안내는 AI 를 다시 열면 보여요)",
          f"Next: say \"{trigger(pack)}\" and the AI follows {show(dest)}/CLAUDE.md (Codex: AGENTS.md). (Reopen the AI to load the new instructions.)"))
    return 0


def install_module(info, a):
    pack, mod = info["pack"], info["module"]
    dest = ROOT / pack
    if not (dest / "kit.py").is_file():
        raise Stop(t(f"이 모듈은 예전 키트용이에요. 전체 패키지는 {GET} install {pack}", f"This module is for the old kit. For the full pack: {GET} install {pack}"))
    link_kit(dest)
    py = venv_py(dest)
    # 키트의 모듈 설치(권한 확인 → ZIP → 크기·sha256 → packs/<팩>/modules/)를 그대로 부른다. 자격은 로그인 때 묶인 이 컴퓨터 연결.
    code = ("import sys,json; sys.path.insert(0,'shared'); import modules_client as m\n"
            "try:\n  print(json.dumps(m.Client(sys.argv[1]).install(sys.argv[2]), ensure_ascii=False))\n"
            "except m.ModuleError as e:\n  print(e); sys.exit(2)")
    r = subprocess.run([str(py if py.exists() else pick_python()), "-c", code, pack, mod], cwd=dest, capture_output=True, text=True, timeout=600,
                       env={**os.environ, "BUILDERLOG_NO_VENV": "1"})
    outp = (r.stdout + r.stderr).strip()
    if r.returncode == 0:
        try:
            res = json.loads(outp.splitlines()[-1])
            say(t(f"유료 모듈 설치: {info['feature']} {res.get('version', '')} — {res.get('message', '')} (packs/{pack}/modules/{mod})",
                  f"Installed paid module: {info['feature']} {res.get('version', '')}: {res.get('message', '')} (packs/{pack}/modules/{mod})"))
        except (ValueError, IndexError):
            say(outp[-800:])
    else:
        say(outp[-800:])
    return r.returncode


# ── 전체 패키지(판매본) 설치·갱신 — 회장 2026-10-15 "990원 구독자 = 그 팩의 지금 패키지 전부, 받는 방식만 다름" ──
# 가진 팩(구매·구독)만: 서버가 회원 토큰 + 그 팩 권한을 확인하고 판매본 ZIP 을 준다. 크기·sha256 이 맞을 때만 설치한다.
# 업데이트하는 쪽은 하나만: 이 도우미가 설치한 팩은 패키지 자체 업데이트(onboarding.py update·매일 확인)를 꺼 두고
# (.onboarding/update-schedule-mode=off + managed-by.json, 업데이트 키 없음), 적용 중에는 패키지와 같은 잠금(.onboarding/update.lock)을 잡는다.
PROTECTED = {"config", "data", "out", "drafts", "state", "reports", "logs", "receipts", "node_modules", ".venv", ".env", ".onboarding", ".backup", ".cache", ".builderlog"}
ALWAYS = {"SHIPPED.sha256", "SHIPPED-HISTORY.sha256"}  # 지문 목록 자체는 항상 새것으로
TRIGGER = {"shorts": "숏츠 만들어 줘", "blog": "블로그 글 써 줘", "reels": "릴스 만들어 줘", "tiktok": "틱톡 영상 만들어 줘", "kmong": "크몽 서비스 글 써 줘",
           "toss": "토스쇼핑 상품 올려 줘", "clip": "네이버 클립 만들어 줘"}
TRIGGER_EN = {"shorts": "make a YouTube Short", "blog": "write a blog post", "reels": "make an Instagram Reel", "tiktok": "make a TikTok video",
              "kmong": "write a Kmong service post", "toss": "list a product on Toss Shopping", "clip": "make a Naver Clip"}


def trigger(pack):
    return (TRIGGER_EN if LANG == "en" else TRIGGER).get(pack, pack)


def plat():
    return "macos" if platform.system() == "Darwin" else "windows-wsl2"


def is_wsl():
    return bool(os.environ.get("WSL_DISTRO_NAME")) or "microsoft" in platform.release().lower()


def vnum(v):
    try:
        return tuple(int(x) for x in str(v).split("."))
    except ValueError:
        return (0,)


def show(path):
    """화면·안내서에 보일 경로: 홈 아래면 ~/… 로. 윈도우는 절대 경로(C:/Users/…, 빈칸 있으면 따옴표) — Git Bash·PowerShell 둘 다 그대로 붙여 쓸 수 있게."""
    if IS_WIN:
        s = Path(path).resolve().as_posix()
        return f'"{s}"' if " " in s else s
    try:
        return "~/" + Path(path).resolve().relative_to(Path.home().resolve()).as_posix()
    except ValueError:
        return str(path)


GET = f"{PY} {show(HELPER)}"  # 안내 문구 속 도우미 실행 명령(맥·리눅스 {GET})


def venv_py(dest):
    """팩 가상환경의 파이썬(윈도우는 Scripts/python.exe)."""
    return dest / (".venv/Scripts/python.exe" if IS_WIN else ".venv/bin/python")


def resolve_exe(cmd):
    """윈도우: npm 으로 깐 claude·codex 는 claude.cmd 라서 이름만으로는 subprocess 가 못 찾는다 → PATH(PATHEXT) 로 찾은 전체 경로."""
    if IS_WIN and cmd and not os.path.dirname(cmd[0]):
        return [shutil.which(cmd[0]) or cmd[0], *cmd[1:]]
    return cmd


def lock_nb(h):
    """기다리지 않는 배타 잠금(닫으면 풀림): 맥·리눅스 flock, 윈도우 msvcrt(첫 1바이트). 이미 잠겨 있으면 BlockingIOError·PermissionError."""
    if IS_WIN:
        import msvcrt
        h.seek(0)
        try:
            msvcrt.locking(h.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as e:
            raise BlockingIOError(str(e)) from e
        return
    import fcntl
    fcntl.flock(h, fcntl.LOCK_EX | fcntl.LOCK_NB)


@contextlib.contextmanager
def pack_lock(dest):
    """이 도우미끼리 + 패키지 자체 업데이트(bin/update.py 의 .onboarding/update.lock)와 동시에 돌지 않게."""
    held = []
    try:
        for f in (STATE / "locks" / f"{dest.name}.lock", dest / ".onboarding" / "update.lock" if dest.is_dir() else None):
            if f is None:
                continue
            f.parent.mkdir(parents=True, exist_ok=True)
            h = os.fdopen(os.open(f, os.O_RDWR | os.O_CREAT, 0o600), "a")
            try:
                lock_nb(h)
            except (BlockingIOError, PermissionError):
                h.close()
                raise Stop(t("이 팩의 다른 업데이트가 진행 중이에요(패키지 자체 업데이트 포함). 끝난 뒤 다시 실행하세요.",
                             "Another update of this pack is running (including the pack's own updater). Run it again when it finishes."), 5)
            held.append(h)
        yield
    finally:
        for h in held:
            h.close()


def shipped(text):
    """SHIPPED.sha256(sha256sum 형식) → {경로: 지문}."""
    out = {}
    for line in text.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and len(parts[0]) == 64:
            out[parts[1].lstrip("*")] = parts[0]
    return out


def package_entries(z, slug):
    out = {}
    for info in safe_members(z):
        name = info.filename
        if not (name == slug + "/" or name.startswith(slug + "/")):
            raise Stop(t("설치 파일 구성이 이상해서 멈췄어요. hello@builderlog.net 으로 알려 주세요.", "The install file looks wrong, so it stopped. Please tell hello@builderlog.net."))
        rel = name[len(slug) + 1:]
        if rel and not name.endswith("/"):
            out[rel] = info
    if "onboarding.json" not in out:
        raise Stop(t("설치 파일 구성이 이상해서 멈췄어요(onboarding.json 없음).", "The install file looks wrong, so it stopped (no onboarding.json)."))
    return out


def write_member(z, info, target, data=None):
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(z.read(info) if data is None else data)
    if (info.external_attr >> 16) & 0o111:
        target.chmod(0o755)


def apply_package(z, entries, dest):
    """3방향 패치(apply_update 와 같은 규칙, 판매본의 SHIPPED.sha256 = 설치 때 지문): 없는 파일은 쓰기, 설치 때 그대로면 새 버전으로,
    사용자가 고쳤으면 그대로 두고 새 내용은 <파일>.new. out/·config/·.env·data/ 같은 사용자 것은 덮어쓰지도 지우지도 않는다(config/ 는 없는 예제만 추가)."""
    old = shipped((dest / "SHIPPED.sha256").read_text(encoding="utf-8")) if (dest / "SHIPPED.sha256").is_file() else {}
    kept, changed = [], 0
    for rel, info in sorted(entries.items()):
        top, target = rel.split("/", 1)[0], dest / rel
        if top in PROTECTED:
            if top == "config" and not target.exists():
                write_member(z, info, target)
                changed += 1
            continue
        data = z.read(info)
        if target.exists():
            if not target.is_file():
                kept.append(rel)
                continue
            cur = sha256_file(target)
            if cur == hashlib.sha256(data).hexdigest():
                continue
            if rel not in ALWAYS and (rel not in old or cur != old[rel]):
                target.with_name(target.name + ".new").write_bytes(data)
                kept.append(rel)
                continue
        write_member(z, info, target, data)
        changed += 1
    removed = 0
    for rel, digest in old.items():
        t = dest / rel
        if rel not in entries and rel.split("/", 1)[0] not in PROTECTED and t.is_file() and sha256_file(t) == digest:
            t.unlink()
            removed += 1
    return kept, changed, removed


def download_package(info):
    dl = STATE / "dl"
    dl.mkdir(parents=True, exist_ok=True)
    path = dl / info["file"]
    req = urllib.request.Request(f"{ORIGIN}/v1/packages/{info['pack']}/download?platform={info['platform']}", headers={**HEADERS, "Authorization": "Bearer " + token()})
    h, size, head = hashlib.sha256(), 0, ""
    try:
        with urllib.request.urlopen(req, timeout=600) as r, open(path, "wb") as f:
            head = r.headers.get("x-package-sha256", "")
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                size += len(chunk)
                if size > info["bytes"]:
                    break
                h.update(chunk)
                f.write(chunk)
    except urllib.error.HTTPError as e:
        path.unlink(missing_ok=True)
        try:
            msg = json.loads(e.read() or b"{}").get("message")
        except ValueError:
            msg = ""
        raise Stop(msg or t(f"내려받지 못했어요({e.code}). 다시 실행해 주세요.", f"Download failed ({e.code}). Please run it again."), 2 if e.code == 403 else 1)
    except OSError as e:
        path.unlink(missing_ok=True)
        raise Stop(t(f"내려받지 못했어요: {e}", f"Download failed: {e}"))
    if size != info["bytes"] or h.hexdigest() != info["sha256"] or (head and head != info["sha256"]):
        path.unlink(missing_ok=True)
        raise Stop(t("받은 파일의 지문(sha256)이 맞지 않아 설치하지 않았어요. 다시 실행해 주세요.", "The downloaded file's fingerprint (sha256) does not match, so nothing was installed. Please run it again."))
    return path


def mark_managed(dest, pack):
    """패키지 자체 업데이트를 끄고(사용자가 직접 끈 것과 같은 표시라 패키지가 다시 켜지 않음) 누가 업데이트하는지 남긴다."""
    ob = dest / ".onboarding"
    ob.mkdir(parents=True, exist_ok=True)
    (ob / "update-schedule-mode").write_text("off")
    write_json(ob / "managed-by.json", {"by": "builderlog-get", "update": f"{GET} update {pack}", "since": int(time.time())})


def pack_goal(dest, title):
    for n in ("CLAUDE.md", "AGENTS.md"):
        f = dest / n
        if f.is_file():
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                if "이 패키지 목표:" in line:
                    return line.split("이 패키지 목표:", 1)[1].strip().rstrip(".") or title
    return title


def guide_of(dest, first):
    for n in (first, "CLAUDE.md", "AGENTS.md", "README.ko.md", "README.md"):
        if (dest / n).is_file():
            return n
    return "README.md"


def package_latest(pack):
    code, info = api("GET", f"/v1/packages/{pack}/latest?platform={plat()}")
    if code == 403:
        raise Stop(info.get("message") or t("가진 팩만 설치할 수 있어요.", "You can install only packs you subscribe to."), 2)
    if code != 200:
        raise Stop(info.get("message") or t(f"설치 정보를 받지 못했어요({code}).", f"Could not get install info ({code})."))
    return info


def install_package(pack, a, info=None, quiet=False):
    """가진 팩의 판매본 ZIP 을 ~/builderlog/<팩>/ 에 설치하거나(처음) 3방향 패치로 갱신한다. 돌려주는 값: (설치 정보, 지킨 파일)."""
    info = info or package_latest(pack)
    pack, inst = info["pack"], installed()
    dest = ROOT / pack
    cur = inst.get(pack, {})
    if cur.get("kind") == "package" and cur.get("version") == info["version"] and (dest / "onboarding.json").is_file() and not getattr(a, "force", False):
        return info, None
    if (dest / "feature.json").is_file() and not (dest / "onboarding.json").is_file():
        raise Stop(t(f"{dest} 에 예전 키트(무료 맛보기)가 있어요. 먼저 {GET} uninstall {pack} (폴더는 .trash 로 옮겨 보관) 뒤 다시 실행하세요.",
                     f"{dest} has an old kit. First run {GET} uninstall {pack} (the folder moves to .trash), then run this again."))
    release_ok(f"{pack} {info['version']}", pkg_message(info["slug"], info["version"], info["platform"], info["file"], info["bytes"], info["sha256"]), info.get("sig"), info.get("kid"))
    with pack_lock(dest):
        path = download_package(info)
        with zipfile.ZipFile(path) as z:
            entries = package_entries(z, info["slug"])
            meta_new = json.loads(z.read(entries["onboarding.json"]))
            if meta_new.get("version") != info["version"]:
                raise Stop(t("설치 파일의 버전이 목록과 달라 멈췄어요. 다시 실행해 주세요.", "The install file's version differs from the list, so it stopped. Please run it again."))
            if (dest / "onboarding.json").is_file():
                kept, changed, removed = apply_package(z, entries, dest)
            else:
                if dest.exists():
                    raise Stop(t(f"{dest} 가 이미 있어요(빌더로그 팩 폴더가 아님). 옮기거나 지운 뒤 다시 실행하세요.", f"{dest} already exists (not a Builderlog pack folder). Move or delete it, then run this again."))
                staging = ROOT / f".{pack}.new"
                shutil.rmtree(staging, ignore_errors=True)
                for rel, item in entries.items():
                    write_member(z, item, staging / rel)
                staging.rename(dest)
                kept = []
        path.unlink(missing_ok=True)
        mark_managed(dest, pack)
    before = cur.get("version")
    inst[pack] = {**cur, "kind": "package", "slug": info["slug"], "version": info["version"], "rev": info["version"], "platform": info["platform"],
                  "title": info.get("title", pack), "goal": pack_goal(dest, info.get("goal") or info.get("title", pack)), "at": int(time.time())}
    write_json(STATE / "installed.json", inst)
    if not quiet:
        say(t(f"{'업데이트' if before else '설치'}했어요: {inst[pack]['title']} {(before + ' → ') if before else ''}{info['version']} → {dest} (sha256 확인)",
              f"{'Updated' if before else 'Installed'}: {inst[pack]['title']} {(before + ' → ') if before else ''}{info['version']} → {dest} (sha256 checked)"))
        if kept:
            say(t(f"내가 고친 파일 {len(kept)}개는 그대로 두고 새 내용은 .new 로 받았어요: ", f"Kept {len(kept)} file(s) you changed; the new versions are saved as .new: ") + ", ".join(kept[:5]))
        say(t("내 결과·설정(out/·config/·.env)은 그대로예요. 업데이트는 이 도우미가 해요(패키지 자체 업데이트는 꺼 둠).",
              "Your results and settings (out/, config/, .env) stay as they are. This helper handles updates (the pack's own updater is off)."))
    return info, kept


def cmd_buy(a):
    """결제 페이지를 기본 브라우저로 연다(결제·카드 입력은 사용자가 직접). --wait: 권한이 생기면 바로 그 팩을 설치한다."""
    pack = a.feature.strip()
    if not token():
        raise Stop(t(f"먼저 로그인해 주세요: {GET} login (결제한 이메일과 같은 이메일로 로그인하면 바로 연결돼요)",
                     f"Please log in first: {GET} login (log in with the same email you pay with and it connects right away)"), 3)
    code, r = api("GET", f"/v1/packages/{pack}/checkout" + ("?plan=yearly" if a.yearly else ""))
    if code != 200:
        raise Stop(r.get("message") or t(f"결제 페이지를 찾지 못했어요({code}).", f"Could not find the checkout page ({code})."))
    if r.get("owned"):
        say(t(f"{r['title']}는 이미 이용 중이에요.", f"You already have {r['title']}."))
        return cmd_install(argparse.Namespace(feature=r["pack"], client=a.client, scope=a.scope, force=False)) if a.wait else 0
    mark = STATE / f"buy-{r['pack']}{'-y' if a.yearly else ''}.json"
    recent = (read_json(mark, {}) or {}).get("opened_at", 0) > time.time() - 600
    if not (a.wait and recent):
        url = ui_url(r["url"])
        used = open_url(url)
        write_json(mark, {"opened_at": int(time.time())})
        price = f" ({r['price']})" if r.get("price") else ""
        say(t(f"{r['title']} 결제 페이지({r.get('price', '')})를 {'브라우저로 열었어요' if used else '열지 못했어요 — 이 주소를 브라우저에 붙여 넣어 주세요'}: {url}",
              f"{r['title']} checkout{price}: {'opened in your browser' if used else 'could not open a browser, so paste this address into one'}: {url}"))
        if r.get("option"):
            say(t(f"1년 이용권 페이지예요: 결제 페이지의 옵션에서 '{r['option']}' 을 골라 주세요(옵션이 곧 받을 팩이에요).",
                  f"This is the yearly page: pick '{r['option']}' in the checkout options (the option is the pack you get)."))
        say(t("카드·결제 정보는 브라우저에서 직접 넣어 주세요(빌더로그와 AI 는 결제를 대신하지 않아요). 빌더로그 로그인 이메일과 같은 이메일로 결제하면 바로 연결돼요.",
              "Enter your card and payment details yourself in the browser (Builderlog and the AI never pay for you). Pay with the same email as your Builderlog login and it connects right away."))
    if not a.wait:
        say(t(f"결제한 뒤: {GET} buy {r['pack']} --wait (확인되면 바로 설치)", f"After paying: {GET} buy {r['pack']} --wait (installs as soon as payment is confirmed)"))
        return 0
    deadline, interval = time.time() + float(os.environ.get("BUILDERLOG_BUY_WAIT", "900")), float(os.environ.get("BUILDERLOG_BUY_INTERVAL", "5"))
    say(t("결제 확인을 기다려요(결제 뒤 보통 1~2분)…", "Waiting for payment confirmation (usually 1 to 2 minutes after paying)..."))
    while time.time() < deadline:
        time.sleep(interval)
        code, s = api("GET", f"/v1/packages/{r['pack']}/checkout")
        if code == 200 and s.get("owned"):
            say(t("결제가 확인됐어요. 바로 설치할게요.", "Payment confirmed. Installing now."))
            mark.unlink(missing_ok=True)
            return cmd_install(argparse.Namespace(feature=r["pack"], client=a.client, scope=a.scope, force=False))
    say(t(f"아직 결제가 확인되지 않았어요. 결제했다면 잠시 뒤 다시: {GET} buy {r['pack']} --wait",
          f"Payment is not confirmed yet. If you paid, try again shortly: {GET} buy {r['pack']} --wait"))
    return 4


def opener(url, system=None, wsl=None, which=None):
    """기본 브라우저로 여는 명령: macOS open · WSL wslview(없으면 cmd.exe start) · 리눅스 xdg-open. 윈도우 그대로는 open_url 이 os.startfile."""
    system, which = system or platform.system(), which or shutil.which
    wsl = is_wsl() if wsl is None else wsl
    if system == "Darwin":
        cands = [["open", url]]
    elif wsl:
        cands = [["wslview", url], ["cmd.exe", "/c", "start", '""', url.replace("&", "^&")]]
    else:
        cands = [["xdg-open", url]]
    return next((c for c in cands if which(c[0])), None)


def open_url(url):
    if os.environ.get("BUILDERLOG_NO_BROWSER"):
        return ""
    if IS_WIN:
        try:
            os.startfile(url)
        except OSError:
            return ""
        return "start"
    cmd = opener(url)
    if not cmd:
        return ""
    try:
        subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        return ""
    return cmd[0]


# ── AI 도구에 등록: 스킬(사용법)·로컬 MCP(팩 도구)·원격 MCP 중계 ──
def project_dir():
    """'project' 범위로 등록할 때의 프로젝트 폴더: BUILDERLOG_PROJECT_DIR(시험·자동화) 또는 지금 폴더.
    홈 폴더에서 실행되면 사용자 범위와 겹치므로(~/.claude/skills) 그때는 '프로젝트 범위'를 쓰지 않는다."""
    d = Path(os.environ.get("BUILDERLOG_PROJECT_DIR") or Path.cwd()).resolve()
    if d == Path.home().resolve():
        raise Stop(t("프로젝트 범위 등록은 홈 폴더가 아닌 프로젝트 폴더에서 해 주세요(또는 --scope user).", "Run project-scope setup from a project folder, not your home folder (or use --scope user)."))
    return d


def claude_dir():
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


def codex_dir():
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def clients(choice):
    if choice in ("claude-code", "codex"):
        return [choice]
    if choice == "none":
        return []
    d = detect_client()
    if d != "auto":
        return [d]
    return [c for c, exe in (("claude-code", "claude"), ("codex", "codex")) if shutil.which(exe)]


def scope_of(scope):
    return scope or os.environ.get("BUILDERLOG_SCOPE") or "user"


def run_quiet(cmd, cwd=None):
    try:
        return subprocess.run(resolve_exe(cmd), capture_output=True, text=True, timeout=60, cwd=cwd).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


SKILLS = {}  # 이번 실행에서 스킬을 넣은 곳(패치 때 같은 곳을 새 안내서로 바꾼다)


def skill_text(pack, dest, title, goal):
    g = guide_of(dest, "CLAUDE.md")
    if LANG == "en":
        return (f"---\nname: builderlog-{pack}\ndescription: {title} (Builderlog). Use it when the user asks for something like \"{trigger(pack)}\" ({goal}). "
                f"Follow the steps in {show(dest)}/{g}.\n---\n# {title}\n\n"
                f"1. Read `{show(dest)}/{g}` and follow its steps (one question at a time; paid generation or posting only after the user approves).\n"
                f"2. Run commands in the `{show(dest)}` folder.\n"
                f"3. Update only with `{GET} update {pack}`. Do not turn on the pack's own updater (`onboarding.py update` or `--schedule on`).\n"
                "4. The guide may be written in Korean. Talk to the user in English.\n")
    return (f"---\nname: builderlog-{pack}\ndescription: {title}(빌더로그). 사용자가 \"{trigger(pack)}\"처럼 {goal} 만들기를 부탁하면 쓴다. "
            f"{show(dest)}/{g} 절차를 따른다.\n---\n# {title}\n\n"
            f"1. `{show(dest)}/{g}` 를 읽고 그 절차대로 진행한다(한 번에 질문 하나, 비용이 드는 생성·게시는 사용자 승인 뒤).\n"
            f"2. 명령은 `{show(dest)}` 폴더에서 실행한다.\n"
            f"3. 업데이트는 `{GET} update {pack}` 로만 한다. 패키지 자체 업데이트(`onboarding.py update`·`--schedule on`)는 켜지 않는다.\n")


def register(pack, dest, choice, scope=None):
    scope, done = scope_of(scope), []
    package = (dest / "onboarding.json").is_file() and not (dest / "SKILL.md").is_file()
    meta = installed().get(pack, {})
    py = venv_py(dest)
    server = [str(py if py.exists() else sys.executable), str(dest / "mcp-server/server.py"), "--packs", pack]
    name = f"builderlog-{pack}"
    for c in clients(choice):
        if c == "claude-code":
            skills = (project_dir() / ".claude/skills") if scope == "project" else claude_dir() / "skills"
            (skills / name).mkdir(parents=True, exist_ok=True)
            if package:
                (skills / name / "SKILL.md").write_text(skill_text(pack, dest, meta.get("title", pack), meta.get("goal", pack)), encoding="utf-8")
            else:
                shutil.copyfile(dest / "SKILL.md", skills / name / "SKILL.md")
            SKILLS.setdefault(pack, []).append(str(skills / name / "SKILL.md"))
            done.append(t(f"Claude Code 스킬 {name}", f"Claude Code skill {name}"))
            if package:
                write_block((project_dir() / "CLAUDE.md") if scope == "project" else claude_dir() / "CLAUDE.md", "claude")
                done.append(t("Claude Code 안내(CLAUDE.md)", "Claude Code guide (CLAUDE.md)"))
            elif shutil.which("claude") and (dest / "mcp-server/server.py").is_file():
                s = "local" if scope == "project" else "user"
                run_quiet(["claude", "mcp", "remove", "-s", s, name])
                if run_quiet(["claude", "mcp", "add", "-s", s, name, "--", *server]):
                    done.append(t(f"Claude Code 로컬 도구 {name}", f"Claude Code local tool {name}"))
        if c == "codex":
            agents_block(scope)
            done.append(t("Codex 안내(AGENTS.md)", "Codex guide (AGENTS.md)"))
            if not package and shutil.which("codex") and scope != "project" and (dest / "mcp-server/server.py").is_file():
                run_quiet(["codex", "mcp", "remove", name])
                if run_quiet(["codex", "mcp", "add", name, "--", *server]):
                    done.append(t(f"Codex 로컬 도구 {name}", f"Codex local tool {name}"))
    return done


def block_lines(which):
    """설치된 팩마다 '이런 부탁이면 이 절차서' 한 줄(Claude Code 는 CLAUDE.md, Codex 는 AGENTS.md 를 먼저)."""
    inst = installed()
    lines = ["<!-- builderlog start -->", t("## 빌더로그 팩(설치됨)", "## Builderlog packs (installed)"),
             t(f"대화를 시작하면 `{GET} news` 를 한 번 실행해 새 소식이 있으면 3줄로 알려 주세요.",
               f"When a conversation starts, run `{GET} news` once and, if there is news, tell the user in 3 lines or fewer.")]
    if LANG == "en":
        lines.append("Talk to the user in English. The pack guides may be written in Korean.")
    for k, v in inst.items():
        dest = ROOT / k
        if v.get("kind") == "package":
            g = guide_of(dest, "CLAUDE.md" if which == "claude" else "AGENTS.md")
            lines.append(t(f"- {v.get('title', k)}: 사용자가 \"{trigger(k)}\"처럼 {v.get('goal') or v.get('title', k)} 만들기를 부탁하면 "
                           f"`{show(dest)}/{g}` 를 읽고 그 절차대로 진행(명령은 `{show(dest)}` 폴더에서).",
                           f"- {v.get('title', k)}: when the user asks for something like \"{trigger(k)}\" ({v.get('goal') or v.get('title', k)}), "
                           f"read `{show(dest)}/{g}` and follow its steps (run commands in `{show(dest)}`)."))
        else:
            lines.append(t(f"- {v.get('title', k)}: `{show(dest)}/SKILL.md` 를 읽고 그 안내대로 실행(명령은 `{show(dest)}` 폴더에서).",
                           f"- {v.get('title', k)}: read `{show(dest)}/SKILL.md` and follow it (run commands in `{show(dest)}`)."))
    if any(v.get("kind") == "package" for v in inst.values()):
        lines.append(t(f"- 팩 업데이트는 빌더로그 도우미만 해요: `{GET} update`. 패키지 자체 업데이트(`onboarding.py update`·`--schedule on`)는 켜지 마세요(둘이 같이 돌면 안 돼요).",
                       f"- Only the Builderlog helper updates packs: `{GET} update`. Do not turn on the pack's own updater (`onboarding.py update` or `--schedule on`); the two must not run together."))
    return lines + ["<!-- builderlog end -->"] if inst else []


def write_block(path, which):
    """안내 파일의 빌더로그 칸만 새로 쓴다(사용자 내용은 그대로). 쓴 곳은 기억해 두고 설치·업데이트·삭제 때 같이 고친다."""
    path = Path(path)
    old = path.read_text(encoding="utf-8") if path.is_file() else ""
    if "<!-- builderlog start -->" in old:
        head, rest = old.split("<!-- builderlog start -->", 1)
        old = head + (rest.split("<!-- builderlog end -->", 1)[1] if "<!-- builderlog end -->" in rest else "")
    lines = block_lines(which)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = old.strip()
    path.write_text((body + ("\n\n" if body and lines else "") + "\n".join(lines)).strip() + "\n" if (body or lines) else "", encoding="utf-8")
    blocks = read_json(STATE / "blocks.json", {}) or {}
    blocks[str(path)] = which
    write_json(STATE / "blocks.json", blocks)


def refresh_blocks():
    for path, which in (read_json(STATE / "blocks.json", {}) or {}).items():
        if Path(path).is_file():
            write_block(path, which)


def agents_block(scope):
    write_block((project_dir() / "AGENTS.md") if scope == "project" else codex_dir() / "AGENTS.md", "codex")


def cmd_connect(a):
    cmd = [sys.executable, str(HELPER), "mcp"]
    done = []
    for c in clients(a.client):
        if c == "claude-code" and shutil.which("claude"):
            s = "local" if scope_of(a.scope) == "project" else "user"
            run_quiet(["claude", "mcp", "remove", "-s", s, "builderlog"])
            if run_quiet(["claude", "mcp", "add", "-s", s, "builderlog", "--", *cmd]):
                done.append("Claude Code")
        if c == "codex" and shutil.which("codex"):
            run_quiet(["codex", "mcp", "remove", "builderlog"])
            if run_quiet(["codex", "mcp", "add", "builderlog", "--", *cmd]):
                done.append("Codex")
    if done:
        say(t(f"빌더로그 원격 MCP 를 연결했어요: {', '.join(done)} (도구: 기능 목록·설치·업데이트·바뀐 점·계정). 토큰은 파일에서만 읽어요. AI 를 다시 열면 보여요.",
              f"Connected the Builderlog remote MCP: {', '.join(done)} (tools: pack list, install, update, news, account). The token is read only from a file. Reopen the AI to see it."))
    else:
        say(t("자동 등록할 AI 도구를 못 찾았어요. 직접: ", "No AI tool found to set up automatically. Do it yourself: ") + "claude mcp add -s user builderlog -- " + " ".join(cmd) + "  (Codex: codex mcp add builderlog -- …)")
    return 0


def cmd_mcp(a):
    """표준입출력 MCP 중계: AI 도구 ↔ {ORIGIN}/mcp. 토큰은 요청마다 파일에서 읽는다(클라이언트 설정에 남지 않음)."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        ids = [m.get("id") for m in (msg if isinstance(msg, list) else [msg]) if isinstance(m, dict) and "id" in m]
        tok = token()
        local = brain_local(msg) if isinstance(msg, dict) else None
        if local is not None:  # AI 뇌 도구는 이 컴퓨터 안에서만 실행(서버로 보내지 않음)
            sys.stdout.write(json.dumps(local, ensure_ascii=False) + "\n")
            sys.stdout.flush()
            continue
        if not tok:
            out = [{"jsonrpc": "2.0", "id": i, "error": {"code": -32001, "message": t(f"빌더로그 로그인이 필요해요: {GET} login",
                                                                                        f"Builderlog login needed: {GET} login")}} for i in ids]
        else:
            req = urllib.request.Request(ORIGIN + "/mcp", method="POST", data=line.encode(), headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                                                                                                    "Authorization": "Bearer " + tok, **HEADERS})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    body = r.read()
                out = json.loads(body) if body.strip() else None
            except urllib.error.HTTPError as e:
                msg_text = (t(f"빌더로그 로그인이 끊겼어요: {GET} login", f"Builderlog login expired: {GET} login") if e.code == 401
                            else t(f"빌더로그 서버 오류({e.code})", f"Builderlog server error ({e.code})"))
                out = [{"jsonrpc": "2.0", "id": i, "error": {"code": -32001, "message": msg_text}} for i in ids]
            except (OSError, ValueError) as e:
                out = [{"jsonrpc": "2.0", "id": i, "error": {"code": -32002, "message": t(f"빌더로그 서버에 연결하지 못했어요: {e}", f"Could not reach the Builderlog server: {e}")}} for i in ids]
        if out is None or out == []:
            continue
        if isinstance(out, list) and not isinstance(msg, list):
            out = out[0] if out else None
        if out is not None and isinstance(msg, dict) and msg.get("method") == "tools/list":
            brain_listed(out)
        if out is not None:
            sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


# ── AI 뇌(brain.py): 보관함 읽기·쓰기는 이 컴퓨터 안에서만. 서버에는 파일 내려받기(구독 확인)뿐이고 대화·노트는 올라가지 않는다 ──
# brain.py 의 sha256: tools/embed_client.py 가 client/brain.py 로 채운다(이 get.py 의 출시 서명이 brain.py 도 보증)
BRAIN_SHA256 = "1e7a220281fa945c6d5e078ebca8ee4d4f17b6cd63bbfb8d59632f52a32f6ef1"
BRAIN = ROOT / "brain" / "brain.py"
BRAIN_NAMES = ("brain_setup", "brain_recall", "brain_note")
_S = {"type": "string"}
BRAIN_TOOLS = [
    {"name": "brain_setup", "title": "AI 뇌 설치·상태", "description": "[구독] AI 뇌(내 컴퓨터 안 옵시디언 보관함: 내 지시·실패·지식을 프로젝트별로 쌓고 다음 요청 때 먼저 꺼내 줌)의 상태 확인·설치·제거. "
     "설치·제거는 사용자에게 무엇이 바뀌는지 말하고 동의를 받은 뒤 confirmed=true 로 다시 부르세요. 모든 처리는 이 컴퓨터 안에서만 일어나요.",
     "inputSchema": {"type": "object", "properties": {"action": {"type": "string", "enum": ["status", "install", "uninstall", "mine_on", "mine_off"], "description": "기본 status"},
                                                       "vault": {**_S, "description": "install 때 보관함 폴더(기본 ~/Documents/AI Brain)"}, "confirmed": {"type": "boolean", "description": "사용자가 동의했을 때만 true(install·uninstall)"}}}},
    {"name": "brain_recall", "title": "AI 뇌 기억 꺼내기", "description": "[구독] 이 요청과 겹치는 과거 실패·원칙을 내 AI 뇌에서 최대 5줄 꺼내요. 어려운 일을 시작하기 전에 부르세요(훅이 없는 AI 도구용).",
     "inputSchema": {"type": "object", "properties": {"query": {**_S, "description": "지금 하려는 일"}}, "required": ["query"]}},
    {"name": "brain_note", "title": "AI 뇌에 기록", "description": "[구독] 사용자의 지시·실패·새 지식을 그 프로젝트 노트에 한 줄 기록해요. 비밀값은 자동으로 지우지만 키·비밀번호·개인정보는 넣지 마세요.",
     "inputSchema": {"type": "object", "properties": {"project": {**_S, "description": "프로젝트 이름(작업 폴더의 git 루트 폴더 이름)"}, "kind": {"type": "string", "enum": ["지시", "시행착오", "지식"]}, "text": {**_S, "description": "한 줄"}},
                     "required": ["project", "kind", "text"]}},
]


def ensure_brain():
    """brain.py 를 ~/builderlog/brain/ 에 두고(구독 확인 · sha256 일치) 이미 설치된 뇌의 복사본도 같은 판으로 맞춘다."""
    if BRAIN.is_file() and sha256_file(BRAIN) == BRAIN_SHA256:
        return
    req = urllib.request.Request(ORIGIN + "/v1/brain.py", headers={**HEADERS, "Authorization": "Bearer " + (token() or "")})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        raise Stop(t(f"AI 뇌는 구독 중인 팩이 있을 때 받을 수 있어요(로그인: {GET} login · 목록: get.py list).", f"AI Brain needs an active pack subscription (log in: {GET} login).") if e.code in (401, 403)
                   else t(f"AI 뇌 파일을 받지 못했어요({e.code}).", f"Could not download AI Brain ({e.code})."))
    except OSError as e:
        raise Stop(t(f"AI 뇌 파일을 받지 못했어요: {e}", f"Could not download AI Brain: {e}"))
    if hashlib.sha256(data).hexdigest() != BRAIN_SHA256:
        raise Stop(t(f"AI 뇌 파일이 이 도우미가 기대한 것과 달라 쓰지 않았어요. 도우미를 업데이트해 주세요: {GET} update", f"AI Brain file does not match this helper, so it was not used. Update the helper: {GET} update"))
    BRAIN.parent.mkdir(parents=True, exist_ok=True)
    BRAIN.write_bytes(data)
    live = Path(os.environ.get("HOME") or os.environ.get("USERPROFILE") or Path.home()) / ".config/ai-brain/brain.py"
    if live.is_file():
        shutil.copyfile(BRAIN, live)


def run_brain(args):
    ensure_brain()
    r = subprocess.run([sys.executable, str(BRAIN), *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300, stdin=subprocess.DEVNULL)
    return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()


def brain_text(name, a):
    a = a if isinstance(a, dict) else {}
    if name == "brain_recall":
        q = str(a.get("query") or "").strip()
        return run_brain(["recall", q]) if q else (2, "query 가 필요해요.")
    if name == "brain_note":
        return run_brain(["note", "--project", str(a.get("project") or ""), "--kind", str(a.get("kind") or ""), "--text", str(a.get("text") or "")])
    act = a.get("action") or "status"
    if act == "status":
        return run_brain(["status"])
    if act in ("mine_on", "mine_off"):
        return run_brain(["mine", "--enable" if act == "mine_on" else "--disable"])
    if act not in ("install", "uninstall"):
        return 2, "action 은 status · install · uninstall · mine_on · mine_off 중 하나예요."
    if not a.get("confirmed"):
        what = ("이 컴퓨터에 옵시디언 보관함(기본 ~/Documents/AI Brain)을 만들고, ~/.claude/settings.json 에 훅 2개와 ~/.claude/CLAUDE.md·~/.codex/AGENTS.md 맨 아래 표시 구역을 추가하고(설치 전 백업), 2시간마다 수집 예약을 켭니다(macOS launchd · Linux cron · Windows 작업 스케줄러). 대화·노트는 어디로도 전송되지 않아요."
                if act == "install" else "추가한 훅·규칙 구역·예약을 지우고 settings.json 을 설치 전 상태로 되돌려요. 쌓인 노트는 남겨요.")
        return 0, f"사용자 동의가 필요해요. {what} 동의하면 confirmed=true 로 다시 부르세요."
    args = ["install", "--yes", *(["--vault", str(a["vault"])] if a.get("vault") else [])] if act == "install" else ["uninstall"]
    return run_brain(args)


def brain_local(msg):
    """tools/call 이 AI 뇌 도구면 이 컴퓨터에서 실행한 JSON-RPC 응답, 아니면 None(서버로 중계)."""
    p = msg.get("params") if isinstance(msg.get("params"), dict) else {}
    if msg.get("method") != "tools/call" or p.get("name") not in BRAIN_NAMES:
        return None
    try:
        if not token():
            raise Stop(t(f"빌더로그 로그인이 필요해요: {GET} login", f"Builderlog login needed: {GET} login"))
        code, text = brain_text(p["name"], p.get("arguments"))
        bad = code != 0
    except Stop as e:
        text, bad = str(e), True
    except (OSError, subprocess.SubprocessError) as e:
        text, bad = f"AI 뇌를 실행하지 못했어요: {e}", True
    return {"jsonrpc": "2.0", "id": msg.get("id"), "result": {"content": [{"type": "text", "text": text}], "isError": bad}}


def brain_listed(out):
    """서버의 tools/list 응답에 AI 뇌 도구 3개를 더한다(이미 있으면 그대로)."""
    res = out.get("result") if isinstance(out, dict) else None
    if isinstance(res, dict) and isinstance(res.get("tools"), list) and not any(x.get("name") in BRAIN_NAMES for x in res["tools"] if isinstance(x, dict)):
        res["tools"] += [{**x, "annotations": {"title": x["title"], "readOnlyHint": x["name"] == "brain_recall"}} for x in BRAIN_TOOLS]


def cmd_brain(a):
    args = [x for x in a.args if x != "--"]
    ensure_brain()
    return subprocess.run([sys.executable, str(BRAIN), *(args or ["status"])]).returncode


# ── 업데이트·소식 ──
def cmd_update(a):
    inst = installed()
    self_update(a.auto)
    if not inst:
        say(t("설치된 팩이 없어요.", "No packs installed."))
        return 0
    news, legacy = [], []
    for pack, v in list(inst.items()):
        if a.feature and pack != a.feature:
            continue
        if v.get("kind") != "package":
            legacy.append(pack)
            continue
        code, info = api("GET", f"/v1/packages/{pack}/latest?platform={plat()}")
        if code == 403:
            say(t(f"- {v.get('title', pack)}: 구독(또는 구매)이 확인되지 않아 업데이트를 받지 않았어요. 설치된 {v.get('version')} 은 그대로예요.",
                  f"- {v.get('title', pack)}: no active subscription was found, so no update was downloaded. Your installed {v.get('version')} stays."))
            continue
        if code != 200:
            say(t(f"- {v.get('title', pack)}: 업데이트를 확인하지 못했어요({code}).", f"- {v.get('title', pack)}: could not check for updates ({code})."))
            continue
        if vnum(info["version"]) <= vnum(v.get("version")):
            continue
        if a.check:
            say(f"- {pack}: {v.get('version')} → {info['version']} ({t('바뀐 점', 'changes')}: {info.get('notes', '')})")
            continue
        try:
            _, kept = install_package(pack, a, info=info, quiet=True)
        except Stop as e:
            say(f"- {v.get('title', pack)}: {e}")
            continue
        for skill in inst[pack].get("skills", []):
            if Path(skill).is_file():
                Path(skill).write_text(skill_text(pack, ROOT / pack, installed()[pack].get("title", pack), installed()[pack].get("goal", pack)), encoding="utf-8")
        lines = [t(f"- {v.get('title', pack)} {v.get('version')} → {info['version']} (자동 업데이트 적용됨) · 바뀐 점: {info.get('notes', '')}",
                   f"- {v.get('title', pack)} {v.get('version')} → {info['version']} (auto-update applied) · changes: {info.get('notes', '')}")]
        if kept:
            lines.append(t(f"  내가 고친 파일 {len(kept)}개는 그대로 두고 새 내용은 .new 로 받았어요: {', '.join(kept[:5])}",
                           f"  Kept {len(kept)} file(s) you changed; the new versions are saved as .new: {', '.join(kept[:5])}"))
        news += lines
        say("\n".join(lines))
    if legacy and not a.auto:
        say(t("예전 키트(" + ", ".join(legacy) + f")는 더 이상 업데이트되지 않아요. 가진 팩이면 전체 패키지로: {GET} uninstall <팩> → install <팩>",
              "Old kits (" + ", ".join(legacy) + f") no longer get updates. If you have the pack, switch to the full pack: {GET} uninstall <pack> → install <pack>"))
    if news:
        refresh_blocks()
        with open(STATE / "news.md", "a", encoding="utf-8") as f:
            f.write(f"## {time.strftime('%Y-%m-%d')} {t('빌더로그 업데이트', 'Builderlog update')}\n" + "\n".join(news) + "\n")
    elif not a.auto and not a.check:
        say(t("모두 최신이에요.", "Everything is up to date."))
    return 0


def self_update(quiet):
    if not HELPER.is_file() or os.environ.get("BUILDERLOG_NO_SELF_UPDATE"):
        return
    tmp = STATE / "get.py.new"
    try:
        fetch(ORIGIN + "/get.py", tmp, timeout=30)
    except Stop:
        return
    digest, text = sha256_file(tmp), tmp.read_text(encoding="utf-8", errors="replace")
    if digest != sha256_file(HELPER) and text.startswith("#!/usr/bin/env python3"):
        new = next((x.split('"')[1] for x in text.splitlines() if x.startswith('VERSION = "')), "")
        try:
            if vnum(new) < vnum(VERSION):  # 되돌리기 공격(옛 버전) 막기. 같은 번호는 받는다
                raise Stop(t(f"get.py {new}: 지금({VERSION})보다 옛 버전이라 바꾸지 않았어요.", f"get.py {new}: older than the current one ({VERSION}), so it was not replaced."))
            code, s = api("GET", "/get.py.sig", auth=False)
            s = s if code == 200 and s.get("sha256") == digest else {}  # 배포 사이에 받은 다른 판의 서명이면 서명 없음과 같게
            release_ok(f"get.py {new}", getpy_message(new, digest), s.get("sig"), s.get("kid"))
            os.replace(tmp, HELPER)
            if not quiet:
                say(t("도우미(get.py)도 새 버전으로 바꿨어요.", "The helper (get.py) was also updated."))
        except (Stop, ValueError, AttributeError) as e:  # 서명 응답이 이상해도 지금 도우미는 그대로 두고 업데이트는 이어 간다
            if not quiet:
                say(str(e))
    tmp.unlink(missing_ok=True)


def cmd_news(a):
    f = STATE / "news.md"
    if not f.is_file():
        if not a.hook:
            say(t("새 소식이 없어요.", "No news."))
        return 0
    text = f.read_text(encoding="utf-8").strip()
    say((t("[빌더로그 업데이트 소식 — 사용자에게 3줄 안으로 알려 주세요]\n", "[Builderlog update news: tell the user in 3 lines or fewer]\n") if a.hook else "") + text)
    with open(STATE / "news-read.md", "a", encoding="utf-8") as r:
        r.write(text + "\n")
    f.unlink()
    return 0


# ── 하루 1번 ──
def plist_path():
    return Path(os.environ.get("BUILDERLOG_LAUNCHD_DIR") or Path.home() / "Library/LaunchAgents") / f"{LABEL}.plist"


def hook_settings(scope):
    return (project_dir() / ".claude/settings.json") if scope == "project" else claude_dir() / "settings.json"


def news_command():
    return f'"{sys.executable}" "{HELPER}" news --hook'


def set_hook(scope, on):
    path = hook_settings(scope)
    data = read_json(path, {}) if path.is_file() else {}
    if path.is_file() and not data and path.read_text(encoding="utf-8").strip():
        say(t(f"{path} 를 읽지 못해 소식 알림 훅은 건너뛰었어요.", f"Could not read {path}, so the news hook was skipped."))
        return False
    groups = [g for g in data.get("hooks", {}).get("SessionStart", []) if not any("get.py" in h.get("command", "") and "news" in h.get("command", "") for h in g.get("hooks", []))]
    if on:
        if path.is_file() and not (path.with_name(path.name + ".builderlog-backup")).exists():
            shutil.copyfile(path, path.with_name(path.name + ".builderlog-backup"))
        groups.append({"hooks": [{"type": "command", "command": news_command()}]})
    data.setdefault("hooks", {})["SessionStart"] = groups
    if not groups:
        data["hooks"].pop("SessionStart")
        if not data["hooks"]:
            data.pop("hooks")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def cmd_schedule(a):
    scope, system = scope_of(a.scope), platform.system()
    state = read_json(STATE / "schedule.json", {}) or {}
    cmd = [sys.executable, str(HELPER), "update", "--auto"]
    log = STATE / "update.log"
    if a.action == "status":
        return cmd_status(a)
    if a.action == "on":
        hour, minute = 10, random.randint(0, 59)
        if system == "Darwin":
            p = plist_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            args = "".join(f"<string>{x}</string>" for x in cmd)
            p.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict><key>Label</key><string>{LABEL}</string><key>ProgramArguments</key><array>{args}</array>
<key>StartCalendarInterval</key><dict><key>Hour</key><integer>{hour}</integer><key>Minute</key><integer>{minute}</integer></dict>
<key>StandardOutPath</key><string>{log}</string><key>StandardErrorPath</key><string>{log}</string></dict></plist>
""", encoding="utf-8")
            if not os.environ.get("BUILDERLOG_NO_SYSTEM"):
                uid = str(os.getuid())
                run_quiet(["launchctl", "bootout", f"gui/{uid}", str(p)])
                run_quiet(["launchctl", "bootstrap", f"gui/{uid}", str(p)])
            kind = "launchd"
        elif IS_WIN:
            set_task(task_cmd(hour, minute))
            kind = "schtasks"
        else:
            line = f"{minute} {hour} * * * {' '.join(cmd)} >> {log} 2>&1 # {MARK}"
            set_cron(line)
            kind = "cron"
        hooks = []
        for c in clients(a.client):
            if c == "claude-code" and set_hook(scope, True):
                hooks.append(t("Claude Code 대화 시작 알림", "Claude Code session-start notice"))
            if c == "codex":
                agents_block(scope)
                hooks.append(t("Codex AGENTS.md 알림", "Codex AGENTS.md notice"))
        write_json(STATE / "schedule.json", {"on": True, "kind": kind, "hour": hour, "minute": minute, "hooks": hooks, "scope": scope})
        say(t(f"하루 1번 업데이트 확인을 켰어요: 매일 {hour}:{minute:02d}({kind}). 새 버전이면 패치하고(내가 고친 파일은 그대로) 바뀐 점을 다음 대화 때 알려 드려요."
              + (f" 알림: {', '.join(hooks)}." if hooks else ""),
              f"Daily update check is on: every day at {hour}:{minute:02d} ({kind}). New versions are patched in (files you changed stay) and the changes are shown in your next conversation."
              + (f" Notices: {', '.join(hooks)}." if hooks else "")))
        if kind == "cron" and "microsoft" in platform.release().lower():
            say(t("WSL 은 cron 이 꺼져 있을 수 있어요: sudo service cron start (Windows 를 켤 때마다 필요하면 알려 주세요)", "cron may be off in WSL: sudo service cron start (you may need this each time Windows starts)"))
        say(t(f"끄기: {GET} schedule off", f"Turn off: {GET} schedule off"))
        return 0
    # off
    p = plist_path()
    if p.is_file():
        if not os.environ.get("BUILDERLOG_NO_SYSTEM"):
            run_quiet(["launchctl", "bootout", f"gui/{os.getuid()}", str(p)])
        p.unlink()
    if IS_WIN:
        set_task(None)
    elif system != "Darwin":
        set_cron(None)
    set_hook(state.get("scope") or scope, False)
    write_json(STATE / "schedule.json", {"on": False})
    say(t(f"하루 1번 업데이트 확인을 껐어요. 다시 켜기: {GET} schedule on", f"Daily update check is off. Turn it on again: {GET} schedule on"))
    return 0


TASK = "Builderlog Update"


def task_cmd(hour, minute):
    """schtasks 로 넣을 명령: 창이 뜨지 않게 pythonw(있으면). 출력은 main 이 update.log 로 돌린다(pythonw 는 stdout 이 없음)."""
    py = Path(sys.executable)
    w = py.with_name("pythonw.exe")
    tr = f'"{w if w.is_file() else py}" "{HELPER}" update --auto'
    return ["schtasks", "/Create", "/F", "/SC", "DAILY", "/TN", TASK, "/ST", f"{hour:02d}:{minute:02d}", "/TR", tr]


def set_task(cmd):
    """윈도우 작업 스케줄러에 넣기(cmd)·빼기(None). 시험은 BUILDERLOG_TASK_FILE 에 명령을 적는다."""
    cmd = cmd or ["schtasks", "/Delete", "/F", "/TN", TASK]
    alt = os.environ.get("BUILDERLOG_TASK_FILE")
    if alt:
        Path(alt).write_text(json.dumps(cmd, ensure_ascii=False), encoding="utf-8")
        return True
    if os.environ.get("BUILDERLOG_NO_SYSTEM"):
        return True
    ok, why = run_reason(cmd)
    if not ok and cmd[1] == "/Create":
        say(t(f"작업 스케줄러에 넣지 못했어요({why}). 나중에 다시: {GET} schedule on", f"Could not add it to Task Scheduler ({why}). Try later: {GET} schedule on"))
    return ok


def set_cron(line):
    alt = os.environ.get("BUILDERLOG_CRONTAB_FILE")
    if alt:
        cur = Path(alt).read_text() if Path(alt).is_file() else ""
    else:
        r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        cur = r.stdout if r.returncode == 0 else ""
    rows = [x for x in cur.splitlines() if MARK not in x] + ([line] if line else [])
    text = "\n".join(rows).strip() + "\n" if rows else ""
    if alt:
        Path(alt).write_text(text)
    else:
        subprocess.run(["crontab", "-"], input=text, text=True, check=False)


def cmd_uninstall(a):
    pack = a.feature
    dest = ROOT / pack
    for c in ("claude-code", "codex"):
        if c == "claude-code":
            shutil.rmtree(claude_dir() / "skills" / f"builderlog-{pack}", ignore_errors=True)
            if shutil.which("claude"):
                run_quiet(["claude", "mcp", "remove", "-s", "user", f"builderlog-{pack}"])
        elif shutil.which("codex"):
            run_quiet(["codex", "mcp", "remove", f"builderlog-{pack}"])
    inst = installed()
    inst.pop(pack, None)
    write_json(STATE / "installed.json", inst)
    refresh_blocks()
    if dest.is_dir() and ((dest / "feature.json").is_file() or (dest / "onboarding.json").is_file()):
        trash = ROOT / ".trash" / f"{pack}-{int(time.time())}"
        trash.parent.mkdir(parents=True, exist_ok=True)
        dest.rename(trash)
        say(t(f"{pack} 를 지웠어요(폴더는 {trash} 로 옮김 — 내 설정·결과를 꺼낼 수 있어요).", f"Removed {pack} (the folder moved to {trash}, so you can still copy out your settings and results)."))
    return 0


# ── 설치 한 줄(curl … /install.sh | bash)의 대화형 진행: 연결 → 로그인 → 고르기 → 설치 → 하루 1번 ──
def ask(question, default=True, yes=False):
    if yes:
        return default
    try:
        a = input(f"{question} {'[Y/n]' if default else '[y/N]'} ").strip().lower()
    except EOFError:
        return default
    return default if not a else a in ("y", "yes", "예", "네", "응", "ㅇ")


def mcp_line(c):
    if c == "claude-code":
        return ["claude", "mcp", "add", "--transport", "http", "-s", "user", "builderlog", ORIGIN + "/mcp"]
    return ["codex", "mcp", "add", "builderlog", "--url", ORIGIN + "/mcp"]


CONNECT = {"found": [], "failed": []}  # 마지막 connect_remote 결과(설치돼 있었는지·등록이 실패했는지 — 안내 문구를 나누려고)


def _is_wsl():
    if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"):
        return True
    try:
        return "microsoft" in Path("/proc/version").read_text(errors="ignore").lower()
    except OSError:
        return False


def _windows_only(exe, win_users="/mnt/c/Users"):
    """WSL 에서 PATH 엔 없는데 윈도우 쪽 npm 폴더(/mnt/c/Users/*/AppData/Roaming/npm)에만 있으면 True."""
    try:
        return any((u / "AppData/Roaming/npm" / n).exists() for u in Path(win_users).iterdir() for n in (exe, exe + ".cmd"))
    except OSError:
        return False


def run_reason(cmd):
    """(성공 여부, 실패 이유 한 줄). 이유는 stderr 첫 줄(없으면 종료 코드) — 긴 출력은 자른다."""
    try:
        r = subprocess.run(resolve_exe(cmd), capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return False, t("60초 안에 끝나지 않았어요", "timed out after 60 s")
    except OSError as e:
        return False, str(e)[:120]
    if r.returncode == 0:
        return True, ""
    lines = [x.strip() for x in (r.stderr or r.stdout or "").splitlines() if x.strip()]
    return False, (lines[0][:160] if lines else t(f"종료 코드 {r.returncode}", f"exit code {r.returncode}"))


def win_npm_steps(exe):
    """WSL 에서 윈도우용 claude/codex 가 잡혔을 때(경로가 /mnt/c/… 이거나 실행하면 'node: not found') — 우분투 안에 Node.js(nvm)·도구 설치 4단계.
    10/27 고객 문의: WSL 안에 node 가 없어 npm 이 윈도우 npm 으로 돌아 Codex 가 /mnt/c/Users/…/AppData/Roaming/npm 에 깔림."""
    name, pkg = ("Claude Code", "@anthropic-ai/claude-code") if exe == "claude" else ("Codex", "@openai/codex")
    quit_cmd = "/exit" if exe == "claude" else "/quit"
    nvm = "curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash → source ~/.bashrc → nvm install --lts"
    return [t(f"{name}: 윈도우용이 잡혔어요 — 이 우분투(WSL) 안에 Node.js 가 없어서 npm 이 윈도우 쪽으로 설치했어요. 우분투 터미널에서 차례로:",
              f"{name}: the Windows copy was picked up. This Ubuntu (WSL) has no Node.js, so npm installed it on the Windows side. In the Ubuntu terminal, in order:"),
            t(f"  1) 우분투 안에 Node.js 설치(관리자 비밀번호 없이 돼요): {nvm}", f"  1) Install Node.js inside Ubuntu (no admin password needed): {nvm}"),
            t(f"  2) 우분투 안에 {name} 설치: npm i -g {pkg} → which {exe} 가 /home/ 으로 시작하면 성공(/mnt/c/ 로 나오면 터미널을 껐다 다시 열고 한 번 더 확인)",
              f"  2) Install {name} inside Ubuntu: npm i -g {pkg} → success if which {exe} starts with /home/ (if it shows /mnt/c/, reopen the terminal and check again)"),
            t(f"  3) {name} 로그인: {exe} → 처음 한 번 로그인한 뒤 {quit_cmd} 로 나오기", f"  3) Log in to {name}: {exe} → log in once, then leave with {quit_cmd}"),
            t(f"  4) 빌더로그 연결: {install_line()} → '연결: {name}' 이 나오면 끝", f"  4) Connect Builderlog: {install_line()} → done when it shows 'Connect: {name}'")]


def connect_remote(wsl=None, win_users="/mnt/c/Users", win_root="/mnt/c/"):
    """설치된 AI 도구에 빌더로그 MCP 한 줄 등록(이미 있으면 그대로 — 다시 실행해도 안전).
    못 찾음과 '찾았지만 등록 실패'를 따로 안내하고, 붙여 넣을 한 줄을 함께 보여 준다."""
    done = []
    CONNECT["found"], CONNECT["failed"] = [], []
    wsl = _is_wsl() if wsl is None else wsl
    for c, exe in (("claude-code", "claude"), ("codex", "codex")):
        name = "Claude Code" if exe == "claude" else "Codex"
        direct = " ".join(mcp_line(c))
        path = shutil.which(exe) or ""
        if wsl and path.startswith(win_root):  # PATH 에 붙은 윈도우 npm 폴더의 것 — 우분투 안에서는 node 가 없어 못 돎
            CONNECT["found"].append(name); CONNECT["failed"].append(name)
            for ln in win_npm_steps(exe): say(ln)
            continue
        if not path:
            if wsl and _windows_only(exe, win_users):
                pkg = "@anthropic-ai/claude-code" if exe == "claude" else "@openai/codex"
                say(t(f"{name} 가 윈도우 쪽에만 설치돼 있어요. 이 Ubuntu(WSL) 안에서는 못 써요 — Ubuntu 터미널에서 npm i -g {pkg} 로 설치한 뒤 이 한 줄을 다시 실행하세요.",
                      f"{name} is installed only on the Windows side, not inside this Ubuntu (WSL). Run npm i -g {pkg} in the Ubuntu terminal, then run this line again."))
            continue
        CONNECT["found"].append(name)
        if run_quiet([exe, "mcp", "get", "builderlog"]):
            done.append(f"{name}{t('(이미 연결됨)', ' (already connected)')}")
            continue
        ok, why = run_reason(mcp_line(c))
        if ok:
            done.append(name)
        elif "node: not found" in why or "node: No such file" in why:  # 윈도우용 npm 이 만든 실행 파일(우분투에 node 없음)
            CONNECT["failed"].append(name)
            for ln in win_npm_steps(exe): say(ln)
        else:
            CONNECT["failed"].append(name)
            say(t(f"{name} 는 찾았지만 연결 등록이 안 됐어요({why}). 버전이 오래됐다면 업데이트한 뒤, 아니면 이 한 줄을 직접 붙여 넣어 보세요: {direct}",
                  f"Found {name}, but registering failed ({why}). If it is an old version, update it; otherwise paste this line yourself: {direct}"))
    return done


def logged_in():
    if not token():
        return ""
    try:
        code, me = api("GET", "/v1/account")
    except Stop:
        return ""
    return me.get("account", "") if code == 200 else ""


def connect_only():
    """AI 도구가 설치 한 줄을 대신 실행했을 때(질문할 사람 화면 없음): 도우미는 이미 받았고, AI 도구 연결까지만."""
    conn = connect_remote()
    say(t(f"빌더로그 준비 끝 — 도우미: {show(HELPER)} · AI 도구 연결: ", f"Builderlog is ready. Helper: {show(HELPER)} · AI tools connected: ")
        + (", ".join(conn) if conn else t("연결 못 함(위 안내 확인)", "not connected (see above)") if CONNECT["found"] else t("찾은 AI 도구 없음", "no AI tool found")))
    say(t("이제 AI 에게 '빌더로그 시작해 줘' 라고 하세요. 빌더로그 MCP 가 로그인 → 기능 고르기 → 설치 → 하루 1번 업데이트를 이끌어요.",
          "Now tell your AI: 'start Builderlog'. The Builderlog MCP walks you through login, picking packs, install and daily updates."))
    say(t(f"(AI 에게: 새로 연결한 MCP 도구는 새 대화부터 보여요. 지금 대화에서 바로 이어 가려면 사용자에게 보여 주고 차례로 —"
          f" {GET} login → 사용자가 브라우저에서 코드 입력 → {GET} login --wait →"
          f" {GET} list → install <기능> → 동의를 받은 뒤 schedule on. 토큰·비밀값은 출력하지 마세요.)",
          f"(For the AI: newly added MCP tools appear from the next conversation. To continue in this one, show the user each step and run in order:"
          f" {GET} login → the user enters the code in the browser → {GET} login --wait →"
          f" {GET} list → install <pack> → schedule on after the user agrees. Never print tokens or secrets. Talk to the user in English.)"))
    return 0


def cmd_wizard(a):
    if a.connect_only:
        return connect_only()
    yes = a.yes or bool(os.environ.get("BUILDERLOG_YES"))
    say(t("빌더로그 설치 — 이렇게 진행해요(서버: ", "Builderlog setup: here is the plan (server: ") + ORIGIN + ")")
    say(t("  1. AI 도구 연결: 이 컴퓨터의 Claude Code·Codex 에 빌더로그 MCP 한 줄 등록", "  1. Connect AI tools: add one Builderlog MCP line to Claude Code and Codex on this computer"))
    say(t("  2. 로그인: 주소와 연결 코드가 나오면 브라우저에서 이메일 6자리 코드로 로그인하고 코드를 넣어요",
          "  2. Log in: when an address and a link code appear, log in in the browser with the 6-digit email code and enter the link code"))
    say(t("  3. 내 팩 설치: 전체 패키지 내려받기 → 지문(sha256) 확인 → ~/builderlog/<팩>/ → AI 에 CLAUDE.md·AGENTS.md 절차 연결",
          "  3. Install your packs: download the full pack → check its fingerprint (sha256) → ~/builderlog/<pack>/ → link the CLAUDE.md and AGENTS.md steps to your AI"))
    say(t("  4. 하루 1번 업데이트를 켤지 따로 물어봐요", "  4. You are asked separately whether to turn on daily updates"))
    say(t("  비밀값(토큰)은 화면에 나오지 않고, 다시 실행해도 안전해요. 게시·결제는 하지 않아요.",
          "  Secrets (tokens) never appear on screen, and it is safe to run again. It never posts or pays for you."))
    if not ask(t("진행할까요?", "Continue?"), True, yes):
        say(t("멈췄어요. 언제든 다시: ", "Stopped. Run again any time: ") + install_line())
        return 0
    conn = connect_remote()
    say(t("1) 연결: ", "1) Connect: ") + (", ".join(conn) if conn else (t("연결은 못 했어요(위 이유 확인 — 고친 뒤 이 한 줄을 다시 실행하면 연결돼요). 기능은 터미널에서도 쓸 수 있어요.",
                                                                      "Not connected (see the reason above; fix it, then run this line again). Packs also work from the terminal.") if CONNECT["found"] else
                                                                      t("Claude Code·Codex 를 못 찾았어요(설치 뒤 이 한 줄을 다시 실행하면 연결돼요). 직접 등록: codex mcp add builderlog --url " + ORIGIN + "/mcp · 기능은 터미널에서도 쓸 수 있어요.",
                                                                        "Claude Code and Codex were not found (install one, then run this line again to connect). Manual: codex mcp add builderlog --url " + ORIGIN + "/mcp. Packs also work from the terminal."))))
    who = logged_in()
    if who:
        say(t(f"2) 로그인: 이미 돼 있어요({who})", f"2) Login: already logged in ({who})"))
    else:
        cmd_login(argparse.Namespace(wait=False, again=False, open=not yes, code=None))
        while True:
            p = read_json(STATE / "login-pending", {})
            if not p.get("device_code"):
                break
            rc = wait_login(p)
            if rc == 0:
                break
            if not ask(t("계속 기다릴까요?", "Keep waiting?"), True, yes):
                say(t(f"나중에 이어서: {GET} login --wait", f"Continue later: {GET} login --wait"))
                return 4
    code, r = api("GET", "/v1/features")
    feats = r.get("features", [])
    inst = installed()
    say(t("3) 팩 고르기 — 번호(여러 개는 쉼표). 이용 중인 팩만 설치돼요:", "3) Pick packs by number (comma-separated). Only packs you subscribe to can be installed:"))
    for i, f in enumerate(feats, 1):
        mine = f" · {t('설치됨', 'installed')} {inst[f['id']].get('version')}" if f["id"] in inst else ""
        say(f"  {i:>2}. {f['title']} · {f['status']}{mine}")
    pick = os.environ.get("BUILDERLOG_PICK")
    if pick is None and not yes:
        try:
            pick = input(t("설치할 번호(건너뛰려면 엔터): ", "Numbers to install (Enter to skip): ")).strip()
        except EOFError:
            pick = ""
    chosen = []
    for x in (pick or "").replace(" ", "").split(","):
        f = feats[int(x) - 1] if x.isdigit() and 0 < int(x) <= len(feats) else next((y for y in feats if y["id"] == x), None)
        if f:
            chosen.append(f)
    for f in chosen:
        if not f["entitled"]:
            say(f"  - {f['title']}: {f['status']}" + (t(f" — 결제 페이지 열기: {GET} buy {f['pack']} --wait (확인되면 바로 설치)",
                                                      f". Open checkout: {GET} buy {f['pack']} --wait (installs once payment is confirmed)") if f.get("buy") else ""))
            continue
        say(t(f"  - {f['title']} 설치 중…", f"  - Installing {f['title']}..."))
        cmd_install(argparse.Namespace(feature=f["id"], client="auto", scope=None, force=False))
    s = read_json(STATE / "schedule.json", {}) or {}
    if s.get("on"):
        say(t(f"4) 하루 1번 업데이트: 이미 켜져 있어요(매일 {s.get('hour', 10)}:{s.get('minute', 0):02d})", f"4) Daily updates: already on (every day at {s.get('hour', 10)}:{s.get('minute', 0):02d})"))
    else:
        sched = os.environ.get("BUILDERLOG_SCHEDULE")
        if (sched.lower() in ("y", "yes", "1") if sched is not None else ask(t("4) 하루 1번 새 버전을 확인해 패치하고 바뀐 점을 다음 대화 때 알려 드릴까요?", "4) Check for new versions once a day, patch them in and tell you what changed in your next conversation?"), False, yes)):
            cmd_schedule(argparse.Namespace(action="on", client="auto", scope=None))
        else:
            say(t(f"4) 하루 1번 업데이트: 안 켰어요(켜기: {GET} schedule on)", f"4) Daily updates: not turned on (turn on: {GET} schedule on)"))
    say("")
    say(t("끝났어요. 이제 Claude Code(또는 Codex)를 열고 '빌더로그 시작해 줘' 라고 해 보세요 — 설치한 기능의 첫 결과를 같이 만들어요.",
          "Done. Now open Claude Code (or Codex) and say 'start Builderlog'. You will make the first result of your pack together."))
    say(t(f"상태: {GET} status · 다시 실행: ", f"Status: {GET} status · run again: ") + install_line())
    return 0


def cmd_lang(a):
    """안내 언어 저장(~/builderlog/lang). 환경 변수 BUILDERLOG_LANG 이 있으면 그게 먼저예요. AI 안내 칸(CLAUDE.md·AGENTS.md)도 그 언어로 다시 써요."""
    global LANG, HEADERS
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / "lang").write_text(a.value + "\n", encoding="utf-8")
    LANG = a.value
    HEADERS = {"User-Agent": UA, **({"Accept-Language": "en"} if LANG == "en" else {})}
    refresh_blocks()
    say(t("안내 언어를 한국어로 바꿨어요.", "Language set to English."))
    env = (os.environ.get("BUILDERLOG_LANG") or "").strip().lower()
    if env in ("en", "ko") and env != a.value:
        say(t(f"(이 셸에는 BUILDERLOG_LANG={env} 이 있어 그 언어가 먼저 쓰여요.)", f"(BUILDERLOG_LANG={env} is set in this shell and takes priority here.)"))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="get.py", description=t("빌더로그 도우미", "Builderlog helper"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("login"); p.add_argument("--wait", action="store_true"); p.add_argument("--code", help=t("MCP login_start 가 준 연결 코드", "link code from the MCP login_start tool")); p.add_argument("--again", action="store_true"); p.add_argument("--open", action="store_true")
    sub.add_parser("logout"); sub.add_parser("list"); sub.add_parser("status")
    p = sub.add_parser("brain", help=t("AI 뇌(내 컴퓨터 안 보관함)", "AI Brain (a vault on this computer)")); p.add_argument("args", nargs=argparse.REMAINDER)
    for name in ("install", "uninstall"):
        p = sub.add_parser(name); p.add_argument("feature")
        p.add_argument("--client", default="auto", choices=["auto", "claude-code", "codex", "none"]); p.add_argument("--scope", choices=["user", "project"]); p.add_argument("--force", action="store_true")
    p = sub.add_parser("connect"); p.add_argument("--client", default="auto", choices=["auto", "claude-code", "codex"]); p.add_argument("--scope", choices=["user", "project"])
    sub.add_parser("mcp")
    p = sub.add_parser("wizard"); p.add_argument("--yes", action="store_true"); p.add_argument("--connect-only", action="store_true")
    p = sub.add_parser("update"); p.add_argument("feature", nargs="?"); p.add_argument("--check", action="store_true"); p.add_argument("--auto", action="store_true")
    p = sub.add_parser("schedule"); p.add_argument("action", choices=["on", "off", "status"]); p.add_argument("--client", default="auto", choices=["auto", "claude-code", "codex", "none"]); p.add_argument("--scope", choices=["user", "project"])
    p = sub.add_parser("news"); p.add_argument("--hook", action="store_true")
    p = sub.add_parser("buy"); p.add_argument("feature"); p.add_argument("--wait", action="store_true"); p.add_argument("--yearly", action="store_true", help=t("1년 이용권(결제 페이지에서 팩 옵션을 고름)", "yearly plan"))
    p.add_argument("--client", default="auto", choices=["auto", "claude-code", "codex", "none"]); p.add_argument("--scope", choices=["user", "project"])
    p = sub.add_parser("lang", help=t("안내 언어(영어·한국어)", "message language (English or Korean)")); p.add_argument("value", choices=["en", "ko"])
    a = ap.parse_args(argv)
    STATE.mkdir(parents=True, exist_ok=True)
    if sys.stdout is None:  # 윈도우 작업 스케줄러(pythonw)
        sys.stdout = sys.stderr = open(STATE / "update.log", "a", encoding="utf-8")
    elif IS_WIN and not os.environ.get("PYTHONIOENCODING"):  # AI 가 읽는 파이프 출력은 UTF-8(코드 페이지 cp949 로 한글이 깨지지 않게)
        for f in (sys.stdout, sys.stderr):
            if f and not f.isatty():
                with contextlib.suppress(Exception):
                    f.reconfigure(encoding="utf-8", errors="replace")
    try:
        os.chmod(STATE, 0o700)
    except OSError:
        pass
    fn = {"login": cmd_login, "logout": cmd_logout, "list": cmd_list, "status": cmd_status, "install": cmd_install, "uninstall": cmd_uninstall, "connect": cmd_connect,
          "mcp": cmd_mcp, "update": cmd_update, "schedule": cmd_schedule, "news": cmd_news, "wizard": cmd_wizard, "buy": cmd_buy, "lang": cmd_lang, "brain": cmd_brain}[a.cmd]
    try:
        return fn(a) or 0
    except Stop as e:
        if a.cmd == "update" and getattr(a, "auto", False):
            with open(STATE / "update.log", "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%F %T')} {e}\n")
        print(str(e), file=sys.stderr, flush=True)
        return e.code
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
