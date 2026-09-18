# V02-004F：A 引擎持久停止与显式恢复

待总控 review；仅 A 源码能力，不关闭004A-G1，不代表 B 工具或用户取消流程已完成。未发布、tag、合入 main、修改 B 或创建后继任务。

最终已验证源码/测试提交：`630398634db15b72064e64e221bc5fa6105e7a25`。生产最后变化来自 `8f334d0`（已退出 worker 的显式恢复重新排队）；后续只增加固定源码的完整分组验证脚本。`source-manifest.json` 固定逐文件 SHA256。

## 固定身份与范围

- A：`C:/Users/15694/Documents/ChatGPT/deep-literature-engine-v02-004f`，`codex/v02-004f-engine-stop`，base `a37a415c4bec9a895f1dc1619cfa35081cf85d26`。初始 clean。
- B：只读 `C:/Users/15694/Documents/ChatGPT/deep-literature-for-codex` 的 `fd1e08d2d35c13af8723a93b794187ea6d87a021`：完整卡、AGENTS、session-protocol、004D-control-review、cancellation-contract。A 没有 AGENTS。receipt 实际 session ID 不可得，保留 null。
- 新增 `reading_control.py`；修改 pipeline、launcher、worker、CLI 及限定测试。scope 只在现有 CLI allowlist 增加 stop/control，原 paper/folder/revision 检查保留。没有修改 schema、迁移、解析/翻译/Reader/Excel 算法、TS/UI、版本或依赖，也没有读取004G输出。
- 测试环境：独立 `C:/tmp/v4f-venv`，固定 Python 3.11.16；依赖严格使用已有 `audit-python-requirements.txt`。详情见 `V02-004F-evidence/runtime.json`。初期定向测试借用004D固定 venv 解释器只读运行；最终验证用本卡独立 venv，源码导入来自本卡 A。无真实模型、用户库或凭据；全部子进程隐藏。

## 持久协议与锁顺序

每个 parent 的 `jobs/<job>/control.json` 是独立 `reading-control-v1` 记录。不存在时 revision=0、stopRequested=false，读取不会为旧记录创建文件。新引擎进入阶段/worker 时登记能力与活动身份。控制记录保留每个 request ID 的种类、expectedRevision、结果 revision；resume 还保留已验证输入和 dispatched 记录。修订严格连续，每个新操作加1；ack、读状态、重试均不加修订。损坏 JSON、未知合同、错误 parent、非法 revision/操作历史/owner/ack 均拒绝，不能降级为“没有停止”。

停止先原子替换意图记录，随后才尝试确认。阶段入口在同一控制锁内检查 stop 并登记 activeStage，运行 provider 时释放锁；阶段产物与 checkpoint 仍按原逻辑提交。退出阶段再持锁清活动标记并确认 `after:<stage>`。因此请求可以在 provider 未返回时立即读回，已进入阶段可以提交，确认后禁止下一阶段。派生 child 创建属于 `schedule_derived_updates` 的阶段内容：该阶段尚未进入时不创建 child；已进入则允许该阶段结束，独立 xlsx child 不被终止。

锁顺序（所有写入先持现有 data_root shared operation）：

1. advance：data_root → `.claim_reading_pipeline` → 短控制 OS 锁；释放控制锁后执行原 heavy/publication/provider 操作；退出时再取控制锁提交确认。控制操作从不等待/领取 pipeline claim，只读取其 owner 兼容旧直接 advance。
2. stop/read：data_root → 控制 OS 锁；只做持久记录和短状态/身份读取，不等待 provider。
3. CLI resume/attach：data_root → 控制锁 → `.claim_resume` → launcher `.launch_claim`。控制锁同线程可重入。launch 从控制检查到 Popen/launch marker 完成始终持锁。
4. worker 注册/退出：data_root → 控制锁；worker 循环通过上述 advance 边界。已确认后，即便已 spawn 的子进程才开始运行，也不能进入阶段；queued 子进程返回现有 waiting_user / pipeline_stop_requested gate。

