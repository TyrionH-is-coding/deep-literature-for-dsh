# V02-004I A 交付（review，未发布）

基线 `2720fac32cf2b989523079405abbd0e4f3698e07`；实现/被测生产源码 `b9365ce622c323ce10b2ab86864f3c85d5edf55c`；验收脚本短路径修正 `8a63f2ba2eb0ed10fd01cb6af47608d6ea5ec5b9`。后者只改验证脚本，生产源码及测试文件不变。固定卡片 context 为 B `d06be8e6367ef4debc758506574a4be9dfa01874`。

新增公开 `engineResumeStoppedFullRead(config, jobId, suppliedInput, {requestId, expectedRevision})`，严格预检 requestId 与安全非负 revision（含 0），传全显式恢复 CLI 参数、stdin、trustedProviderEnv、异步 scope。普通 continue 签名/行为保持。未注册新的分类工具，未改 Python、版本、依赖或锁文件。新测试登记 test:offline 与 test:stop-control-api。

## 验证

运行 `./scripts/v02-004i-verify.ps1`，build、typecheck 和六项相关 TS 检查先通过；library-assets-tools 在长 TEMP 路径触发 Windows MAX_PATH，保留 `library-assets-tools-previous.txt` 和失败夹具。验证脚本改用本卡 `C:/tmp/v02-004i-ts`，运行 `./scripts/v02-004i-verify.ps1 -Remaining` 后资产工具、review-engine-adapter、phase1-plugin-contract 三项通过。合计 11 个唯一命令最终通过、12 次执行包含 1 次保留的环境失败；不是 12 项全绿。

完整精确命令、时间与退出码：[runs.json](V02-004I-evidence/runs.json)。构建和测试使用本卡 `.venv/Scripts/python.exe`，Python 3.11.16，依赖逐项匹配 `docs/codex-v02/evidence/audit-python-requirements.txt`；见 [audit.json](V02-004I-evidence/audit.json)、[environment.json](V02-004I-evidence/environment.json)。本卡拷贝独立 Python runtime，venv 不共享用户库；52 个 Python 文件逐字节匹配基线当前源码。sitecustomize 仅禁 socket 网络连接，不替换业务函数。构建所需 setuptools 80.9.0 wheel 已在任务目录，本次最终 build 使用 PIP_NO_INDEX 与本地 PIP_FIND_LINKS。

API 参数/环境测试使用子进程探针，单独标记为传输合同。真实链由 B `scripts/v02-004i-integration.mjs` 导入本卡 `lib/index.js`、B adapter 和本卡实际 Python 模块：17 个观察覆盖新 parent read→stop→重复 stop→普通 resume/attach exit 2→显式 resume→重复 resume→同 parent 缺 PDF gate，含跨 paper/分类、revision/ID 冲突拒绝。B 证据文件 `docs/project/evidence/V02-004I-integration.json` 固定导入路径、源码/JS 哈希及双方源码 commit。没有真实 provider/模型、凭据或用户安装。

## 保留失败、清理和回退

- 初次 npm ci 因仓库既有 peer 解析冲突失败；npm ci --ignore-scripts --legacy-peer-deps 成功，锁文件无变化。
- 初次运行被中断于 runtime 拷贝，未生成宽松 pip install 日志/venv；恢复后采用精确 requirements。拷贝残留产生过 runtime 的 distutils .pth 警告；隔离 venv 后精确版本审计和运行均通过。
- Git 初次提交因缺少作者配置失败；随后仅对命令指定与既有提交一致的 Codex <codex@openai.com>，没有修改全局或共享仓库配置。
- 未手改生成产物；构建得到的 lib/client.js 只有工作树换行标记，已还原至 HEAD。lib 其余产物、wheel、venv 和失败夹具保留在本卡目录；短 TEMP 也仅归本卡所有。Python 进程检查无本卡残留；真实 worker 已到 waiting_user/pdf_required 并注销。
- 回退 A 实现提交及本卡测试/证据即可撤销接口；B 必须配套回退 adapter。回退不删除库、停止记录或用户数据，旧引擎不宣称具备停止保护。

未跑未变化的 Python 全集；未做产品安装、真实模型、UI 或用户取消链验收。下一卡仍由总控派发。本卡源码交付只表示停止控制跨包合同准备完成。
