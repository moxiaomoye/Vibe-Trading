# Daily Intelligence 与 Opportunity Alert V2

版本：V2.3

## 1. 两个产品，不是两种格式

`Daily Research Report`解决“每天研究上发生了什么”；`Opportunity Alert`解决“是否出现罕见、高质量、需要立即投入研究时间的机会”。

日报追求稳定和完整，Alert追求稀缺与高Precision。

## 2. 运行规则

- A股交易日18:30 Asia/Shanghai运行；
- 数据截止时间必须显示；
- 非交易日不重复发送；
- 失败后重试，但同一交易日同一版本幂等；
- 报告生成成功与渠道投递成功分别记录；
- 飞书与邮箱各自重试。

## 3. 日报结构

```text
AI Investment Research Daily
Trade Date / Generated At / Data Cutoff

Market State
- Current Regime
- Change vs Previous Day
- Main Drivers
- Data Gaps

Thesis Updates
- Strengthened
- Weakened
- New Counter Evidence
- Reviews Due

Opportunity Changes
- New / Strengthening / Weakening / Closed

Research Candidates
- Why Now
- Action Level
- Confidence Band
- First Rejection
- Next Review

Action Candidates
- Eligible Alert / Report Only

Today Conclusion
- New high-quality opportunity / No new opportunity
- Continue waiting
- Continue the user's pre-existing long-term plan if configured
```

## 4. 空机会原则

零候选是完整、成功的研究结果。日报必须敢于输出：

> 今天没有发现新的高赔率机会。继续等待，继续观察。若已设定独立长期定投计划，继续执行既定计划。

不得用低等级Watch填充“今日机会”。

## 5. Opportunity Alert

内容：

```text
Opportunity Alert
Asset
Related Thesis
Mispricing Opportunity
Why Now
Why the Market Is Selling
Temporary / Structural / Uncertain
Action Level: Action Candidate
Confidence Band + Internal Value
Supporting Evidence
Counter Evidence
Main Risk / Kill Criteria
Evidence Cutoff
Next Review
Not a buy recommendation
```

Alert只引用已保存的Assessment和EvidenceSet，不在通知阶段重新调用AI。

## 6. 变化优先

日报重点展示“相对昨日发生了什么变化”，而不是每天复制完整研究报告。候选详情通过稳定ID链接到研究页。

变化类型：新增、升级、降级、Evidence更新、Thesis变化、Review到期、Opportunity关闭。

## 7. 投递可靠性

每个渠道维护：pending / delivered / retrying / failed / dead-letter。一个渠道成功不影响另一个渠道重试。

去重键包含：内容类型、交易日、Candidate/Assessment版本和渠道。

## 8. 验收场景

1. 没有候选仍生成完整日报。
2. 同日重跑不重复通知。
3. 飞书成功、邮箱失败时仅重试邮箱。
4. AI候选变化后生成新版本，而不是覆盖旧日报。
5. 非交易日不发送重复日报。
6. 数据缺失时显示缺口，不伪造Market State变化。
7. Alert内容与研究页使用同一个EvidenceSet。

