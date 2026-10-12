import random

from sqlalchemy import delete

from evigraph_core import documents
from evigraph_core.models import Project, ProvenanceReason, WordTypeBand

BASE = (
    "Commission Regulation establishing the standard import values for determining the entry "
    "price of certain fruit and vegetables. Having regard to the Treaty on the Functioning of "
    "the European Union and to Council Regulation on the common organisation of agricultural "
    "markets, the standard import values shall be as set out in the Annex to this Regulation. "
    "This Regulation shall enter into force on the day of its publication in the Official "
    "Journal of the European Union and shall be binding in its entirety in all Member States."
)
RUSSIAN = (
    "Договор поставки оборудования. Поставщик обязуется уведомить покупателя об инциденте "
    "информационной безопасности в течение двадцати четырёх часов с момента его обнаружения. "
    "Перечень категорий персональных данных приведён в приложении к настоящему договору."
)


def _project(session) -> Project:
    p = Project(name=f"p{random.random()}")
    session.add(p)
    session.flush()
    return p


def _ingest(session, settings, project, text, source=None):
    return documents.create_document(
        session, project_id=project.id, title=None, raw_text=text, source=source, settings=settings
    )


def test_exact_copy_joins_group(factory, settings) -> None:
    with factory() as s:
        p = _project(s)
        a = _ingest(s, settings, p, BASE)
        b = _ingest(s, settings, p, BASE + "  \r\n")  # same canonical text
        s.commit()
    assert a.provenance_reason is ProvenanceReason.new
    assert b.provenance_reason is ProvenanceReason.exact
    assert b.provenance_group_id == a.provenance_group_id


def test_near_copy_joins_group_and_distinct_text_does_not(factory, settings) -> None:
    words = BASE.split()
    near = " ".join(w for i, w in enumerate(words) if i != 20)  # one word dropped
    with factory() as s:
        p = _project(s)
        a = _ingest(s, settings, p, BASE)
        b = _ingest(s, settings, p, near)
        c = _ingest(s, settings, p, RUSSIAN)
        s.commit()
    assert b.provenance_reason is ProvenanceReason.near
    assert b.provenance_group_id == a.provenance_group_id
    assert b.provenance_jaccard is not None
    assert b.provenance_jaccard >= settings.near_duplicate_threshold
    assert c.provenance_reason is ProvenanceReason.new
    assert c.provenance_group_id != a.provenance_group_id


def test_source_identity_links_rewritten_text(factory, settings) -> None:
    src = documents.SourceRef(system="dms", id="contract-17")
    with factory() as s:
        p = _project(s)
        a = _ingest(s, settings, p, RUSSIAN, src)
        b = _ingest(s, settings, p, BASE, src)  # completely different text, same source id
        s.commit()
    assert b.provenance_reason is ProvenanceReason.source_id
    assert b.provenance_group_id == a.provenance_group_id


def test_groups_do_not_cross_projects(factory, settings) -> None:
    with factory() as s:
        p1, p2 = _project(s), _project(s)
        a = _ingest(s, settings, p1, BASE)
        b = _ingest(s, settings, p2, BASE)
        s.commit()
    assert b.provenance_reason is ProvenanceReason.new
    assert b.provenance_group_id != a.provenance_group_id


def test_canonical_text_is_nfc_and_versions_increment(factory, settings) -> None:
    with factory() as s:
        p = _project(s)
        v1 = _ingest(s, settings, p, "Café \r\nline  ")
        doc = s.get(documents.Document, v1.document_id)
        v2 = documents.add_version(
            s, project_id=p.id, document=doc, raw_text=RUSSIAN, source=None, settings=settings
        )
        s.commit()
    assert v1.canonical_text == "Café\nline"
    assert (v1.version, v2.version) == (1, 2)


def _long_text(seed: int, words: int = 600) -> str:
    """Deterministic text with a few hundred distinct words (enough for containment checks)."""
    rng = random.Random(seed)
    vocab = [f"term{seed}x{i}" for i in range(300)] + BASE.split()
    return " ".join(rng.choice(vocab) for _ in range(words))


def _delete_words(text: str, share: float, seed: int = 0) -> str:
    rng = random.Random(seed)
    return " ".join(w for w in text.split() if rng.random() >= share)


def test_copy_with_words_deleted_is_contained(factory, settings) -> None:
    source = _long_text(1)
    copy = _delete_words(source, 0.3)  # 5-gram MinHash cannot see this copy
    with factory() as s:
        p = _project(s)
        a = _ingest(s, settings, p, source)
        b = _ingest(s, settings, p, copy)
        s.commit()
    assert b.provenance_reason is ProvenanceReason.contained
    assert b.provenance_group_id == a.provenance_group_id
    assert b.provenance_containment is not None
    assert b.provenance_containment >= settings.containment_threshold
    assert b.provenance_jaccard is None


def test_containment_is_directional_and_skips_short_texts(factory, settings) -> None:
    source = _long_text(2)
    superset = source + " " + _long_text(3)  # contains the source, is not contained in it
    excerpt = " ".join(source.split()[:30])  # contained, but too few word types to judge
    with factory() as s:
        p = _project(s)
        a = _ingest(s, settings, p, source)
        b = _ingest(s, settings, p, superset)
        c = _ingest(s, settings, p, excerpt)
        s.commit()
    assert len(set(excerpt.lower().split())) < settings.containment_min_types
    assert b.provenance_reason is ProvenanceReason.new
    assert c.provenance_reason is ProvenanceReason.new
    assert c.type_minhash is None
    assert {b.provenance_group_id, c.provenance_group_id}.isdisjoint({a.provenance_group_id})


def test_backfill_indexes_older_versions(factory, settings) -> None:
    source = _long_text(4)
    with factory() as s:
        p = _project(s)
        a = _ingest(s, settings, p, source)
        # simulate a version ingested before the word-type index existed
        s.execute(delete(WordTypeBand).where(WordTypeBand.document_version_id == a.id))
        a.type_minhash = None
        s.flush()
        before = _ingest(s, settings, p, _delete_words(source, 0.2, seed=1))
        assert documents.backfill_word_types(s, settings) >= 1
        after = _ingest(s, settings, p, _delete_words(source, 0.2, seed=2))
        s.commit()
    assert before.provenance_reason is ProvenanceReason.new
    assert after.provenance_reason is ProvenanceReason.contained
    assert after.provenance_group_id == a.provenance_group_id
