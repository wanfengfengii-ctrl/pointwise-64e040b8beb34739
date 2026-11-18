# 涂层试片复测台账

涂层试验室登记线速等工况与厚度偏差口径，接纳带片号的测量并保存更正历史。校准员为一件待测片冻结指定修订的比较依据。复测组用签发的精确范围选择候选偏差，接班员按报告号取得原成果。

## 运行

使用 Python 3.11 标准库。在仓库根目录运行，以下命令中的 `python3` 指向 Python 3.11。

```sh
python3 -B -m verify
python3 -B -m demo
python3 -B -m unittest discover -s tests -t . -v
```

核验入口执行完整回归。演示从 `sample.json` 读取测量和更正，在临时数据库中完成两个修订、原校准与报告、停用、重开和续签，并输出真实的报告导出。

## 计量与测量

- `handoff.database.open_database(path)` 打开并初始化 SQLite 库，调用方负责关闭连接。重复打开或调用 `initialize_database` 保全已有记录。
- `protocol.catalog.register_protocol(db, name, covariates, deviation_unit='um')` 登记不可变口径并返回修订号。`covariates` 是一至四个不重复的有序名称。偏差单位统一为微米，也接受 `µm`、`μm` 和 `微米` 作为输入拼写。
- `cohort.intake.record_cohort(db, protocol_id, rows)` 接纳一个非空队列。每行包含 `specimen_id`、`conditions`、`deviation_um`。同工况的不同片号各占一条。工况可以是按口径顺序排列的序列，也可以是键与坐标名完全匹配的映射。数值可用整数、`fractions.Fraction` 或有理数字符串，比如 `'-3/2'`。缺值、浮点数、布尔值、非法单位、重复片号和不匹配坐标报 `ValueError`，整批拒绝。
- `cohort.revisions.correct_cohort(db, parent_revision_id, protocol_id, rows)` 在可用父版上用同口径逐片更正。更正行写出该片的完整记录，片号须属于父版。结果是独立的后继修订号，父版和未更正的记录保持原值。`CohortStore.get_revision` 可按号核对历史快照和停用状态。

## 冻结与签发

- `calibration.publish.freeze_calibration(db, source_revision_id, target_conditions)` 从指定可用修订冻结一个待测工况，返回校准号。模型含固定截距，原试片和一件待测片共同拟合。秩亏时使用列空间上的唯一最小二乘拟合值。`CalibrationStore.get_calibration` 可按号读取证据，其中 `evidence.residuals_at(candidate)` 以精确有理数复算原试片依次及末位待测片的残差。
- `review.issue.issue_report(db, calibration_id, k, *, before_commit=None)` 原子签发并返回 `ReportRecord`。原片绝对残差不小于待测片时计入，待测片自身总是计入。合法 k 为 1 到含待测片的总数。结果保留完整排序的闭区间、闭射线及孤立点。偏差集合可使用 `candidate in report.candidates` 核对指定有理候选。提交前的无参数钩子在数据库已写入报告时运行，抛出异常时整份回滚。钩子可以读取相同事务中的状态，事务控制由签发入口负责。
- `cohort.retirement.retire_cohort(db, source_revision_id)` 停用指定来源，重复停用保留已停用状态。停用后拒绝从该修订创建更正或新校准。已冻结校准仍可用于续签。
- `handoff.lookup.read_report(db, report_id)` 按号读取原固定正文。`handoff.export.export_report(db, report_id)` 返回确定性 JSON。`candidate_regions` 的每一项为 `[下界, 上界]`，有理端点用 `[分子, 正分母]`，无界端用 `null`。同端点表示孤立点，`[]` 表示空集，`[[null,null]]` 表示全实轴。

业务号使用库返回的正整数。未知业务号报 `KeyError`。不合法的工况、门槛或停用源上的新冻结报 `ValueError`。签发失败会保留原报告和原目录。多个独立使用者各自打开连接，冻结、停用等写入按数据库事务提交顺序生效。

## 一次交班

1. 计量员登记线速口径，取得本班测量使用的口径号。
2. 试验员登记同线速的 A、B 两片，分别记录 −1 与 1 微米。
3. 试验员把 A 更正为 −2 微米，后继版保留 B 并指向原版。
4. 校准员为核查原批次，选原版和同线速待测片冻结校准。
5. 复测组申请至少两片的绝对残差达到待测片。原片和待测片以同一候选偏差共同拟合。
6. 台账签发闭区间 [−3,3]。复测组可选择边界值，校准号和门槛随报告一起固定。
7. 试验员停用原版。原版不再用于新冻结，既有校准和报告仍可领取。
8. 接班员重开数据库，按原号取得原区间和确定性导出，再以同一校准和 k=1 签发全实轴报告。两份成果各有自己的报告号。
