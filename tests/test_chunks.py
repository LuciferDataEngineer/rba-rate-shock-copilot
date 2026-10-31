from rba_copilot.rag.chunk import chunk_section
from rba_copilot.rag.retrieve import reciprocal_rank_fusion
from rba_copilot.themes import theme_hits


def test_chunks_overlap():
    text = " ".join(f"Sentence number {index} is long enough to stand alone here." for index in range(40))
    chunks = chunk_section("Inflation", text, max_chars=220, overlap=60)
    assert len(chunks) >= 3
    assert chunks[0][-40:][:20] in chunks[1] or chunks[0].split()[-3][0] in chunks[1]


def test_rrf_prefers_a_document_found_by_both():
    both = {"chunk_id": "a", "doc_id": "a"}
    only_left = {"chunk_id": "b", "doc_id": "b"}
    only_right = {"chunk_id": "c", "doc_id": "c"}
    fused = reciprocal_rank_fusion([both, only_left], [both, only_right])
    assert fused[0]["chunk_id"] == "a"


def test_theme_patterns():
    assert theme_hits("Oil prices rose after the conflict")["energy"]
    assert theme_hits("AI-related investment in data centres")["ai_investment"]
    assert not theme_hits("The Board said inflation is high")["ai_investment"]
