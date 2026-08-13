import json
import zipfile

import pytest

from luanma.cli import main

from helpers import make_bad_zip, make_encrypted_zip, make_utf8_zip, mojibake

GBK_NAMES = {
    "期末大作业/实验报告.docx": b"report",
    "课程设计说明.txt": b"readme",
}


def test_preview_default(tmp_path, capsys):
    p = make_bad_zip(tmp_path / "gbk.zip", GBK_NAMES, "gbk")
    assert main([str(p)]) == 0
    out = capsys.readouterr().out
    assert "GB18030" in out
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
    assert archive["encoding"] == "gb18030"
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


def test_glob_expansion(tmp_path, capsys):
    # PowerShell and cmd pass "*.zip" through literally; we must expand it.
    make_bad_zip(tmp_path / "a.zip", GBK_NAMES, "gbk")
    make_bad_zip(tmp_path / "b.zip", GBK_NAMES, "gbk")
    assert main([str(tmp_path / "*.zip")]) == 0
    out = capsys.readouterr().out
    assert "a.zip" in out and "b.zip" in out


def test_encrypted_without_password_exit_code(tmp_path, capsys):
    p = make_encrypted_zip(
        tmp_path / "enc.zip", "机密.txt", b"secret", "pw"
    )
    assert main([str(p), "-x", "-d", str(tmp_path / "out")]) == 1
    assert "已加密" in capsys.readouterr().out


def test_password_flag(tmp_path, capsys):
    p = make_encrypted_zip(
        tmp_path / "enc.zip", "机密.txt", b"secret", "pw"
    )
    dest = tmp_path / "out"
    assert main([str(p), "-x", "-d", str(dest), "-p", "pw"]) == 0
    assert (dest / "机密.txt").read_bytes() == b"secret"


def test_dest_requires_extract(tmp_path):
    p = make_bad_zip(tmp_path / "gbk.zip", GBK_NAMES, "gbk")
    import pytest

    with pytest.raises(SystemExit):
        main([str(p), "-d", "somewhere"])


def _mojibake_dir(tmp_path):
    d = tmp_path / "extracted"
    d.mkdir()
    (d / mojibake("期末大作业.docx")).write_bytes(b"doc")
    (d / mojibake("数据分析.xlsx")).write_bytes(b"xls")
    return d


def test_dir_preview_default(tmp_path, capsys):
    d = _mojibake_dir(tmp_path)
    assert main([str(d)]) == 0
    out = capsys.readouterr().out
    assert "计划重命名" in out
    assert "期末大作业.docx" in out
    assert "--rename" in out
    # dry run: nothing renamed yet
    assert (d / mojibake("期末大作业.docx")).exists()


def test_dir_rename_applies(tmp_path, capsys):
    d = _mojibake_dir(tmp_path)
    assert main([str(d), "--rename"]) == 0
    out = capsys.readouterr().out
    assert "已重命名 2 项" in out
    assert (d / "期末大作业.docx").read_bytes() == b"doc"
    assert (d / "数据分析.xlsx").read_bytes() == b"xls"


def test_dir_json_output(tmp_path, capsys):
    d = _mojibake_dir(tmp_path)
    assert main([str(d), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    entry = payload["archives"][0]
    assert entry["action"] == "dir-preview"
    news = {i["new"] for i in entry["report"]["planned"]}
    assert news == {"期末大作业.docx", "数据分析.xlsx"}


def test_clean_dir_message(tmp_path, capsys):
    d = tmp_path / "clean"
    d.mkdir()
    (d / "正常文件.txt").write_bytes(b"x")
    assert main([str(d)]) == 0
    assert "未发现乱码" in capsys.readouterr().out


def test_rename_on_zip_rejected(tmp_path, capsys):
    p = make_bad_zip(tmp_path / "gbk.zip", GBK_NAMES, "gbk")
    assert main([str(p), "--rename"]) == 2
    assert "仅用于目录" in capsys.readouterr().err


def test_extract_on_dir_rejected(tmp_path, capsys):
    d = _mojibake_dir(tmp_path)
    assert main([str(d), "-x"]) == 2
    assert "--rename" in capsys.readouterr().err


def test_rename_conflicts_with_fix(tmp_path):
    d = _mojibake_dir(tmp_path)
    with pytest.raises(SystemExit):
        main([str(d), "--rename", "--fix"])


def test_fix_output_missing_dir_exit2(tmp_path, capsys):
    p = make_bad_zip(tmp_path / "gbk.zip", GBK_NAMES, "gbk")
    out = tmp_path / "no_such_dir" / "o.zip"
    assert main([str(p), "--fix", "-o", str(out)]) == 2
    assert "无法写入" in capsys.readouterr().err


def test_extract_dest_under_file_exit2(tmp_path, capsys):
    p = make_bad_zip(tmp_path / "gbk.zip", GBK_NAMES, "gbk")
    blocker = tmp_path / "blocker"
    blocker.write_bytes(b"file")
    assert main([str(p), "-x", "-d", str(blocker / "sub")]) == 2
    assert "无法创建目标目录" in capsys.readouterr().err


def test_preview_shows_encrypted_hint(tmp_path, capsys):
    p = make_encrypted_zip(
        tmp_path / "enc.zip", "机密资料.txt", b"secret", "pw"
    )
    assert main([str(p)]) == 0
    assert "加密条目" in capsys.readouterr().out


def test_rezipped_double_mojibake_end_to_end(tmp_path, capsys):
    names = {
        mojibake("期末大作业.docx"): b"d",
        mojibake("数据分析.xlsx"): b"x",
    }
    p = make_utf8_zip(tmp_path / "re.zip", names)
    dest = tmp_path / "out"
    assert main([str(p), "-x", "-d", str(dest)]) == 0
    assert (dest / "期末大作业.docx").read_bytes() == b"d"
    assert (dest / "数据分析.xlsx").read_bytes() == b"x"


def test_dir_root_renamed_cli(tmp_path, capsys):
    wreck = tmp_path / mojibake("学习资料")
    wreck.mkdir()
    (wreck / mojibake("课堂笔记.txt")).write_bytes(b"n")
    assert main([str(wreck), "--rename"]) == 0
    out = capsys.readouterr().out
    assert "目录本身已改名" in out
    assert (tmp_path / "学习资料" / "课堂笔记.txt").exists()


def test_control_chars_not_echoed(tmp_path, capsys):
    # A hostile archive name embedding ESC must not reach the terminal.
    p = make_bad_zip(
        tmp_path / "evil.zip",
        {"课程设计说明.txt": b"x"},
        "gbk",
        flagged_names={"\x1b]0;pwned\x07.txt": b"y"},
    )
    assert main([str(p)]) == 0
    out = capsys.readouterr().out
    assert "\x1b" not in out
