"""Translation tooling that works without GNU gettext (handy on Windows).

    python scripts/i18n.py extract   # update locale/<lang>/LC_MESSAGES/django.po from code + templates
    python scripts/i18n.py compile   # build django.mo from django.po

Equivalent to Django's makemessages / compilemessages, which need the GNU
gettext binaries. On PythonAnywhere (Linux) the standard commands also work.
"""
import io
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

import django  # noqa: E402

django.setup()

import polib  # noqa: E402
from babel.messages.extract import extract  # noqa: E402
from django.utils.translation.template import templatize  # noqa: E402

LANGUAGES = ["ar"]
PLURAL_FORMS = {
    "ar": "nplurals=6; plural=n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 : n%100>=11 && n%100<=99 ? 4 : 5;",
}
KEYWORDS = {
    "_": None,
    "gettext": None,
    "gettext_lazy": None,
    "gettext_noop": None,
    "ngettext": (1, 2),
    "ngettext_lazy": (1, 2),
    "pgettext": ((1, "c"), 2),
    "pgettext_lazy": ((1, "c"), 2),
    "npgettext": ((1, "c"), 2, 3),
}
SOURCE_DIRS = ["apps", "config", "templates"]
SKIP_PARTS = {"migrations", "__pycache__", "tests"}


def iter_sources():
    for folder in SOURCE_DIRS:
        for path in sorted((ROOT / folder).rglob("*")):
            if path.suffix not in (".py", ".html", ".txt") or SKIP_PARTS & set(path.parts):
                continue
            yield path


def extract_messages():
    """{(context, msgid, msgid_plural): [occurrences]}"""
    messages = {}
    for path in iter_sources():
        source = path.read_text(encoding="utf-8")
        if path.suffix != ".py":
            # templatize() turns a template into gettext() calls padded with filler text;
            # dedent it so Python's tokenizer accepts it.
            source = "\n".join(line.lstrip() for line in templatize(source, origin=str(path)).splitlines())
        rel = path.relative_to(ROOT).as_posix()
        for lineno, message, _comments, context in extract(
            "python", io.BytesIO(source.encode("utf-8")), keywords=KEYWORDS, options={"encoding": "utf-8"}
        ):
            if isinstance(message, (tuple, list)):
                msgid, plural = message[0], message[1]
            else:
                msgid, plural = message, ""
            if not msgid:
                continue
            key = (context or "", msgid, plural or "")
            messages.setdefault(key, []).append((rel, lineno if path.suffix == ".py" else ""))
    return messages


def po_path(lang):
    return ROOT / "locale" / lang / "LC_MESSAGES" / "django.po"


def update_catalog(lang, messages):
    path = po_path(lang)
    path.parent.mkdir(parents=True, exist_ok=True)
    old = polib.pofile(str(path)) if path.exists() else polib.POFile()
    previous = {(e.msgctxt or "", e.msgid, e.msgid_plural or ""): e for e in old if not e.obsolete}

    po = polib.POFile(wrapwidth=0)
    po.metadata = {
        "Project-Id-Version": "PPR",
        "POT-Creation-Date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M%z"),
        "Language": lang,
        "MIME-Version": "1.0",
        "Content-Type": "text/plain; charset=UTF-8",
        "Content-Transfer-Encoding": "8bit",
        "Plural-Forms": PLURAL_FORMS.get(lang, "nplurals=2; plural=(n != 1);"),
    }
    nplurals = int(po.metadata["Plural-Forms"].split("nplurals=")[1].split(";")[0])
    missing = 0
    for (context, msgid, plural), occurrences in sorted(messages.items(), key=lambda kv: kv[0][1].lower()):
        before = previous.get((context, msgid, plural))
        entry = polib.POEntry(
            msgid=msgid,
            msgctxt=context or None,
            occurrences=[(file, str(line)) for file, line in occurrences],
            flags=["python-format"] if "%(" in msgid or "%s" in msgid else [],
        )
        if plural:
            entry.msgid_plural = plural
            forms = before.msgstr_plural if before else {}
            entry.msgstr_plural = {i: forms.get(i, "") for i in range(nplurals)}
            missing += not all(entry.msgstr_plural.values())
        else:
            entry.msgstr = before.msgstr if before else ""
            missing += not entry.msgstr
        po.append(entry)
    po.save(str(path))
    print(f"{path.relative_to(ROOT)}: {len(po)} messages, {missing} untranslated")


def compile_catalogs():
    for lang in LANGUAGES:
        path = po_path(lang)
        po = polib.pofile(str(path))
        po.save_as_mofile(str(path.with_suffix(".mo")))
        print(f"{path.with_suffix('.mo').relative_to(ROOT)}: {po.percent_translated()}% translated")


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "extract":
        found = extract_messages()
        for language in LANGUAGES:
            update_catalog(language, found)
    elif command == "compile":
        compile_catalogs()
    else:
        print(__doc__)
        sys.exit(1)
