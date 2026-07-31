# eva-jo-re

《新世纪福音战士：序》PSP 版（ULJS00201）的纯 Python 汉化构建工具。

项目只提交代码和文件级 ParaTranz JSON。原始镜像放在
`temp/ULJS00201.iso`；`build/` 和 `dist/` 中的内容均可重新生成。

```bash
uv sync
make export
# 在 translations/ 中翻译各个 NUT/XML 对应的 JSON
make check
make build
make verify
make test
```

`make export` 只读取镜像内 `NEVA.PKG` 的 NUT/XML，不维护完整解包树。
`make build` 根据当前译文动态生成码表和新 PKG，再通过稀疏 overlay 生成镜像。

目录约定：

- `translations/`：提交 Git 的文件级 ParaTranz JSON。
- `overrides/`：可选的静态 PSP 镜像覆盖文件。
- `temp/`：原始 ISO 和包缓存，`make clean` 不会删除。
- `build/`：码表、PKG、overlay 和验证报告，可随时重建。
- `dist/`：最终 ISO、xdelta 和校验和。

所有项目路径集中在 `Makefile` 顶部；Python CLI 不读取额外项目配置文件。
