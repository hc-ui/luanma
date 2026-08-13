"""Filename-encoding detection for archives with mojibake names.

The ZIP format predates a mandatory filename encoding. Archives created by
old or locale-dependent tools store names as raw bytes in the creator's
local code page (GBK on Chinese Windows, Shift-JIS on Japanese Windows,
Big5 on Traditional-Chinese systems, EUC-KR on Korean ones) without the
UTF-8 flag (general-purpose bit 11). Unzipping tools then fall back to
CP437 and produce mojibake.

Detection strategy: decode the raw name bytes with each candidate encoding
and score how much the result looks like real text -- hits on tables of
high-frequency hanzi and hangul, kana for Shift-JIS, and penalties for
undecodable bytes, control characters, private-use-area and replacement
characters. Frequency tables (not just script ranges) matter because CJK
double-byte encodings overlap heavily: GBK bytes usually decode "fine"
under CP949 or Big5, but into rare characters instead of common ones.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

#: Candidate encodings, also the tie-break preference order. GB18030 is a
#: strict superset of GBK/GB2312, so it decodes everything GBK archives
#: contain plus rarer characters that plain GBK would reject.
CANDIDATES = ("utf-8", "gb18030", "cp932", "big5", "cp949")

_PREFERENCE = {enc: i for i, enc in enumerate(CANDIDATES)}

#: Human-readable confidence labels shared by all report types.
CONFIDENCE_LABELS = {
    "high": "高",
    "medium": "中",
    "low": "低",
    "none": "无需修复",
    "forced": "手动指定",
}

# High-frequency hanzi (simplified + traditional) plus characters common in
# file names. Hits on this set are strong evidence the decoding is right;
# a wrong decoding of CJK bytes yields mostly rare characters instead.
_COMMON_HANZI = frozenset(
    # frequent simplified characters
    "的一是了我不人在他有这个上们来到时大地为子中你说生国年着就那和要她出"
    "也得里后自以会家可下而过天去能对小多然于心学么之都好看起发当没成只如"
    "事把还用第样道想作种开美总从无情己面最女但现前些所同日手又行意动方期"
    "它头经长儿回位分爱老因很给名法间知世什两次使身者被高已亲其进此话常与"
    "活正感见明问力理点文几定本公特做外孩相西果走将月十实向声车全信重三机"
    "工物气每并别真打太新比才便夫再书部水像眼等体却加电主界门利海受听表德"
    "少克代员许先口由死安写性马光白或住难望教命花结乐色更拉东神记处让母父"
    "应直字场平报友关放至张认接告入笑内英军候民岁往何度山觉路带万男边风解"
    "叫任金快原吃妈变通师立象数四失满战远格士音轻目条呢病始达深完今提求清"
    "王化空业思切怎非找片罗钱吗语元喜曾离飞科言干流欢约各即指合反题必该论"
    "交终林请医晚制球决传画保读运及则房早院量苦火布品近坐产答星精视五连司"
    "巴奇管类未朋且婚台夜青北队久乎越观落尽形影红爸百令周吧识步希亚术留市"
    "半热送兴造谈容极随演收首根讲整式取照办强石古华拿计您装似足双妻尼转诉"
    "米称丽客南领节衣站黑刻统断福城故历惊脸选包紧争另建维绝树系伤示愿持千"
    "史谁准联妇纪基买志静阿诗独复痛消社算义竟确酒需单治卡幸兰念举仅钟怕共"
    "毛句息功官待究跟穿室易游程号居考突皮哪费倒价图具刚脑永歌响商礼细专块"
    "脚灵"
    # characters common in file and folder names
    "文件资料报告作业总结数据分析说明测试项目照片图片视频音乐下载文档表格"
    "幻灯演示压缩备份笔记简历合同发票收据申请模板源码代码脚本配置日志实验"
    "论文毕业设计课件复习考试答案练习汇报周报月报名单成绩排班培训手册指南"
    # frequent traditional characters (also used to tell Big5 from GBK)
    "這個們來時為說國學會對還發當沒樣後點裡經長兒與問聽門見話東車馬風氣書"
    "寫難萬邊讓認識覺數關係間變離錢類飛紀讀運歷應該體禮節藥鐵銀錄陽陰際隨"
    "雙雞雲電靜頭題顏願食飯養骨魚鳥麗黃齊龍謝報總結專內容資料單議記錄檔傳"
    "輸壓縮案測試務處產業員動論戰爭權現實條約線組織調查許證據觀織續維護費"
    "設計劃區域圖標準備註冊開發環境優"
)

# High-frequency hangul syllables, drawn from words common in Korean file
# names (보고서, 학생, 자료, 문서, 첨부, 회의, 결과, 최종, ...). Random
# bytes mis-decoded as CP949 fall mostly outside this set, in the long
# tail of the 11 172 possible syllables.
_COMMON_HANGUL = frozenset(
    "보고서류학생명단정리자료문서사진파일첨부계획회의결과분석발표과제출최"
    "종수정완료요약내용목록번호기말시험답안연구개발업무일정관리제안계약견"
    "적이력포트폴리오데터백업다운로드새폴임시메모노트강의녹음영상음악게임"
    "설치프로그램한글워드엑셀공지사항안내문신청양식샘플예시테스트버전편집"
    "원본복사인쇄용유개비밀번암호중요긴급참고타및전체부분작성확인검토승년"
    "월화수목금토주간행사할당대상자동으로가나히"
)


def _score_text(text: str, encoding: str) -> float:
    """Score how plausible *text* is as a real, human-written name."""
    score = 0.0
    for ch in text:
        o = ord(ch)
        if ch in _COMMON_HANZI or ch in _COMMON_HANGUL:
            score += 3.0
        elif 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF:
            score += 0.5  # CJK ideograph (incl. Ext-A), not a common one
        elif 0x3040 <= o <= 0x30FF:  # kana: strong signal by itself
            score += 2.0
        elif 0xAC00 <= o <= 0xD7A3:  # hangul, but not a common syllable
            score += 0.5
        elif 0x3000 <= o <= 0x303F:  # CJK punctuation
            score += 0.5
        elif 0xFF61 <= o <= 0xFF9F:  # halfwidth katakana: mojibake look
            score += 0.2 if encoding == "cp932" else -1.0
        elif 0xFF00 <= o <= 0xFFEF:  # other fullwidth forms
            score += 0.3
        elif o < 0x80:
            score += 0.05 if ch.isprintable() else -2.0
        elif 0xE000 <= o <= 0xF8FF or ch == "\ufffd":  # PUA / replacement
            score -= 4.0
        elif 0x2500 <= o <= 0x25FF:  # box drawing: classic mojibake look
            score -= 2.0
        # anything else (Latin ext, Greek, Cyrillic, ...) scores 0
    return score


@dataclass
class DetectionResult:
    """Outcome of encoding detection over a set of raw filenames."""

    encoding: Optional[str]
    confidence: str  # "high" | "medium" | "low" | "none" | "forced"
    needs_fix: bool
    scores: Dict[str, float] = field(default_factory=dict)

    @property
    def confidence_label(self) -> str:
        return CONFIDENCE_LABELS.get(self.confidence, self.confidence)

    def ranked(self) -> List[str]:
        """Candidate encodings sorted from best to worst score."""
        return sorted(
            self.scores, key=lambda e: (-self.scores[e], _PREFERENCE[e])
        )


def detect_names(raw_names: Sequence[bytes]) -> DetectionResult:
    """Detect the filename encoding for the given raw name bytes.

    ``raw_names`` should only contain names that actually need fixing,
    i.e. names from entries without the UTF-8 flag.
    """
    non_ascii = [raw for raw in raw_names if any(b >= 0x80 for b in raw)]
    if not non_ascii:
        return DetectionResult("utf-8", "none", False)

    scores: Dict[str, float] = {}
    for enc in CANDIDATES:
        total = 0.0
        for raw in non_ascii:
            try:
                text = raw.decode(enc)
            except (UnicodeDecodeError, ValueError):
                total -= 10.0
                continue
            total += _score_text(text, enc)
        scores[enc] = round(total, 2)

    best = min(scores, key=lambda e: (-scores[e], _PREFERENCE[e]))
    ordered = sorted(scores.values(), reverse=True)
    margin = ordered[0] - ordered[1] if len(ordered) > 1 else ordered[0]
    total_bytes = sum(len(raw) for raw in non_ascii) or 1
    per_byte = scores[best] / total_bytes

    # 0.4 per byte keeps names that mix ASCII (extensions, dates, "v2")
    # with CJK text in the "high" bucket while random decodes stay out.
    if scores[best] <= 0:
        confidence = "low"
    elif margin / max(abs(scores[best]), 1.0) >= 0.25 and per_byte >= 0.4:
        confidence = "high"
    elif margin > 0:
        confidence = "medium"
    else:
        confidence = "low"
    return DetectionResult(best, confidence, True, scores)
