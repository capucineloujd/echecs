import re
from dataclasses import dataclass

HEADING = re.compile(r"^(={2,6})\s*(.*?)\s*\1\s*$", re.M)

# Sections sans valeur pour la recherche (listes de liens, tableaux aplatis...)
SKIPPED_SECTIONS = {
    "references", "notes", "notes et références", "bibliographie", "liens externes",
    "external links", "see also", "voir aussi", "articles connexes", "theory table",
    "statistics", "all possible black's moves", "all possible white's moves", "poème",
}
FOOTER = re.compile(r"^\s*Portail d[eu]s? .*$", re.M)


@dataclass
class Chunk:
    section: str
    text: str


def split_sections(text: str) -> list[tuple[str, str]]:
    """Découpe un texte MediaWiki brut en (chemin de section, contenu).

    Le chemin garde la hiérarchie : "Variantes > La variante Winawer".
    """
    text = FOOTER.sub("", text)
    sections, path = [], []
    last_end, current = 0, "Introduction"

    for match in HEADING.finditer(text):
        sections.append((current, text[last_end:match.start()]))
        level = len(match.group(1)) - 2
        path = path[:level] + [match.group(2)]
        current = " > ".join(path)
        last_end = match.end()
    sections.append((current, text[last_end:]))

    return [
        (name, body.strip())
        for name, body in sections
        if body.strip() and not any(part.lower() in SKIPPED_SECTIONS for part in name.split(" > "))
    ]


def chunk_text(text: str, max_chars: int = 1200, min_chars: int = 80) -> list[Chunk]:
    """Regroupe les paragraphes d'une même section jusqu'à max_chars.

    On ne coupe jamais au milieu d'un paragraphe (sauf s'il dépasse seul la limite)
    et on reprend le dernier paragraphe du chunk précédent pour garder le fil.
    """
    chunks = []
    for section, body in split_sections(text):
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\n(?=\S)", body) if p.strip()]
        paragraphs = [piece for p in paragraphs for piece in _split_long(p, max_chars)]

        current: list[str] = []
        for paragraph in paragraphs:
            if current and len("\n".join(current + [paragraph])) > max_chars:
                chunks.append(Chunk(section, "\n".join(current)))
                overlap = current[-1] if len(current[-1]) + len(paragraph) < max_chars else None
                current = [overlap] if overlap else []
            current.append(paragraph)
        if current:
            chunks.append(Chunk(section, "\n".join(current)))

    return [c for c in chunks if len(c.text) >= min_chars]


def _split_long(paragraph: str, max_chars: int) -> list[str]:
    if len(paragraph) <= max_chars:
        return [paragraph]
    sentences = re.split(r"(?<=[.!?])\s+", paragraph)
    pieces, current = [], ""
    for sentence in sentences:
        if current and len(current) + len(sentence) + 1 > max_chars:
            pieces.append(current)
            current = ""
        current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current)
    return pieces


def embedding_text(opening_name: str, eco: str, section: str, text: str) -> str:
    """Texte réellement vectorisé : on préfixe le contexte pour qu'un passage
    isolé ("3...a6 forces White to...") reste rattaché à son ouverture."""
    return f"{opening_name} ({eco}) — {section}\n{text}"
