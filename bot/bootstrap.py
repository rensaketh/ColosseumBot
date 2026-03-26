import json
import re
import subprocess
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urljoin

from bot.fingerprint import FingerprintProfile, octofence_fp_value
from bot.session import save_cookies, session_cookie_dict

INLINE_SCRIPT_RE = re.compile(r"<script\b[^>]*>(.*?)</script>", re.IGNORECASE | re.DOTALL)
SCRIPT_SRC_RE = re.compile(r"<script\b[^>]*src=['\"]([^'\"]+)['\"][^>]*>\s*</script>", re.IGNORECASE)
SCRIPT_TAG_RE = re.compile(r"<script\b([^>]*)>(.*?)</script>", re.IGNORECASE | re.DOTALL)
SRC_ATTR_RE = re.compile(r"src=['\"]([^'\"]+)['\"]", re.IGNORECASE)


def bootstrap_session(session, cookies_path: str, config: dict, slug: str) -> dict:
    bootstrap_cfg = config.get("bootstrap", {})
    if not bootstrap_cfg.get("enabled", True):
        return {"enabled": False}

    browser_cfg = config.get("browser_profile", {})
    summary = {
        "enabled": True,
        "landing_url": None,
        "visited_urls": [],
        "generated_fp": False,
        "inline_script_found": False,
        "inline_script_count": 0,
        "solved_cookie_names": [],
        "cookies_after_bootstrap": {},
        "preflight_cookie_diffs": [],
    }

    should_generate_fp = bootstrap_cfg.get("generate_fp_cookie", True)
    overwrite_fp_cookie = bootstrap_cfg.get("overwrite_fp_cookie", True)
    if should_generate_fp and (overwrite_fp_cookie or "octofence_jslc_fp" not in session.cookies):
        profile = FingerprintProfile.from_config(browser_cfg)
        session.cookies.set("octofence_jslc_fp", octofence_fp_value(profile))
        summary["generated_fp"] = True

    landing_url = bootstrap_cfg.get("landing_url", "https://ticketing.colosseo.it/")
    summary["landing_url"] = landing_url
    event_url = f"https://ticketing.colosseo.it/en/eventi/{slug}/"
    configured_preflight_urls = bootstrap_cfg.get("preflight_urls")
    if configured_preflight_urls:
        preflight_urls = [landing_url, *configured_preflight_urls]
    else:
        preflight_urls = [landing_url, event_url]

    total_inline_scripts = 0
    solved_cookie_names: set[str] = set()
    for idx, url in enumerate(preflight_urls):
        before_cookies = session_cookie_dict(session)
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none" if idx == 0 else "same-origin",
        }
        response = session.get(url, headers=headers, timeout=bootstrap_cfg.get("timeout_seconds", 20))
        response.raise_for_status()
        summary["visited_urls"].append(str(response.url))
        response_cookies = session_cookie_dict(session)
        dump_page_inventory(
            f"preflight_{idx}",
            response.text,
            str(response.url),
            response_cookies,
        )
        if bootstrap_cfg.get("scan_scripts_for_markers", True):
            scan_scripts_for_markers(session, f"preflight_{idx}", response.text, str(response.url))
        step_summary = {
            "url": str(response.url),
            "set_cookie_headers": _header_list(response.headers, "set-cookie"),
            "cookie_diff_after_response": cookie_diff(before_cookies, response_cookies),
        }

        if bootstrap_cfg.get("solve_inline_script", True):
            scripts = extract_inline_scripts(response.text)
            total_inline_scripts += len(scripts)
            solved = solve_challenge_html(session, response.text, str(response.url), browser_cfg)
            if solved:
                solved_cookie_names.update(solved.keys())
                step_summary["cookie_diff_after_solver"] = cookie_diff(
                    response_cookies,
                    session_cookie_dict(session),
                )
        summary["preflight_cookie_diffs"].append(step_summary)

    summary["inline_script_count"] = total_inline_scripts
    summary["inline_script_found"] = total_inline_scripts > 0
    summary["solved_cookie_names"] = sorted(solved_cookie_names)
    summary["cookies_after_bootstrap"] = session_cookie_dict(session)

    if bootstrap_cfg.get("persist_cookies", True):
        save_cookies(cookies_path, session_cookie_dict(session))

    return summary


def extract_inline_scripts(html: str) -> list[str]:
    return [match.strip() for match in INLINE_SCRIPT_RE.findall(html) if match.strip()]


def extract_script_sources(html: str, base_url: str) -> list[str]:
    return [urljoin(base_url, src.strip()) for src in SCRIPT_SRC_RE.findall(html) if src.strip()]


