from chunking import chunk_markdown, embedding_text

DOC = """# X-1 Fan: Manual

Intro line.

## 1 Safety

Lock out first.

## 2 Maintenance

### 2.1 Belts

Check belts.

Second paragraph.

## 3 Empty section
"""


def test_title_sections_and_order():
    chunks = chunk_markdown(DOC, "x1-fan")
    assert [c["section"] for c in chunks] == ["Introduction", "1 Safety", "2.1 Belts"]
    assert all(c["title"] == "X-1 Fan: Manual" and c["source"] == "x1-fan" for c in chunks)
    assert chunks[2]["text"] == "Check belts.\n\nSecond paragraph."


def test_headings_without_text_make_no_chunk():
    sections = [c["section"] for c in chunk_markdown(DOC, "x1-fan")]
    assert "2 Maintenance" not in sections and "3 Empty section" not in sections


def test_long_section_is_split_with_overlap():
    paragraphs = [f"Paragraph {n} " + "word " * 40 for n in range(6)]
    doc = "## 5 Long\n\n" + "\n\n".join(paragraphs)
    chunks = chunk_markdown(doc, "long", max_chars=500)
    assert len(chunks) > 1
    assert all(len(c["text"]) <= 500 for c in chunks)
    # the last paragraph of one chunk starts the next one, so no fact is cut in half
    for first, second in zip(chunks, chunks[1:]):
        assert second["text"].startswith(first["text"].split("\n\n")[-1])


def test_tables_stay_together():
    doc = "## 8 Limits\n\n| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |"
    (chunk,) = chunk_markdown(doc, "t")
    assert chunk["text"].count("|") == 12


def test_embedding_text_carries_manual_and_section():
    chunk = chunk_markdown(DOC, "x1-fan")[1]
    assert embedding_text(chunk).startswith("X-1 Fan: Manual\nSection: 1 Safety\n\nLock out first.")


def test_real_manuals_chunk_sensibly(manuals):
    for key, (text, _etag) in manuals.items():
        chunks = chunk_markdown(text, key)
        assert len(chunks) >= 8
        assert all(20 < len(c["text"]) <= 1200 for c in chunks)
