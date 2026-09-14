# Midi2Key

> 把 MIDI 键盘当作电脑键盘用 —— 零依赖、带 GUI 的 Windows MIDI 按键映射工具。

**按下 MIDI 键盘的某个键 → 敲击电脑键盘的某个键。** 适合用 MIDI 键盘在游戏、DAW、编辑器里演奏/操作。内置「光遇 PC」键位预设。

[![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-0078D6)](#运行环境)
[![Python](https://img.shields.io/badge/python-3.8%2B-3776AB)](#运行环境)
[![Dependencies](https://img.shields.io/badge/dependencies-0-brightgreen)](#运行环境)
[![License](https://img.shields.io/badge/license-MIT-blue)](#许可)

*English: A dependency-free Windows GUI tool that maps MIDI keyboard notes to computer keyboard keys (with a built-in Sky: Children of the Light preset).*

---

## 特性

- **零第三方依赖**：只用 Python 标准库。MIDI 用 Windows 自带的 `winmm.dll` 读取，按键用 `user32.dll` 的 `SendInput` 注入，不需要 `pip install` 任何东西。
- **图形界面 + Learn 捕获**：点「捕获 MIDI 音符」按下 MIDI 键，再点「捕获按键」按下电脑键，即可完成一条映射。
- **两种触发方式**：`点按`（按下即敲击一次，松开无动作，默认）/ `按住`（按住即按住，松开才抬起）。
- **三种按键编码**：`混合` / `扫描码` / `虚拟键`，应对不同游戏对按键事件的处理方式。
- **权限自检**：自动识别「目标程序以管理员运行导致按键被系统拦截」这一常见问题，并给出一键提权重启。
- **内置光遇预设**：`--preset sky` 或界面上的「预设：光遇」按钮，一键套用光遇 PC 的 15 键乐器键位。

## 运行环境

- Windows 10 / 11
- Python 3.8+（已在 3.14 + Tk 9.0 上验证）
- **无需管理员权限**——除非目标程序以管理员运行（见 [排查](#排查按了没反应)）

## 快速开始

1. 启动：双击 `run.bat`（无控制台窗口）；或 `debug.bat`（带控制台，便于排错）；或命令行 `python main.py`。
2. 顶部下拉框选择你的 MIDI 键盘，点「开始」。
3. 左侧点「添加」：
   - 「捕获 MIDI 音符」→ 按下 MIDI 键盘上的一个键；
   - 「捕获按键」→ 按下一个电脑按键；
   - 「确定」。
4. 切到目标程序（记事本 / DAW / 游戏），弹那个 MIDI 键即可。

配置自动保存到项目根目录的 `config.json`（首次运行用默认布局，保存后生成）。

## 光遇 PC 预设

光遇 PC 的 15 键乐器是 C4–C6 的 15 个白键，键位如下：

```
Y U I O P    C4 D4 E4 F4 G4
H J K L ;    A4 B4 C5 D5 E5
N M , . /    F5 G5 A5 B5 C6
```

**命令行**：

```powershell
python main.py --preset sky                 # 写入预设（保留已选设备）
python main.py --preset sky --start-note 48 # 键盘把中央 C 标成 C3 时，整体下移一个八度
```

**图形界面**：点左侧「预设：光遇」，确认后替换全部映射（保留设备/触发方式/力度阈值）。

## 命令行参数

```powershell
python main.py                       # 启动图形界面
python main.py --list-devices        # 列出 MIDI 输入设备后退出
python main.py --monitor             # 控制台实时打印 MIDI 事件（验证设备用）
python main.py --monitor --device 1  # 指定设备序号
python main.py --preset sky          # 写入内置预设
python main.py --config D:\my.json   # 指定配置文件
```

## 配置文件

`config.json`（UTF-8，自动生成，已被 `.gitignore` 忽略）。仓库里的 [`config.example.json`](config.example.json) 是「光遇预设」的完整示例，可直接复制为 `config.json` 使用：

```json
{
  "version": 1,
  "device": "Your MIDI Keyboard",
  "velocity_threshold": 0,
  "mode": "tap",
  "tap_ms": 50,
  "send_mode": "both",
  "mappings": [
    { "note": 60, "key": "y", "enabled": true },
    { "note": 62, "key": "u", "enabled": true }
  ]
}
```

| 字段 | 说明 |
| --- | --- |
| `note` | MIDI 音符编号 0–127（60 = 中央 C / C4）。 |
| `key` | 目标按键名，见下节。 |
| `enabled` | 是否启用该条映射。 |
| `velocity_threshold` | 小于该力度的音符被忽略（0 = 全部响应）。 |
| `mode` | `tap` 点按（默认）/ `hold` 按住。 |
| `tap_ms` | `tap` 模式下按键保持按住的毫秒数，默认 50。游戏按帧采样，太快会被漏掉。 |
| `send_mode` | `both` 混合（默认）/ `vk` 虚拟键 / `scancode` 扫描码。 |
| `device` | 记住的 MIDI 设备名（按名字恢复）。 |

## 支持的按键名

- 字母 `a`–`z`、数字 `0`–`9`、功能键 `f1`–`f24`
- `space` `enter` `tab` `esc` `backspace` `capslock`
- `up` `down` `left` `right` `insert` `delete` `home` `end` `pageup` `pagedown`
- 修饰键 `shift` `ctrl` `alt` `lshift` `rshift` `lctrl` `rctrl` `lalt` `ralt` `lwin` `rwin`
- 小键盘 `num0`–`num9` `add` `subtract` `multiply` `divide` `decimal` `numlock`
- 符号 `minus` `equals` `comma` `period` `slash` `backtick` `semicolon` `quote` `bracketleft` `bracketright` `backslash`
- 其他 `printscreen` `scrolllock` `pause` `apps`

## 使用提示

- 先用「开始」连上设备，再点「捕获 MIDI 音符」，否则捕获不到事件。
- 「全部释放 (Panic)」松开当前所有按住的键；关闭窗口、切换设备/触发方式时也会自动释放。
- 收到 MIDI `All Notes Off`（CC 123）或 `All Sound Off`（CC 120）时自动释放全部按键。
- `hold` 模式下，多个音符共用同一目标键会做引用计数，全部松开后才真正抬键。

## 排查：按了没反应？

按顺序对照下表：

| 现象 | 大概率原因 | 处理 |
| --- | --- | --- |
| 日志有事件、**记事本能输入**、游戏没反应 | 游戏以**管理员**运行，Windows UIPI 静默丢弃了普通权限进程的模拟按键 | 点界面『以管理员重启』或用 `run-admin.bat` 启动 |
| 日志完全没有事件 | 键盘没进 MIDI 模式 / 设备选错 | 多在键盘上按 `MIDI` 模式键；用 `python main.py --monitor` 验证 |
| 偶尔漏音符、快弹不触发 | 游戏按帧采样，点按太快落在两帧之间 | 调大「按键时长 (ms)」到 80–120 |
| 换了「按键时长」仍不行 | 游戏只认扫描码 | 「发送方式」改为「扫描码」，再试「虚拟键」 |
| 以上都不行 | 游戏主动过滤合成输入（部分带反作弊/Raw Input 的游戏） | `SendInput` 无解，需驱动级（Interception）或硬件方案 |

程序会自动做第 1 项的检测，并在日志里给出【警告】。

## 工作原理

```
MIDI 键盘 ──winmm──▶ 回调线程 ──队列──▶ 工作线程 ──映射──▶ user32!SendInput ──▶ 目标程序
```

- `midiin`：用 `midiInOpen(CALLBACK_FUNCTION)` 打开设备，回调只做「解析 3 字节 → 入队」，保证低延迟；用独立线程 + 消息循环承载。
- `engine`：工作线程消费队列，查映射后驱动 `keysender`；`tap` 模式用到期队列做非阻塞的「按下→延时→抬起」，和弦互不阻塞。
- `keysender`：`SendInput` 封装，支持虚拟键/扫描码/混合三种编码。
- `winutil`：读取进程完整性级别（UIPI 诊断）与提权重启。

## 开发与测试

```powershell
python -m unittest discover -s tests -v
```

81 个单元测试，覆盖音名转换、映射模型与配置读写、虚拟键/扫描码表、引擎调度、预设与权限工具。

## 目录结构

```
main.py / main.pyw      入口（控制台 / 无控制台）
run.bat / run-admin.bat 普通 / 管理员启动
debug.bat               带控制台启动（排错）
midi2key/
  vk.py                 虚拟键码与扫描码表
  keysender.py          SendInput 按键注入（三种编码）
  midiin.py             winmm MIDI 输入
  mapping.py            映射模型 + 配置读写 + 音名
  engine.py             MIDI 事件 → 按键输出
  winutil.py            权限(完整性级别)检测与提权重启
  presets.py            内置键位预设（光遇 PC）
  gui.py                Tkinter 界面
  cli.py                命令行入口
tests/                  单元测试
```

## 许可

MIT，见 [LICENSE](LICENSE)。
