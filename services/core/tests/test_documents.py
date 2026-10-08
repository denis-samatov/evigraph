import random

from evigraph_core import documents
from evigraph_core.models import Project, ProvenanceReason

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
