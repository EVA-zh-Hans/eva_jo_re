# EVA_JO_RE

《新世纪福音战士：序》PSP 版（ULJS00201）的汉化与逆向工程项目。

项目使用 Python 处理文本、图片、`NEVA.PKG` 和 ISO。PSP 插件负责加载自定义 PGF 字体。仓库提交构建代码、字体和文件级 ParaTranz JSON，不提交原始游戏镜像。

# 使用说明
在 GitHub Release 下载对应 `xdelta3` 补丁

使用[Xdelta patcher](https://kotcrab.github.io/xdelta-wasm/)对日文原版镜像打补丁。

> 如果 PPSSPP 菜单文字无法显示，请在设置中切换到软件渲染或于 https://www.ppsspp.org/devbuilds/ 下载每日构建版本 PPSSPP
> 针对这一问题的修复截至2026年8月初尚未进入正式版

## 环境要求

- Python 3.12 或更高版本
- [uv](https://docs.astral.sh/uv/)
- CMake
- [PSPDEV](https://pspdev.github.io/)，用于构建 PSP loader 和 runtime
- OpenSSL 与 zlib，用于构建 `pspdecrypt`
- Source Han Sans SC，路径为 `~/Library/Fonts/SourceHanSansSC-Normal.otf`
- `xdelta3`，仅在生成发布补丁时使用

先初始化依赖并构建 `pspdecrypt`：

```bash
git submodule update --init --recursive
uv sync
cmake -S third_party/pspdecrypt -B third_party/pspdecrypt/build
cmake --build third_party/pspdecrypt/build
```

设置 `PSPDEV`，再准备以下两个原版文件：

```text
temp/ULJS00201.iso
temp/ULJS00201/PSP_GAME/SYSDIR/EBOOT.BIN
```

第二个文件是镜像内的原始加密 EBOOT。根 Makefile 会用 `pspdecrypt` 将它解密为 `temp/cache/ULJS00201/EBOOT.BIN`。项目只支持与当前翻译偏移和补丁地址匹配的 ULJS00201 镜像。

## 构建

```bash
# 从原版 ISO 更新 translations/ 中的 ParaTranz JSON
make export

# 检查译文、控制符、EBOOT 偏移和编码
make check

# 构建插件、NEVA.PKG 和汉化 ISO
make build

# 重新构建并校验 ISO 内的所有预期修改
make verify

# 运行 Python 单元测试
make test

# 生成 xdelta 和 SHA-256 文件
make release
```

`make export` 会增量合并 JSON。源文和键未变化时，它会保留已有译文与 `stage`。导出报告位于 `build/reports/export.json`。

`make build` 生成 `dist/ULJS00201-zh.iso`。`make release` 还会生成 `dist/ULJS00201-zh.xdelta` 和 `dist/SHA256SUMS`。

## 构建流程

```text
temp/ULJS00201.iso
        |
        +-- extract --> temp/cache/ULJS00201/NEVA.PKG
        |                    |
        |                    +-- scan NUT/XML/BIN
        |                    +-- merge translations/*.json
        |                    +-- rebuild JIS2UCS.BIN
        |                    +-- patch GIM/BIN pictures
        |                    `-- rebuild NEVA.PKG
        |
        +-- decrypt EBOOT.BIN --> BOOT.BIN -- patch strings
        |
        +-- build PSP loader/runtime and collect static overrides
        |
        `-- sparse ISO overlay --> dist/ULJS00201-zh.iso
```

流程不会维护完整的 ISO 或 PKG 解包树。`app/iso.py` 只提取所需文件，并将 overlay 写回原镜像。`app/workflow.py` 为每个阶段生成 JSON 报告。

## 翻译文件

`translations/` 保留 `NEVA.PKG` 内的相对路径，并在源文件名后增加 `.json`。例如：

```text
NEVA.PKG:     FREE/NEV_TEV0201.NUT
ParaTranz:    translations/FREE/NEV_TEV0201.NUT.json
```

每个 JSON 项目包含稳定键、源文、译文和上下文：

```json
{
  "key": "e_0123456789_0001_abcdef0123",
  "original": "原文",
  "translation": "译文",
  "context": "File: FREE/NEV_TEV0201.NUT\nLine: 42"
}
```

键由文件路径、字符串序号和源文哈希组成。不要手工修改 `key` 或 `original`。重新导出时，任一部分变化都会生成新键，并在报告中记录旧项目。

构建会检查 `$变量`、`%s`、标签和 `▽`、`△` 等控制符。译文必须保留同组语义控制符。换行控制符可以按中文排版调整。

### NUT

`app/nut.py` 提取包含非 ASCII 字符的 Squirrel 原始字符串 `@"..."`。扫描器跳过行注释、块注释和普通字符串。`DecideStart("...")` 是已确认的例外。

导出上下文包括行号、调用名、`IMC_*` 说话人和相邻语音 ID。回填时，真实换行会转换为 `\n`，未转义的双引号会自动转义。

### XML

游戏内有少量不符合标准的 `<!-- ... ->` 注释。`app/xml.py` 使用保留原始文本布局的扫描器，不用 XML 序列化器重写文件。

扫描器提取文本节点、CDATA 和属性。文本节点会转义 XML 特殊字符。游戏属性保持原样，因此属性译文不能包含双引号。

### BIN

项目处理以下结构化 BIN：

| 文件 | 可翻译字段 |
| --- | --- |
| `ADJUST/WEP_PARAM.BIN` | 武器名、格式化属性、说明 |
| `ADJUST/EVA_SKILL_PRICE.BIN` | 技能名、说明 |
| `EVENT/MISSION_FORMAT.BIN` | 任务名 |
| `PEI/AI_TALKLIST.BIN` | 自由行动话题 |

前三个文件使用通用表结构。`AI_TALKLIST.BIN` 使用固定长度记录。两类文件都由专用解析器检查边界、指针、CP932 和填充字节。

### EBOOT

`translations/EBOOT.BIN.json` 只包含人工确认的 CP932 字符串偏移。每个键使用 `eboot_XXXXXXXX` 格式，并额外保存 `offset`。

EBOOT 译文在原槽位内替换，编码后不能长于源文。`app/eboot_patch.py` 还维护一组固定 UTF-8 偏移，用于存档标题和章节名称。受限 SJIS 扫描器 `scripts/scan_eboot_sjis.py` 只用于调查，不参与正式导出。

## `NEVA.PKG` 格式

以下结构来自 ULJS00201 的实测文件、当前解析器和单元测试。所有整数均为小端序。名称使用 CP932，并以 NUL 结尾。

```text
0x00000000  BPK0 header
0x00000014  header 后的保留区
0x00000800  BDL0 文件数据块，通常按 0x800 对齐
...         文件索引块，按 0x10 对齐
...         目录索引块，按 4 字节对齐
EOF
```

这与早期逆向结论一致：具体文件位于前部，文件索引位于中部，目录索引位于末尾。目录名不是嵌套树。`NUT` 等名称中的路径关系由目录记录和文件名共同组成。

### BPK0 头

头长 `0x14` 字节，对应 `struct.Struct("<4sIIII")`。

| 偏移 | 大小 | 含义 |
| ---: | ---: | --- |
| `0x00` | 4 | 魔数 `BPK0` |
| `0x04` | 4 | 未知字段，重打包时保留 |
| `0x08` | 4 | 目录索引起点 |
| `0x0C` | 4 | 目录索引与文件索引的距离 |
| `0x10` | 4 | 文件索引起点 |

解析器要求 `0x14 <= 文件索引起点 <= 目录索引起点 < 文件大小`。重建时，`0x0C` 写入两个索引起点之差。

### 目录记录

固定部分长 `0x14` 字节，对应 `struct.Struct("<IHHIII")`。固定部分后紧跟目录名，再对齐到 4 字节。

| 偏移 | 类型 | 含义 |
| ---: | --- | --- |
| `0x00` | `u32` | 未知字段 0 |
| `0x04` | `u16` | 未知字段 1 |
| `0x06` | `u16` | 目录内文件数 |
| `0x08` | `u32` | 该目录的文件记录表偏移 |
| `0x0C` | `u32` | 文件记录表和名称区的分配大小 |
| `0x10` | `u32` | 原文件中为零，重打包时保留 |

目录名 `.` 表示 PKG 根目录。空目录可以使用零偏移和零大小。

### 文件记录

每条记录长 `0x10` 字节，对应 `struct.Struct("<IIII")`。同一目录的全部记录之后，按相同顺序连续存放文件名。

| 偏移 | 类型 | 含义 |
| ---: | --- | --- |
| `0x00` | `u32` | 未知字段，重打包时保留 |
| `0x04` | `u32` | BDL0 头、负载和尾部填充的分配大小 |
| `0x08` | `u32` | 解压后的文件大小 |
| `0x0C` | `u32` | BDL0 数据块偏移 |

`allocated_size` 决定能否原位替换。新数据块不超过该值时，工具保留整个 PKG 布局，并将剩余区域清零。

### BDL0 数据块

每个文件数据块以 `0x20` 字节的 BDL0 头开始，对应 `struct.Struct("<4sIIII12s")`。

| 偏移 | 大小 | 含义 |
| ---: | ---: | --- |
| `0x00` | 4 | 魔数 `BDL0` |
| `0x04` | 4 | 解压后的文件大小 |
| `0x08` | 4 | zlib 负载大小，零表示未压缩 |
| `0x0C` | 4 | 未知字段 1，重打包时保留 |
| `0x10` | 4 | 未知字段 2，重打包时保留 |
| `0x14` | 12 | 未知或填充数据，重打包时保留 |

工具保留每个条目的压缩方式。压缩条目使用 Python `zlib.compress()`，未压缩条目直接写入。读取时，解析器同时检查 zlib 流和解压后大小。

### 重打包策略

`app.pkg.replace_entries()` 根据新数据大小选择策略：

1. 没有替换项时，直接复制原 PKG。
2. 所有新数据块均能放回原分配区时，使用 `fixed-layout`。
3. 任一数据块溢出时，使用 `rebuilt` 重建全部偏移和索引。

`rebuilt` 保留目录顺序、文件顺序、未知字段、原始文件名和未修改负载。数据块按 `0x800` 对齐，文件索引按 `0x10` 对齐。

## 其他二进制格式

### 通用 BIN 表

`app/bintable.py` 处理一个小端序单表格式。头部包含五个 `u32`：

| 偏移 | 含义 |
| ---: | --- |
| `0x00` | 表数量，当前文件必须为 1 |
| `0x04` | 记录区偏移 |
| `0x08` | 记录数 |
| `0x0C` | 字段数 |
| `0x10` | 字段类型表偏移，当前文件必须为 `0x14` |

字段类型表为连续 `u32`。类型 `0`、`1`、`2`、`3`、`4` 的宽度分别为 4、4、1、2、4 字节。类型 `4` 保存字符串池的绝对偏移。

字符串池紧跟记录区。字符串使用 CP932 和 NUL 结尾，并按指针顺序连续排列。文件末尾允许最多三个零字节，使总大小对齐到 4 字节。回填会重建字符串池并更新每个指针。

### AI_TALKLIST.BIN

每条记录长 `0x70` 字节：

| 偏移 | 大小 | 含义 |
| ---: | ---: | --- |
| `0x00` | `0x20` | CP932 话题文本，NUL 结尾 |
| `0x20` | `0x20` | CP932 角色 ID，NUL 结尾 |
| `0x40` | `0x30` | 当前未解释的数据 |

最后一条 `0x70` 字节记录全部为 `0xFF`，用作结束标记。文本槽最多容纳 31 个编码字节。回填不会改变文件大小或其他字段。

### GIM 和内嵌 P4 图片

PSP GIM 以 `MIG.00.1PSP` 标识开始。根块类型为 `2`，picture 块类型为 `3`。`app.gim.split_gim_pictures()` 根据块大小和 next-block 偏移拆分多 picture 文件。

当前图片补丁直接替换三个已确认文件的像素区：

- `COMMON/DECIDE.BIN`：确认和取消标签。
- `BF/BF_CALL_0.GIM`：30 张 loading 标题。
- `BF/BF_01.BIN`：战斗简报字段标签。

这些图片使用 4 bpp 调色板像素。像素按 `32 x 8` tile swizzle，低半字节在前。调色板包含 16 项，补丁按原调色板的 alpha 选择最接近的索引。

### JIS2UCS.BIN 与字体映射

`FONT/JIS2UCS.BIN` 是小端序 `u16` Unicode 码点表。游戏文本仍使用受限 CP932 双字节编码。

`app.font.build_plan()` 查找未被源文或译文直接占用的双字节字符槽。它将所需汉字写入对应的 Unicode 表项，并在文本中写入该槽原有的 CP932 字节。构建结果位于：

- `build/generated/JIS2UCS.BIN`
- `build/generated/charset-map.json`
- `build/reports/charset.json`

这种替换避开游戏不能安全处理的 CP932 扩展区。自定义 `plugin/fonts.pgf` 必须包含最终 Unicode 字形。

## EBOOT 逆向函数分析

本节保留旧 README 的逆向结果。地址和全局变量只适用于当前 ULJS00201 解密 EBOOT。`sub_*` 名称来自反编译器，未知字段名称仍是推测。

### 职责索引

下表的建议名称用于记录当前理解，不表示游戏原始符号名。

| 地址 | 建议名称 | 当前判断 | 置信度 |
| --- | --- | --- | --- |
| `sub_898B380` | `ResourcePrepare` | 初始化文件上下文，并在外部资源、普通文件和 PKG 条目之间选择。 | 高 |
| `sub_898BA34` | `DirectFileOpen` | 打开普通文件，并将 fd 与文件大小写入上下文。 | 中 |
| `sub_898ADE0` | `BuildResourcePath` | 根据运行模式生成 `host0:`、`disc0:` 或 `ms0:` 路径。 | 高 |
| `sub_898B520` | `ResourceLoad` | 分配或选择缓冲区，再从已选数据源读取全部内容。 | 高 |
| `sub_898AAD0` | `IsPkgOpen` | 返回 `NEVA.PKG` 全局状态是否有效。 | 高 |
| `sub_898C9F8` | `PkgFindEntry` | 查询 PKG 索引，并填写大小、偏移和压缩相关字段。 | 中 |
| `sub_898CAF0` | `PkgReadEntry` | 从 PKG 读取条目，并在需要时解压。 | 中 |
| `sub_898ABD4` | `ProbeSourceA` | 按资源名查询第一类已注册数据源。返回值存入上下文 `0x04`。 | 低 |
| `sub_898AFF8` | `ProbeSourceB` | 按资源名查询第二类已注册数据源。返回值存入上下文 `0x08`。 | 低 |
| `sub_898D2B8` | `GetSourceBSize` | 在第二类数据源命中后返回资源大小。 | 中 |
| `sub_898D3B4` | `ReadSourceB` | 将第二类数据源内容复制到目标缓冲区。 | 中 |
| `sub_898AAE0` | `PrepareSharedBuffer` | 准备 `dword_8AA270C` 指向的共享缓冲区。 | 中 |
| `sub_89E8524` | `Allocate` | 分配 `size + 1` 字节的读取缓冲区。 | 中 |
| `sub_89E8570` | `Free` | 释放上下文之前持有的缓冲区。 | 中 |

整体调用关系如下：

```text
ResourcePrepare (sub_898B380)
    |
    +-- ProbeSourceA (sub_898ABD4)
    +-- ProbeSourceB (sub_898AFF8) --> GetSourceBSize (sub_898D2B8)
    +-- IsPkgOpen (sub_898AAD0) ----> PkgFindEntry (sub_898C9F8)
    `-- DirectFileOpen (sub_898BA34) -> BuildResourcePath (sub_898ADE0)

ResourceLoad (sub_898B520)
    |
    +-- ReadSourceB (sub_898D3B4)
    +-- sceIoLseek / sceIoRead / sceIoClose
    `-- PkgReadEntry (sub_898CAF0)
```

### 文件上下文结构

`sub_898B380()`、`sub_898BA34()` 和 `sub_898B520()` 共享一个约 `0x130` 字节的上下文。当前可确认的布局如下：

```c
typedef struct FileContext {
    int state_00;
    int state_04;
    int source_08;
    void *pkg_buffer;       // 0x0C，PKG 读取目标或中间状态
    char *buffer;           // 0x10，最终数据缓冲区
    int state_14;
    int size;               // 0x18，解压后的文件大小
    int pkg_offset;         // 0x1C，BDL0 在 NEVA.PKG 中的偏移
    int pkg_stored_size;    // 0x20，PKG 中的读取大小
    int fd;                 // 0x24，直接文件句柄
    int pkg_fd;             // 0x28，NEVA.PKG 文件句柄或相关状态
    char name[256];         // 0x2C，资源名
    int flags_12c;          // 0x12C，低字节参与缓冲区策略
} FileContext;
```

字段总大小和部分名称尚未完全确认。`a1 + 301` 的字节写入说明末尾标志可能包含多个独立子字段。

### `sub_898B380()`：准备资源

该函数初始化 `FileContext`，复制资源名，并决定资源来自外部文件、已注册对象或 `NEVA.PKG`。

```text
初始化状态和标志
    |
    +-- sub_898ABD4(name) 命中 --> 记录状态并返回
    |
    +-- sub_898AFF8(name) 命中 --> 取得大小并返回
    |
    +-- NEVA.PKG 已打开 --> sub_898C9F8(context, name)
    |
    `-- NEVA.PKG 未打开 --> sub_898BA34(context, name, 1)
```

`sub_898C9F8()` 很可能查询 PKG 索引，并填入 `size`、`pkg_offset` 和压缩大小。`sub_898BA34()` 走普通文件系统路径。早期测试确认，强制走普通文件可以读取资源，但会因文件句柄未及时复用而耗尽 fd。

该函数及后续读取函数使用类似布尔值的返回约定。反编译结果中的 `1` 表示该分支已处理，`0` 表示没有取得可用数据。

### `sub_898BA34()`：打开普通文件

现有反编译记录只确认了该函数的入口部分。它先调用 `sub_898ADE0()` 生成设备路径，然后走 PSP 文件 API。调用完成后，`sub_898B520()` 可以从上下文中的 `fd` 和 `size` 读取文件。

该路径主要用于 PKG 未打开时的资源访问。它也是早期“将 PKG 文件全部拆到 disc0”实验使用的入口。

### `sub_898ADE0()`：生成设备路径

该函数根据全局模式生成完整路径。已观察到三种分支：

| 模式 | 结果 |
| ---: | --- |
| `0` | `host0:%s%s` |
| `1` | `disc0:/PSP_GAME/USRDIR/%s%s` |
| `2` | `ms0:NEVA/%s%s` |

disc0 分支会先将资源名转换为大写。第三个参数决定使用哪一个路径前缀，但两个前缀的具体语义仍未命名。

### `sub_898B520()`：加载资源内容

该函数使用 `FileContext` 中已选择的数据源完成读取。调用者未提供缓冲区时，它通过 `sub_89E8524(4, size + 1)` 分配内存。

读取顺序如下：

1. 如果 `source_08` 指向已注册对象，调用 `sub_898D3B4()`。
2. 如果 `fd >= 0`，调用 `sceIoLseek()`、`sceIoRead()` 和 `sceIoClose()`。
3. 如果 `NEVA.PKG` 已打开，调用 `sub_898CAF0()` 从 PKG 读取并解压。
4. 读取成功后，在 `buffer[size]` 写入 NUL。

函数对所有资源都额外保留一个 NUL 字节。这说明上层资源接口允许调用者把部分数据直接当作字符串使用，但该行为不表示所有资源都是文本。

低位标志为真时，函数使用 `dword_8AA270C` 指向的共享静态缓冲区。否则，它分配独立缓冲区。旧分析中的其他全局量如下：

- `dword_8AA272C`：异步 PKG 读取的临时缓冲区。
- `dword_8AA273C`：传给 `sub_898C0C0()` 的资源路径。

这些函数说明游戏本身已经统一了直接文件与 PKG 资源读取。当前汉化流程没有改写这条读取链，只在构建时重打包 PKG。

## PSP 字体插件

`plugin/src/loader/loader.c` 先加载原版 `BOOT.BIN`，再加载 `EVAJORT.PRX`。runtime 查询原模块基址，并安装字体补丁。

`FontPatch_Install()` 将原地址 `0x089CA918` 的 `sceFontOpen` 调用改为 `sceFontOpenUserFile`。游戏随后从 `disc0:/PSP_GAME/USRDIR/fonts.pgf` 加载自定义字体。补丁写入后会刷新数据缓存和指令缓存。

详细构建和地址说明见 [`plugin/README.md`](plugin/README.md)。

## 目录

| 路径 | 内容 |
| --- | --- |
| `app/` | Python 解析器、构建流程和 CLI |
| `translations/` | 提交到 Git 的文件级 ParaTranz JSON |
| `plugin/` | PSP loader、runtime 和自定义 PGF |
| `scripts/` | 调查、扫描、OCR 和 GIM 辅助脚本 |
| `tests/` | PKG、文本、BIN、字体和图片单元测试 |
| `third_party/` | `prxtool`、`pspdecrypt` 和 `pgftool` 子模块 |
| `overrides/` | 可选的静态 ISO 覆盖文件 |
| `temp/` | 原始 ISO 与缓存，`make clean` 不删除 |
| `build/` | 生成的 PKG、overlay、码表和报告 |
| `dist/` | 最终 ISO、xdelta 和校验和 |

`evajo.idc` 可为 IDA 数据库创建模块、导入、导出和重定位信息。`prxtool` 用于准备可供 IDA 分析的 PSP 模块。

## 验证范围

`make verify` 不只检查目标文件能否打开。它还执行以下检查：

- PKG 目录数、文件数、顺序和路径保持不变。
- 每个 BDL0 数据块都能读取和解压。
- 只有译文、码表和三组图片补丁可以修改 PKG 条目。
- 三组图片补丁与确定性重建结果完全一致。
- EBOOT 的 CP932 和 UTF-8 目标槽已经改变。
- 源 ISO、目标 ISO、源 PKG 和目标 PKG 均记录 SHA-256。

单元测试覆盖 PKG 原位替换与重建、NUT/XML 扫描、ParaTranz 合并、BIN 指针、字体槽、EBOOT 原位替换和 GIM 像素范围。
