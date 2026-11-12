# 热点站点双路区间校核在线拆分设计（单键在线迁往 r² 个独立工作者库）

本轮只交付设计，不实现拆分。生产源码 `intervaljoin/`、`checks.py`、`reviewcheck.py`、`samples.json` 及原断言保持原样；
下文所有"基线观测"均直接调用现有入口得出，所有"提案预测"均为设计论证，两者分列，不以基线单库成功充当拆分正确性证明。

## 1. 基线盘点（源码锚点）

- 纯关联参照：`intervaljoin/model.py:1`。`canonical`（`intervaljoin/model.py:6`）是全部绑定、排序、去重的规范化基础；
  `normalize`（`intervaljoin/model.py:10`）做基础格式校验；`revise`（`intervaljoin/model.py:33`）实现最高修订语义
  （旧版忽略 `intervaljoin/model.py:39`，同版异内容整批冲突 `intervaljoin/model.py:41`）；
  `materialize`（`intervaljoin/model.py:50`）以 `max(start)<min(end)` 判交（`intervaljoin/model.py:56`-`intervaljoin/model.py:57`），
  并对零匹配有效行各出一条整区间未匹配结果（`intervaljoin/model.py:61`-`intervaljoin/model.py:67`）；
  `delta`（`intervaljoin/model.py:71`）给出批前后集合净差。
- 单库事务基线：`intervaljoin/worker.py:1`。五张表（heads/rows/outputs/receipts/journal）建在 `intervaljoin/worker.py:12`-`intervaljoin/worker.py:19`；
  `read` 在单读事务内取 heads+outputs（`intervaljoin/worker.py:29`-`intervaljoin/worker.py:38`）；
  `apply` 在 `BEGIN IMMEDIATE`（`intervaljoin/worker.py:47`）内依次做回执重放检查（`intervaljoin/worker.py:49`-`intervaljoin/worker.py:54`，
  优先于 seq 与修订判断）、连续 seq 检查（`intervaljoin/worker.py:55`-`intervaljoin/worker.py:57`）、批前后净差
  （`intervaljoin/worker.py:58`-`intervaljoin/worker.py:61`）、源行与结果重写（`intervaljoin/worker.py:62`-`intervaljoin/worker.py:65`）、
  两个故障注入点（`intervaljoin/worker.py:66`-`intervaljoin/worker.py:67`、`intervaljoin/worker.py:72`-`intervaljoin/worker.py:73`）、
  heads/journal/receipts 同事务落库（`intervaljoin/worker.py:69`-`intervaljoin/worker.py:71`）与 `COMMIT`（`intervaljoin/worker.py:74`），
  任何异常整批回滚（`intervaljoin/worker.py:76`-`intervaljoin/worker.py:78`）。`export_key` 是单读事务整键导出
  （`intervaljoin/worker.py:80`-`intervaljoin/worker.py:91`），不是增量搬运接口。
- 路由：`Cluster.owner` 按 key 固定哈希取模（`intervaljoin/cluster.py:12`-`intervaljoin/cluster.py:13`），
  `apply`/`read` 直通属主（`intervaljoin/cluster.py:15`-`intervaljoin/cluster.py:19`）。工作者是独立连接、独立库，无跨库事务。

## 2. 基线证据（实际观测）

以下恰一个 `json baseline-evidence` 代码围栏，内容逐值等于 `python3 reviewcheck.py replay` 的实际输出（由 `reviewcheck.py verify` 重放核对）：

