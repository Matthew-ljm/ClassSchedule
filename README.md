# ClassSchedule｜课程表进度条
> 面向中小学多媒体教室的悬浮课表桌面工具｜MIT License
> 历史版本：**v2.1.6**｜支持 Windows10 / Windows11 x64 及 国产统信系统
> 最新稳定版本：**v3.1.1**｜仅支持 Windows10 / Windows11 x64（其他系统暂未适配）

[![Release](https://img.shields.io/github/release/Matthew-ljm/ClassSchedule.svg)](https://github.com/Matthew-ljm/ClassSchedule/releases)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python‑3.10+-blue)](.)

> 仓库地址：[https://github.com/Matthew-ljm/ClassSchedule](https://github.com/Matthew-ljm/ClassSchedule)
> 作者：刘俊铭

## 📖 项目概述
**课程表进度条 ClassSchedule** 是一套完全使用 Python 编写，面向学校教室公用电脑的桌面悬浮课表解决方案。
本软件在屏幕顶部放置一条置顶悬浮进度条，可视化展示当日课程、上课剩余/已进行时长；支持云端API课表与完全离线本地课表双模式。

项目不止单一悬浮窗口程序，是一整套完整套件：包含主UI程序、进程保护器、自动下课清理插件、座位表扩展插件、图形化设置面板、自动更新组件、一键安装程序。

> 设计初衷：解决多媒体教室缺少直观课表提示，动态调课，~~下课需要教师手动关闭一大堆软件~~为了防止老师拖堂的痛点。
> ⚠️ 自动下课清理插件仅适合**学校公共机房/教室电脑，不建议家用电脑开启**。

## ✨ 项目整体特性
### 📊 课表悬浮窗口核心
1. 无边框圆角置顶悬浮窗口，置于屏幕顶部，可拖拽、键盘方向键移动位置。
2. **双数据源**：云端HTTP API 获取课表；网络异常自动降级读取本地JSON课表。
3. NTP阿里云网络校时，系统时间不准时提供软件内部计时器兜底。
4. 内置课程配色库，支持单/双周课程语法解析，超长课程名字体自动缩小，支持Emoji表情渲染。
5. 可视化进度条，灰色覆盖已经结束课程区域，区分进行中、已结束课程；显示已上课时长 / 剩余倒计时。
6. 鼠标交互：单击隐藏窗口，再次单击2秒后恢复；鼠标悬停自动渐变透明隐藏，移出恢复显示，最大程度不遮挡课件。

### 🎥 教学模式（课件识别）
自动识别**WPS演示全屏放映、希沃EasiNote白板课件**运行状态；识别成功自动切换简约界面、降低窗口透明度，避免遮挡课件；课件退出自动切回普通模式。

### 🧩 模块化可扩展组件
1. **进程守护保护器**：多层保活机制，程序意外崩溃自动重启；特殊锁文件机制支持正常退出时阻止保护器反复拉起程序。
2. **class‑over 自动下课插件**：识别课程结束，下一节为课间/休息课时触发。弹出倒计时弹窗，支持立即下课、拖堂两分钟；倒计时结束批量清理非白名单进程，关闭文件夹窗口。可开关组件，设置面板可视化控制启用/禁用。
3. **座位表插件（可选组件）**：独立扩展程序，安装时可选部署；支持座位排布展示、首字母人名搜索、偏移天数配置，解决每周换座位同学发作业困难等问题。
4. **图形化设置面板**：快捷键 `Ctrl + ,` 唤起，图形界面完成全部配置，内置本地课表可视化编辑器，无需手写JSON，支持一键重置全部配置。
5. **全自动更新系统**：后台更新检测，图形更新弹窗，支持推迟更新、跳过特定版本；更新器自动结束全部旧进程，下载、解压新版本，保留用户课表、配置、白名单，覆盖更新程序文件。
6. **一键安装程序**：控制台交互式安装脚本，管理员权限运行；可选组件安装，设置各项参数；自动生成进程白名单；支持创建Windows计划任务实现开机自启。

### ⌨️ 快捷键汇总
|快捷键|功能说明|
|---|---|
|`Ctrl + ,`（逗号）|打开设置窗口（程序需要前台焦点）|
|`Ctrl + Q`|**彻底退出程序**，写入锁，阻止保护器自动重启|
|鼠标左键拖拽|移动悬浮进度条窗口|
|鼠标左键单击|临时隐藏窗口|
|↑ ↓ ← →|键盘微调窗口位置|

## 📦 系统要求
- 操作系统：Windows10 / Windows11 **x64** 或 国产统信系统
- Python运行环境（源码运行）：Python3.10+
> 新版不支持 Windows7、32位Windows、Linux、macOS；大量依赖Windows原生Win32 API。

### Python依赖清单
```txt
PyQt6
psutil
requests
pynput
pywin32
ntplib
```

## 🚀 使用方式
### 方式一：下载Release打包exe（普通用户推荐）
前往 [Releases](https://github.com/xxx/ClassSchedule/releases) 下载最新版本安装包
1. 解压后自动运行 `installer.exe`，脚本自动申请管理员权限。
2. 根据控制台提示选择：是否开启自动下课插件、是否安装座位表插件，填写班级、各类延时参数。
3. 可选导入座位表JSON文件。
4. 脚本自动清理旧版本、复制程序资源、生成进程白名单。
5. 可选注册Windows计划任务实现开机自启。

> ⚠️ 安全软件会拦截计划任务注册，需要放行，否则开机自启失效。

### 方式二：源码直接运行（开发者、二次修改）
1. 克隆仓库
```bash
git clone [https://github.com/Matthew-ljm/ClassSchedule.git](https://github.com/Matthew-ljm/ClassSchedule.git)
cd ClassSchedule
```
2. 运行主程序
```bash
python 课程表进度条.py
```

## 📁 软件安装之后本地目录
> 默认安装路径 `%LOCALAPPDATA%\Programs\ClassSchedule`
```
%LOCALAPPDATA%\Programs\ClassSchedule
├─课程表进度条/
│   ├─课程表进度条.exe        # 主悬浮窗口
│   ├─ClassSchedule.exe        # 守护入口程序
│   ├─class‑over.exe / class‑over.lock #自动下课组件，exe启用，lock禁用
│   ├─settings.json           # 全局配置文件
│   ├─schedule.json           # 默认本地课表JSON
│   └─process_lock.lock       # 进程锁文件，标记用户手动退出
├─座位表/                     # 可选座位表插件目录
├─update_cache/               # 更新下载缓存
├─ClassScheduleUpdater.exe    # 后台自动更新程序
└─version.json                # 本地版本记录文件
```
额外配置文件：
- `C:\Users\[用户名]\Documents\sys_whitelist.txt`：class‑over自动下课进程清理白名单，一行一个进程名，名单内进程不会被杀死。

## 🔌 课表API规范
默认API地址：`https://test.m‑code.top/api/class‑schedule/`
GET请求参数 `class_num=班级数字`
返回JSON示例：
```json
{
    "status":"success",
    "is_single_week":true,
    "data":{
        "courses":[
            {"course_name":"语文","start_time":"08:00:00","end_time":"08:45:00"}
        ]
    }
}
```
> **如果你需要，我可以为你开放专属 API 接口服务，统一云端编辑页：[M-Code官网页面](https://test.m-code.top/edit-schedule.html/ "点击跳转编辑页")**。

### 本地课表JSON格式示例
```json
{
  "day1": [
    {"name":"语文","start":"08:00","end":"08:45"},
    {"name":"课间","start":"08:45","end":"08:55"}
  ],
  "day2": [],
  "day3": [],
  "day4": [],
  "day5": [],
  "day6": [],
  "day7": []
}
```
> `day1`代表周一，`day7`代表周日；支持单双周语法 `数学(单)/英语(双)`

## ⚠️ 重要风险提示
1. **class‑over自动下课插件风险**：该功能会批量结束系统进程，**仅限学校多媒体教室/机房公用电脑，家用电脑严禁开启**；务必维护好`sys_whitelist.txt`白名单，防止误杀需要保留的软件。
2. v3.1.1 目录架构发生重大变更，旧版本程序、配置文件不兼容。
3. 若要真正退出软件，请使用快捷键 `Ctrl + Q`，直接关闭窗口只会被保护器自动重新拉起。
4. 开机自启依靠Windows计划任务最高权限运行，部分杀毒软件会拦截。
5. 网络用于NTP校时、云端课表；断网可以完全使用本地课表运行。

## 📋 版本更新说明
完整更新日志见 [CHANGELOG.md](./docs/v3.1.1/CHANGELOG.md)
> 最新稳定版 v3.1.1（2026‑10‑02）
> - GUI全面迁移PyQt6，新增教学模式、悬停自动隐藏、图形课表编辑器、进程保护器、座位表增强、自动更新优化；目录结构重构，旧版本不兼容。

## 🤝 贡献指南
欢迎提交 Issue 反馈BUG、提出功能建议；欢迎提交 Pull Request。
1. 提交BUG请附上系统版本、软件版本、报错信息。
2. 代码遵循现有编码风格；UI相关修改需要保证Windows平台兼容性。

反馈渠道：
- 网页反馈：https://m‑code.top/feedback.html
- 邮箱：contact@m‑code.top

## 📄 License
MIT License
Copyright © 2026 刘俊铭

> 本项目开源免费，允许修改、分发；二次分发请保留原始版权声明。
