"""evalcraft doctor — diagnose setup issues.

Checks:
  1. Python version compatibility
  2. evalcraft package installed correctly
  3. Optional dependencies (openai, anthropic, etc.)
  4. API keys configured
  5. Cassette directory exists and has files
  6. pytest plugin registered
  7. Golden sets and staleness
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path


def run_doctor(cassette_dir: str = "tests/cassettes", golden_dir: str | None = None) -> bool:
    """Run all diagnostic checks. Returns True if all pass."""
    passed = 0
    warned = 0
    failed = 0

    def ok(msg: str) -> None:
        nonlocal passed
        passed += 1
        print(f"  \033[32m✓\033[0m {msg}")

    def warn(msg: str) -> None:
        nonlocal warned
        warned += 1
        print(f"  \033[33m!\033[0m {msg}")

    def fail(msg: str) -> None:
        nonlocal failed
        failed += 1
        print(f"  \033[31m✗\033[0m {msg}")

    print()
    print("  evalcraft doctor")
    print("  " + "─" * 50)
    print()

    # ── 1. Python version ────────────────────────────────────────────────
    v = sys.version_info
    if v >= (3, 9):
        ok(f"Python {v.major}.{v.minor}.{v.micro}")
    else:
        fail(f"Python {v.major}.{v.minor}.{v.micro} — requires >= 3.9")

    # ── 2. evalcraft installed ───────────────────────────────────────────
    try:
        import evalcraft
        ok(f"evalcraft {evalcraft.__version__}")
    except ImportError:
        fail("evalcraft not installed — run: pip install evalcraft")
        # Can't continue without evalcraft
        print(f"\n  {passed} passed, {warned} warnings, {failed} errors")
        return False

    # ── 3. Core dependencies ─────────────────────────────────────────────
    for pkg, name in [("click", "click"), ("rich", "rich"), ("pydantic", "pydantic"), ("yaml", "pyyaml")]:
        try:
            mod = importlib.import_module(pkg)
            try:
                from importlib.metadata import version as pkg_version
                ver = pkg_version(name)
            except Exception:
                ver = getattr(mod, "__version__", "?")
            ok(f"{name} {ver}")
        except ImportError:
            fail(f"{name} not installed")

    # ── 4. Optional framework SDKs ───────────────────────────────────────
    print()
    optional_sdks = [
        ("openai", "openai", "evalcraft[openai]"),
        ("anthropic", "anthropic", "evalcraft[anthropic]"),
        ("google.generativeai", "google-generativeai", "evalcraft[gemini]"),
        ("pydantic_ai", "pydantic-ai", "evalcraft[pydantic-ai]"),
        ("langchain_core", "langchain-core", "evalcraft[langchain]"),
    ]
    for import_name, display_name, install_hint in optional_sdks:
        try:
            mod = importlib.import_module(import_name)
            ver = getattr(mod, "__version__", getattr(mod, "VERSION", "?"))
            ok(f"{display_name} {ver}")
        except ImportError:
            warn(f"{display_name} not installed — install with: pip install \"{install_hint}\"")

    # ── 5. API keys ──────────────────────────────────────────────────────
    print()
    api_keys = [
        ("OPENAI_API_KEY", "OpenAI"),
        ("ANTHROPIC_API_KEY", "Anthropic"),
        ("GOOGLE_API_KEY", "Google Gemini"),
    ]
    for env_var, name in api_keys:
        val = os.environ.get(env_var, "")
        if val:
            masked = val[:8] + "..." + val[-4:] if len(val) > 16 else "***"
            ok(f"{name} API key configured ({masked})")
        else:
            warn(f"{name} API key not set ({env_var}) — needed for recording, not for replay")

    # ── 6. Cassette directory ────────────────────────────────────────────
    print()
    cassette_path = Path(cassette_dir)
    if cassette_path.exists():
        cassettes = list(cassette_path.glob("*.json"))
        if cassettes:
            ok(f"Cassette directory: {cassette_dir}/ ({len(cassettes)} cassette(s))")

            # Check for stale cassettes (>30 days old)
            import time
            now = time.time()
            stale = []
            for c in cassettes:
                age_days = (now - c.stat().st_mtime) / 86400
                if age_days > 30:
                    stale.append((c.name, int(age_days)))
            if stale:
                warn(f"{len(stale)} stale cassette(s) (>30 days old):")
                for name, days in stale[:3]:
                    print(f"       {name} ({days} days)")
                if len(stale) > 3:
                    print(f"       ... and {len(stale) - 3} more")
        else:
            warn(f"Cassette directory exists but is empty: {cassette_dir}/")
    else:
        warn(f"Cassette directory not found: {cassette_dir}/ — run: evalcraft init")

    # ── 7. Golden sets ───────────────────────────────────────────────────
    golden_path = Path(golden_dir) if golden_dir else None
    if golden_path is None:
        # Try common locations
        for candidate in ["golden", "tests/golden", "."]:
            p = Path(candidate)
            goldens = list(p.glob("*.golden.json"))
            if goldens:
                golden_path = p
                break

    if golden_path:
        goldens = list(golden_path.glob("*.golden.json"))
        if goldens:
            ok(f"Golden sets: {len(goldens)} found in {golden_path}/")
        else:
            warn("No golden sets found — run: evalcraft golden save <cassette> --name <name>")
    else:
        warn("No golden sets found — run: evalcraft golden save <cassette> --name <name>")

    # ── 8. pytest plugin ─────────────────────────────────────────────────
    print()
    try:
        import pytest  # type: ignore[import]
        ok(f"pytest {pytest.__version__}")

        # Check if evalcraft plugin is registered
        try:
            from evalcraft.pytest_plugin import plugin  # noqa: F401
            ok("evalcraft pytest plugin registered")
        except ImportError:
            warn("evalcraft pytest plugin not found")
    except ImportError:
        warn("pytest not installed — install with: pip install \"evalcraft[pytest]\"")

    # ── 9. Cloud config ──────────────────────────────────────────────────
    config_path = Path.home() / ".evalcraft" / "config.json"
    if config_path.exists():
        ok(f"Cloud config: {config_path}")
    else:
        warn("No cloud config — run: evalcraft cloud login (optional)")

    # ── Summary ──────────────────────────────────────────────────────────
    print()
    print("  " + "─" * 50)
    parts = [f"\033[32m{passed} passed\033[0m"]
    if warned:
        parts.append(f"\033[33m{warned} warnings\033[0m")
    if failed:
        parts.append(f"\033[31m{failed} errors\033[0m")
    print(f"  {', '.join(parts)}")
    print()

    return failed == 0
