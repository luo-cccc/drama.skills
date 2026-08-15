# Location / View 设计

## 分工

- **Location** 保存空间身份：可行走的地理、分区关系、入口、固定锚点和主要材料。
- **View** 保存可复用的观看方向/生产状态：面向哪个区域、哪些锚点同时可见，以及
  陈设阶段、时段、天气、光态。

Location 不是场景标题字符串，View 也不是每个相机角度。目标是让参考图、分镜和相邻
镜头共享同一空间逻辑，而不是为每镜创建“新场景”。

## 先画脑内平面，再写氛围

读取剧本时先整理：

1. 内/外与可通行边界；
2. 区域之间的相对关系；
3. 人和道具会使用的入口/出口；
4. 不能移动的识别锚点；
5. 主要材料、尺度和功能；
6. 剧本明确的时间、天气与有因果的光源。

“潮湿、压迫、怀旧”可以辅助气氛，却不能替代“北门通走廊、窗口面向河面、配电箱
在柜台后”这样的地理事实。也不能为了画面好看新增一扇后来影响追逐路线的门。

## Location 边界

### 新 Location

当空间具有不同、可独立生产的地理/入口/固定锚点时新建。例如同一渡站建筑里的候船
厅和值班室各自有完整动作和明确连接，适合两个 Location，并记录 `connected_to`。

### 同一 Location

停电前后、白天夜晚、晴雨、临时布置变化都不改变空间身份。若只因镜头转向就新建
地点，会让门窗方向和演员动线互相矛盾。

**`reviewed_invariant` AST-04：** 固定地理与临时时段/天气/灯光不得混成两个
Location identity。

## View 边界

View 值得存在，是因为下游要反复引用一种稳定、能说明空间的方向或状态：

- 从柜台侧朝北门，能同时看到门、河窗和配电箱；
- 停电后的同方向，主灯灭、只剩河窗冷光；
- 暴雨期外景，站牌、台阶和河岸关系保持，天气和地面状态变化。

单纯“低机位”“特写门把手”“35mm”属于 shot/keyframe，不建 View。演员站在左边也
不是地点事实。**`craft_default` AST-03：** 一组镜头能共用方向/状态并需要参考 plate
时才建 View。

## 光、天气和陈设必须有来源

- 剧本写停电，则 View 可从 `normal_night` 变为 `blackout`，cause 指向断电 block；
- 创作者选择蓝调夜景是 visual direction，可记录 creator source；
- 不能因 prompt 惯性擅加霓虹、雾、逆光或移动窗户；
- 临时海报、散落文件、积水若会影响故事/连续性，进入 View state 或 delta；普通可替换
  装饰可留作 set dressing。

## 空间证据状态

完整 Location 的 `coordinate_system` 必须把观察方向编码成数据，而不是只在提示词里口头声明：

```json
{"north":"候船厅方向","origin":"室内西南角地面","front":"观察者位于南侧并朝北观察","left_right":"观察者朝北时，西为左、东为右"}
```

四项都必须是非空字符串。`front` 定义正交板 Front，`left_right` 固定手性，防止左右板互换或镜像。

需要正交板、俯视板或其它会暴露不可见背面的生产板时，spatial model 增加非空对象
`evidence_elements`。对象 key 是稳定、可用 RFC 6901 定位的证据 key；每个 value 必须包含
唯一非空 `element_id`、`confirmed | inferred | unknown` 状态、受控 `prompt_group`
（`shell | opening | fixed_furniture | region`），以及至少一条有效 canonical
`source_refs`。例如：

```json
{"north_door":{"element_id":"north door","status":"confirmed","prompt_group":"opening","source_refs":[{"owner":"short-drama-assets","artifact":"设定集/locations.jsonl","hash":"<sha256>","record_id":"LOC-FERRY-OFFICE","field":"/entrances/0"}]}}
```

`confirmed` 才是可直接复用的空间事实；
`inferred` 是保守补全，`unknown` 是明确缺口，两者都不得混入 `fixed_anchors`、
`entrances` 或 `pairwise_relations` 冒充已确认地理。

图片提示词只能逐项投影这些已接受状态，且必须用 spatial model 自身的
`/evidence_elements/<key>` 引用覆盖全部条目，不能自行判断背面结构属于确认、推定还是未知。

## 合成例：旧渡站值班室

`LOC-FERRY-OFFICE`：狭长室内；北门通候船厅；东侧河窗；西侧整面旧柜台；配电箱
固定在柜台后墙。Location 不写“夜”“暴雨”“顾禾站在门口”。

- `VIEW-FERRY-OFFICE-NORTH-NIGHT`：从柜台内侧朝北门，河窗位于画面右后方；夜间
  顶灯正常，柜台上只有铁皮匣。
- `VIEW-FERRY-OFFICE-NORTH-BLACKOUT`：同一地理和方向；断电后顶灯灭，河窗冷光
  保留，铁皮匣位置不变。它是 View/state 变体，不是“黑暗值班室”新 Location。

如果剧本只需要一次门把手特写，无需 `VIEW-FERRY-OFFICE-DOOR-CLOSEUP`；镜头可以
引用 Location/既有 View 后自行拥有 framing。

## 检查问题

- 不看氛围词，仍能判断入口、固定锚点和区域关系吗？
- 同一空间各 View 的门窗/光向是否保持可调和？
- View 是否错误拥有相机焦段、演员站位或 shot boundary？
- 时段、天气、光态与陈设变化有 source/cause/validity 吗？
- 相邻空间该拆 Location 还是做 View，是否依据地理和制作复用，而非名称习惯？
- creator 是否明确选择空景/含角色政策？该政策由后续 image prompt 具体实现。

空间拆分颗粒度可以是 **`taste_option`**；但无论选粗或细，入口关系和连续性必须可
解释，不能用风格选择掩盖矛盾。