控制锁复用已有跨平台 OS file-lock 实现，键包含完整控制文件路径；不同 parent 不共用锁。锁文件在既有 operation-lock 临时目录，不删除可能仍被持有的 inode；进程退出由 OS 释放。control 写入使用既有 JSON 原子替换，不改变业务 JSON/schema。新增 launch marker 的 `controlRevision` 只用于识别同一次 resume 的启动回执。

业务阶段不改成 canceled。停止 gate 是返回值/worker status 的覆盖层，原 pipeline 的源 SHA、阶段、输出、业务 required_action 留存，显式恢复仍校验原 gate 输入。只有 status.reason_code=pipeline_stop_requested 时，pipeline 加载允许这个独立 gate 与底层业务阶段不同；未改变004D failed后直接advance的不变量/行为。`bounded-change.json` 的 AST 对比确认原 advance 阶段执行主体与状态校验器均保留。

## 精确 CLI 合同

全局参数位置仍为 `python -m scientific_reading --data-root <root> <command> ...`。

| 命令 | 成功/拒绝 |
| --- | --- |
| `full-read-pipeline-stop --job-id J --request-id S --expected-revision N` | exit 0，JSON控制快照；同 ID 同参数返回当前快照和旧 operation，不重新停止新 revision；过期修订/ID冲突 exit 4 |
| `full-read-pipeline-control --job-id J` | exit 0，当前控制及实际业务快照；可以对已结束的活动补记安全边界 ack，不清 stop、不启动 worker |
| `full-read-pipeline-resume --job-id J --resume-stopped --request-id R --expected-revision N [--input ABS或-]` | exit 0，同 parent 的显式解除结果；验证 scope、source、原 gate、revision、worker静默后才清 stop；不满足条件 exit 4 |
| 普通 `full-read-pipeline-resume` / `full-read-pdf-attach-resume` 遇到 stop | exit 2，控制快照，stop 保留，不提交 attach 或启动 worker。attach 先核对 paper/job 身份 |
| 同键 start 遇到 stop | exit 0，仍返回既有 pipeline 结构，非终态为 needs_user / required_action.reason_code=pipeline_stop_requested；同 parent，不启动 worker |

控制快照字段：contract、parentJobId、revision、stopRequested、requestId、acknowledgedRevision、effectiveBoundary、activeStage、worker、operations，以及 `status`、`businessStatus`、`pipelineState`、`independentChildrenStopped:false`、`compatibility`、`replayedOperation`。

`status` 精确含义：`requested`=意图已保存但活动阶段/未知worker尚未确认；`acknowledged`=当前停止 revision 已确认安全边界；`terminal`=实际 pipeline 或 background 的 completed/failed 优先；`active`=当前无停止意图。terminal 不是 canceled，也不暗示失败资产被回滚。调用方不得把 exit 0 或 stopRequested=true 单独显示为“已停止”。businessStatus 与 pipelineState 保留短暂提交过渡，控制层不伪造两者一致。

错误统一为 exit 4、`{"status":"failed","error":"<code>"}`。新增 code 包括 reading_control_invalid、reading_control_operation_invalid、reading_control_request_conflict、reading_control_revision_conflict、reading_control_not_stopped、reading_control_stop_unconfirmed、reading_control_terminal、reading_control_resume_input_invalid、reading_control_dispatch_uncertain、reading_control_worker_busy；沿用 full_read_parent_mismatch、scope_*、原 gate 输入错误。缺少显式选项但传 request/revision 返回 resume_stopped_required。缺少/错误 CLI 语法仍沿用 argparse exit 2 与 stderr usage，并非业务 JSON。

resume 在清 stop 前持久化已验证输入，然后记录操作，再排队/启动。重放已完成 resume 不清后来 stop，不再启动。未完成 dispatch 同 ID 可对账：worker 注册也标记该操作已送达；匹配 controlRevision 且有 PID 的 launch marker 视为已有启动，不重启；只有预启动标记而 PID 未知的窗口返回 dispatch_uncertain，保守留待人工核对，不猜测后再启动。不存在当前启动记录才重试派发。若原业务状态仍是 running、但其明确 PID 已退出，则在已通过停止确认/source/gate/revision 校验后转 interrupted 并重新排队；活跃或未知 PID 不走此路径。这是明确的未知窗口，不承诺任意断电点自动恢复或 exactly-once 外部计费。

