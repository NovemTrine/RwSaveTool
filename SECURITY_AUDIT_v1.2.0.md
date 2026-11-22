# RwSaveTool v1.2.0 安全审计报告

- **审计对象**：`RwSaveTool-v1.2.0-win64-20261118.zip` 及对应源码（`D:/Projects/Code_Projects/RwSaveTool`）
- **审计日期**：2026-11-18
- **审计方式**：源码通读、数据流追踪、依赖与打包配置核对、发布包完整性验证
- **程序形态**：Python 3.13 + PyInstaller 打包的 Windows 桌面程序，pywebview 6.2.1（EdgeChromium/WebView2）作为界面壳

---

## 一、总体安全结论

**总体风险等级：中低。未发现任何恶意行为（无网络外传、无遥测、无键盘记录、无后门、无硬编码密钥）。**

这是一个设计克制、以"只读"为核心纪律的本地单机工具。绝大多数安全实践到位：存档/游戏/模组全程只读、不可信数据统一 HTML 转义、外部输入有大小上限、发布前主动抹除本机绝对路径、并附带可核对的 SHA256 校验清单（本次核验 8 个关键文件全部吻合）。

需要改进的核心问题只有 1 项（中危）：**区域缓存 JSON 中的 `code` 字段未做白名单净化，直接拼入文件名并用于文件删除**。在正常"从游戏目录导入"流程下不可利用（导入端有区域名正则校验），但如果用户加载了他人分享或被篡改的 `region_data/*.json` 缓存包，则可能触发受限的任意文件读取/删除。考虑到本项目 README 明确鼓励"带缓存分发"，这条链路值得认真加固。

其余为纵深防御层面的低危与设计说明级事项，不影响日常安全使用。

---

## 二、按风险等级的问题清单

### 中危（Medium）

#### M-1　区域缓存 `code` 未净化 → 路径穿越（受限的任意文件读取/删除）

- **位置**：`core/region_store.py`
  - `_region_path(code)`（`L47-48`）：`os.path.join(paths.data_dir(), f"{code.upper()}.json")`
  - `delete_region(code)`（`L487-496`）：`os.remove(path)`，无 `code` 合法性校验
  - `delete_layer` / `set_override` / `get_region` / `save_*` 同样直接使用 `code`
- **数据流**：前端 `data-code` 属性（`ui/rw_gui.html` L4435、L4993、L5011）来自区域缓存 JSON 的 `code` 字段 → `bridgeCall('delete_region', code)`（L5138）→ 后端直接拼路径。
- **触发条件**：攻击者提供一个含恶意 `code`（如 `..\..\..\Users\...\foo`）的 `region_data/*.json` 缓存，让用户放入程序数据目录并点击"移除全部/移除来源"。仅本地导入（有 `REGION_DIR_RE = ^[A-Za-z0-9]{2,8}$` 校验）时不产生恶意 code。
- **影响**：
  - `delete_region`：可删除程序数据目录之外、攻击者指定位置的 `.json` 文件（后缀固定为 `.json`，因此影响受限）；
  - `map_image`（`core/bridge.py` L435-470）：`imagePath` 同样来自缓存 JSON，配合 `.upper()` 无关的路径 `open(image_path,'rb')` 可读取本机任意文件并以 base64 返回前端（可利用面比删除更大）。
- **建议修复**：
  1. 在 `region_store` 增加统一校验函数：`_valid_code(code)` 仅允许 `^[A-Za-z0-9]{2,8}$`，所有以 `code` 为入口的公开函数（读/写/删）入口先校验，非法直接返回错误。
  2. `_region_path` 用校验后的 code 拼路径，并追加 `os.path.commonpath([full, data_dir]) == data_dir` 的兜底断言，防止 `..` 逃逸。
  3. 加载缓存 JSON 时（`_read_json` 之后）对 `code` 字段做一次规范化校验， SKIP/隔离不合法的缓存文件。
  4. `bridge.map_image` 对 `imagePath` 同样做"必须位于已登记游戏/模组根目录下"的白名单约束，拒绝任意绝对路径。

### 低危（Low）

#### L-1　pywebview `js_api` 暴露面偏宽

- **位置**：`core/bridge.py` 中 `Api` 类的公开方法（无下划线开头者全部暴露给 JS），尤其 `read_save(path)`（L169）、`import_mod_path(path)`（L200）、`set_game_path(path)`（L262）、`pick_text_file()`（L338）。
- **现状**：前端 `bridgeCall(name)` 的 `name` 均为代码内写死的字面量（`ui/rw_gui.html` L2593-2603），且不可信数据渲染统一经过 `esc()`，当前**没有可利用的 XSS 入口**。`rwunescape()`（L1371）仅用于解析存档 payload，解码结果进入解析器而非直接进 innerHTML。
- **风险**：纵深防御不足。一旦未来引入任何 DOM XSS，攻击者即可通过 `pywebview.api.read_save('任意路径')` 读取本机文件——特别是 `read_save` 接受任意路径字符串，虽经 `save_io.read_save_file` 的 `abspath + isfile + 128MiB 上限` 检查，但并无"必须在存档目录内"的约束。
- **建议**：
  1. `read_save` 限制路径必须落在 `default_dir()`（Rain World 存档目录）或用户通过文件对话框选中的路径集合内；
  2. 将仅供内部使用的辅助方法改为下划线开头（pywebview 不暴露 `_` 前缀方法）；
  3. 为 `js_api` 增加一层"调用来源校验"（如校验 `window.location`/自定义 nonce），并持续保持不可信数据 `esc()` 纪律。

#### L-2　运行依赖未精确锁定，供应链可重复性不足

