# V02-004G：直接 advance 失败路径归因

单目标：判断004D保留的 failed→直接ReadingPipeline.advance→reading_pipeline_state_invalid 是否为受支持入口缺陷、调用前提遗漏或夹具错误，并给出最小后续建议。只诊断，不修改生产。

A 工作树 `C:/Users/15694/Documents/ChatGPT/deep-literature-engine-v02-004g`，分支 `codex/v02-004g-advance-audit`，base `a37a415c4bec9a895f1dc1619cfa35081cf85d26`。应用默认旧dsh reader不使用。总控B `C:/Users/15694/Documents/ChatGPT/deep-literature-for-codex` 指定contextCommit，用git show读本卡/AGENTS/session-protocol/004D-control-review，以及 `docs/project/evidence/V02-004D/restart-failure-direct-advance.json/.txt` 和当前 `scripts/fixtures/v02-004d/restart-failure.py`。只读冻结文件，不访问或改变旧实例。核对Git并写A `docs/codex-v02/V02-004G-receipt.json`。

仅新增 `scripts/v02-004g-*`、`scripts/fixtures/v02-004g/`、`docs/codex-v02/V02-004G*`。不改生产、既有测试/版本/锁，不把尚未归因失败加入全局测试链，不改004F工作树。独立固定依赖环境/短路径合成库/provider、隐藏进程和自有清理；无真实模型/凭据/用户安装。

1. 重建最小失败场景，分别比较直接服务advance与真实CLI resume/worker入口；不能仅通过直接transition重排后成功就宣称公共CLI通过。记录完整错误堆栈、调用参数、前后pipeline/status/checkpoint，定位具体状态校验不变量。
2. 核实是否存在生产调用路径会遇到该序列；在同源、显式失败恢复、gate、阶段完成时间等必要条件内收敛原因。正常CLI和内部API支持边界分别说明，不能未经源码证据称“内部不支持”。
3. 若缺陷成立，保留正确期望的失败探针、最小源码修复建议和回归范围；若夹具错误，解释违规前提及可重放正确用法。任何结论需新证据，不沿用旧报告口头限制。
4. 保留原失败资料，准确列新执行/未执行和进程清理。最终提交本分支、clean、receipt review，交总控决定下一卡。不能自行修复、合并main、发布或领取任务。

与004F独立：本卡冻结输入且只写专属诊断文件，不采用004F未完成控制接口；若判断修复触及同一pipeline，后续实施必须等待004F并串行协调，本卡不抢写。
