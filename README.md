# 项目规划
```
EvaProject/
├── cmake/                      # CMake 模块 (如 FindZlib.cmake)
├── src/                        # C++ 源代码 (核心二进制处理)
│   ├── archiver/               # PKG 打包/解包逻辑
│   ├── common/                 # 共有定义, RawDirectory 结构体等
│   └── main.cpp                # 命令行入口 (pkgtool)
├── python/                     # Python 源代码 (业务逻辑)
│   ├── evatrans/               # 作为一个可安装的 Python 包
│   │   ├── __init__.py
│   │   ├── extractor.py        # 提取日文逻辑
│   │   ├── injector.py         # 回填逻辑
│   │   └── encoder.py          # 自定义 CP932/GB2312 映射
│   └── tests/                  # Python 单元测试
├── include/                    # C++ 公开头文件
├── third_party/                # 外部依赖 (nlohmann_json, pugixml, zlib)
│   └── CMakeLists.txt          # 统一管理第三方库
│
├── data/                       # 【数据资产区】(不进入版本控制)
│   ├── 01_raw/                 # 原始 PKG 和解包后的原始副本
│   ├── 02_workspace/           # 翻译过程中的文件 (XML/NUT)
│   └── 03_patch/               # 回填后的、待打包的文件
│
├── .gitignore                  # 忽略 data/ 和 build/
├── CMakeLists.txt              # 顶级 CMake 配置
├── pyproject.toml              # Python 依赖管理 (Poetry/Pip)
└── Makefile                 # 全流程自动化脚本 (Task Runner)
```

Python 使用 uv 管理依赖
C++ 使用 CMake 管理构建和第三方库，使用 Boost。