```json baseline-evidence
{"head_after_replay": 7, "history": [{"key": "station-7", "rows": [["l1", "r1", 5, 10, {"reading": 9}, {"quality": "ok"}]], "seq": 1}, {"key": "station-7", "rows": [["l1", "r1", 5, 10, {"reading": 9}, {"quality": "ok"}], ["l2", "r2", 25, 30, {"reading": 8}, {"quality": "ok"}]], "seq": 2}, {"key": "station-7", "rows": [["l1", null, 0, 10, {"reading": 9}, null], ["l2", "r1", 22, 27, {"reading": 8}, {"quality": "revised"}], ["l2", "r2", 25, 30, {"reading": 8}, {"quality": "ok"}]], "seq": 3}, {"key": "station-7", "rows": [["l1", null, 0, 10, {"reading": 9}, null], ["l2", "r1", 22, 27, {"reading": 8}, {"quality": "revised"}]], "seq": 4}, {"key": "station-7", "rows": [["l1", null, 0, 10, {"reading": 9}, null], ["l2", "r1", 45, 50, {"reading": 8}, {"quality": "revised"}]], "seq": 5}, {"key": "station-7", "rows": [["l1", null, 0, 10, {"reading": 9}, null], ["l2", null, 40, 50, {"reading": 8}, null]], "seq": 6}, {"key": "station-7", "rows": [["l1", null, 0, 10, {"reading": 9}, null], ["l2", "r2", 42, 48, {"reading": 8}, {"quality": "back"}]], "seq": 7}], "repeated_move": {"add": [["l1", null, 0, 10, {"reading": 9}, null], ["l2", "r1", 22, 27, {"reading": 8}, {"quality": "revised"}]], "key": "station-7", "remove": [["l1", "r1", 5, 10, {"reading": 9}, {"quality": "ok"}]], "seq": 3}, "responses": [{"add": [["l1", "r1", 5, 10, {"reading": 9}, {"quality": "ok"}]], "key": "station-7", "remove": [], "seq": 1}, {"add": [["l2", "r2", 25, 30, {"reading": 8}, {"quality": "ok"}]], "key": "station-7", "remove": [], "seq": 2}, {"add": [["l1", null, 0, 10, {"reading": 9}, null], ["l2", "r1", 22, 27, {"reading": 8}, {"quality": "revised"}]], "key": "station-7", "remove": [["l1", "r1", 5, 10, {"reading": 9}, {"quality": "ok"}]], "seq": 3}, {"add": [], "key": "station-7", "remove": [["l2", "r2", 25, 30, {"reading": 8}, {"quality": "ok"}]], "seq": 4}, {"add": [["l2", "r1", 45, 50, {"reading": 8}, {"quality": "revised"}]], "key": "station-7", "remove": [["l2", "r1", 22, 27, {"reading": 8}, {"quality": "revised"}]], "seq": 5}, {"add": [["l2", null, 40, 50, {"reading": 8}, null]], "key": "station-7", "remove": [["l2", "r1", 45, 50, {"reading": 8}, {"quality": "revised"}]], "seq": 6}, {"add": [["l2", "r2", 42, 48, {"reading": 8}, {"quality": "back"}]], "key": "station-7", "remove": [["l2", null, 40, 50, {"reading": 8}, null]], "seq": 7}]}
```

基线回归（`python3 checks.py normal`）实测输出 `{"normal": "NORMAL_REGRESSION_OK", "final": {... "seq": 8 ...}}`；
`python3 checks.py demo` 实测展示七笔真实变更、`move` 净差、seq=1 旧回执重放与整键导出（含 journal 八条、receipts 七条、含墓碑源行四行）。
这些是单库基线观测，不证明任何拆分性质；拆分协议的正确性论证见第 9–10 节，留待人工独立复核。

## 3. 目标布局（提案）

r 为 ≥2 整数，目标为 r² 个独立工作者库，逻辑槽位排成 r×r 网格 `(i,j)`，`0≤i,j<r`。哈希 `H` 作用于 `(side,key,id)`：

- L 行 `(key,"L",id)` 复制到行 `i=H_L(id)` 的全部 r 个槽位 `(i,0..r-1)`；R 行 `(key,"R",id)` 复制到列 `j=H_R(id)` 的全部 r 个槽位 `(0..r-1,j)`。
  每条源记录（含墓碑）恰 r 份（满足"至多 r 份"），两侧状态均按行/列分摊；槽位 `(i,j)` 持有 `L_i={l:H_L(l)=i}` 与 `R_j={r:H_R(r)=j}`，
  期望份额各约 `N_L/r`、`N_R/r`。
- 配对见证者唯一：候选对 `(l,r)` 只在槽位 `(H_L(l),H_R(r))` 计算。该槽位本地同时持有双方副本（行覆盖全列、列覆盖全行），
  配对计算完全本地化，且全局只有一个槽位产出该对——可见结果中关联对只计一次。
- 未匹配见证者唯一：取该键固定列 `W(key)=H("W",key) mod r`。L 行 `l` 的未匹配结果只由槽位 `(H_L(l),W(key))` 物化，
  R 行 `r` 的未匹配结果只由槽位 `(W(key),H_R(r))` 物化；物化条件是"全局度为零"（见下），不是本地无匹配。
- 全局零匹配用计数区维护：控制库为该键保存 `cnt_L[l][0..r-1]`（槽位 `(H_L(l),j)` 上报的本地匹配度）与 `cnt_R[r][0..r-1]`，
  全局度 `deg=Σ分量`。计数区只存整数计数，不存区间、载荷、配对或结果行，不做关联计算——它不是集中式关联器；
  配对与结果的计算、物化、存储全部在槽位，源行与结果没有任何集中副本。
