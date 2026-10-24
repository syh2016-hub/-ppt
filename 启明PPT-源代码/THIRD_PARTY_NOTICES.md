# 第三方组件与许可说明

启明 PPT 使用了以下开源组件。完整许可文本以各自项目发布页为准。

## 动画 OOXML 预设

`backend/animations.py` 中的 PowerPoint 原生入场动画预设 XML 参考并改编自：

- **ppt-master** — https://github.com/hugohe3/ppt-master
- Copyright (c) 2025-2026 Hugo He
- MIT License

我们只取了本软件实际使用的少量入场效果（淡入、飞入、擦除、缩放、溶解），
并按每个形状重新编号、设定时长与目标。分页转场使用标准 PresentationML
元素独立编写。

MIT License 要点：允许使用、复制、修改、合并、发布、分发、再许可和销售，
但需保留版权声明与许可声明。本文件即为该声明。

### ppt-master MIT 许可全文

```
MIT License

Copyright (c) 2025-2026 Hugo He

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Python 运行库

| 组件 | 用途 | 许可 |
| --- | --- | --- |
| Flask | 本地 HTTP 服务 | BSD-3-Clause |
| Waitress | 本地 WSGI 服务器 | ZPL-2.1 |
| pywebview | 桌面窗口（WebView2） | BSD-3-Clause |
| python-pptx | 生成可编辑 PPTX | MIT |
| python-docx | 读取 Word 参考文档 | MIT |
| pypdf | 读取 PDF 参考文档 | BSD-3-Clause |
| openpyxl / et_xmlfile | 读取 Excel 参考文档 | MIT |
| edge-tts | 高质量中英文神经网络旁白 | LGPL-3.0 |
| aiohttp | edge-tts 网络请求 | Apache-2.0 |
| Pillow | 图像生成与处理 | HPND |
| NumPy | 背景与视频帧计算 | BSD-3-Clause |
| requests / BeautifulSoup / lxml | 联网检索与网页解析 | Apache-2.0 / MIT / BSD |
| imageio-ffmpeg | 内置 ffmpeg 可执行文件 | BSD-2-Clause（封装） |
| PyMuPDF（开发环境，可选） | PDF 预览辅助 | AGPL-3.0（未打包进 exe） |
| LibreOffice（外部可选） | 旧版 Office 格式转换与 PDF 导出 | MPL-2.0（不随软件分发） |

## 图标

界面图标为手绘线性 SVG，参考通用线性图标风格；品牌图形由本项目绘制。
字体使用 Windows 系统自带字体（微软雅黑等），不随软件分发字体文件。

## 在线内容

联网模板搜索只提取公开图片的配色用于生成原创版式。图片来源与授权请在
使用前自行确认；软件不会在导出文件中添加任何水印或品牌标识。
