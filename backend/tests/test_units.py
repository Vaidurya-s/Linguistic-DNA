import pytest

from app.importers.common import Citation, SchemaMismatch, parse_citations, read_csv
from app.importers.jambu import (
    clean_reference,
    has_native_script,
    inherited_citations,
    plain_gloss,
    reconstruction_status,
)
from app.models.enums import ReconstructionStatus
from app.services.ids import lexeme_id
from app.services.normalize import normalize_form


def test_normalize_composes_to_nfc_and_keeps_diacritics_and_case():
    assert normalize_form("dánta") == "dánta"
    assert normalize_form("  Áryas\t ") == "Áryas"
    assert normalize_form("ō\u0000ṭu") == "ōṭu"


def test_normalize_keeps_native_script_marks():
    assert normalize_form("बाड़") == "बाड़"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("CDIAL", [Citation("CDIAL", None)]),
        ("CDIAL[6152]", [Citation("CDIAL", "6152")]),
        (
            "dunkel2014lipp[p. 179];wiktionary-piir[Reconstruction:Proto-Indo-Iranian/Há-, "
            "revision 92152085]",
            [
                Citation("dunkel2014lipp", "p. 179"),
                Citation(
                    "wiktionary-piir", "Reconstruction:Proto-Indo-Iranian/Há-, revision 92152085"
                ),
            ],
        ),
        ("x[a; b];y", [Citation("x", "a; b"), Citation("y", None)]),
        ("", []),
    ],
)
def test_parse_citations(value, expected):
    assert parse_citations(value) == expected


def test_native_script_detection_ignores_latin_ipa_and_modifier_letters():
    assert not has_native_script("dāt̃")
    assert not has_native_script("uddʰí")
    assert has_native_script("बाड़")
    assert has_native_script("ಹಗಲು")


def test_reconstruction_status():
    assert reconstruction_status("*ōṭu", False, False) is ReconstructionStatus.reconstructed
    assert reconstruction_status("Hdántas", True, False) is ReconstructionStatus.reconstructed
    assert reconstruction_status("√añc", False, True) is ReconstructionStatus.uncertain
    assert reconstruction_status("dāt", False, True) is ReconstructionStatus.attested
    assert reconstruction_status("dāt", False, False) is ReconstructionStatus.unknown


def test_plain_gloss_strips_markup():
    assert plain_gloss("made of <i>kr̥muká</i> wood") == "made of kr̥muká wood"
    assert plain_gloss("") is None


def test_ids_are_deterministic():
    assert lexeme_id("jambu", "6152") == lexeme_id("jambu", "6152")
    assert lexeme_id("jambu", "6152") != lexeme_id("jambu", "6153")


def test_read_csv_rejects_missing_columns(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("ID,Form\n1,a\n", encoding="utf-8")
    with pytest.raises(SchemaMismatch):
        list(read_csv(p, ("ID", "Form", "Language_ID")))


def test_inherited_citations_prefer_the_parents_work():
    assert inherited_citations("bagri;CDIAL", "CDIAL;NIA") == [Citation("CDIAL", None)]
    assert inherited_citations("bagri", "CDIAL") == [Citation("bagri", None)]


def test_clean_reference_strips_markdown_and_extracts_url():
    title, url = clean_reference(
        "Eldose K. Mathai. Bagri survey. *Journal of Language Survey Reports*, 2011. "
        "URL: [https://www.sil.org/x/43105](https://www.sil.org/x/43105)."
    )
    assert title == "Eldose K. Mathai. Bagri survey. Journal of Language Survey Reports, 2011"
    assert url == "https://www.sil.org/x/43105"


def test_form_kind_separates_words_from_stems_affixes_roots_phrases():
    from app.models.enums import FormKind
    from app.services.normalize import form_kind

    assert form_kind("dāt") is FormKind.word
    assert form_kind("*ōṭu") is FormKind.word
    assert form_kind("svatva-") is FormKind.stem
    assert form_kind("*aŋkaṭa-") is FormKind.stem
    assert form_kind("-ṭa-") is FormKind.affix
    assert form_kind("√añc") is FormKind.root
    assert form_kind("bāl baccā") is FormKind.phrase
    assert form_kind("dantapāli", is_compound=True) is FormKind.compound


def test_jambu_headword_locators_name_the_dictionary_entry():
    from app.importers.jambu import headword_locator

    assert headword_locator("6152") == "CDIAL 6152"
    assert headword_locator("d3690") == "DEDR 3690"
    assert headword_locator("f_4xxedqnm7toyk") == "Jambu record f_4xxedqnm7toyk"