- 结果存储：配对结果行只存见证者槽位的 `outputs`；未匹配结果行只存未匹配见证者槽位。每行结果带物化时的 `seq`。
  `read` 归并 r² 个槽位的 `outputs` 按 `canonical` 排序（结果行全局唯一，归并不需要去重逻辑）。
- journal 不集中于控制库：批 `seq` 的日志条目落槽位 `seq mod r²`（确定性、可收集，供下次迁移追后缀）；
  控制库只保存控制元数据与回执（契约明确允许的两类）。

单行更正的访问集：1 次控制库读（布局/回执/head）+ 该 id 的 r 个副本槽位 + 这些槽位上的区间相交索引（对 `start/end` 建本地索引）
+ 真实受影响配对的见证者槽位 + 计数区与未匹配见证者。全程不扫描全键；多行同批按 `(l_id,r_id)` 去重受影响集合。

## 4. 发布策略比较与选择

- 策略一（选定）：单协调者 + 控制库仲裁的两阶段栅栏发布。协调者经控制库单行原子 claim 获得 `(key,gen,token)`，
  顺扫复制 → 追日志后缀 → 栅栏（撤销旧布局写令牌）→ 哨兵带锁读最终前缀并搬运 → 控制库单事务 PUBLISH。
  适用边界：要求逐键线性化、精确回执、源事务不拆批的硬语义场景（本契约）。代价：协调者是临时单点（由控制库状态接管恢复），
  栅栏窗口内新写被短缓冲。
- 策略二（否决）：逐槽位滚动发布——槽位建好即上线，read 在滚动窗口内跨新旧布局合并。窗口内"批前后净差"与"全局零匹配"
  必须跨两个布局合并计算，等价于临时集中合并器（违反禁止集中式关联器），且不同槽位处于不同代际，read 会拼接不同 seq 的净态，
  破坏完整前缀与逐键线性化。仅适用于可容忍最终一致读的分析型副本，不满足本契约。
- 策略三（备选边界）：阴影双写——迁移开始后所有写同时走旧布局与目标 2PC，追上即切。切换瞬间新布局已热、无需栅栏缓冲；
  但整个迁移期每次写都付 r 副本 + 2PC 放大，且双写批的净差与回执需双路径一致，未升级旧工作者无法参与。
  仅当该键写入稀疏、读极重、迁移窗口长时值得；本设计不选为主策略，列为后续可选优化。

选择依据：只有策略一把"切换"压缩为控制库一个单库事务（唯一线性化点），同时满足禁止跨库事务、禁止全量广播
（只通知该键参与者，路由缓存惰性失效）、禁止集中式关联器、有限写入后完成全部硬约束。

## 5. 最少持久状态

- 控制库（每键）：`claims(key,gen,r,token,coordinator,phase,cut_seq)`；`layout(key,published_gen,fence_epoch,槽位映射)`；
  `heads(key,seq)`；回执区 `receipts(key,request,digest,response)`（切换后）；计数区 `cnt(key,side,id,slot,degree)`；
  2PC `decisions(key,seq,outcome,response)` 与 `acks(key,seq,slot)`；复制进度 `copy_progress(key,gen,cursor,caught_seq)`。
  全部为该键 O(1) 行或 O(r·(N_L+N_R)) 个机器字，不含源行内容、区间索引或结果全集。
- 旧工作者：基线五表不动（`intervaljoin/worker.py:12`-`intervaljoin/worker.py:19`）。
- 目标槽位：`rows`（本槽位份额，含墓碑）、`outputs(body,seq)`、本地相交索引（`start/end` 索引列）、`prepare` 暂存区、
  `slot_meta(gen,token,applied_seq)`、journal 份额（`seq mod r²`）。
- 协调者无可丢状态：其进度全部在控制库 `copy_progress`/`claims`，崩溃后由任一恢复者凭 `(gen,token)` 续跑。

## 6. 参与者间接口条件

- 消息可重排、重复、延迟但最终可达；所有命令携带 `(key,gen,token,seq,内容)` 且幂等，接收方按 `(gen,token)` 与 `seq` 去重。
- 不使用跨库事务、不 ATTACH、不共享业务库；控制库事务只写控制元数据与回执。
- 活性不依赖超时判活：接管靠控制库 token 单调递增（新 token 使旧协调者写控制库时被 STALE 拒绝）；
  栅栏靠令牌撤销 + 旧库写锁内验证，不靠"猜测旧进程已死"。
- 持久化边界即 SQLite 已提交事务；进程可在任意边界退出，已提交事务不丢。

## 7. 协议流程与逐语句伪代码