def extract_script_entries(html: str, base_url: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for attrs, body in SCRIPT_TAG_RE.findall(html):
        src_match = SRC_ATTR_RE.search(attrs)
        if src_match:
            src = src_match.group(1).strip()
            if src:
                entries.append({"kind": "external", "src": urljoin(base_url, src)})
        else:
            script = body.strip()
            if script:
                entries.append({"kind": "inline", "content": script})
    return entries


def cookie_diff(before: dict[str, str], after: dict[str, str]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {"added": {}, "changed": {}, "removed": {}}
    for key, value in after.items():
        if key not in before:
            out["added"][key] = value
        elif before[key] != value:
            out["changed"][key] = value
    for key, value in before.items():
        if key not in after:
            out["removed"][key] = value
    return out


def _header_list(headers, name: str) -> list[str]:
    if hasattr(headers, "get_list"):
        return headers.get_list(name)
    value = headers.get(name)
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def solve_challenge_html(session, html: str, url: str, browser_cfg: dict | None = None) -> dict[str, str]:
    browser_cfg = browser_cfg or session.bot_config.get("browser_profile", {})
    ordered_scripts: list[dict[str, str]] = []
    for entry in extract_script_entries(html, url):
        if entry["kind"] == "inline":
            ordered_scripts.append({"url": url, "content": entry["content"]})
            continue
        src = entry["src"]
        try:
            resp = session.get(src, timeout=10)
        except Exception:
            continue
        content_type = resp.headers.get("content-type", "")
        if 200 <= resp.status_code < 300 and ("javascript" in content_type.lower() or src.endswith(".js")):
            ordered_scripts.append({"url": src, "content": resp.text})

    solved = solve_script_sequence(ordered_scripts, url, browser_cfg)
    if solved:
        session.cookies.update(solved)
        if session.bot_config.get("bootstrap", {}).get("persist_cookies", True):
            save_cookies(session.cookies_path, session_cookie_dict(session))
    return solved


def dump_debug_artifacts(prefix: str, html: str, url: str) -> None:
    debug_dir = Path("debug")
    debug_dir.mkdir(exist_ok=True)
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "_", prefix)
    (debug_dir / f"{slug}.html").write_text(html, encoding="utf-8")
    meta = {
        "url": url,
        "inline_script_count": len(extract_inline_scripts(html)),
        "script_sources": extract_script_sources(html, url),
    }
    (debug_dir / f"{slug}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


def dump_page_inventory(prefix: str, html: str, url: str, cookies: dict[str, str]) -> None:
    debug_dir = Path("debug")
    debug_dir.mkdir(exist_ok=True)
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "_", prefix)
    payload = {
        "url": url,
        "inline_script_count": len(extract_inline_scripts(html)),
        "script_sources": extract_script_sources(html, url),
        "cookies": cookies,
    }
    (debug_dir / f"{slug}_inventory.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def scan_scripts_for_markers(session, prefix: str, html: str, url: str) -> None:
    debug_dir = Path("debug")
    debug_dir.mkdir(exist_ok=True)
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "_", prefix)
    markers = ["octofence_jslc", "jslc", "document.cookie", "new Fingerprint", "fp.get(", "uid ="]
    findings = []
    for src in extract_script_sources(html, url):
        try:
            resp = session.get(src, timeout=10)
        except Exception as exc:
            findings.append({"src": src, "error": type(exc).__name__})
            continue
        content_type = resp.headers.get("content-type", "")
        if not (200 <= resp.status_code < 300 and ("javascript" in content_type.lower() or src.endswith(".js"))):
            findings.append({"src": src, "status_code": resp.status_code, "content_type": content_type})
            continue
        text = resp.text
        findings.append(
            {
                "src": src,
                "status_code": resp.status_code,
                "content_type": content_type,
                "matched_markers": [marker for marker in markers if marker in text],
            }
        )
    (debug_dir / f"{slug}_script_scan.json").write_text(json.dumps(findings, indent=2), encoding="utf-8")


def solve_inline_cookie_script(script: str, url: str, browser_cfg: dict) -> dict[str, str]:
    return solve_script_sequence([{"url": url, "content": script}], url, browser_cfg)


def solve_script_sequence(scripts: list[dict[str, str]], url: str, browser_cfg: dict) -> dict[str, str]:
    driver = Path(__file__).with_name("js").joinpath("solve_inline_challenge.js")
    payload = {
        "scripts": scripts,
        "url": url,
        "browser_profile": browser_cfg,
    }

    with NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
        tmp.write(json.dumps(payload))
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            ["node", str(driver), tmp_path],
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    if result.returncode != 0 or not result.stdout.strip():
        return {}

    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}
    if "__solver_error__" in parsed:
        script_blob = "\n\n".join(f"// {item['url']}\n{item['content']}" for item in scripts)
        dump_solver_failure(script_blob, url, parsed["__solver_error__"], parsed.get("__cookies__", {}))
        return {k: str(v) for k, v in parsed.get("__cookies__", {}).items()}
    return {k: str(v) for k, v in parsed.items()}


def dump_solver_failure(script: str, url: str, error: dict, cookies: dict[str, str]) -> None:
    debug_dir = Path("debug")
    debug_dir.mkdir(exist_ok=True)
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", url)[:120]
    (debug_dir / f"solver_failure_{safe}.js").write_text(script, encoding="utf-8")
    (debug_dir / f"solver_failure_{safe}.json").write_text(
        json.dumps({"url": url, "error": error, "cookies": cookies}, indent=2),
        encoding="utf-8",
    )