## 验证与证据

最终完整 Python **571 passed / 3 skipped / 0 failed / 0 errors**（574项），4个互不重复的测试文件分组，源码运行前后SHA一致。总墙钟 655.47 秒。原恢复32项、控制单测17项、真实进程7项均通过；编译50个模块通过。skip为Windows目录symlink权限、Unix zombie生命周期、未启用原生凭据服务。

最终执行结果见 `V02-004F-evidence/verification.json` 和 `V02-004F-evidence/accepted/run.json`；四个独立 pytest 进程使用同一源码快照，每个测试文件仅分配一次，不拼接不同候选。`accepted/` 是最终权威轮次，其余命名日志是保留的诊断历史。完整回归日志/XML包含每个测试及 skip。最终候选源码提交与证据提交分开记录，后续文档提交不修改被测生产/测试源。

- 真实隐藏 provider 进程：parse运行中、batch提交后、Reader阶段入口前、Reader发布后/派生入口前、derived已启动。请求中可读、未中断当前provider、边界后调用数不增加、parse/batch/Reader SHA保持、同parent显式恢复到completed；derived场景保持真实terminal并等待独立child自然结束。两次全新模块CLI进程重读停止状态，重复请求、start、直接advance、launcher都不能解除。
- 真实模块CLI并发：重复stop与start；stop/resume同revision竞争；重复显式resume只增加一次running事件；旧resume重放不能解除后来stop。旧worker用真实进程仅执行旧background状态合同，没有能力登记，仍运行时只返回requested；其真实failed优先。
- 单测：损坏记录、请求冲突/过期、未知PID、原业务gate与源SHA验证、scope移动/跨paper拒绝、其他paper不受影响、generic resume和attach守卫、回执丢失及未知dispatch窗口。
- 原004A/004B恢复32项继续执行；仅把“无cancel CLI”的历史事实测试改为新增stop与显式resume参数合同，其余资产和恢复断言保留。完整Python集合包括scope、worker、launcher、Reader/Excel既有回归。无TS源码变化，不运行会重新构建/替换制品的发布链。

## 限制、清理与回退

控制协议只约束新版 A 的受支持入口。已经运行的旧worker、缺失/未知PID或预启动回执不被假称已停止；必须等其结束并重新核对。已有独立xlsx child继续运行，返回 independentChildrenStopped=false。请求期间当前阶段仍可能提交合法资产。没有强杀provider、撤销资产、删除checkpoint或回退正式Reader指针。

停止记录存在时降级旧引擎不会继续提供保护，禁止将“回退代码”描述为停止保证；保留控制记录、库和全部资产，待具有本合同能力的引擎恢复。回退源码不回退数据。损坏控制记录应保留证据人工处理，不能删除记录作为自动恢复。文件替换与两次进程重启有测试；物理掉电/fsync故障、非Windows、任意跨版本并发、真实模型质量、B/UI最终集成和安装组合不在本次已验证范围。

本卡合成实例没有宿主服务。验证结束检查登记worker和xlsx PID已退出，真实进程诊断库未留下owner claim；TemporaryDirectory进程夹具已回收，显式pytest basetemp中的普通tmp_path夹具、专属短路径诊断库及日志保留供复核（其中静态模拟锁文件不代表存活worker）。未修改或终止用户实例。最终 Git clean、receipt phase=review，不把 review 写成 integrated。



早期诊断轮次保留了两次 CLI 夹具缺少 --data-root 的失败，以及补正夹具后的570/3诊断结果；随后补上死亡worker恢复边界。它们不参与最终571/3计数。唯一最终验收为6303986固定源码的accepted/run.json及四份XML。

差异检查：生产/测试/报告无空白错误。三处历史失败 traceback 的行尾空格位于原始 .log/.xml，按原文保留，不清洗失败证据。