记号：`【控】`=控制库单事务；`【旧】`=旧库事务；`【槽】`=槽位本地事务；`→`=幂等消息。`P` 为页大小。

### P1 协调者迁移主流程 `migrate(key,r_new)`（可重入）

- P1.1 `gen ← 【控】read published_gen(key)+1`。
- P1.2 `【控】claim(key,gen,r_new,self)`：无该 gen 记录则插入并返回 `(WON,token)`；同 gen 同协调者重入返回原 token；
  同 gen 不同协调者先到者胜（主键冲突即败）；更高 gen 的 claim 直接抢占并使旧 token 失效。败者退出或转投更高 gen。
- P1.3 `【控】set_cut(key,gen,token,cut_seq=旧布局 heads[key])`：复制截点（对应 `intervaljoin/worker.py:12` 的 heads）。
- P1.4 `cursor ← 【控】copy_progress(key,gen)`：崩溃续跑依据；首次为空。
- P1.5 循环：`页 ← 【旧】SELECT body FROM rows WHERE k=? AND (side,id)>cursor ORDER BY side,id LIMIT P`
  （有界游标顺扫，对原布局该键源行至多一遍；复用 `intervaljoin/worker.py:13` 的行表，不调用 `export_key`）。
- P1.6 对页内每行 `→ COPY(gen,token,row)` 到该行的 r 个目标槽位（行/列副本规则，见 P4.2）。
- P1.7 `【控】set_progress(key,gen,token,页末(side,id))`：页确认后才推进游标；未确认页崩溃后重读（幂等），已确认页不重读。
- P1.8 追赶循环：`后缀 ← 【旧】SELECT seq,request,changes FROM journal WHERE k=? AND seq>caught ORDER BY seq LIMIT P`
  （只追日志后缀，对应 `intervaljoin/worker.py:18`）；空则退出循环（源写入有限时必出现）。
- P1.9 对后缀每批按 P5 在候选布局执行（标 `gen`，不发布）；`【控】set_caught(key,gen,token,末seq)`。
- P1.10 `【控】fence(key,gen,token)`：校验 token，`fence_epoch+1`，`phase=FENCED`——旧布局写令牌从此刻撤销（栅栏）。
- P1.11 哨兵：`【旧】BEGIN IMMEDIATE`（同 `intervaljoin/worker.py:47`，与在飞旧事务互斥）；锁内读 `heads.seq`、
  `journal` 后缀（>caught）、`receipts` 全量该键条目；`ROLLBACK`（不污染业务）。拿到锁即知：凡栅栏前验证通过的旧事务皆已提交，
  凡未提交者锁内验证必失败——此前缀即最终前缀。
- P1.12 CARRY：哨兵 journal 后缀按 P5 逐批在候选布局执行（源事务不拆批）；`【控】`回执区 `INSERT OR IGNORE` 哨兵回执（幂等搬运）；
  栅栏窗口内被协调者内存缓冲的调用方请求按 seq 续排（已在 journal 者跳过，其回执已随搬运入区，重试即命中）。
- P1.13 `【控】publish(key,gen,token,槽位映射)`：`phase=PUBLISHED,published_gen=gen`——切换线性化点。
- P1.14 异步 DRAIN：路由缓存惰性失效；`acks` 完备后后台删除旧布局该键五表内容（幂等，可重入）。

### P3 升级后旧布局写路径（基线事务外加令牌验证）

- P3.1 格式校验与绑定同基线（`intervaljoin/worker.py:41`-`intervaljoin/worker.py:46`）。
- P3.2 `【旧】BEGIN IMMEDIATE`；锁内`【控】`读校验 `(key,fence_epoch)` 未撤销；已撤销则 `ROLLBACK` 并回 `REDIRECT(gen,布局)`。
- P3.3 其余完全按基线 `intervaljoin/worker.py:49`-`intervaljoin/worker.py:74` 执行；回执仍写旧库，切换时由 P1.11–P1.12 搬运。

### P4 目标槽位命令处理

- P4.1 任何命令：`【槽】`若 `(gen,token)` 陈旧于 `slot_meta` 则忽略（旧协调者/旧代际隔离）。
- P4.2 `COPY(row)`：`【槽】`若现有行 `rev ≥ row.rev` 则跳过，否则 upsert 并建索引；重复/乱序复制安全（同 `intervaljoin/model.py:39` 语义）。
- P4.3 `PREPARE(seq,…)`：同 seq 暂存已存在→直接回 YES；`applied_seq+1≠seq`→回 HOLD（协调者先补前序 COMMIT，保证每槽位净态是完整前缀）；
  否则暂存落库回 YES。
