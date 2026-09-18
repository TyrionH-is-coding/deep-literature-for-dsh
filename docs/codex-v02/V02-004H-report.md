# V02-004H：直接推进的生命周期写前守卫

状态：review，交总控复核。完整回归已通过；交付提交仅追加证据和报告，未改变被测源码。仅 A 引擎源码能力；B 接入、安装、发布和总控门槛不在本次交付范围。

## 身份与最小改动

A `C:/Users/15694/Documents/ChatGPT/deep-literature-engine-v02-004h`；branch `codex/v02-004h-advance-guard`；base `776a018c7855442de38d591517eea831eae5b463`。启动时 HEAD/branch 匹配且 clean，随后立即写 receipt。没有可确认的当前 session ID，保持空字符串。

B 只用 `git show` 读取 `76767f0cc5f5adeb9accb8a5aeec28bef6db45f4` 的任务卡、AGENTS、session-protocol、004F/004G-control-review。A 无 AGENTS；读取点名的 F/G 报告与相关源码/测试。没有在默认旧 dsh reader 工作树开发，没有改 B 或总控台账。

固定被测源码提交：`2379f9341e872c900edf5258848f0c1bc603600a`。生产只在 `reading_pipeline.py` 增加 13 行。在既有 advance claim 内、短 control 锁下读取/授权/校验，显式非 completed 推进遇到后台 failed/waiting_user/waiting_agent，且当前无 stop 意图时，抛出 `RuntimeError("full_read_pipeline_resume_required")`。检查先于 `control.stage` 登记、业务持久化和 runner；不改变后台状态。

该错误是直接服务调用合同，不是新增 CLI 命令或退出码。worker/CLI 继续拥有生命周期，支持的恢复先转 queued/running，因此 pipeline.state 仍为 failed/gate 时仍可合法推进。已有 stop 意图走原 F stage/overlay，不解除意图、不改变 revision。原 source/scope/身份/输出校验和终态一致性校验保留；没有修改 schema、依赖、算法、UI 或调度接口。

## 基线证据与失败保留

`V02-004H-evidence/base-reproduction.json` 记录实际基线导入位置/源码 SHA、合成库、advance 返回 queued/parse_mineru、后台 failed、inspect 报 reading_pipeline_state_invalid，以及变化文件。此独立复现使用真实 worker 形成 failed，再注入合成成功 runner 执行直接 advance，不冒称 CLI。

新增生命周期测试在未改生产的固定 base 上首次运行：13 failed / 11 passed，保留 `base.log` / `base.xml`。其中12项证明基线进入了本应拒绝的 runner；第13项是新 completed 夹具错误地要求整个 SQLite 字节不变，原行为本来会同步库状态。只修正本次新增断言为 parent 持久记录幂等且可 inspect；没有弱化任何既有测试。基线错误未混入最终通过计数。

定向回归 `targeted.log` / `targeted.xml`：47 passed，覆盖24项新增生命周期测试、6项 integrity、17项 control。首次 git commit 因未配置作者失败，随后核对基线作者/提交者均为 Codex <codex@openai.com>，用单次 `git -c` 参数提交，没有改全局身份设置。

## 执行方法和来源

定向检查仅只读使用既有 F Python 解释器，PYTHONPATH 指向本卡 A；完整回归与真实 CLI 用独立 `C:/tmp/v004h-env`、固定审计依赖，安装输出和 freeze 保留。新 `v02-004h-prepare.py` 将本卡当前 scientific_reading/reader 52个 Python 文件复制到新环境，逐文件 SHA 校验；`environment.json` 记录 Python、源 SHA、合成 provider exe SHA。从未导入旧 G 的私有 site-packages。

所有合成 provider 无真实模型。CLI 环境只继承 Windows 运行必要变量，Python sitecustomize 禁止 socket connect；完整回归也使用环境白名单，不携带模型、scope 或账户变量。全部子进程隐藏。自有短路径库位于 C:/tmp；不接触用户安装、凭据或真实文献库。

真实 CLI 命令为 `python -I -X utf8 -m scientific_reading --data-root ROOT full-read-pipeline-start/resume ...`。新 H 审计脚本改编历史夹具但对当前合同断言；旧 G 脚本、报告和红灯不修改。CLI 两场景没有手动 transition、替换 CLI/launcher/worker/pipeline。provider 第一次 exit19、第二次合成解析成功，然后真实 worker 停在 translate_full_read gate。

完整回归使用 `python -I scripts/v02-004h-verify.py --output docs/codex-v02/V02-004H-evidence/accepted`。所有 engine Python 源码/测试和 H 脚本在启动前 SHA 固定、结束后比较；每个测试文件只分配到一个分组，四份 XML 和每组 stdout 完整保留。测试运行期间没有修改源码或测试。后续仅写验证证据和报告。

