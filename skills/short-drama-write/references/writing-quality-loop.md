# 写作质量闭环

本文件用于新写、续写或大修单集。目标不是把剧本写成统一模板，而是让每次生成都拿到同样清楚的当前合同、近期差异约束和可定位的返修反馈。

## 1. 先编译写前包

在写剧本前，把当前分集记录和最多三份紧邻的已接受剧本编译为临时写前包：

```bash
python3 <skill-dir>/scripts/writer_quality.py \
  --project <project-root> --episode-map 项目开发/episode-map.jsonl --episode EP003 \
  --recent 剧集/EP001/screenplay.md --recent 剧集/EP002/screenplay.md \
  build-brief --output <project-root>/.short-drama/work/writer-briefs/EP003.md
```

`writer-brief.md` 是 `.short-drama/` 下的私有派生工作文件，不是新的剧情权威，也不能发布、接受或作为下游 artifact 引用。它只提取当前集不可改写的合同、因果链、义务操作、近期动作差异和人物对白样本。不要把它作为理由改写上游目标、反制、兑现或交接。

没有上游地图的 `write_standalone` 项目同样使用已接受单集卡：把上面的 `--episode-map ... --episode EP003` 换成 `--episode-card 剧集/EP003/episode-card.json`。建立多集地图后再切回地图输入。没有近期剧本时正常生成首集，不补造“差异要求”。

## 2. 成稿后检查落点

剧本与索引生成后执行：

```bash
python3 <skill-dir>/scripts/writer_quality.py \
  --project <project-root> --episode-map 项目开发/episode-map.jsonl --episode EP003 \
  --recent 剧集/EP001/screenplay.md --recent 剧集/EP002/screenplay.md \
  check --screenplay 剧集/EP003/screenplay.md \
  --output <project-root>/.short-drama/reports/writer-quality/EP003.json
```

检查器报告 `warning` 不阻断发布；它只检查可机械近似的风险：

- `WRQ_CONTRACT_NO_CARRIER`：合同的选择、反制、状态变化、兑现或出去压力在正文没有可识别载体；
- `WRQ_HOOK_NO_CARRIER`：已声明推进/兑现的连载义务没有载体或行动后果；
- `WRQ_RECENT_ACTION_REPEAT`：与提供的近期剧本重复多个动作短语；
- `WRQ_EMOTION_ONLY_DELIVERY`：对白提示只写情绪，演员没有策略。

近期剧本必须位于项目内、早于当前集、按集号递增且已由 `short-drama-write` 接受；最多三集。检查报告保持为 `status: pass`，其中 `findings` 是待审查的 craft 风险而非自动否决。它不判断故事是否动人、对白是否自然、重复是否为创作者有意选择，也不用关键词替代审查。审查者仍必须从剧本证据判断因果、场景、人物声音与模板感。

## 3. 定向返修

按检查结果只改受影响的场景或对白：保留单集合同、已实现的事实与不相关块。返修顺序是合同落点、义务落点、重复动作、对白策略。不要因为一个 warning 把整集重写成另一条故事。

返修后重建 `screenplay-index.jsonl`，再运行一次检查，并将该次报告放入审阅包：

```bash
python3 <core-skill-dir>/scripts/project_tool.py review-bundle <project-root> \
  --episode EP003 \
  --mechanical-report .short-drama/reports/writer-quality/EP003.json
```

随后按常规流程交给 `$short-drama-review`。当重复是已接受的仪式、喜剧、创伤或格式选择时，在审查请求中声明其新增意义或代价，而不是机械替换。