- P4.4 `COMMIT(seq)`：`【槽】`幂等应用暂存（rows/outputs/journal 份额，`applied_seq:=seq`），回 `ACK(key,seq,slot)`；重复投递直接 ACK。
- P4.5 `ABORT(seq)`：`【槽】`删暂存，幂等。
- P4.6 `READ(h)`：`applied_seq==h` 返回 `outputs`；`<h` 回 STALE（调用方重试）；`>h` 不可能（head 先于槽位推进，见 P5.6–P5.8）。

### P5 目标稳态 apply（亦用于追赶与 CARRY 的逐批执行）

- P5.1 `changes←normalize(changes)`（`intervaljoin/model.py:10` 语义）；格式失败整批拒绝，不留痕迹。
- P5.2 `binding←canonical({"seq","changes"})`（`intervaljoin/model.py:6`）。
- P5.3 `【控】`回执区查 `(key,request)`：命中且 digest 同→返回原响应（不推进 head）；digest 异→`REQUEST_CONFLICT`。重放优先于 seq 与修订判断。
- P5.4 `【控】``seq≠head+1`→`SEQ_GAP`（同 `intervaljoin/worker.py:55`-`intervaljoin/worker.py:57`）。
- P5.5 批内每 `(side,id)` 读其任一副本槽位当前行，按 `revise`（`intervaljoin/model.py:33`）判定：旧 rev 忽略、同版同内容忽略、
  同版异内容→`REVISION_CONFLICT` 整批拒绝。
- P5.6 受影响配对集：对每个被接受变更，用其旧区间与新区间分别在该行/列的 r 个槽位查相交索引，取批前/批后配对差；
  同批多行按 `(l_id,r_id)` 去重，配对结果一律用批后双侧状态计算（不暴露中间匹配，等价基线 `intervaljoin/worker.py:58`-`intervaljoin/worker.py:61`）。
- P5.7 由配对差派生计数增量 `Δcnt` 与翻零集 `Z`（deg 由正变零或反之）；`Z` 中有效行生成未匹配物化/撤销指令（唯一见证者）。
- P5.8 `response←{"key","seq","remove","add"}`（`canonical` 排序的集合净差，同 `intervaljoin/model.py:71`）。
- P5.9 `→ PREPARE(gen,token,seq,副本修订,按见证者分组的配对差,Δcnt,Z,未匹配差,response)` 至受影响槽位（只发该键参与者，非广播）。
- P5.10 全 YES→`【控】decision=COMMIT`：同事务写 `heads=seq`、回执区 `(key,request,binding,response)`、计数区应用 `Δcnt`、
  `decisions(key,seq,COMMIT,response)`——该事务提交即写入完成点（线性化点）。任一 NO/协调者故障→`decision=ABORT`，`→ABORT`，整批无痕迹。
  `fail_at="after_state"` 在 P5.9 后注入、`fail_at="after_receipt"` 在 P5.10 事务内回执写后提交前注入，均整批回滚抛 `INJECTED`，
  与基线两注入点（`intervaljoin/worker.py:66`-`intervaljoin/worker.py:67`、`intervaljoin/worker.py:72`-`intervaljoin/worker.py:73`）语义对齐。
- P5.11 `→COMMIT(seq)` 至各槽位（幂等，可重发）；槽位 ACK 落 `【控】acks`；空批/全旧修订批无受影响槽位，仍走 P5.10 推进 head
  （对齐基线 `intervaljoin/worker.py:69`-`intervaljoin/worker.py:71` 对空净差同样落三表）。
- P5.12 返回 response。响应丢失不影响已持久化回执；调用方重放走 P5.3。

### P6 read 路由

- P6.1 `【控】`读 `(phase,published_gen,head)`。
- P6.2 `phase<PUBLISHED`→旧布局 `read`（`intervaljoin/worker.py:29` 语义），迁移期间读无感。
- P6.3 否则并行 `READ(head)` 全部 r² 槽位；任一 STALE→重试（COMMIT 在途或恢复者重发，有限故障下必齐）；绝不拼接不同 seq 的净态。
- P6.4 归并 `outputs` 按 body 排序，返回 `{"key","seq":head,"rows"}`；read 的线性化点是 P6.1 读 head 的时刻。

### P7 恢复（任一协议参与者可担任恢复者）