## 限制和回退

仅 Windows/Python 源码验收；没有验证真实模型质量、物理掉电、任意跨版本并发或 B 安装组合，不解除004A-G1或其他总控门槛。未合入 main、未发布/tag、未创建后继。

回退点为指定 base。撤销本任务生产改动会重新暴露直接显式 advance 缺陷，但保留基线 F 停止能力；不能把源码回退描述为库/资产回滚。保留所有持久 control、pipeline、checkpoint 和资产，正常恢复仍使用受支持 CLI。合成库与环境保留供复核；不删除他人路径或终止用户进程。

## 最终实际验收

完整 Python：**595 passed / 3 skipped / 0 failed / 0 errors**，598个唯一测试、65个测试文件，每文件恰好一次。四分组共用同一固定源码，墙钟431.55秒。122个 engine 源码/测试及 H 脚本 SHA 运行前后相同。独立解析四份 XML 校验计数、唯一测试身份、文件全覆盖，见 `V02-004H-evidence/verification.json` 和 `accepted/run.json`。后续没有再改被测代码。三个 skip：Windows目录软链接权限、Unix zombie生命周期、未启用原生凭据服务。

| 检查 | 实际结果 | 证据 |
| --- | --- | --- |
| fixed base 缺陷重现 | 返回 queued，background failed；inspect 拒读 | base-reproduction.json |
| 当前生命周期24项 | failed/waiting_user/waiting_agent 显式拒绝；包括无control旧记录；全库业务/控制/资产字节不变；inspect 正常 | accepted/regression_a.xml |
| None、completed、queued/running | 无自动恢复、parent幂等、合法单步保持后台状态 | 同上 |
| integrity/source/parent | 同源parent保留、变源新parent、失配拒绝，既有6项全通过 | accepted/regression_b.xml |
| 原 F control | 原17项通过：gate/revision、移动/跨paper scope、变源拒绝、dead worker 显式恢复等 | accepted/regression_a.xml |
| 真实停止边界/竞争 | 7项通过；parse/batch/Reader前/Reader后/derived，显式恢复同parent、资产不变、独立child自然结束 | accepted/control_process.xml、accepted/processes/ |
| 原恢复32项 | 32 passed，无skip | accepted/original_recovery.xml |
| 真实CLI failed→resume/start | 两条路径各保持同parent，到合法waiting_agent/translate_full_read gate；provider各2次；非空失败恢复输入拒绝且JSON不变 | audit.json、cli-audit.log、cli-exit.txt=0 |
| 真实来源和清理 | 52个源码文件安装副本与A一致；CLI worker/provider已退出；四个pytest进程已退出；三类自有库owner.json为0 | environment.json、provenance.json、cleanup.json、verification.json |

真实 CLI 六场景还覆盖 None 只读，以及三个直接显式推进对照。三个对照均抛 full_read_pipeline_resume_required，parent JSON 完全不变、可 inspect、provider调用保持1次，没有在拒绝后执行注入 runner。更广的全库字节保留由新增生命周期测试证明。`audit.json` 中 direct-refail/direct-gate 是“试图注入的结果”，当前守卫均在 runner 前拒绝，不能理解为当前仍执行这些 runner。

实际命令（在指定A；省略的环境配置见脚本/正文）：

```powershell
# 基线/定向用只读F解释器，PYTHONPATH指向本卡A
& C:/tmp/v4f-venv/Scripts/python.exe -m pytest engine/tests/test_reading_pipeline_lifecycle.py -q --junitxml=docs/codex-v02/V02-004H-evidence/base.xml
& C:/tmp/v4f-venv/Scripts/python.exe -m pytest engine/tests/test_reading_pipeline_lifecycle.py engine/tests/test_reading_pipeline_integrity.py engine/tests/test_reading_control.py -q --junitxml=docs/codex-v02/V02-004H-evidence/targeted.xml
# 当前源码专用环境及固定最终源码验收
& C:/tmp/v004h-env/Scripts/python.exe -I scripts/v02-004h-prepare.py
& C:/tmp/v004h-env/Scripts/python.exe -I scripts/v02-004h-verify.py --output docs/codex-v02/V02-004H-evidence/accepted
& C:/tmp/v004h-env/Scripts/python.exe -I -X utf8 scripts/v02-004h-audit.py --expect-direct-safe
& C:/tmp/v004h-env/Scripts/python.exe -I scripts/v02-004h-cleanup.py
```

上述 prepare/audit/verify 重跑会覆盖同名证据，复核若要重放应先保存既有输出。原始失败日志/XML保留原文，不把其 traceback 行尾空白当产品源码问题。最终报告/receipt提交不包含源码变化；最终完整commit由交接消息和Git HEAD标识，避免提交内自引用。receipt phase=review，Git clean；不代表 integrated。
