import zipfile

from luanma import convert_zip, extract_zip, preview_zip
from luanma.ziputil import UTF8_FLAG

from helpers import make_bad_zip, make_utf8_zip

GBK_NAMES = {
    "期末大作业/": b"",
    "期末大作业/实验报告.docx": b"report-content",
    "课程设计说明.txt": b"readme",
}


def test_preview_shows_fixed_names(tmp_path):
    p = make_bad_zip(tmp_path / "gbk.zip", GBK_NAMES, "gbk")
    det, previews = preview_zip(p)
    fixed = {pv.fixed for pv in previews}
    assert "期末大作业/实验报告.docx" in fixed
    assert "课程设计说明.txt" in fixed
    assert all(pv.needs_fix for pv in previews)


def test_preview_forced_encoding(tmp_path):
    p = make_bad_zip(tmp_path / "gbk.zip", GBK_NAMES, "gbk")
    det, previews = preview_zip(p, encoding="gbk")
    assert det.confidence == "forced"
    assert {pv.fixed for pv in previews} >= {"课程设计说明.txt"}


def test_extract_restores_names_and_content(tmp_path):
    p = make_bad_zip(tmp_path / "work.zip", GBK_NAMES, "gbk")
    report = extract_zip(p, dest=tmp_path / "out")
    assert report.extracted == 2
    target = tmp_path / "out" / "期末大作业" / "实验报告.docx"
    assert target.read_bytes() == b"report-content"
    assert (tmp_path / "out" / "课程设计说明.txt").exists()


def test_extract_default_dest_is_archive_stem(tmp_path):
    p = make_bad_zip(tmp_path / "work.zip", GBK_NAMES, "gbk")
    report = extract_zip(p)
    assert report.dest == str(tmp_path / "work")
    assert (tmp_path / "work" / "课程设计说明.txt").exists()


def test_extract_skips_junk_by_default(tmp_path):
    names = dict(GBK_NAMES)
    names["__MACOSX/._实验报告.docx"] = b"applespam"
    names[".DS_Store"] = b"junk"
    p = make_bad_zip(tmp_path / "mac.zip", names, "gbk")
    report = extract_zip(p, dest=tmp_path / "out")
    assert report.junk_skipped == 2
    assert not (tmp_path / "out" / "__MACOSX").exists()
    assert not (tmp_path / "out" / ".DS_Store").exists()


def test_extract_keep_junk(tmp_path):
    names = {".DS_Store": b"junk", "文档.txt": b"x"}
    p = make_bad_zip(tmp_path / "mac.zip", names, "gbk")
    report = extract_zip(p, dest=tmp_path / "out", keep_junk=True)
    assert report.junk_skipped == 0
    assert (tmp_path / "out" / ".DS_Store").exists()


def test_extract_blocks_zip_slip(tmp_path):
    p = make_bad_zip(
        tmp_path / "evil.zip", {"../逃逸文件.txt": b"evil"}, "gbk"
    )
    report = extract_zip(p, dest=tmp_path / "out")
    assert not (tmp_path / "逃逸文件.txt").exists()
    inside = list((tmp_path / "out").rglob("*.txt"))
    assert len(inside) == 1  # extracted, but confined inside dest


def test_extract_sanitizes_illegal_windows_chars(tmp_path):
    p = make_bad_zip(
        tmp_path / "bad.zip", {"报告:最终版?.docx": b"x"}, "gbk"
    )
    report = extract_zip(p, dest=tmp_path / "out")
    assert report.sanitized == 1
    assert (tmp_path / "out" / "报告_最终版_.docx").exists()


def test_extract_handles_backslash_separators(tmp_path):
    p = make_bad_zip(
        tmp_path / "old.zip", {"目录\\子目录\\文件.txt": b"x"}, "gbk"
    )
    extract_zip(p, dest=tmp_path / "out")
    assert (tmp_path / "out" / "目录" / "子目录" / "文件.txt").exists()


def test_extract_collision_renames(tmp_path):
    # Two different raw names may sanitize to the same target.
    p = make_bad_zip(
        tmp_path / "dup.zip",
        {"报告?.txt": b"one", "报告*.txt": b"two"},
        "gbk",
    )
    report = extract_zip(p, dest=tmp_path / "out")
    assert report.extracted == 2
    assert report.renamed == 1
    assert (tmp_path / "out" / "报告_.txt").exists()
    assert (tmp_path / "out" / "报告_ (2).txt").exists()


def test_extract_preserves_mixed_flagged_names(tmp_path):
    p = make_bad_zip(
        tmp_path / "mixed.zip",
        GBK_NAMES,
        "gbk",
        flagged_names={"正常文件.txt": b"ok"},
    )
    extract_zip(p, dest=tmp_path / "out")
    assert (tmp_path / "out" / "正常文件.txt").read_bytes() == b"ok"


def test_convert_produces_utf8_zip(tmp_path):
    p = make_bad_zip(tmp_path / "work.zip", GBK_NAMES, "gbk")
    report = convert_zip(p)
    assert report.output == str(tmp_path / "work_utf8.zip")
    with zipfile.ZipFile(report.output) as zf:
        names = zf.namelist()
        assert "期末大作业/实验报告.docx" in names
        assert zf.read("期末大作业/实验报告.docx") == b"report-content"
        for info in zf.infolist():
            if any(ord(c) > 127 for c in info.filename):
                assert info.flag_bits & UTF8_FLAG
            assert info.date_time == (2026, 8, 13, 12, 0, 0)


def test_convert_drops_junk_by_default(tmp_path):
    names = dict(GBK_NAMES)
    names["__MACOSX/._x"] = b"spam"
    p = make_bad_zip(tmp_path / "mac.zip", names, "gbk")
    report = convert_zip(p)
    assert report.junk_skipped == 1
    with zipfile.ZipFile(report.output) as zf:
        assert not any("__MACOSX" in n for n in zf.namelist())


def test_convert_refuses_same_path(tmp_path):
    p = make_bad_zip(tmp_path / "a.zip", GBK_NAMES, "gbk")
    import pytest

    from luanma import ArchiveError

    with pytest.raises(ArchiveError):
        convert_zip(p, output=p)


def test_convert_utf8_archive_roundtrip(tmp_path):
    p = make_utf8_zip(tmp_path / "ok.zip", {"中文文档.txt": b"x"})
    report = convert_zip(p, output=tmp_path / "out.zip")
    with zipfile.ZipFile(report.output) as zf:
        assert zf.namelist() == ["中文文档.txt"]


def test_missing_file_raises(tmp_path):
    import pytest

    from luanma import ArchiveError

    with pytest.raises(ArchiveError):
        preview_zip(tmp_path / "nope.zip")


def test_not_a_zip_raises(tmp_path):
    bad = tmp_path / "fake.zip"
    bad.write_bytes(b"this is not a zip at all")
    import pytest

    from luanma import ArchiveError

    with pytest.raises(ArchiveError):
        preview_zip(bad)
