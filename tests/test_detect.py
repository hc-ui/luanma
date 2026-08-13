from luanma import detect_zip
from luanma.detect import detect_names

from helpers import make_bad_zip, make_utf8_zip

GBK_NAMES = {
    "期末大作业/": b"",
    "期末大作业/实验报告.docx": b"report",
    "期末大作业/数据分析结果.xlsx": b"data",
    "课程设计说明文档.txt": b"readme",
}

BIG5_NAMES = {
    "會議記錄.txt": b"minutes",
    "學生名單.xlsx": b"list",
    "專題報告/內容說明.docx": b"doc",
}

SJIS_NAMES = {
    "レポート.txt": b"report",
    "研究データ.csv": b"data",
    "報告書まとめ.docx": b"doc",
}

EUCKR_NAMES = {
    "보고서.hwp": b"report",
    "학생명단정리.xlsx": b"list",
}


def test_detect_gbk(tmp_path):
    p = make_bad_zip(tmp_path / "gbk.zip", GBK_NAMES, "gbk")
    det = detect_zip(p)
    assert det.needs_fix
    assert det.encoding == "gb18030"  # superset of GBK
    assert det.confidence == "high"


def test_detect_gb18030_four_byte_char(tmp_path):
    p = make_bad_zip(
        tmp_path / "g4.zip", {"文档㐀备份.txt": b"x"}, "gb18030"
    )
    det = detect_zip(p)
    assert det.encoding == "gb18030"


def test_detect_big5(tmp_path):
    p = make_bad_zip(tmp_path / "big5.zip", BIG5_NAMES, "big5")
    det = detect_zip(p)
    assert det.needs_fix
    assert det.encoding == "big5"


def test_detect_shift_jis(tmp_path):
    p = make_bad_zip(tmp_path / "sjis.zip", SJIS_NAMES, "cp932")
    det = detect_zip(p)
    assert det.needs_fix
    assert det.encoding == "cp932"


def test_detect_euc_kr(tmp_path):
    p = make_bad_zip(tmp_path / "euckr.zip", EUCKR_NAMES, "cp949")
    det = detect_zip(p)
    assert det.needs_fix
    assert det.encoding == "cp949"


def test_detect_unflagged_utf8(tmp_path):
    # Some tools write UTF-8 bytes but forget flag bit 11.
    p = make_bad_zip(
        tmp_path / "u8.zip",
        {"毕业论文终稿.docx": b"thesis", "参考文献列表.txt": b"refs"},
        "utf-8",
    )
    det = detect_zip(p)
    assert det.needs_fix
    assert det.encoding == "utf-8"


def test_flagged_utf8_needs_no_fix(tmp_path):
    p = make_utf8_zip(tmp_path / "ok.zip", {"中文文档.txt": b"x"})
    det = detect_zip(p)
    assert not det.needs_fix
    assert det.confidence == "none"


def test_ascii_only_needs_no_fix(tmp_path):
    p = make_bad_zip(tmp_path / "ascii.zip", {"readme.txt": b"x"}, "ascii")
    det = detect_zip(p)
    assert not det.needs_fix


def test_mixed_archive_detects_from_unflagged_only(tmp_path):
    p = make_bad_zip(
        tmp_path / "mixed.zip",
        GBK_NAMES,
        "gbk",
        flagged_names={"已经正常的文件.txt": b"ok"},
    )
    det = detect_zip(p)
    assert det.encoding == "gb18030"


def test_detect_names_empty():
    det = detect_names([])
    assert not det.needs_fix
    assert det.confidence == "none"


def test_ranked_orders_by_score(tmp_path):
    p = make_bad_zip(tmp_path / "gbk2.zip", GBK_NAMES, "gbk")
    det = detect_zip(p)
    assert det.ranked()[0] == "gb18030"
