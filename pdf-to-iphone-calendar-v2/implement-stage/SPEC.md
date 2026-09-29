# 本次目标

让其他人提供同类西南大学文本型教务课表 PDF 时，也能按内容与表头自动识别，不依赖个人姓名、课程名或页面固定坐标。输入为 PDF 与第一周周一；输出为 ICS。日期由用户指定，不猜测开学日。

Base commit: none (not a git repo).

验收：`python3 -m unittest discover -s tests -v`；原始两页 PDF 回归与匿名合成 PDF 端到端测试。

范围不含扫描件 OCR、任意学校任意模板、节假日调课推断、服务器托管与自动修改用户日历。
