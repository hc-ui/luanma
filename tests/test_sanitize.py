from luanma.junk import is_junk
from luanma.sanitize import safe_components, sanitize_component


def test_illegal_chars_replaced():
    assert sanitize_component('a<b>c:d"e|f?g*h.txt')[0] == "a_b_c_d_e_f_g_h.txt"


def test_trailing_dots_and_spaces_stripped():
    assert sanitize_component("report. ")[0] == "report"


def test_reserved_device_names_prefixed():
    assert sanitize_component("CON")[0] == "_CON"
    assert sanitize_component("con.txt")[0] == "_con.txt"
    assert sanitize_component("lpt1.log")[0] == "_lpt1.log"


def test_normal_name_unchanged():
    name, changed = sanitize_component("实验报告.docx")
    assert name == "实验报告.docx"
    assert not changed


def test_parent_dir_component_neutralized():
    assert sanitize_component("..")[0] == "_"


def test_safe_components_splits_both_slashes():
    parts, _ = safe_components("a/b\\c/file.txt")
    assert parts == ["a", "b", "c", "file.txt"]


def test_safe_components_drops_empty_and_dot():
    parts, _ = safe_components("./a//b/./c.txt")
    assert parts == ["a", "b", "c.txt"]


def test_junk_macosx():
    assert is_junk(["__MACOSX", "._file"])
    assert is_junk(["dir", ".DS_Store"])
    assert is_junk(["Thumbs.db"])
    assert is_junk(["._resource"])


def test_junk_normal_files_pass():
    assert not is_junk(["dir", "报告.docx"])
    assert not is_junk(["DS_Store提醒.txt"])
