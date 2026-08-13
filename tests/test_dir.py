"""Tests for directory mode: repairing already-extracted mojibake names."""

from __future__ import annotations

import pytest

from luanma.dirutil import _claim_name, rename_dir, scan_dir
from luanma.ziputil import ArchiveError

from helpers import mojibake


def _make_tree(root):
    """A typical wrongly-extracted archive plus innocent bystanders."""
    bad_dir = root / mojibake("期末大作业")
    bad_dir.mkdir()
    (bad_dir / mojibake("实验报告.docx")).write_bytes(b"doc")
    (root / mojibake("数据分析.xlsx")).write_bytes(b"xls")
    (root / "readme.txt").write_bytes(b"ascii, leave me alone")
    (root / "已经正常.txt").write_bytes(b"proper utf-8 name")
    return bad_dir


def test_scan_detects_and_plans(tmp_path):
    _make_tree(tmp_path)
    det, report = scan_dir(tmp_path)
    assert det.encoding == "gb18030"
    assert report.needs_fix
    mapping = {i.old_name: i.new_name for i in report.planned}
    assert mapping[mojibake("实验报告.docx")] == "实验报告.docx"
    assert mapping[mojibake("数据分析.xlsx")] == "数据分析.xlsx"
    assert mapping[mojibake("期末大作业")] == "期末大作业"
    assert "readme.txt" not in mapping
    assert "已经正常.txt" not in mapping


def test_scan_is_read_only(tmp_path):
    bad_dir = _make_tree(tmp_path)
    scan_dir(tmp_path)
    assert bad_dir.exists()
    assert (bad_dir / mojibake("实验报告.docx")).exists()


def test_rename_applies_bottom_up(tmp_path):
    bad_dir = _make_tree(tmp_path)
    report = rename_dir(tmp_path, apply=True)
    assert report.renamed == 3
    assert report.errors == []
    assert (tmp_path / "期末大作业" / "实验报告.docx").read_bytes() == b"doc"
    assert (tmp_path / "数据分析.xlsx").exists()
    assert (tmp_path / "readme.txt").exists()
    assert (tmp_path / "已经正常.txt").exists()
    assert not bad_dir.exists()


def test_rename_default_is_dry_run(tmp_path):
    _make_tree(tmp_path)
    report = rename_dir(tmp_path)  # apply not given
    assert report.needs_fix
    assert report.renamed == 0
    assert (tmp_path / mojibake("数据分析.xlsx")).exists()


def test_nested_three_levels(tmp_path):
    a = tmp_path / mojibake("论文")
    b = a / mojibake("初稿")
    b.mkdir(parents=True)
    (b / mojibake("正文.txt")).write_bytes(b"x")
    report = rename_dir(tmp_path, apply=True)
    assert report.renamed == 3
    assert (tmp_path / "论文" / "初稿" / "正文.txt").exists()


def test_clean_dir_needs_nothing(tmp_path):
    (tmp_path / "report.txt").write_bytes(b"a")
    (tmp_path / "总结.docx").write_bytes(b"b")
    det, report = scan_dir(tmp_path)
    assert not report.needs_fix
    assert report.planned == []


def test_accented_latin_names_protected(tmp_path):
    # cp437-encodable but NOT mojibake: must never be renamed.
    (tmp_path / "café.txt").write_bytes(b"fr")
    report = rename_dir(tmp_path, apply=True)
    assert report.renamed == 0
    assert report.skipped_unsure >= 1
    assert (tmp_path / "café.txt").exists()


def test_collision_with_existing_file(tmp_path):
    (tmp_path / "报告.txt").write_bytes(b"old correct file")
    (tmp_path / mojibake("报告.txt")).write_bytes(b"the mojibake one")
    report = rename_dir(tmp_path, apply=True)
    assert report.renamed == 1
    assert (tmp_path / "报告.txt").read_bytes() == b"old correct file"
    assert (tmp_path / "报告 (2).txt").read_bytes() == b"the mojibake one"


def test_claim_name_dedupes_within_plan(tmp_path):
    taken: dict = {}
    first = _claim_name(tmp_path, "数据.txt", taken)
    second = _claim_name(tmp_path, "数据.txt", taken)
    assert first == "数据.txt"
    assert second == "数据 (2).txt"


def test_forced_encoding(tmp_path):
    (tmp_path / mojibake("報告書.doc", "cp932")).write_bytes(b"jp")
    report = rename_dir(tmp_path, encoding="cp932", apply=True)
    assert report.renamed == 1
    assert (tmp_path / "報告書.doc").exists()


def test_missing_dir_raises(tmp_path):
    with pytest.raises(ArchiveError):
        scan_dir(tmp_path / "不存在")


def test_big5_tree(tmp_path):
    # Note: some Big5 mojibake contains Windows-illegal chars (e.g. 會議記錄
    # yields a "|") and cannot even exist on NTFS; use clean samples here.
    (tmp_path / mojibake("學習筆記.txt", "big5")).write_bytes(b"tw")
    (tmp_path / mojibake("專案計劃.txt", "big5")).write_bytes(b"tw2")
    det, report = scan_dir(tmp_path)
    assert det.encoding == "big5"
    names = {i.new_name for i in report.planned}
    assert names == {"學習筆記.txt", "專案計劃.txt"}
