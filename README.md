# 歌词下载器

![Version](https://img.shields.io/badge/Version-1.0.2-blue)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows-0078D4?logo=windows&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

一个面向 Windows 的桌面歌词下载工具：输入歌曲名，在**网易云音乐、QQ 音乐、酷狗音乐**标签页中浏览结果，双击即可把歌词保存为 `.lrc` 文件。

界面使用 Python 标准库 Tkinter 编写，不依赖额外的 GUI 框架。发布版是**单文件 exe**，另附当前用户安装包。程序启动时会将运行库解压到 `%LOCALAPPDATA%` 下的临时目录，退出时自动清理，不依赖系统的 `%TEMP%`。

## 功能

- 只搜索当前所在平台的标签页，切换标签即可搜索另一个平台
- 每次加载 20 条结果，底部“加载更多”继续加载，已加载的条目不会重复
- 每个平台独立标签页，显示歌曲名、歌手、专辑、时长
- 双击搜索结果直接下载歌词；也可选中后点击“下载所选歌词”
- 自动保存为 UTF-8（带 BOM）的 `.lrc` 文件，文件名取自歌曲名
- 同名文件不会覆盖，自动保存为 `歌曲名 (2).lrc`、`歌曲名 (3).lrc`
- 主窗口显示当前保存目录，提供“打开保存目录”和“设置”按钮
- 保存目录可修改并记住，下次启动继续使用
- 搜索期间有状态提示；接口失败、歌词为空、保存失败都会给出中文提示
- 支持键盘操作：`Enter` 搜索、`F5` 重新搜索、`Ctrl+F` 聚焦搜索框、`Ctrl+1/2/3` 切换平台

## 下载

前往 [Releases](https://github.com/pyk136874470692022/Lyrics-Download/releases/latest) 下载：

| 文件 | 用途 |
|---|---|
| `LyricsFetcher-Setup-1.0.2.exe` | 推荐，当前用户安装包，不需要管理员权限 |
| `LyricsFetcher-1.0.2.exe` | 单文件绿色版，复制一个文件即可运行 |

> GitHub 上的附件使用英文文件名；本机 `dist\` 中的构建产物仍是中文名，内容相同。

## 直接使用

推荐运行下载的安装包 `LyricsFetcher-Setup-*.exe`。它只安装到当前用户目录，不需要管理员权限：

```text
%LOCALAPPDATA%\Programs\LyricsFetcher
```

也可以直接运行单文件绿色版 `LyricsFetcher-*.exe`。它只有这一个文件，可以单独复制到桌面或其他目录，不再需要 `_internal` 文件夹。

1. 在顶部输入歌曲名或歌手名，按 `Enter` 或点击“搜索”。
2. 程序只搜索当前选中的平台；点击标签切换平台后，再点“搜索”即可查另一个平台。
3. 首批显示 20 条结果；点击列表底部“加载更多”继续加载。
4. 双击某条结果下载歌词，或选中后点击“下载所选歌词”。
5. 下载完成后右下角会提示文件名；点击主窗口底部的“打开保存目录”即可查看。
6. 点击“设置”可以修改保存目录，保存后立即生效。

默认保存目录是 `%USERPROFILE%\Music\歌词`。设置保存在 `%APPDATA%\LyricsFetcher\settings.json`。

> 搜索结果可能包含翻唱、Live、钢琴版等版本。网易云的搜索排序不一定把原唱放在第一位，请根据歌手和专辑名选择需要的版本。

## 从源码运行

环境：Windows 10/11，Python 3.10+（开发使用 Python 3.12.7）。在项目根目录执行：

```powershell
python -m pip install -r requirements.txt
python lyrics_app.py
```

运行核心单元测试：

```powershell
python -m unittest discover -s tests -v
```

## 打包为单文件和安装包

需要额外安装 PyInstaller，以及 Inno Setup 6（默认路径 `C:\Program Files (x86)\Inno Setup 6`）。在项目根目录执行：

```powershell
python -m pip install -r requirements-dev.txt
powershell -ExecutionPolicy Bypass -File build.ps1
```

脚本会先运行单元测试，再用 `LyricsFetcher.spec` 打包单文件 exe，最后用 `installer.iss` 生成当前用户安装包。输出为：

```text
dist\歌词下载器.exe                 # 单文件绿色版
dist\歌词下载器安装包.exe           # 推荐分发的安装包
```

单文件版为无控制台窗口（windowed），图标与版本信息已写入 exe。启动时 PyInstaller 会把运行库解压到 `%LOCALAPPDATA%\_MEIxxxxxx`，程序退出时自动删除；这样即使普通用户的 `%TEMP%` 不可写，也不会再报 `Could not create temporary directory!`。安装包默认安装到 `%LOCALAPPDATA%\Programs\LyricsFetcher`，不需要管理员权限。

## 项目结构

```text
Lyrics-Download/
├─ .gitattributes
├─ .gitignore
├─ LICENSE
├─ README.md
├─ CHANGELOG.md
├─ requirements.txt
├─ requirements-dev.txt    # 开发/打包依赖
├─ api_clients.py          # 三个平台的搜索与歌词接口
├─ lyrics_app.py           # Tkinter 界面与下载/保存逻辑
├─ LyricsFetcher.spec      # PyInstaller 打包配置（单文件）
├─ installer.iss           # Inno Setup 当前用户安装包脚本
├─ version_info.txt        # exe 版本信息
├─ build.ps1               # 测试 + 打包 + 生成安装包
├─ assets/
│  └─ app.ico
├─ tests/
│  └─ test_core.py
├─ tools/
│  └─ make_icon.ps1        # 重新生成应用图标
└─ dist/                   # 本地构建产物，已忽略，不上传 Git
```

## 接口说明

程序调用的是各平台网页端正在使用的公开接口，无需登录：

- 网易云音乐：网页搜索接口 + 歌词接口
- QQ 音乐：`client_search_cp` 搜索 + `fcg_query_lyric_new` 歌词
- 酷狗音乐：`song_search_v2` 搜索，再通过 `krcs` 候选与 `lyrics.kugou.com/download` 获取 LRC

这些接口并非官方开放 API，平台调整后可能失效；程序会把异常转换为中文提示，而不是直接崩溃。

## 常见问题

**搜索很慢或平台失败？**  
程序每次只请求当前标签页的平台。常见原因是网络不稳定或平台临时限流；切换到其他标签页仍可正常搜索，稍后重试即可。

**提示“暂无可下载的歌词”？**  
该歌曲可能是纯音乐、尚未配词，或平台没有公开歌词。换一个版本试试。

**提示保存失败？**  
检查保存目录是否存在写权限，以及安全软件是否拦截了程序写入。

**为什么不再提示 `Could not create temporary directory!`？**  
1.0.2 虽然是单文件程序，但打包时把运行库解压位置固定到了每个用户都可写的 `%LOCALAPPDATA%`，不再使用 `%TEMP%`/`%TMP%`。因此普通用户（非管理员）也能正常启动，临时目录不可写时不会再报这个错。

程序正常退出时会自动清理 `_MEIxxxx` 文件夹；如果被任务管理器强制结束，可能残留一个 `%LOCALAPPDATA%\_MEIxxxxxx` 目录，手动删除即可，不影响下次启动。

**安装需要管理员权限吗？**  
不需要。安装包使用 `PrivilegesRequired=lowest`，默认安装到当前用户的 `%LOCALAPPDATA%\Programs\LyricsFetcher`，不会写入 `Program Files`，也不改系统级设置。

**Windows 仍提示“Windows 已保护你的电脑 / 未知发布者”？**  
这是因为安装包没有受信任的商业代码签名证书，SmartScreen 对“下载来的、没有信誉记录的 exe”会拦截。彻底消除该提示只能购买受信任的代码签名证书并对 exe 和安装包签名；自签名证书不能真正解决。

可用的处理方式：

1. 确认文件来自本机打包或可信来源。
2. 右键文件 →“属性”→ 勾选/点击“解除锁定”（Unblock）→“确定”。这能去掉下载标记，多数情况下不再触发 SmartScreen。
3. 若仍提示，点击“更多信息”→“仍要运行”。

程序本身不联网下载可执行文件，也不修改系统设置；部分安全软件可能对 PyInstaller/Inno Setup 打包的程序误报，可加入信任。

## 发布与更新到 GitHub

仓库地址：https://github.com/pyk136874470692022/Lyrics-Download

仓库只提交源码、测试和构建脚本，`dist/` 已在 `.gitignore` 中排除。构建产物作为 **GitHub Release** 附件上传，不提交进 Git 历史。

> 后续请直接在 `Lyrics-Download` 仓库目录中修改，不要同时改旧的 `lyrics_fetcher` 备份，避免两份代码不一致。

### 修改 README 或其他文件

```powershell
cd C:\Users\1.hacker\Desktop\dsh\Lyrics-Download
git status
git diff
git add README.md
git commit -m "docs: update README"
git push
```

修改多个文件时可以用 `git add .`，但提交前先看 `git status`，确认没有把 `dist/`、`build/`、`_MEI*` 或测试歌词加进去。

### 发布新版本

1. 修改源码，并同步更新 `__init__.py`、`version_info.txt`、`installer.iss` 中的版本号。
2. 在 `CHANGELOG.md` 顶部增加新版本说明，更新 README 顶部的 Version 徽章和“下载”表格中的附件名。
3. 重新打包：

   ```powershell
   powershell -ExecutionPolicy Bypass -File build.ps1
   ```

4. 提交源码并推送：

   ```powershell
   git add .
   git commit -m "release: v1.0.3"
   git push
   ```

5. 创建并推送标签：

   ```powershell
   git tag -a v1.0.3 -m "歌词下载器 v1.0.3"
   git push origin v1.0.3
   ```

6. 打开仓库的 **Releases → Draft a new release**，选择刚推送的标签，填写标题和更新说明，上传附件后发布。

GitHub Release 附件建议用英文名，避免上传接口把中文名变成 `default.exe`：

```text
dist\歌词下载器.exe          → LyricsFetcher-1.0.3.exe
dist\歌词下载器安装包.exe    → LyricsFetcher-Setup-1.0.3.exe
```

## 许可证

本项目使用 [MIT License](LICENSE)。`LICENSE` 中的版权人写的是 `LyricsFetcher contributors`，你可以改成自己的名字。

## 声明

本项目仅供个人学习与离线歌词整理使用，与网易云音乐、QQ 音乐、酷狗音乐均无关联。歌词版权归原权利人所有，请勿用于商业传播或再分发。