- P7.1 `【控】`读 `claims[key]`；无记录→退出。
- P7.2 `phase=CLAIMED/COPYING/CATCHING`→以同 gen 更高 token 重 claim（P1.2 重入规则）接管，从 `copy_progress` 续 P1.5。
- P7.3 `phase=FENCED`→续 P1.11（哨兵可重入，ROLLBACK 无副作用）。
- P7.4 `phase=PUBLISHED`→续 P1.14（DRAIN 幂等）。
- P7.5 扫描 `decisions`：`COMMIT` 而未全 ACK→重发 `COMMIT`（P4.4 幂等）；`ABORT`→重发 `ABORT`。
- P7.6 旧协调者复活后写控制库→token 不符→STALE 拒绝；其发往槽位的命令被 P4.1 忽略。

## 8. 线性化点与逐键线性化

- 写：同键写由协调者串行处理（控制库该键行级互斥），写入完成点=P5.10 decision 事务提交（或基线 `intervaljoin/worker.py:74`）。
  完成写入之后才开始的 read：P6.1 读到的 head 必 ≥ 该 seq；P6.3 保证归并的是该 head 的完整净态——不落后。
- 切换：PUBLISH（P1.13）是 read 路由的唯一翻转点；之前 read 走旧布局（其净态随写推进），之后走新布局
  （CARRY 完成后新布局净态=旧布局最终前缀+缓冲批，二者在同一 seq 上相等），故切换瞬间 read 结果连续。
- 重放旧回执只读回执区（P5.3），不写 head——head 不回退。
- 源事务不拆批：一批的全部效果在 P5.10 一个控制库事务 + 一轮槽位 COMMIT 内生效；read 只在全槽位同 seq 时返回（P6.3），
  部分提交的中间态对外不可见。配对及未匹配行不存在"短暂重漏"的可见窗口：候选布局的内部中间态从不对外服务（P6.2），
  稳态下配对撤销与未匹配物化同属一批的同一 decision。

## 9. 契约时序走查（提案预测，对照 `samples.json` 与 `checks.py:22`-`checks.py:37` 的基线预期）

### A. 截点 seq=2；r1 未复制完时提交 seq=3；新修订先于旧复制到达，seq=3 重复投递

r=2，P1.3 记 `cut_seq=2`。游标已确认 `l1(rev1,[0,10))`、`l2(rev1,[20,30))`，`r1` 页未确认。旧布局提交 seq=3
（`r1→rev2,[22,27)`，journal 落 `intervaljoin/worker.py:70`）。目标先经追赶流收到 `r1 rev2`（P1.9），
后经重排的复制流收到 `r1 rev1,[5,15)`（P1.6 的页在 seq=3 提交前已读出）：槽位 P4.2 按 rev 判定 `1<2` 直接丢弃，
源行收敛于 rev2。配对：见证者 `(H_L(l2),H_R(r1))` 本地已有 `l2[20,30)` 与 `r1[22,27)` → 物化 `l2-r1@[22,27)`；
`l1` 与 rev2 的 r1 不交，`deg(l1)=0` → 未匹配见证者物化 `[l1,null,0,10)`。若乱序反转（rev1 先到）：槽位先物化
`l1-r1@[5,10)`，rev2 到达后同批增量撤销并改物化 `l2-r1@[22,27)` 与 l1 未匹配——中间态只在候选布局内部，P6.2 下 read 不可见。
seq=3 重复投递：P5.3 回执命中（或追赶去重键 `(gen,seq)` 命中）→ 原样返回/忽略，不二次执行。游标崩溃重开：P1.4 读
`copy_progress` 的已确认页末 `(side,id)` 续扫，未确认的 r1 页重读重发（P4.2 幂等），已确认页不重读。

### B. seq=5 部分参与者持久化、另一些先收到 seq=6；逐边界 read；随后 seq=7

目标布局服务中（r=2）。seq=5 批：`l2→rev2,[40,50)`、`r1→rev3,[45,55)`。P5.6 受影响配对去重后仅 `(l2,r1)`：
批前 `[22,27)`、批后 `[45,50)`，同一见证者；`deg(l2)` 保持 1（配对仍存在），绝不产生 l2 未匹配——全局零匹配由计数区判定，
不把各槽位"本地无匹配"并集（本地度只是 `cnt` 分量）。故障使部分槽位暂存落库、协调者在 decision 前退出：
恢复者 P7.5/P7.2 重走 P5.9–P5.10（暂存幂等，P4.3 同 seq 直接 YES），decision=COMMIT(5) 持久化后 `head=5`。
此时 seq=6 的 PREPARE 才可能发出（同键串行）；消息重排使某槽位先收 PREPARE(6) 后收 COMMIT(5)：P4.3 因
`applied_seq+1≠6` 回 HOLD，协调者补发 COMMIT(5) 后再暂存 6——每槽位净态始终是完整前缀。各边界 read：
decision(5) 前 `head=4` → `[l1未匹配, l2-r1@[22,27)]`；decision(5) 后若有槽位未 COMMIT，P6.3 重试直至齐全 →
`[l1未匹配, l2-r1@[45,50)]`；seq=6（r1 rev4 墓碑）同批撤销 `l2-r1@[45,50)` 且 `deg(l2)→0` 物化 `[l2,null,40,50)`，
二者同一 decision → read 只见 `[l1未匹配, l2未匹配]` 或前一态，不见空也不见双份；seq=7（r2 rev3 复活 `[42,48)`）同批
物化 `l2-r2@[42,48)` 并撤销 l2 未匹配，l1 未匹配始终保留——与基线样例预期（`checks.py:31`-`checks.py:36`）逐值一致。

