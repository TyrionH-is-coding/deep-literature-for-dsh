# V02-004D 总控复核与组合验证

2026-09-18：接收固定 dev.3 安装恢复候选，关闭004A-F1。004A-G1与F2仍开放，004整体未通过；没有正式发布或升级用户安装。

A交付 `a37a415c4bec9a895f1dc1619cfa35081cf85d26` 已fast-forward集成；B交付 `865647f0fdcd4ec9164b44790823e8b66a7581e2` 已合入总控 `6b979d18dcb14d54e2e9bb3dc026dfd7b5325b87`。A制品源码 `a45aff9a6d5419c1b7a5cbc7954355176d56fac5`、B制品源码 `c78dc5846dac799b024a4cd07dfbef40bc2e8f6a` 与最终报告提交分开。

npm A/B dev.3、Python dev2；固定Node22.22.2/Python3.11.16/DSHrc7/schema4。生产变化仅版本/插件身份，Python实现沿用已验收004B，B包不包含004E。总控检查范围、原锁字段、模块身份及安装专用探针隔离入口，没有发现源码路径覆盖安装模块。

总控实际重新读取ZIP/tgz/wheel/清单与安装文件：434清单文件＋BUILD-MANIFEST无额外项、41个安装B源文件、两实例各51个Python文件与wheel一致，安装client与构建一致。哈希结果见 [独立记录](V02-004D-control-verification.json)。旧记录原始ZIP的hash与两份原始checkpoint字节也独立校验通过。检查已记录的32项安装断言、六场景同parent/资产保护/进程回收、两组真实旧wheel产生的无SHA running记录及新wheel续接、两次宿主重启后的失败状态/JSON不变。总控没有重复执行整套安装。

开发任务本轮实际回归：Python547pass/3skip、42条offline＋4条assets、构建打包；安装32断言；Excel14pass；smoke12pass＋F2 known_gap。原始早期失败仍保留。每个测试集合按各自单位和来源报告，不累加。安装探针使用 -I，真实模块路径和SHA有证据，provider/翻译及故障注入是合成夹具；不能代替真实内容质量。

当前总控源码组合同时含004E workflow0.1.1及dev.3 engine身份。合入后模块check通过10/47/152，workflow及调用方 **80pass/1 Windows POSIX skip**，见 [组合测试](V02-004DE-control-tests.txt)。这仅是组合源码验证；原dev.3 ZIP仍是workflow0.1.0，后续最终组合必须重新打包验收。

## 未关闭事项

- 004D-O1：直接在failed后调用ReadingPipeline.advance，后续inspect报reading_pipeline_state_invalid；正常worker重排路径已通过。不能仅凭后者成功就认定前者不受支持。004G在冻结基线仅做归因，核对实际CLI路径与状态不变量，再决定修复。
- 004A-G1：后台引擎没有持久停止控制；004F先实现A的安全边界停止、幂等请求与显式恢复，B工具/界面接入随后单卡。当前cancelRequested不等于A worker停止。
- F2、非Windows、真实模型/科学质量、Office/新视觉、任意并发与崩溃窗口仍未验收。两个本卡实例已停止，cleanup记录残留0；真实用户数据不受影响。

004F写A停止控制生产及其回归；004G只写专属诊断并固定旧输入。两者工作树/输出独立，004G不得抢写pipeline。只允许这两个任务并行，后续修复与接口集成串行。安全边界停止不强杀当前provider，已提交资产不回滚；收到停止请求、确认停止与实际终态分别表达。
