# V02-004G：failed 后直接 advance 的归因

结论：004D-O1 已重现并归因。worker 已终结为 failed 后，直接 `ReadingPipeline.advance(parent, {})` 会接受显式恢复、推进并落盘 pipeline，却不改变后台 status；随后 `_load/inspect` 的终态一致性校验拒绝该组合。这是直接服务入口缺少前提保护的缺陷，也是旧探针混用 worker 生命周期和服务级推进的触发条件。不是同源 PDF、解析 checkpoint 或阶段时间格式错误。不能把它扩大为公共 CLI 恢复故障，也不能称内部 API “不支持”而直接关闭问题。

状态 **review**，生产未修复。仅新增本卡 docs/scripts/fixture；无 schema、接口、版本、锁文件、既有测试或全局测试链改动。基线 `a37a415c4bec9a895f1dc1619cfa35081cf85d26`，分支 `codex/v02-004g-advance-audit`；B context `fd1e08d2d35c13af8723a93b794187ea6d87a021`。A 路径见回执。最终提交由交接消息及 Git HEAD 标识，避免在提交内自引用提交号。

## 新证据与结果

| 本轮实际执行 | 结果 | 证据 |
| --- | --- | --- |
| 冻结004D provider 在独立库产生 `controlled_parse_fail_before`，再直接 advance({}) | worker exit 4；advance 返回 queued/translate_full，后台仍 failed；inspect 抛同一 ValueError | [原异常重放](V02-004G-evidence/original-replay.json)、[命令输出](V02-004G-evidence/original-replay.txt) |
| failed 后 advance(None) | 返回 failed；parent JSON 哈希全部不变；inspect 正常 | [六场景记录](V02-004G-evidence/audit.json) direct-none |
| failed 后 advance({})，真实本地 provider 重试成功 | pipeline queued/translate_full 与 job failed 冲突；inspect 失败 | 同上 direct-success |
| failed 后 advance({})，受控 runner 再次失败 | pipeline/job 均 failed，inspect 正常 | 同上 direct-refail |
| failed 后 advance({})，受控 runner 进入 gate | pipeline waiting_agent 与 job failed 冲突；inspect 失败；说明无须阶段成功/finished_at 即可触发 | 同上 direct-gate |
| 真实 CLI start → worker parse failed → CLI resume → worker | 同 parent 到 translate_full_read gate；pipeline/job 均 waiting_agent；inspect 正常；provider 两次 | 同上 cli-resume，含完整 argv/stdout/stderr、PID/创建身份、事件链 |
| 真实 CLI start → worker failed → 再次 CLI start | 同 parent 到相同合法 gate；provider 两次 | 同上 cli-start |
| 两个 CLI 对照在 failed 时先传非空输入 | exit 4 / terminal_resume_input_invalid；所有 parent JSON 不变 | 同上 rejected_nonempty |
| 正确预期的回归探针 `--expect-direct-safe` | **RED，exit 1**；不是通过。六场景诊断断言完成后，以“已接受显式 advance 必须保持可读取，或写前拒绝”为预期失败 | [红灯输出](V02-004G-evidence/red.txt)、[退出码](V02-004G-evidence/red-exit.txt) |

各快照包含完整 pipeline/status/request、事件、paper/generation job.json checkpoint、parent JSON 哈希及 inspect 堆栈。原004D失败 JSON/日志、当时总控提交中的已修改 restart-failure.py 与其 provider fixture 原文分别保留；它们不是本轮执行结果。冻结输入的字节 SHA 见 [frozen-inputs.json](V02-004G-evidence/frozen-inputs.json)。未访问这些旧日志中出现的任何实例路径。

## 具体不变量与调用前提

源码坐标固定于上述 A 基线：

- `engine/src/scientific_reading/reading_pipeline.py:682`：advance 获取 claim、读取状态；691–695 对 failed/needs_user/waiting_agent 仅在 supplied_input 为 None 时返回。传 `{}` 明确进入执行。699–708 在 runner 之前修改 state 并 `_save`。737–759 在成功后写 finished_at、输出，并返回 queued 的下一阶段；它没有 background status transition。
- 同文件 `:841` 的 `_validate_state`，尤其 `:865–873`：job failed 必须对应 pipeline failed；waiting_agent 必须对应 waiting_agent；waiting_user 必须对应 needs_user；completed 必须对应 completed。`:933` 的通用错误并不是专指时间校验。
- 相同快照用纯校验函数分别传入 job_state failed/queued/running：direct-success 和 direct-gate 在 failed 下拒绝，在 queued/running 下通过。此诊断只改**校验函数参数**，没有写 store、更没有将它计作 CLI 验收。它隔离了终态不匹配这一原因。
- before 中失败阶段的 finished_at 为 null；成功重试后 parse_mineru 的 finished_at 是合法、有时区且不早于 started_at 的值，下一阶段尚未建立 timing。gate 对照保留 null 仍失败。因此完成时间不是本次根因。ensure_pdf 的完整 source SHA 在恢复前后不变，generation 和已完成 acquisition checkpoint 沿用同一来源；没有删除或伪造 checkpoint 促成成功。
- `worker.py:384–407` 从 resume.json 保留显式空输入，先 transition running 再调用 handler；`:290–306` 循环 advance，将 gate/failed 返回转换为 worker 终态。`__main__.py:297–319` 的 resume 则先校验 gate/空输入、保存 resume、transition queued、真实 launch。failed 的再次 start 在 `:293–295` 保存 `{}`；`background_launcher.py:137–145` 负责 failed → queued。