### C. seq=6 提交完成但响应丢失；迁移切换且 seq=7 完成后重放 seq=6 原 request

seq=6 的持久化时刻：源修订与结果随槽位 COMMIT 落库（P4.4），匹配计数、head=6、回执随 P5.10 decision 事务落控制库，
响应在之后返回——丢失不影响已持久化状态。随后迁移（任一 gen）：P1.11 哨兵把旧布局回执（若 seq=6 在旧布局执行）或
P5.10 已落的回执区条目随 P1.12 就位；P1.13 PUBLISH 后 seq=7 在新布局完成，`head=7`。重放 seq=6 原 request：
P5.3 命中回执区 digest → 返回原响应 `{seq:6, remove:[l2-r1@[45,50)], add:[[l2,null,40,50,…]]}`，head 保持 7
（重放路径不写 head）。同 request 改内容：digest 异 → `REQUEST_CONFLICT`（对齐 `intervaljoin/worker.py:51`-`intervaljoin/worker.py:52`）。
布局切换的可见性：PUBLISH 前 read 走旧布局见 seq=6 净态，PUBLISH 后走新布局见同一前缀加 seq=7——切换本身不改写任何业务净态。

### D. 两协调者竞争同键 r=2 与 r=3；赢家发布持久化后、响应前退出；旧工作者迟到

P（r=2）与 Q（r=3）同基于 gen1：P1.2 控制库单行原子裁决，先插入者胜；败者观察到既有 claim 后若以 gen2 再 claim
（更高 gen 直接抢占），则 P 的 token 失效，其后续写控制库被 STALE 拒绝、发槽位命令被 P4.1 忽略——赢家裁决不依赖关闭任何旧进程。
设赢家已执行 P1.13（PUBLISH 持久化）后在响应前退出：发布已是控制库事实；恢复者 P7.4 续 DRAIN。旧工作者恢复并收到下一个源请求：
P3.2 锁内验证发现 `fence_epoch` 已撤销 → 回滚并回 REDIRECT；调用方同时用新路由重试：若该请求曾被旧布局执行，
其回执已随 P1.12 入区 → P5.3 命中返回原响应；否则按 P5 在新布局执行。请求绑定（`canonical({"seq","changes"})`，
`intervaljoin/worker.py:46`）保证两条路径不会重复生效。重开续跑：新协调者凭 P7.2 的 token 重入接管，复制游标、
追赶位置、decision 全部在控制库，无内存态不可恢复。

## 10. 正确性论证（提案，待人工复核）

- 关联对唯一性：`(l,r)` 的见证者 `(H_L(l),H_R(r))` 由确定性哈希唯一指定；复制/命令幂等使同一对不会被重复物化；
  read 归并的结果集每行至多一份。墓碑行不参与配对（同 `intervaljoin/model.py:51`-`intervaljoin/model.py:52` 只取有效行）。
- 全局零匹配：`deg(x)=Σ_slot cnt` 是全局量；未匹配行当且仅当 `deg=0` 且行有效时由唯一见证者物化；配对增删与 `Δcnt`
  在同一 decision 事务应用，故未匹配行与配对行不会同时可见也不会同时缺失。
- 修订幂等：副本槽位按 `revise` 语义（`intervaljoin/model.py:33`）判定，乱序/重复的 COPY 与 PREPARE 均被 rev 与
  `(gen,seq)` 去重吸收；同版异内容整批 `REVISION_CONFLICT`，不推进 head、不留痕迹（对齐 `intervaljoin/worker.py:76`-`intervaljoin/worker.py:78`）。
- 完整前缀：每槽位 `applied_seq` 严格 +1 推进（P4.3 HOLD）；read 只在全槽位同 seq 归并（P6.3）；切换点前后净态在同一
  seq 相等（P1.11–P1.12 的最终前缀 + CARRY）。read 永不拼接不同 seq 的状态。
