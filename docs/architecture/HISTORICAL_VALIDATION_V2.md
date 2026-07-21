# Historical Validation V2

版本：V2.3

## 1. 目标

历史验证不证明AI能预测未来，而是检验：在当时可获得的信息条件下，系统是否识别了真正值得研究的机会、是否遗漏决定性反方证据，以及Confidence和Action Level是否合理。

## 2. 三层验证

### 数据层

- 公告和财报按发布日期可得；
- 行业/指数/ETF成分按历史有效期；
- 退市和幸存者偏差得到处理；
- 复权和公司行动正确；
- 禁止使用未来修订值。

### 研究层

- 重建当时MarketState；
- 加载当时ThesisVersion；
- 只使用截止时点Evidence；
- 锁定Opportunity、Candidate、Confidence和Action Level；
- 再揭晓未来结果。

### 结果层

- 未来1/3/6/12个月收益；
- 相对行业和基准超额；
- 最大回撤；
- Thesis后续是否被证实；
- Price Move Attribution是否正确；
- 是否发生当时不可知事件。

## 3. 过程与结果四象限

| 过程 | 结果 | 分类 |
|---|---|---|
| 正确 | 正向 | 高质量成功 |
| 正确 | 负向 | 合理失败/随机损失 |
| 错误 | 正向 | 运气盈利 |
| 错误 | 负向 | 典型错误 |

False Positive首先依据当时研究过程定义，不简单等同于未来价格下跌。

## 4. 验证对象

- MarketState分类；
- Thesis状态和Confidence变化；
- Mispricing Hypothesis；
- Temporary/Structural归因；
- Asset Expression选择；
- Research Priority；
- Action Level；
- Alert Eligibility；
- Missed Opportunity。

## 5. Confidence校准

内部Confidence分桶后比较：

- Thesis完整率；
- 核心假设被验证率；
- Structural误判为Temporary的比例；
- Evidence遗漏率；
- Opportunity在预定窗口内保持有效的比例。

它不直接校准为上涨概率。

## 6. False Positive分类

- Thesis当时已经破坏但系统遗漏；
- 将Structural误判为Temporary；
- 市场隐含预期理解错误；
- Asset暴露并不真实；
- Evidence质量不足却给高Confidence；
- 估值便宜被误当Mispricing；
- AI叙事过度；
- 数据时点污染；
- 后续不可知事件（不计入研究错误，但计入风险记录）。

## 7. Missed Opportunity

事后表现优秀不自动构成遗漏。只有当历史时点已经存在足够公开Evidence，并且满足当时定义的研究条件，却未进入研究队列时，才记为Missed Opportunity。

## 8. 实验隔离

- Development：设计和调试规则；
- Validation：校准Confidence和阈值；
- Holdout：最终评估，不反复调参；
- Forward：模型训练截止日期之后的真实运行。

任何规则变更创建新版本，不覆盖旧回测。

## 9. 输出

每次验证生成：

- 数据与代码版本manifest；
- Evidence cutoff；
- 候选漏斗；
- Research Quality指标；
- Process/Outcome分类；
- False Positive和Missed Opportunity案例；
- Confidence校准；
- 不应据此修改的偶然结果；
- 下一版改进假设。

## 10. 验收场景

1. 隐藏未来公告后系统仍能重建当时判断。
2. 不可知爆雷不会被反向编造成技术面错误。
3. 运气盈利不会进入高质量成功库。
4. Holdout表现不佳时不得继续用Development结果宣传。
5. 规则版本变化后旧报告仍可重放。
6. AI模型更换时明确区分原始历史输出与现代模型重跑。

