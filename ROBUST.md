# 按批剔除后的复测签发

校准员在原测量修订可用时登记具名剔除情景。复测组可在来源停用后凭冻结证据号申请合格偏差范围，接班员凭报告号领取当时的分组、门槛和结果。原有完整批次流程见 README.md。

## 冻结和签发接口

- `calibration.publish.freeze_scenarios(db, revision_id, target_conditions, groups) -> int` 返回新冻结证据号。指定修订须可用，待测工况沿用该修订的 V1 口径、坐标顺序和精确输入规则。`groups` 是非空的列表或元组，由 `(name, specimen_ids)` 二元项组成。每个 `specimen_ids` 是非空的片号列表或元组，表示该情景剔除的片号。所有名称和片号都是非全空白字符串，按原字符串比较。组名不得重复，同组不得重复片号，片号须在指定修订中，每组至少剔除和保留一件原片。各组可以重叠。不同名称即使对应相同的剔除片号也各自代表一个情景。冻结件绑定同一源修订、口径、待测工况、完整分组和独立签发所需的证据。
- `review.issue.issue_robust(db, evidence_id, k, q)` 用指定冻结件签发并返回报告对象。签发仅消费该冻结件，不读取源测量。`k`、`q` 均为非布尔正整数。`k` 不超过任何一个情景含待测片的总片数，`q` 不超过具名情景数。
- `handoff.lookup.read_robust(db, report_id)` 按报告号返回原固定报告。读取不重算。两处返回的报告对象都提供 `report_id`、`evidence_id`、`groups`、`k`、`q` 和 `candidates` 属性。`groups` 为 `tuple[tuple[str, tuple[str, ...]], ...]`，组名、片号及其各自的输入顺序随报告固定。`candidates` 沿用 V1 的 `review.region_set.CandidateSet`，按序给出合并后的最大闭分量。有限端点为 `Fraction`，无界端为 `None`。空集、全实轴、闭射线和孤立点沿用 V1 集合表示及 `to_payload()` 编码。

每个候选偏差 `t` 都以微米计，并用于同一件待测片。对每个情景，用该组剩余的原片和这件待测片按 V1 含截距模型精确重拟合，在秩亏设计上仍取唯一的拟合值。待测片自身计一次，原片的绝对残差大于或等于待测片绝对残差时计入。计数达到 `k` 的情景给该候选贡献一票。合格范围是同一候选取得至少 `q` 票的完整闭集合。允许全量重算。

业务号沿用库返回的正整数，布尔值不是业务号。未知业务号报 `KeyError`，非法输入和停用源上的新冻结报 `ValueError`。冻结、签发各自完整提交，失败无部分成果并可重试。来源更正、停用和数据库关闭重开均保全已冻结证据与已签报告。保留 V1 接口、既有数据库的读写、旧报告编码及全部原回归。本次新增结果通过 `read_robust` 领取。

## 手算样例

| 输入 | 申请 | 预期 |
| --- | --- | --- |
| A、B、C 的线速依次为 `(-1, 0, 1)`，偏差全为 `0`，待测线速为 `0`，两组分别剔除 A 和 C | `k=2, q=2` | 全实轴 `[[null, null]]` |
| A、B、C 的线速依次为 `(-1, -1, 2)`，其余同上 | `k=2, q=2` | `{0}`，编码为 `[[[0, 1], [0, 1]]]` |
| A、B、C、D 均与待测片同速，偏差分别为 `0, 1, 3, 4`，两组分别剔除 C、D 和 A、B | `k=2, q=1` | `[-1, 5]` |
| 同一四片样例 | `k=2, q=2` | `{2}`，编码为 `[[[2, 1], [2, 1]]]` |

前两份完整批次的 V1 证据具有相同的逐片响应，整批 `k=2` 均返回 `{0}`。分组后，第一份的两个情景里至少各有一片原片与待测片的绝对残差相同。第二份剔除 C 后残差全零，剔除 A 后的残差为 `(-6t/14, -3t/14, 9t/14)`，仅在 `t=0` 达到 `k=2`。四片样例中，两组的单独合格范围是 `[-1,2]` 和 `[2,5]`，两组仅在端点 `2` 共同达标。

## 调用与运行

新增入口交付后的调用样例如下。`robust_examples.py` 提供输入，并可在独立连接上屏蔽源测量读取。`reject_commit` 可用于 SQLite 提交失败的核验。两个夹具都会在退出时解除各自的限制。

```python
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from calibration.publish import freeze_scenarios
from cohort.retirement import retire_cohort
from handoff.database import open_database
from handoff.lookup import read_robust
from review.issue import issue_robust
from robust_examples import (
    TARGET, TOUCH_SPEEDS, TOUCH_DEVIATIONS, TOUCH_GROUPS,
    forbid_source_measurements, record_line,
)

with TemporaryDirectory() as directory:
    path = Path(directory) / 'coating.sqlite3'
    with closing(open_database(path)) as db:
        _, source = record_line(db, TOUCH_SPEEDS, TOUCH_DEVIATIONS)
        evidence = freeze_scenarios(db, source, TARGET, TOUCH_GROUPS)
        retire_cohort(db, source)
        with forbid_source_measurements(db):
            wide = issue_robust(db, evidence, 2, 1)
            point = issue_robust(db, evidence, 2, 2)
        print(wide.candidates.to_payload())   # [[[-1, 1], [5, 1]]]
    with closing(open_database(path)) as db:
        fixed = read_robust(db, point.report_id)
        print(fixed.groups, fixed.k, fixed.q, fixed.candidates.to_payload())
        # TOUCH_GROUPS, 2, 2, [[[2, 1], [2, 1]]]
```

现有 `.pointwise-runtime.json` 提供运行入口。交付时让 `verify` 执行原回归和新增链路核验，核验失败返回非零退出码。让 `demo` 展示停用后实际签发的结果及关闭重开后按原号领取的结果。简述冻结件为何足以支持各组重拟合，以及如何确保签发采用的是指定证据。基线的 `python3 -B -m robust_examples` 可独立核对两份整批 V1 证据相同的输入。