- 迁移终止：源写入有限 ⇒ P1.8 后缀最终为空；哨兵拿锁（公平执行）得最终前缀；CARRY 有界；2PC 参与者有限；
  故障有限 ⇒ 恢复者有限次接管后 PUBLISH 必达。持续高频写入下追赶可能滞后（限速与页大小缓解），契约只要求有限写入后完成，满足。

## 11. 成本模型（提案预测；`N_L,N_R`=源行数含墓碑，`r`=副本因子，`M`=结果行数，`Δ`=批真实受影响配对数，`b`=批内行数）

- 稳态空间（目标布局）：源行副本 `r(N_L+N_R)`；槽位相交索引与行同阶 `O(r(N_L+N_R))`；计数区 `O(r(N_L+N_R))` 机器字；
  结果恰 `M` 份分布各槽位；回执 `O(请求数)` 在控制库；journal `O(批数)` 分摊槽位。旧布局基线对照：`N_L+N_R+M+O(批数)+O(请求数)`。
- 单行更正：`O(1)` 控制库事务×2 + 副本读写 `r` + 索引查询 `O(log + 命中)` + 见证者命令 `O(Δ)` + 计数/未匹配 `O(Δ+|Z|)`
  + 2PC 消息 `O(参与者数)`；与 `N_L,N_R` 无关，不扫描全键。多行批乘 `b` 且受影响集合去重。
- read：`O(r²+M)`（契约不计入增量限制）。
- 迁移峰值（每键，共存分别核算）：旧布局保持 `N_L+N_R+M`；候选布局顺扫读 `N_L+N_R` 恰一遍（分页重试只重读未确认页）、
  副本写 `r(N_L+N_R)`、索引构建 `O(r(N_L+N_R)·log)`；初始配对的总输入扫描 `=Σ槽位(本地L+本地R)=r(N_L+N_R)`（这是输入扫描），
  配对输出恰 `P≤M`（每对一次，这是不可避免的真实输出）；追赶与 CARRY 各 `O(窗口内写入量·r)`；控制库新增
  `O(r(N_L+N_R))` 字 + 回执。无全量广播：消息只发该键参与者。

## 12. 分配与偏斜局限

`H` 按 `(side,id)` 散列，期望每槽位 `(N_L+N_R)/r` 行，但不保证任意 ID 分布的完美均衡：偏斜时单槽位份额超期望，
而单条记录仍 ≤ r 份、配对见证仍唯一、正确性不变。未匹配物化集中在 `(·,W(key))` 与 `(W(key),·)` 共 `2r-1` 个槽位，
`W(key)` 按 key 散列使不同键分摊到不同列；单键内未匹配行极多时是已知热点局限，缓解（未匹配结果再分片、
`W` 动态迁移）列入后续拆解，不影响本轮语义。

## 13. 后续开发拆解

1. 控制库 schema 与 `claim/fence/publish/decision` 单事务原语（P1.2/P1.10/P1.13/P5.10）。
2. 路由层升级：布局缓存、P3 令牌验证、REDIRECT 重试。
3. 目标槽位服务：rows/outputs/相交索引/暂存区与 P4 命令处理器。
4. 协调者状态机 P1 与恢复者 P7（含哨兵与 CARRY）。
5. 稳态 P5/P6（2PC、计数区、read 归并）。
6. 迁移执行器：分页顺扫、后缀追赶、DRAIN。
7. 回归：保留 `checks.py normal|demo` 与 `reviewcheck.py replay|verify` 作基线证据；新增目标布局在 r=2、r=3 下
  对同一 `samples.json` 七笔的逐值一致性重放（本轮不实现）。

## 14. 验证与重跑

- `python3 checks.py normal`：基线正常业务、重放、冲突、事务回滚断言（实测通过）。
- `python3 checks.py demo`：真实七笔变更、旧回执与导出状态（实测输出见第 2 节概述）。
- `python3 reviewcheck.py replay`：输出固定样例全部实际 history/responses/repeated_move/head_after_replay（第 2 节围栏逐值等于其输出）。
- `python3 reviewcheck.py verify`：重跑原业务回归与全部样例，逐值核对第 2 节证据并校验本文件源码行号有效性。
- `.pointwise-runtime.json` 保持 `version=1,kind=cli,setup=[]`，`verify` 改为 `["python3","reviewcheck.py","verify"]`，
  `demo` 改为 `["python3","reviewcheck.py","replay"]`；demo 展示的是真实基线结果。
