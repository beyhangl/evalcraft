"""The bundled Agent Skill must stay truthful.

Coding agents act on the skill literally, so a renamed function or a CLI
command that no longer exists would teach them to write broken tests. These
checks tie the skill to the real public API and to the Agent Skills spec
limits (agentskills.io), so drift fails CI instead of misleading users.
"""

from __future__ import annotations

import re
from pathlib import Path

import evalcraft
from evalcraft.cli.main import cli

SKILL_DIR = Path(evalcraft.__file__).parent / ".agents" / "skills" / "evalcraft"
SKILL = SKILL_DIR / "SKILL.md"
DOCS = [SKILL, *sorted((SKILL_DIR / "references").glob("*.md"))]


def _frontmatter() -> tuple[dict, str]:
    text = SKILL.read_text()
    _, fm, body = text.split("---", 2)
    fields = dict(re.findall(r"^([a-z_]+): (.+)$", fm, re.M))
    return fields, body


class TestSpecLimits:
    def test_skill_ships_inside_the_package(self):
        # library-skills discovers `<pkg>/.agents/skills/*/SKILL.md` in the wheel.
        assert SKILL.is_file()

    def test_name_matches_folder(self):
        fields, _ = _frontmatter()
        assert fields["name"] == SKILL_DIR.name
        assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", fields["name"])

    def test_description_is_within_limit_and_carries_triggers(self):
        fields, _ = _frontmatter()
        desc = fields["description"]
        assert 1 <= len(desc) <= 1024
        for trigger in ("evalcraft", "cassette", "tool", "cost"):
            assert trigger in desc.lower(), trigger

    def test_body_is_under_500_lines(self):
        _, body = _frontmatter()
        assert len(body.splitlines()) < 500

    def test_version_matches_package(self):
        assert f'version: "{evalcraft.__version__}"' in SKILL.read_text()


class TestNamesAreReal:
    def test_every_assertion_mentioned_exists(self):
        mentioned = set()
        for doc in DOCS:
            mentioned |= set(re.findall(r"\b((?:assert|pairwise)_[a-z_]+)\b", doc.read_text()))
        missing = sorted(n for n in mentioned if not hasattr(evalcraft, n))
        assert not missing, f"skill mentions names evalcraft does not export: {missing}"

    def test_every_adapter_mentioned_exists(self):
        import evalcraft.adapters as adapters

        mentioned = set(re.findall(r"\b([A-Z][A-Za-z]+Adapter)\b", SKILL.read_text()))
        assert mentioned
        missing = sorted(n for n in mentioned if not hasattr(adapters, n))
        assert not missing, missing

    def test_every_cli_command_mentioned_exists(self):
        commands = set(cli.commands)
        text = SKILL.read_text()
        # Only real invocations: shell code blocks and inline `evalcraft ...` spans.
        shell = "\n".join(re.findall(r"```bash\n(.*?)```", text, re.S))
        inline = " ".join(re.findall(r"`(evalcraft [^`]+)`", text))
        mentioned = set(re.findall(r"^evalcraft ([a-z][a-z-]+)", shell, re.M))
        mentioned |= set(re.findall(r"evalcraft ([a-z][a-z-]+)", inline))
        assert mentioned, "expected the skill to show at least one CLI command"
        missing = sorted(c for c in mentioned if c not in commands)
        assert not missing, f"skill mentions CLI commands that do not exist: {missing}"

    def test_pytest_flag_mentioned_is_registered(self):
        from evalcraft.pytest_plugin import plugin

        src = Path(plugin.__file__).read_text()
        for flag in set(re.findall(r"(--evalcraft-[a-z-]+)", SKILL.read_text())):
            assert f'"{flag}"' in src, flag
