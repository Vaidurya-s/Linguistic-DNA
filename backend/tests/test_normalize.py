from app.services.normalize import clean_form, is_placeholder_form, normalize_form, plain_text


def test_clean_form_removes_source_markup_but_keeps_linguistic_notation():
    assert clean_form("kakadg <i> ('our k.')") == "kakadg ('our k.')"
    assert clean_form("S&amp;amp;P500") == "S&P500"
    assert clean_form("c&amp;#339;lacanthe") == "cœlacanthe"
    assert clean_form("dauč<sup>1</sup>") == "dauč1"
    # infix and proto-form notation is not an HTML tag
    assert clean_form("l<əm>idiʔ") == "l<əm>idiʔ"
    assert clean_form("<PIH *a->") == "<PIH *a->"
    assert clean_form("a < b") == "a < b"


def test_clean_form_drops_invisible_junk_and_keeps_joiners():
    assert clean_form("a​b﻿⁠c") == "abc"
    assert clean_form("déc�vant") == "décvant"
    assert clean_form("x\x13y") == "xy"
    assert clean_form("  two   words \n") == "two words"
    assert clean_form("क‍ष") == "क‍ष"  # ZWJ changes how the conjunct is written
    assert clean_form("می‌خواهم") == "می‌خواهم"  # ZWNJ in Persian


def test_clean_form_unwraps_wiki_links_and_comments():
    assert clean_form("[[Σοφία]]") == "Σοφία"
    assert clean_form("[[x|shown]]") == "shown"
    assert clean_form("word<!-- note -->") == "word"


def test_plain_text_for_glosses():
    assert plain_text("HgCl<sub>2</sub>; [[name of a prince]]") == "HgCl2; name of a prince"
    assert plain_text("m.; See akṣība.; {{Lbody=693}}") == "m.; See akṣība.;"
    assert plain_text("([[Appendix:Swahili_noun_classes#M-wa class|m class_((I))]])") == (
        "(m class_((I)))"
    )
    assert plain_text("&amp;quot;tooted&amp;quot;") == '"tooted"'
    assert plain_text(None) == ""


def test_placeholder_forms():
    for placeholder in ("-", "--", "?", "—", "()", "̃", "  ", ""):
        assert is_placeholder_form(placeholder), placeholder
    # Klingon pIqaD is written in the private-use area: real writing, not a placeholder
    for word in ("a", "पानी", "-आलय", "*pal", "ʔ", "二", "\uf8d4\uf8e5\uf8dd"):
        assert not is_placeholder_form(word), word


def test_normalize_form_is_unchanged_by_the_cleaners():
    # ids are derived from this; the cleaners must never leak into it
    assert normalize_form("a&amp;b") == "a&amp;b"
    assert normalize_form("a​b") == "a​b"