- **位置**：`requirements.txt` 仅 `pywebview>=6.0,<7`（配 `--index-url https://pypi.org/simple`），无 hash 锁定、无 lock 文件；发布包内含 `libcrypto-3-x64.dll` / `libssl-3-x64.dll` / `Python.Runtime.dll` 等多个二进制。
- **现状**：实际打包为 pywebview 6.2.1（较新版本），检索未发现与其直接对应的已知 CVE（搜索到的 CVE-2026-17736 属 Android WebView，与本程序 EdgeChromium 桌面后端无关）。发布包附 CHECKSUMS 清单，降低传输环节掉包风险。
- **风险**：宽泛版本范围意味着未来构建可能拉取到不同（甚至被投毒）的传递依赖；OpenSSL DLL 版本未固定，若 OpenSSL 曝出 CVE，难以及时确认是否受影响。
- **建议**：生成 `requirements.lock.txt`（`pip freeze` 全量精确版本），关键二进制依赖记录版本与 SHA256；建立依赖 CVE 的定期核查（如 `pip-audit`）；在构建脚本中校验依赖哈希。

#### L-3　WebView2 用户数据持久化（`private_mode=False`）

- **位置**：`main.py` L46 `webview.start(debug=debug, private_mode=False)`。
- **影响**：非隐私模式的 WebView2 会在本地留下 profile（缓存、localStorage 等）。本程序 UI 用 localStorage 保存主题首屏防闪（`DEVELOPMENT.md` §3.9），属有意为之；但会残留浏览数据。
- **建议**：若无需 localStorage，改 `private_mode=True`；若需保留主题记忆，可改为完全依赖 `config.json`，去掉 localStorage 依赖后启用隐私模式。

### 信息级 / 设计说明（Informational）

- **I-1　存档 MD5 校验和未在浏览器端验证**：`ui/rw_gui.html` L3475 明确提示"缺少 SALT，不影响读取"。这是设计为只读查看器的合理取舍（存档校验属写回场景才需要），非漏洞。
- **I-2　`--debug` 参数会开启 DevTools**：`main.py` L73/L82。仅开发期使用，桌面版给普通用户的快捷方式不应带此参数。建议发布版移除该入口或在正式构建中禁用远程调试端口。
- **I-3　本地静态服务绑定 127.0.0.1**：`main.py` L93 `TCPServer(("127.0.0.1", 8777), ...)`，仅调试用且只绑回环地址，风险可接受；不要在 `--serve` 模式下绑 `0.0.0.0`。

---

## 三、重点维度专项结论

| 维度 | 结论 |
|---|---|
| **潜在漏洞** | 仅 M-1 一项实质性问题（区域缓存路径净化缺失，中危），其余均为纵深防御建议。无命令注入、无不安全反序列化（全程 `json.load`）、无 `eval/exec`（前端无动态代码执行，后端无）。 |
| **权限控制** | 本地单机工具，无账户/角色体系。文件系统写入严格限定在 `region_data/`、`_translations.json`、`config.json`（`paths.py` L81-101、L272-289 有白名单）；进程仅以当前用户权限运行，无提权、无自启动、无注册表写入（注册表仅只读查询 Steam 安装路径，`core/official_world.py` L36-47）。 |
| **敏感数据处理** | 无密码/令牌/私钥/API Key（`saltPath` 为遗留空字段，默认 `None`）。存档内容仅在本地解析，不上传。发布前 `strip_local_paths.py` 抹除约 3300 处本机绝对路径。config 中仅存用户主动选择的路径与界面偏好。 |
| **第三方依赖** | pywebview 6.2.1（较新，无直接 CVE）；OpenSSL 3.x、Python 3.13、pythonnet（用于 WebView2 的 .NET 桥接）。主要问题是版本锁定与哈希验证不足（L-2），而非已确认的漏洞。 |
| **配置风险** | `save_config` 有字段白名单（`paths.py` L285-286），前端临时字段不会落盘；配置损坏自动改名留档（`config.broken.json`）；来自更高版本的配置只读不写。整体稳健。低危项为 `private_mode=False`（L-3）与调试参数（I-2）。 |

---

## 四、发布包完整性验证

从 zip 内 `CHECKSUMS.txt` 解析出 8 个关键文件（两个 exe、`_internal/ui/rw_gui.html`、4 个 data JSON、`_sources.json`），逐一重算 MD5 与 SHA256 前 32 位：

```
parsed key rows: 8
mismatches: 0
```

**结论：发布包内文件与校验清单完全一致，未发现掉包或篡改。** 压缩包共 276 个条目、解压约 53.6 MB，与清单声明（275 文件 + 清单本身）一致。

---

## 五、修复优先级建议

1. **优先（本次发布前）**：修复 M-1——为 `region_store` 全部 `code` 入参加白名单校验 + commonpath 兜底；对 `map_image` 的 `imagePath` 做根目录约束。这是一处集中改动、收益最高。
2. **次优先**：L-2 依赖精确锁定 + 哈希记录，建立 `pip-audit` 例行检查。
3. **择机**：L-1 收敛 js_api 暴露面（`read_save` 路径约束）；L-3 视是否需要 localStorage 决定是否启用隐私模式。
4. **文档层面**：I-2 明确告知用户不要用 `--debug` 启动正式版。

---

## 六、给普通使用者的安全提示

- 只从项目官方 Releases 下载，解压后核对 `CHECKSUMS.txt`（本版本已核对无误）。
- **不要加载来路不明的 `region_data` 缓存包**——这是当前唯一实质性风险点（M-1）的触发前提；坚持自己从正版游戏目录导入数据最安全。
- 杀毒软件误报属 PyInstaller 打包的常见现象，核对哈希无误后可按项目说明加白名单。

---

*本报告基于 v1.2.0（构建日期 2026-11-18）源码与发布包。代码变更后建议重新审计关键项。*
