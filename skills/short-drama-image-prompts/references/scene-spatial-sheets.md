# 场景正交板与俯视板

## 目录

- [共同边界](#共同边界)
- [`scene_orthographic`](#scene_orthographic)
- [`scene_top_view`](#scene_top_view)
- [证据图例](#证据图例)
- [提示词顺序](#提示词顺序)
- [审查](#审查)

这两个 `sheet_profile` 是 Location 资产的可选生产板式，仍使用
`prompt_components.profile: asset_board`。它们不创建空间事实，也不把一张合成板升级为新的
Location、View 或镜头权威。

## 共同边界

启用前必须具备：

1. 一个已接受的 `LOC-*` 与 spatial model；
2. spatial model 中已接受的坐标系；`coordinate_system` 必须以非空字符串明确 `north`、
   `origin`、`front`、`left_right`，以及非空 `evidence_elements`；
3. 与本板匹配的 canonical `view_projection` fragment；其 `scope.sheet_profile` 为当前板式，
   `model_refs` 只绑定该 spatial model，不创建或冒充镜头 View；
4. 已接受的时间、天气、陈设与光态；
5. 参考图参与时，每张图有独立 `role / may_control / must_not_control` 与观察证据。

只有单张透视参考而空间背面未知时，板式可以表达保守补全，但不得把推定写回 Location。
生产级闭环依赖的墙体、门窗、楼梯或固定家具仍未知时，保持 `unresolved` 或请求补充参考。

两种板式都必须：

- 绑定一个 Location 资产，不混入第二个房间；
- 使用自身固定的 `board_aspect_ratio: 16:9`；它是资产规划板画幅，不继承项目成片 `format.aspect_ratio`；
- 保持 accepted layout、入口、固定锚点、材料、尺度、光源和当前 state；
- 使用同一坐标基准、统一比例和稳定方向标签；
- 默认空场；人物、剧情动作和临时拍摄器材不进入稳定场景板；
- 让材料和光线帮助读取结构，不用景深、辉光或重滤镜遮挡地理；
- 将文字视为排版要求，不声称生成模型能可靠绘制标签。

## `scene_orthographic`

用于 Front、Left、Right、Back 四方向场景正交板。结构字段固定为：

```json
{
  "name": "scene_orthographic",
  "projection": "orthographic",
  "panels": ["front", "left", "right", "back"],
  "layout": "horizontal_4_panel",
  "board_aspect_ratio": "16:9",
  "safe_margin": true,
  "shared_scale": true,
  "orientation_basis_ref": {
    "owner": "short-drama-assets",
    "artifact": "设定集/generation/spatial-models.jsonl",
    "hash": "<sha256>",
    "record_id": "SPATIAL-LOC-<id>",
    "field": "/coordinate_system"
  },
  "cutaway_policy": "hide_obstructing_wall_only",
  "evidence_display": {
    "confirmed": "solid",
    "inferred": "dashed_or_translucent",
    "unknown": "dash_dot_labeled"
  },
  "evidence_bindings": [
    {"element_id": "<must equal spatial evidence element_id>", "status": "confirmed | inferred | unknown", "prompt_group": "shell | opening | fixed_furniture | region", "source_ref": {"owner": "short-drama-assets", "artifact": "设定集/generation/spatial-models.jsonl", "hash": "<same spatial model hash>", "record_id": "SPATIAL-LOC-<id>", "field": "/evidence_elements/<RFC-6901-escaped-key>"}}
  ],
  "annotation_treatment": {"mode": "postproduction", "generated_text": "none", "unknown_label": "needs_confirmation"}
}
```

板式义务：

- 四面只改变观察方向，不改变房间、陈设、材料、时间或光态；
- 平行线保持平行，不使用消失点、广角拉伸、三分之四透视、俯拍或仰拍；
- 四格使用统一地面基线、层高基线和投影尺度；
- Front/Back 保持相同空间宽度，Left/Right 保持相同空间进深；
- 每格只隐藏当前方向最前方、确实阻挡内部的墙体；门窗和入口关系以轮廓保留；
- Left/Right 不得互相镜像；不对称墙体、门窗、家具和固定装饰保持真实归属；
- 隐藏区域只延续已接受轴线、材料和功能，低信息补全优先于新增设计。

该 profile 不接受 camera 或 blocking overlay。摄影机机位、演员走位和视野锥不属于正交资产板。

## `scene_top_view`

用于严格 90 度垂直向下的场景俯视板。结构字段固定为：

```json
{
  "name": "scene_top_view",
  "projection": "orthographic_top_down_90",
  "panels": ["top"],
  "layout": "single_top_panel",
  "board_aspect_ratio": "16:9",
  "safe_margin": true,
  "shared_scale": true,
  "orientation_basis_ref": {
    "owner": "short-drama-assets",
    "artifact": "设定集/generation/spatial-models.jsonl",
    "hash": "<sha256>",
    "record_id": "SPATIAL-LOC-<id>",
    "field": "/coordinate_system"
  },
  "roof_policy": "remove_roof_and_ceiling",
  "evidence_display": {
    "confirmed": "solid",
    "inferred": "dashed_or_translucent",
    "unknown": "dash_dot_labeled"
  },
  "evidence_bindings": [
    {"element_id": "<must equal spatial evidence element_id>", "status": "confirmed | inferred | unknown", "prompt_group": "shell | opening | fixed_furniture | region", "source_ref": {"owner": "short-drama-assets", "artifact": "设定集/generation/spatial-models.jsonl", "hash": "<same spatial model hash>", "record_id": "SPATIAL-LOC-<id>", "field": "/evidence_elements/<RFC-6901-escaped-key>"}}
  ],
  "annotation_treatment": {"mode": "postproduction", "generated_text": "none", "unknown_label": "needs_confirmation"}
}
```

板式义务：

- 摄影机光轴垂直于地面，禁止鸟瞰透视、斜俯视、消失点与近大远小；
- 移除屋顶和天花，墙体以统一开顶切面表达；
- 显示房间边界、连接、门窗开启关系、楼梯、高差、家具顶视轮廓和实际功能区；
- 使用 accepted dimensions 或相对尺度，不虚构工程尺寸；
- 入口、主要通道和 movement paths 来自 spatial model，不为构图移动家具；
- 只生成地理底板，不自行规划或叠加摄影机、视野锥、镜头编号与演员路线。

摄影机、coverage 和演员走位属于 M4b storyboard。需要空间调度图时，由 storyboard 消费已接受的
俯视地理底板并在自身产物中增加 overlay；不得回写或重新发布 M4a 图片提示词来形成反向依赖。

## 证据图例

`evidence_display` 使用固定机器值；`evidence_bindings` 必须与绑定 spatial model 的
`evidence_elements` 一一对应。每项还继承一个受控 `prompt_group`，只允许
`shell | opening | fixed_furniture | region`。每项 `source_ref` 指向同一 artifact、hash、record，并用
`/evidence_elements/<key>` 精确定位；提示词侧 `element_id` 和 `status` 必须等于该条空间证据，
且全部 key 恰好覆盖一次，不能遗漏、添加或自行改判：

| 状态 | 机器值 | 呈现义务 |
|---|---|---|
| 已确认 | `solid` | 实线或正常不透明度 |
| 保守推定 | `dashed_or_translucent` | 短虚线或低饱和半透明 |
| 未知 | `dash_dot_labeled` | 点划线并明确待确认 |

至少一项必须为 `confirmed`。没有推定或未知内容时不制造虚线区域。未知元素只在生成画面中
预留点划线和引线；`needs_confirmation` 标签由后期排版添加，生成模型不得绘制可读注释文字。
图例和注释都不改变上游记录状态。

编译后的可执行正文按 `status + prompt_group` 汇总为有限类别与精确绑定数量，不平铺所有
`element_id`。逐元素 ID、状态、来源和完整覆盖仍保留在结构化元数据中，审计强度不降低。

## 提示词顺序

在通用 asset-board 编译顺序内，将本板专属内容放入 `task_and_format` 与
`prompt_components.local_instructions`：

1. 从 `layout / board_aspect_ratio / safe_margin` 写明固定板式、面板顺序和统一尺度；
2. 引用 accepted orientation basis 与固定地理；
3. 写投影、切墙或开顶规则；
4. 写跨面板必须保持的结构、材料、光源和 state；
5. 按 `evidence_bindings` 写具体元素的线型/透明度，并声明标签只在后期添加；
6. 排除透视漂移、镜像、家具移动、无来源补建、人物、摄影机/走位 overlay 和文字污染。

不要在 `generic_prompt` 中放 artifact 路径、hash、`confirmed/inferred` 内部状态名或审查话术；
把它们转换成画面可执行的线型、透明度、标签和保持项。

## 审查

### 正交板

- 四格是否来自同一 spatial model，并按 canonical order 排列；
- 平行线、尺度、基线、层高、门窗和家具是否跨格闭合；
- 切墙是否只移除当前阻挡面，是否意外删除入口关系；
- Left/Right 是否被镜像或重新装修；
- 推定与未知结构是否按图例区分。

### 俯视板

- 是否为严格 90 度正交顶视，而非高位三分之四透视；
- 墙体、门窗、通道、家具和功能区是否与 Location 一致；
- 是否无来源新增房间、走廊、秘密入口或精确尺寸；
- 是否误加摄影机、视野锥、镜头编号或演员走位；
- 后期标签预留和图例是否遮挡必须读取的空间关系。

审查发现地理或元素证据矛盾时退回 assets；coverage 或 blocking 问题只在 storyboard 处理；
只在板式、投影、后期注释预留或提示词表达错误时由 image-prompts 修订。