因此服务级单步推进实际依赖后台 status 尚为 queued/running，或终态仍与返回结果一致。worker 管理此状态机；只执行 store.transition 后跑 handler 的旧修正版夹具验证不了公共 CLI。服务源码显式接受 failed + 输入，而且既有 integrity 测试直接使用 advance；现有证据不足以宣称它是禁止直接调用的内部方法。更准确的表述是：**存在未声明、未在写前保护的生命周期前提，服务调用可产生自身随后拒绝读取的持久状态。**

## 产品可达性与边界

本基线生产中唯一 `ReadingPipeline.advance` 调用位于 full_read_pipeline worker handler；另一处 worker `.advance` 属于不同对象。A `src/routes.ts:620`、`src/library_tools.ts:157` 通过 `src/cli.ts:532–534` 的 engineContinueFullRead 调用 full-read-pipeline-resume。start 同样走 CLI。该路径按上述生命周期重排，因此**本次同源、正常退出失败、显式恢复条件下未发现公共入口会产生 O1 的调用序列**。

本轮两个公共对照没有替换 CLI、launcher、worker、ReadingPipeline、JobStore 或服务；没有手动 transition。MinerU 是独立受控本地 exe，首次 parse exit 19，第二次输出合成 content list。真实服务完成解析并停在翻译 gate；未伪造翻译或声称整篇 completed。两个 runner 注入仅用于 direct-refail/direct-gate 的因果对照，和公共 CLI 证据分列。

不据此承诺任意并发、进程崩溃写入窗口、被外部破坏的状态或未来其他调用者安全。未检验004F新增入口；绝未读取004F工作树。若未来公开 direct resume，必须先确定其状态所有权合同。

## 最小后续建议（本卡不实施）

建议保留现有终态校验，不以放宽 `_validate_state` 掩盖不一致。最低风险方案是在 advance claim 内、任何 `_save`/runner 调用前检查后台 terminal/gate 状态：显式调用若绕过 worker 生命周期，返回明确的“需要后台恢复入口”错误且不改文件；completed 幂等和 None 的只读返回保留。同步补充服务前提说明。若产品要求 direct advance 自身承担恢复，则需统一后台状态转换和 gate/failed/completed 落盘责任，不能只在入口强行 transition running 或仅把失败改 queued；这比写前拒绝范围更大，需总控决策。

最小回归范围：本卡 RED 探针；failed/needs_user/waiting_agent 直接显式调用写前拒绝及字节不变（或协调后可重读）；None 不自动恢复；queued/running 正常单步；completed 幂等；真实 CLI resume/start；同源与变源父作业约束；gate 的正确输入和失败空输入；阶段时间与输出一致性。修改触及 pipeline，必须等004F验收后串行安排，本卡不创建后继。

## 重放与环境

本轮固定私有 venv 为 `C:/Users/15694/AppData/Local/Temp/v004g-env`，CPython **3.11.9**（与004D发布验证用3.11.16不同，故不作安装/制品验收）；全部依赖来自 A 的 `docs/codex-v02/evidence/audit-python-requirements.txt` 精确版本。[freeze.txt](V02-004G-evidence/freeze.txt) 记录实际安装版本。`prepare` 复制基线的 scientific_reading/reader 到私有 site-packages，逐文件校验 **51 个 SHA**，见 [environment.json](V02-004G-evidence/environment.json)。无 PYTHONPATH/源码覆盖、无用户 site；这是源码诊断环境，未构建或安装发布 wheel。私有 sitecustomize 只禁止 Python socket connect；子进程环境使用白名单，不继承模型/API凭据或 scope。无真实模型、MinerU服务、账户凭据或用户安装。

在同一 A 分支运行（PowerShell；首次创建独立环境，路径如已存在应先核对用途，不覆盖其他环境）：

```powershell
python -m venv C:/Users/15694/AppData/Local/Temp/v004g-env
$py = 'C:/Users/15694/AppData/Local/Temp/v004g-env/Scripts/python.exe'
& $py -m pip install -r docs/codex-v02/evidence/audit-python-requirements.txt
& $py -I scripts/v02-004g-prepare.py
& $py -I scripts/v02-004g-freeze-inputs.py
& $py -I -X utf8 scripts/v02-004g-audit.py --expect-direct-safe # 当前预期 exit 1，保留缺陷
& $py -I -X utf8 scripts/v02-004g-original-replay.py
& $py -I scripts/v02-004g-cleanup-audit.py
```

本轮完整六场景执行两次：第二次用于确认 RED 探针仅要求正确预期，不把当前损坏当成未来通过条件；首轮进程检查保留在 cleanup-first-run.json，audit.json/red.txt 为第二次输出。每次重放新建短路径 g4-/g4d- 合成库；完整 argv/前后状态保存在本卡 evidence。脚本重放会更新同名本卡报告文件，复核者如要保留首轮证据应先复制输出。当前无超时/强杀：全部已记录 worker/provider 正常退出，owner.json 为零；[cleanup.json](V02-004G-evidence/cleanup.json) 逐 PID 留证。同步 version 探测进程由 subprocess.run 等待。合成库和私有环境保留供复核，不删除其他任务文件。

另实际执行既有 `test_reading_pipeline_integrity.py` 定向检查，**6 passed / exit 0**，结果见 [输出](V02-004G-evidence/integrity-tests.txt) 与退出码；不将它替代 RED 缺陷探针。不运行全量测试、发布打包、安装、浏览器、Office、非Windows、真实内容质量、004F停止控制或全部崩溃窗口。没有合并 main/总控、发布、修改总控台账或创建后继任务。
