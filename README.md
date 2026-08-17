# luanma(乱码)

> **简体中文** | [English](#features-english)

[![CI](https://github.com/hc-ui/luanma/actions/workflows/ci.yml/badge.svg)](https://github.com/hc-ui/luanma/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**解压后文件名全是乱码?一条命令自动检测编码、预览、修复。已经解压出一堆乱码文件?也能原地改回来。**

Fix mojibake filenames in zip archives — and in directories that were already extracted wrong. Auto-detects the filename encoding (GBK / Big5 / Shift-JIS / EUC-JP / EUC-KR / UTF-8), previews the fix, safely extracts, rewrites the archive to standard UTF-8, or renames on-disk files back to their real names. Even "double mojibake" archives (a wrecked tree re-zipped with a modern tool) are recognized and repaired. Pure Python, zero dependencies, works offline.

```text
之前:                          之后:
ÆÚÄ©´ó×÷Òµ/                    期末大作业/
  ╔ÁÑ╬▒¿copy.docx               实验报告-最终版.docx
  ╩²¥¦ÂÍ╬÷.xlsx                 数据分析.xlsx
```

## 为什么会乱码

zip 格式诞生时没有规定文件名必须用什么编码。中文 Windows 上老工具(以及百度网盘、部分邮箱、旧版 WinRAR、Java 程序等)打包时,把文件名按 **GBK 字节**写进压缩包,而且不设置"这是 UTF-8"的标志位(bit 11)。解压工具读到这些字节,只能按 zip 规范的历史默认编码 **CP437** 去猜——于是 `期末大作业` 变成 `ÆÚÄ©´ó×÷Òµ`。

反过来,macOS/Linux 打包的 UTF-8 压缩包在一些旧版 Windows 工具里解出来也是乱码。跨系统、跨语言(日文游戏 MOD、繁中资源、韩文资料)时更是重灾区。

## 为什么用 luanma

| 现有方案 | 问题 |
|---|---|
| Bandizip / 7-Zip GUI | 要手动逐个试编码;命令行 `-mcp=936` 得背代码页数字 |
| Python 3.11 `metadata_encoding` | 需要**你自己知道**是什么编码,且只能读不能修 |
| 网传脚本 `encode('cp437').decode('gbk')` | 只处理 GBK,不防路径穿越,不清垃圾文件 |

`luanma` 把这件事变成一条命令:**自动检测**是 GBK、Big5、Shift-JIS、EUC-JP、EUC-KR 还是漏标 flag 的 UTF-8,先给你看修复对照表,再安全解压或直接产出一个人人都能正常打开的 UTF-8 压缩包。压缩包早就删了、只剩一目录乱码文件?`--rename` 原地改回来。乱码文件被人**重新打包**成了"正常"压缩包(二次乱码)?也能识别并修复。

## 安装

```bash
pip install git+https://github.com/hc-ui/luanma.git
```

零第三方依赖,Python 3.9+,Windows / macOS / Linux 通用。（PyPI 包名 `luanma` 上架中，上架后可直接 `pip install luanma`。）

## 使用

```bash
# 1. 预览:检测编码,显示"乱码 -> 修复后"对照表(不写盘,放心跑)
luanma bad.zip

# 2. 解压:按检测到的编码解压
luanma bad.zip -x
luanma bad.zip -x -d 输出目录

# 3. 修复压缩包本身:生成文件名为标准 UTF-8 的 bad_utf8.zip,可直接转发别人
luanma bad.zip --fix
luanma bad.zip --fix -o fixed.zip

# 自动检测不对时,手动指定编码
luanma bad.zip -e big5 -x

# 加密压缩包(ZipCrypto)
luanma bad.zip -x -p 密码

# 4. 已经解压出乱码了?对目录预览重命名计划,确认后 --rename 原地改回
#    (嵌套目录、乱码的目录名本身都会一并修复)
luanma 乱码目录/
luanma 乱码目录/ --rename

# 批量处理(自动展开通配符, PowerShell/cmd 下也可用) + 机器可读输出
luanma *.zip --json
```

预览输出示例:

```text
bad.zip: 检测到文件名编码 GB18030(置信度: 高)
  ÆÚÄ©´ó×÷Òµ/╔ÁÑ╬▒¿.docx
    -> 期末大作业/实验报告.docx
  (另有 2 个系统垃圾文件将被跳过, --keep-junk 可保留)
提示: 加 -x 按此编码解压, 或加 --fix 生成 UTF-8 压缩包
```

也可以作为 Python 库使用:

```python
from luanma import detect_zip, extract_zip, convert_zip, rename_dir

det = detect_zip("bad.zip")
print(det.encoding, det.confidence)   # 'gb18030' 'high'

report = extract_zip("bad.zip", dest="out/")
report = convert_zip("bad.zip", output="fixed.zip")
report = rename_dir("乱码目录/", apply=True)   # 修复已解压的目录
```

## 检测原理

对每个未标 UTF-8 flag 的文件名,取出原始字节,分别用候选编码(UTF-8、GB18030(GBK 超集)、Shift-JIS、EUC-JP、Big5、EUC-KR)试解码,再给解码结果打分:

- 命中**高频汉字表**(简体+繁体,约 900 字)或**高频韩文音节表**得高分——错误的编码解出来的多是生僻字,得分很低
- 假名是 Shift-JIS 的强信号;半角片假名(`ｱｲｳ` 这种经典乱码形态)在非日文编码下扣分
- 解码失败、控制字符、私用区字符、替换符 `�`、制表符画线(`╔╩╦`)重罚

得分最高的编码胜出,并给出置信度;置信度低时会列出候选,让你用 `-e` 指定。

对于**二次乱码**(乱码文件名被重新打包、带上了 UTF-8 标志):把名字按 CP437 还原成原始字节后走同一套检测,只在高置信度时才动手,且逐个名字做合理性打分——`café.txt` 这类真欧文文件名永远不会被误改。

## 安全性

- **默认只预览**,不碰任何文件;解压/转换永不修改源压缩包
- **防路径穿越**(zip-slip):`../` 等越界路径一律被约束在目标目录内
- **Windows 非法文件名自动清洗**:`< > : " | ? *`、保留设备名(`CON`、`LPT1`)、结尾空格/点
- **自动跳过系统垃圾**:`__MACOSX/`、`._*`、`.DS_Store`、`Thumbs.db`、`desktop.ini`(`--keep-junk` 可保留)
- 重名文件自动加 ` (2)` 后缀,不覆盖
- **`--fix` 原子写入**:先写临时文件再替换,中途失败不会留下残缺的"成品"压缩包
- **Windows 长路径支持**:深层中文目录树(含 UNC 网络路径)超过 260 字符限制时自动用 `\\?\` 前缀读写,不会解压到一半失败
- **目录重命名默认演习**(dry-run):先看完整计划,加 `--rename` 才动手;疑似乱码但把握不足的名字(如 `café.txt` 这类真欧文文件名)一律跳过不碰
- **终端输出防转义注入**:压缩包内文件名里的控制字符(如 ESC)显示前会被中和,恶意压缩包无法向你的终端注入转义序列

## Features (English)

- **Auto-detection.** Scores candidate encodings (GB18030/GBK, Big5, Shift-JIS, EUC-JP, EUC-KR, unflagged UTF-8) against frequency tables of common hanzi and hangul, instead of asking you to guess a code page.
- **Preview first.** Dry-run by default: see the mojibake-to-fixed name table before anything touches your disk.
- **Four actions.** Preview, extract with the right encoding, rewrite the whole archive to standard UTF-8 (flag bit 11 set) — or repair a directory that was already extracted with the wrong encoding (`--rename`, including the directory's own name), with a plausibility guard so real accented-Latin names like `café.txt` are never touched.
- **Double-mojibake aware.** Recognizes archives where a wrecked tree was re-zipped with a modern tool (names UTF-8-flagged but the text is cp437 mojibake) and repairs them only at high confidence.
- **Safe by default.** Zip-slip protection, Windows-illegal-name sanitizing, terminal-escape neutralization, OS-junk filtering (`__MACOSX`, `.DS_Store`, ...), collision-safe renaming, atomic `--fix` output, source archive never modified.
- **Zero dependencies.** Pure standard library, Python 3.9+, `py.typed`. Usable as a CLI and as a library. `--json` output for scripting.
- **Real-world hardened.** ZipCrypto password support (`-p`), Windows long-path (`\\?\`, UNC) handling, glob expansion under PowerShell/cmd, file-vs-directory collision recovery.

## 局限

- 检测是启发式的:文件名极短或没有 CJK 字符时置信度会下降,此时请用 `-e` 手动指定(预览模式会给出候选排序)。
- 目录模式假定乱码来自最常见的 CP437 回退(`ÆÚÄ©´ó` 这种形态);经由其他错误编码链产生的乱码(如按 Big5 误解 GBK)暂不支持。
- 加密支持传统 ZipCrypto(最常见);AES 加密的 zip(7-Zip/WinRAR 的可选项)受标准库限制暂不支持,会明确报错。
- 不支持 rar/7z(这两种格式自带 Unicode 文件名,本身较少出这个问题);tar/tar.gz 支持在路线图中。
- 只修文件名,不改文件内容——文件内容的乱码是另一个问题。

## 姆妹项目

- [eoldoctor](https://github.com/hc-ui/eoldoctor) — Git 换行符医生，一键治好 CRLF/LF
- [whoseport](https://github.com/hc-ui/whoseport) — 一条命令查出端口被谁占用并释放
- [gbt7714-lint](https://github.com/hc-ui/gbt7714-lint) — GB/T 7714—2025 参考文献格式检查与自动修复
- [kebiao2ics](https://github.com/hc-ui/kebiao2ics) — 大学课表转手机日历 .ics

## 贡献

欢迎 issue 与 PR,尤其欢迎附上检测失败的真实压缩包样本(可只发 `luanma xx.zip --json` 的输出)。跑测试:

```bash
pip install -e ".[dev]"
pytest
```

## License

[MIT](LICENSE)
