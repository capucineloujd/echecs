from app.rag.chunking import chunk_text, split_sections

ARTICLE = """La partie française est une ouverture.

== Histoire ==
Elle doit son nom à un match par correspondance Londres-Paris en 1834.

== Variantes ==
=== La variante Winawer ===
3. Cc3 Fb4, la variante la plus tranchante.

== Notes et références ==
Une note sans intérêt.

== Bibliographie ==
Un livre.

 Portail des échecs"""

def test_sections_keep_hierarchy_and_skip_noise():
    names = [name for name, _ in split_sections(ARTICLE)]
    assert names == ["Introduction", "Histoire", "Variantes > La variante Winawer"]


def test_footer_removed():
    assert all("Portail" not in body for _, body in split_sections(ARTICLE))


def test_chunks_respect_max_size():
    paragraphs = "\n\n".join(f"Paragraphe {i} " + "x" * 300 for i in range(10))
    chunks = chunk_text(f"== Plans ==\n{paragraphs}", max_chars=1000)
    assert len(chunks) > 1
    assert all(len(c.text) <= 1000 for c in chunks)
    assert all(c.section == "Plans" for c in chunks)


def test_overlap_between_consecutive_chunks():
    paragraphs = "\n\n".join(f"Paragraphe {i} " + "x" * 300 for i in range(6))
    first, second, *_ = chunk_text(paragraphs, max_chars=1000)
    assert first.text.split("\n")[-1] == second.text.split("\n")[0]


def test_long_paragraph_split_on_sentences():
    long_paragraph = " ".join(f"Phrase numéro {i} assez longue pour remplir." for i in range(80))
    chunks = chunk_text(long_paragraph, max_chars=500)
    assert all(len(c.text) <= 500 for c in chunks)
    assert all(c.text.endswith(".") for c in chunks)


def test_tiny_chunks_dropped():
    assert chunk_text("== Vide ==\nTrop court.") == []
