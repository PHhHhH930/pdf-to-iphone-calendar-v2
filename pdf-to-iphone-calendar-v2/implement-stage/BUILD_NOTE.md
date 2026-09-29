# 实现与检查记录

| Rung | 内容 | 验收命令 | Tier | Status |
|---|---|---|---|---|
| F0 | 既有真实 PDF 到 ICS 主路径 | 原版 CLI 对原 PDF 转换 | MUST | 已通过：15 时段、131 日程；原 7 测试通过 |
| F1 | 表头定位、周次、完整性与时间表解析 | `python3 -m unittest discover -s tests -v` | MUST | 19 项纯逻辑测试通过 |
| F2 | 导出验证、稳定 UID 与文件保护 | `python3 -m unittest discover -s tests -v` | MUST | 通过（同套测试中的导出测试） |
| F3 | 匿名实际 PDF、文档和打包 | `python3 -m unittest discover -s tests -v` | MUST | 22 项测试通过；打包待最终复核 |

## Run record

2026-09-29：F0 exit 0，生成临时基准 ICS。原项目未初始化 Git；不自动初始化或提交。

F1：移除固定星期坐标，按表头方向与字符位置重组课程；原 PDF 提取全部14节时间，15课程时段、131事件；第一次真实 PDF 回归 exit 0。

F2：19项测试 exit 0，包含参数异常、UID、重复事件、ICS 字节行长度与 CRLF；无占位逻辑。

F3：4份匿名实际 PDF 加入仓库；22项测试 exit 0，无跳过（本机 macOS）；合成 PDF 正常版已渲染检查。与修改前基准逐条对比，131/131日程标题、开始和结束日期时间一致。

## Deferred

扫描件 OCR、其他学校任意模板、网页上传托管、手机端实际同步验收。

## Blockers

无。
