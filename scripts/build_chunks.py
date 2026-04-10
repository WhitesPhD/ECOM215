#!/usr/bin/env python3
"""
build_chunks.py — chunk ECOM215 course material for the chat widget.

Walks ../{Lectures,Notes,Tutorials} (the course folders that sit next to
this script's parent directory), splits each .tex file into
section/subsection blocks, cleans the LaTeX, extracts matching text from
the compiled PDF via pdftotext, and writes course-chunks.json into the
parent directory (next to README.md).

Each chunk entry looks like:

    {
      "id": "lectures-week-2-section-03-proof-of-stake",
      "source_type": "lectures",     # lectures | notes | tutorials
      "week": 2,
      "title_full": "Blockchain Economics",
      "section": "Proof-of-Stake",
      "subsection": null,
      "tex_path": "Lectures/Week 2 Slides.tex",
      "pdf_path": "Lectures/Week 2 Slides.pdf",
      "tex_text": "…cleaned LaTeX prose…",
      "pdf_text": "…pdftotext slice that contains the section title…",
      "token_estimate": 412
    }

Run with no arguments:

    python3 scripts/build_chunks.py

Requires Python 3.9+ and pdftotext on $PATH (Poppler or MacTeX).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
SOURCE_ROOT = REPO_ROOT
OUTPUT_FILE = REPO_ROOT / "course-chunks.json"

SOURCE_TYPES = {
    "lectures": SOURCE_ROOT / "Lectures",
    "notes": SOURCE_ROOT / "Notes",
    "tutorials": SOURCE_ROOT / "Tutorials",
}


# ---------------------------------------------------------------------------
# LaTeX cleaning
# ---------------------------------------------------------------------------

# Regexes we reuse
RE_SECTION = re.compile(r"\\(section|subsection)\*?\s*\{([^}]*)\}")
RE_FRAME_TITLE = re.compile(r"\\begin\{frame\}(?:\[[^\]]*\])?\s*\{([^}]*)\}")
RE_COMMENT = re.compile(r"(?<!\\)%.*")
RE_BEGIN_DOC = re.compile(r"\\begin\{document\}")
RE_END_DOC = re.compile(r"\\end\{document\}")


# Commands whose first argument carries text we want to keep. Rendered as
# plain text (the argument content).
TEXT_COMMANDS = {
    "textbf", "textit", "emph", "underline", "texttt", "textsc",
    "textsf", "textrm", "text", "keyword", "highlight", "good", "bad",
    "emphbox", "mbox", "hbox",
}

# Commands to drop entirely along with their single braced argument.
DROP_COMMANDS = {
    "label", "ref", "pageref", "cite", "footcite", "citep", "citet",
    "includegraphics", "includepdf", "input", "include", "index",
    "hypersetup", "definecolor", "setbeamercolor", "setbeamerfont",
    "setbeamertemplate", "usetheme", "usecolortheme", "usefonttheme",
    "usetikzlibrary", "geometry", "pagestyle", "fancyhf", "lhead",
    "chead", "rhead", "lfoot", "cfoot", "rfoot", "colorbox",
    "textcolor", "fcolorbox", "addcontentsline", "tableofcontents",
    "titlepage", "maketitle", "today", "insertframetitle",
    "insertsection", "insertsubsection", "insertshorttitle",
    "insertshortauthor", "insertshortdate", "insertframenumber",
    "inserttotalframenumber", "insertauthor", "insertinstitute",
    "inserttitle", "insertsubtitle", "insertdate", "renewcommand",
    "newcommand", "providecommand", "newenvironment", "renewenvironment",
    "setlength", "vspace", "hspace", "vskip", "hskip", "vfill", "hfill",
    "leavevmode", "par", "noindent", "indent", "medskip", "bigskip",
    "smallskip", "resizebox", "scalebox", "titleformat", "titlespacing",
}

# Commands in DROP_COMMANDS that take more than one braced argument.
# We list their argument counts here; the default for DROP_COMMANDS is 1.
DROP_COMMAND_ARITY = {
    "addcontentsline": 3,
    "definecolor": 3,
    "setbeamercolor": 2,
    "setbeamerfont": 2,
    "setbeamertemplate": 2,
    "hypersetup": 1,
    "renewcommand": 2,
    "newcommand": 2,
    "providecommand": 2,
    "newenvironment": 2,
    "renewenvironment": 2,
    "setlength": 2,
    "resizebox": 3,
    "scalebox": 2,
    "titleformat": 5,
    "titlespacing": 5,
    "fcolorbox": 3,
    "textcolor": 2,
    "colorbox": 2,
}

# Environments whose content we drop outright (figures, tikz, tables that
# carry no useful prose).
DROP_ENVIRONMENTS = {
    "tikzpicture", "figure", "wrapfigure", "pspicture", "equation",
    "align", "align*", "equation*", "eqnarray", "eqnarray*",
    "thebibliography", "filecontents",
}


def strip_comments(text: str) -> str:
    """Remove % comments, preserving \\%."""
    out_lines = []
    for line in text.splitlines():
        cleaned = RE_COMMENT.sub("", line)
        out_lines.append(cleaned)
    return "\n".join(out_lines)


def strip_environments(text: str, envs: set[str]) -> str:
    """Remove `\\begin{env} ... \\end{env}` blocks for the listed envs."""
    for env in envs:
        pattern = re.compile(
            r"\\begin\{" + re.escape(env) + r"\}.*?\\end\{" + re.escape(env) + r"\}",
            re.DOTALL,
        )
        text = pattern.sub(" ", text)
    return text


def _find_matching_brace(text: str, start: int) -> int:
    """Given index of an opening `{`, return index of matching `}`, or -1."""
    depth = 0
    i = start
    while i < len(text):
        c = text[i]
        if c == "\\" and i + 1 < len(text):
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def unwrap_text_commands(text: str) -> str:
    """Replace `\\textbf{foo}` etc. with just `foo`."""
    cmd_pattern = re.compile(r"\\([a-zA-Z]+)\s*")
    out = []
    i = 0
    while i < len(text):
        m = cmd_pattern.match(text, i)
        if not m:
            out.append(text[i])
            i += 1
            continue
        name = m.group(1)
        j = m.end()
        # Skip optional argument `[...]`.
        if j < len(text) and text[j] == "[":
            close = text.find("]", j)
            if close != -1:
                j = close + 1
        if name in DROP_COMMANDS:
            # Eat up to `arity` consecutive braced arguments.
            arity = DROP_COMMAND_ARITY.get(name, 1)
            eaten = 0
            while eaten < arity and j < len(text):
                # Skip whitespace between arguments.
                k = j
                while k < len(text) and text[k].isspace():
                    k += 1
                if k < len(text) and text[k] == "{":
                    end = _find_matching_brace(text, k)
                    if end == -1:
                        break
                    j = end + 1
                    eaten += 1
                    continue
                break
            i = j
            continue
        if name in TEXT_COMMANDS:
            if j < len(text) and text[j] == "{":
                end = _find_matching_brace(text, j)
                if end != -1:
                    out.append(text[j + 1 : end])
                    i = end + 1
                    continue
            i = j
            continue
        # Generic unknown command: drop the command but keep any braced
        # argument content verbatim (one level).
        if j < len(text) and text[j] == "{":
            end = _find_matching_brace(text, j)
            if end != -1:
                out.append(" ")
                out.append(text[j + 1 : end])
                i = end + 1
                continue
        out.append(" ")
        i = j
    return "".join(out)


def strip_list_markers(text: str) -> str:
    """Replace `\\item` with a bullet and `\\begin{itemize}`-style markers
    with nothing."""
    text = re.sub(r"\\begin\{(itemize|enumerate|description)\}(\[[^\]]*\])?", " ", text)
    text = re.sub(r"\\end\{(itemize|enumerate|description)\}", " ", text)
    text = re.sub(r"\\begin\{(block|alertblock|exampleblock|quote|quotation|columns|column|center|flushleft|flushright|tabular|tabular\*|table|frame)\}(\[[^\]]*\])?(\{[^}]*\})?", " ", text)
    text = re.sub(r"\\end\{(block|alertblock|exampleblock|quote|quotation|columns|column|center|flushleft|flushright|tabular|tabular\*|table|frame)\}", " ", text)
    text = re.sub(r"\\item\b", "• ", text)
    return text


def strip_math(text: str) -> str:
    """Replace inline and display math with a placeholder [math]."""
    # Display math \\[ ... \\] and $$ ... $$
    text = re.sub(r"\\\[.*?\\\]", " [math] ", text, flags=re.DOTALL)
    text = re.sub(r"\$\$.*?\$\$", " [math] ", text, flags=re.DOTALL)
    # Inline math $ ... $
    text = re.sub(r"(?<!\\)\$[^$]*\$", " [math] ", text, flags=re.DOTALL)
    return text


def normalise_whitespace(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    return text.strip()


def latex_to_text(latex: str) -> str:
    """Best-effort conversion of a LaTeX fragment to readable plain text."""
    text = strip_comments(latex)
    # Strip the leading \section{...} / \subsection{...} declaration; the
    # title is already captured on the chunk's metadata.
    text = re.sub(
        r"\\(section|subsection|subsubsection|chapter|paragraph)\*?\s*\{[^}]*\}",
        " ",
        text,
    )
    text = strip_environments(text, DROP_ENVIRONMENTS)
    text = strip_math(text)
    text = strip_list_markers(text)
    text = unwrap_text_commands(text)
    # Collapse leftover LaTeX escapes
    text = text.replace("\\\\", "\n")
    text = re.sub(r"\\[&%_#]", lambda m: m.group(0)[1], text)
    # Collapse `\ ` (non-breaking space after an abbreviation) and `\,`
    # (thin space) to a regular space.
    text = re.sub(r"\\[ ,;:!]", " ", text)
    text = re.sub(r"\\[a-zA-Z]+\*?", " ", text)
    text = text.replace("{", " ").replace("}", " ")
    text = text.replace("~", " ")
    text = text.replace("---", "—").replace("--", "–")
    text = text.replace("``", "“").replace("''", "”")
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return normalise_whitespace(text)


# ---------------------------------------------------------------------------
# Section splitting
# ---------------------------------------------------------------------------

@dataclass
class RawSection:
    level: str  # "section" or "subsection"
    title: str
    start: int  # offset in the *body* (post `\begin{document}`)
    end: int  # exclusive


def split_sections(tex: str) -> list[RawSection]:
    """Return top-level sections (with their subsections flattened inside)
    from the body of a .tex file."""
    # Restrict to document body when present.
    m_begin = RE_BEGIN_DOC.search(tex)
    m_end = RE_END_DOC.search(tex)
    body_start = m_begin.end() if m_begin else 0
    body_end = m_end.start() if m_end else len(tex)
    body = tex[body_start:body_end]

    matches = list(RE_SECTION.finditer(body))
    if not matches:
        return []

    sections: list[RawSection] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        sections.append(
            RawSection(
                level=m.group(1),
                title=m.group(2).strip(),
                start=start,
                end=end,
            )
        )
    # We also want access to the body text itself, so attach as attribute.
    for s in sections:
        s.__dict__["body_text"] = body[s.start : s.end]
    return sections


# For Beamer decks without sections, fall back to frames.
def split_frames(tex: str) -> list[tuple[str, str]]:
    m_begin = RE_BEGIN_DOC.search(tex)
    m_end = RE_END_DOC.search(tex)
    body = tex[(m_begin.end() if m_begin else 0) : (m_end.start() if m_end else len(tex))]
    titles = list(RE_FRAME_TITLE.finditer(body))
    if not titles:
        return []
    chunks: list[tuple[str, str]] = []
    for i, m in enumerate(titles):
        start = m.start()
        end = titles[i + 1].start() if i + 1 < len(titles) else len(body)
        chunks.append((m.group(1).strip(), body[start:end]))
    return chunks


# ---------------------------------------------------------------------------
# PDF text extraction
# ---------------------------------------------------------------------------

def pdftotext_full(pdf_path: Path) -> str:
    if not pdf_path.exists():
        return ""
    if shutil.which("pdftotext") is None:
        return ""
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", "-nopgbrk", str(pdf_path), "-"],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        return result.stdout or ""
    except Exception:
        return ""


_TOC_LINE_RE = re.compile(r"\.{3,}|\s\d+\s*$")


def _looks_like_toc_line(pdf_dump: str, idx: int) -> bool:
    """Return True if the match at `idx` sits on a ToC-style line
    (trailing dots-and-page-number, e.g. `Overview ........ 2`)."""
    line_start = pdf_dump.rfind("\n", 0, idx) + 1
    line_end = pdf_dump.find("\n", idx)
    if line_end == -1:
        line_end = len(pdf_dump)
    line = pdf_dump[line_start:line_end]
    return bool(_TOC_LINE_RE.search(line))


def slice_pdf_by_title(pdf_dump: str, title: str, next_title: str | None) -> str:
    """Find the first non-ToC occurrence of `title` in `pdf_dump` and return
    text up to the next section title (or up to 8000 chars)."""
    if not pdf_dump:
        return ""
    norm_title = re.sub(r"\s+", " ", title).strip().lower()
    if not norm_title:
        return ""
    lowered = pdf_dump.lower()

    # Walk all occurrences; skip any that look like ToC lines.
    search_from = 0
    idx = -1
    while True:
        found = lowered.find(norm_title, search_from)
        if found == -1:
            break
        if not _looks_like_toc_line(pdf_dump, found):
            idx = found
            break
        search_from = found + len(norm_title)
    if idx == -1:
        return ""

    end_idx = len(pdf_dump)
    if next_title:
        next_norm = re.sub(r"\s+", " ", next_title).strip().lower()
        # Again, skip ToC matches when looking for the next boundary.
        probe = idx + len(norm_title)
        while True:
            nxt = lowered.find(next_norm, probe)
            if nxt == -1:
                break
            if not _looks_like_toc_line(pdf_dump, nxt):
                end_idx = nxt
                break
            probe = nxt + len(next_norm)
    end_idx = min(end_idx, idx + 8000)
    return pdf_dump[idx:end_idx].strip()


# ---------------------------------------------------------------------------
# Chunk building
# ---------------------------------------------------------------------------

WEEK_RE = re.compile(r"Week\s+(\d+)", re.IGNORECASE)


def week_from_filename(name: str) -> int | None:
    m = WEEK_RE.search(name)
    return int(m.group(1)) if m else None


def extract_document_title(tex: str) -> str | None:
    m = re.search(r"\\title\s*\{([^}]*)\}", tex)
    return m.group(1).strip() if m else None


def slugify(text: str) -> str:
    s = text.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


@dataclass
class Chunk:
    id: str
    source_type: str
    week: int | None
    title_full: str | None
    section: str
    subsection: str | None
    tex_path: str
    pdf_path: str
    tex_text: str
    pdf_text: str
    token_estimate: int = 0


def estimate_tokens(text: str) -> int:
    # Rough heuristic: 1 token ≈ 4 characters of English prose.
    return max(1, len(text) // 4)


def build_chunks_for_file(tex_path: Path, source_type: str) -> list[Chunk]:
    tex_raw = tex_path.read_text(encoding="utf-8", errors="replace")
    tex_clean = strip_comments(tex_raw)
    week = week_from_filename(tex_path.name)
    doc_title = extract_document_title(tex_raw)

    pdf_path = tex_path.with_suffix(".pdf")
    pdf_dump = pdftotext_full(pdf_path)

    rel_tex = str(tex_path.relative_to(SOURCE_ROOT))
    rel_pdf = str(pdf_path.relative_to(SOURCE_ROOT))

    chunks: list[Chunk] = []
    sections = split_sections(tex_clean)

    if sections:
        # Walk sections, keeping track of the most recent \section title for
        # subsection parents.
        current_section: str | None = None
        idx_counter = 0
        section_titles = [s.title for s in sections]
        for i, sec in enumerate(sections):
            title_clean = latex_to_text(sec.title) or sec.title
            if sec.level == "section":
                current_section = title_clean
                section_label = title_clean
                subsection_label: str | None = None
            else:  # subsection
                section_label = current_section or title_clean
                subsection_label = title_clean

            body_latex = sec.__dict__.get("body_text", "")
            tex_text = latex_to_text(body_latex)
            next_title = section_titles[i + 1] if i + 1 < len(sections) else None
            pdf_text = slice_pdf_by_title(pdf_dump, title_clean, next_title)

            idx_counter += 1
            chunk_id = "-".join(
                filter(
                    None,
                    [
                        source_type,
                        f"week-{week}" if week is not None else None,
                        f"s{idx_counter:02d}",
                        slugify(subsection_label or section_label),
                    ],
                )
            )
            chunks.append(
                Chunk(
                    id=chunk_id,
                    source_type=source_type,
                    week=week,
                    title_full=doc_title,
                    section=section_label,
                    subsection=subsection_label,
                    tex_path=rel_tex,
                    pdf_path=rel_pdf,
                    tex_text=tex_text,
                    pdf_text=pdf_text,
                    token_estimate=estimate_tokens(tex_text),
                )
            )
    else:
        # Beamer-style: no \section — fall back to frames.
        frames = split_frames(tex_clean)
        frame_titles = [t for t, _ in frames]
        for i, (title, body) in enumerate(frames):
            title_clean = latex_to_text(title) or title
            tex_text = latex_to_text(body)
            next_title = frame_titles[i + 1] if i + 1 < len(frames) else None
            pdf_text = slice_pdf_by_title(pdf_dump, title_clean, next_title)
            chunk_id = "-".join(
                filter(
                    None,
                    [
                        source_type,
                        f"week-{week}" if week is not None else None,
                        f"f{i + 1:03d}",
                        slugify(title_clean),
                    ],
                )
            )
            chunks.append(
                Chunk(
                    id=chunk_id,
                    source_type=source_type,
                    week=week,
                    title_full=doc_title,
                    section=title_clean,
                    subsection=None,
                    tex_path=rel_tex,
                    pdf_path=rel_pdf,
                    tex_text=tex_text,
                    pdf_text=pdf_text,
                    token_estimate=estimate_tokens(tex_text),
                )
            )
    return chunks


def main() -> int:
    if not SOURCE_ROOT.exists():
        print(f"error: source root not found: {SOURCE_ROOT}", file=sys.stderr)
        return 1

    all_chunks: list[Chunk] = []
    for source_type, folder in SOURCE_TYPES.items():
        if not folder.exists():
            print(f"skip: {folder} not found")
            continue
        tex_files = sorted(folder.glob("*.tex"))
        for tex_path in tex_files:
            file_chunks = build_chunks_for_file(tex_path, source_type)
            all_chunks.extend(file_chunks)
            print(
                f"  {source_type}/{tex_path.name}: {len(file_chunks)} chunks"
            )

    payload = {
        "schema_version": 1,
        "generated_by": "scripts/build_chunks.py",
        "source_root": str(SOURCE_ROOT),
        "chunk_count": len(all_chunks),
        "chunks": [asdict(c) for c in all_chunks],
    }
    OUTPUT_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    total_tokens = sum(c.token_estimate for c in all_chunks)
    print(
        f"\nwrote {OUTPUT_FILE.relative_to(REPO_ROOT)}: "
        f"{len(all_chunks)} chunks, ~{total_tokens:,} tokens total"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
