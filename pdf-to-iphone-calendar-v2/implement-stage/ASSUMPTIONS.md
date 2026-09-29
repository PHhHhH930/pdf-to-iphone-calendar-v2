# Assumption Ledger

ASK mode: never; effort: balanced; assurance: draft

| ID | 未指定事项 | 选择 | Class | Source |
|---|---|---|---|---|
| A-001 | 类似 PDF 的边界 | macOS 上有可提取文字、七天表头及节次/周次字段的同类教务表；不承诺 OCR 或任意模板 | semantic | default |
| A-002 | 起始日期与假期 | 必须指定第一周周一；不推断假期、调休与临时停课 | semantic | default |
| A-003 | 节次时间 | 从 PDF 提取；提取不全则失败，允许显式 JSON 时间表覆盖，不静默套用旧课表时间 | semantic | default |
| A-004 | 识别异常 | 标题、周次、节次或星期无法可靠匹配即停止，不生成部分日历 | semantic | default |
| A-005 | 上传方式 | 保留本地文件输入 CLI；不新增公开上传网站，课表不离开电脑 | interface | default |
| A-006 | 输出覆盖 | 输出必须是 .ics；已有文件需显式 --force | interface | default |
| A-007 | 地点 | 西南大学南北区为校园内部区域，数字为楼号；坐标仅为校园级，不代表具体教学楼 | semantic | user |
| A-008 | UID | 使用课程内容与日期生成稳定 ID，不依赖文件名、绝对路径或课程排序；旧版重导可能重复 | interface | default |
| A-009 | 跨页 | 无表头的续页仅在页面尺寸和旋转与上一页一致时沿用星期布局 | semantic | default |
