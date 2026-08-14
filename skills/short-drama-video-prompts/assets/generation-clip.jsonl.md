# `generation-clips.jsonl` 填写模板

生成片段是一次视频模型调用的执行单位，不是新的剪辑镜头。所有片段的 `source_window`
必须连续、无重叠地覆盖所属 accepted shot；单片段时长不得超过
`short-drama.json#/format/generation_limits/max_clip_seconds`。

```json
{
  "clip_id": "GCLIP-<EP>-<SHOT>-01",
  "status": "candidate",
  "shot_ref": {
    "owner": "short-drama-storyboard",
    "artifact": "剧集/<EP>/storyboard/shots.jsonl",
    "hash": "<sha256>",
    "record_id": "SHOT-<id>"
  },
  "motion_ref": {
    "owner": "short-drama-video-prompts",
    "artifact": "剧集/<EP>/storyboard/motion-specs.jsonl",
    "hash": "<sha256>",
    "record_id": "MOTION-<id>"
  },
  "order": 1,
  "source_window": {
    "start_seconds": 0.0,
    "end_seconds": 12.0
  },
  "duration_seconds": 12.0,
  "execution_mode": "independent | continuation",
  "start_source": "shot_start | previous_clip_end",
  "handoff": null,
  "prompt_delta": "<只写本片段相对完整 motion spec 的时间窗口、阶段职责与终点>",
  "output_observation_ref": null
}
```

第二片段及以后必须填写：

```json
{
  "start_source": "previous_clip_end",
  "handoff": {
    "from_clip_id": "GCLIP-<EP>-<SHOT>-01",
    "planned_boundary": {
      "pose": "<片段交接姿态>",
      "position": "<片段交接位置>",
      "gaze": "<片段交接视线>",
      "hands_and_props": "<双手与持物>",
      "visible_state": "<可见状态>"
    },
    "observation_ref": null
  }
}
```

规划阶段的 `independent` 片段允许 `observation_ref` 为 `null`。一旦填写
`execution_mode: continuation`，上一片段的 `output_observation_ref` 与本片段
`handoff.observation_ref` 必须是同一条完整授权观察引用，否则 VID-22 阻断。观察结果不能反向
改写 accepted shot 的起止边界。`independent` 表示每段从已接受或规划边界独立生成，
`continuation` 还要求项目配置明确支持。
