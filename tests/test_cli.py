import json
import zipfile

from luanma.cli import main

from helpers import make_bad_zip, make_utf8_zip

GBK_NAMES = {
    "期末大作业/实验报告.docx": b"report",
    "课程设计说明.txt": b"readme",
}


def test_preview_default(tmp_path, capsys):
    p = make_bad_zip(tmp_path / "gbk.zip", GBK_NAMES, "gbk")
    assert main([str(p)]) == 0
    out = capsys.readouterr().out
    assert "GBK" in out
    assert "课程设计说明.txt" in out


def test_preview_clean_archive(tmp_path, capsys):
    p = make_utf8_zip(tmp_path / "ok.zip", {"文档.txt": b"x"})
    assert main([str(p)]) == 0
    assert "无需修复" in capsys.readouterr().out


def test_json_output(tmp_path, capsys):
    p = make_bad_zip(tmp_path / "gbk.zip", GBK_NAMES, "gbk")
    assert main([str(p), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    archive = payload["archives"][0]
    assert archive["encoding"] == "gbk"
    assert archive["needs_fix"] is True
    assert any(
        e["fixed"] == "课程设计说明.txt" for e in archive["entries"]
    )


def test_extract_action(tmp_path, capsys):
    p = make_bad_zip(tmp_path / "gbk.zip", GBK_NAMES, "gbk")
    dest = tmp_path / "out"
    assert main([str(p), "-x", "-d", str(dest)]) == 0
    assert (dest / "课程设计说明.txt").read_bytes() == b"readme"


def test_fix_action(tmp_path):
    p = make_bad_zip(tmp_path / "gbk.zip", GBK_NAMES, "gbk")
    out = tmp_path / "fixed.zip"
    assert main([str(p), "--fix", "-o", str(out)]) == 0
    with zipfile.ZipFile(out) as zf:
        assert "课程设计说明.txt" in zf.namelist()


def test_forced_encoding(tmp_path, capsys):
    p = make_bad_zip(tmp_path / "b5.zip", {"會議記錄.txt": b"x"}, "big5")
    assert main([str(p), "-e", "big5"]) == 0
    assert "會議記錄.txt" in capsys.readouterr().out


def test_unknown_encoding_rejected(tmp_path, capsys):
    p = make_bad_zip(tmp_path / "gbk.zip", GBK_NAMES, "gbk")
    import pytest

    with pytest.raises(SystemExit):
        main([str(p), "-e", "not-an-encoding"])


def test_missing_file_exit_code(tmp_path, capsys):
    assert main([str(tmp_path / "nope.zip")]) == 2


def test_multiple_archives(tmp_path, capsys):
    p1 = make_bad_zip(tmp_path / "a.zip", GBK_NAMES, "gbk")
    p2 = make_utf8_zip(tmp_path / "b.zip", {"ok.txt": b"x"})
    assert main([str(p1), str(p2)]) == 0
    out = capsys.readouterr().out
    assert "a.zip" in out and "b.zip" in out


def test_extract_and_fix_conflict(tmp_path):
    p = make_bad_zip(tmp_path / "gbk.zip", GBK_NAMES, "gbk")
    import pytest

    with pytest.raises(SystemExit):
        main([str(p), "-x", "--fix"])
