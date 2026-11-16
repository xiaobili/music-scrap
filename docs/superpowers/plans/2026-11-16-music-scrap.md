# music-scrap 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 subagent-driven-development（推荐）或 executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 实现一个常驻 NAS/服务器的 Web 工具，完成整轨/分轨音乐文件的元数据刮削、封面设置、差异预览、写入与回滚。

**架构：** 单体 FastAPI + SQLite（WAL）+ 进程内 asyncio 任务执行器；Provider 适配层统一多源检索；mutagen 负责标签与内嵌封面读写；Vue 3 + Tailwind + Headless UI 构建 SPA，由 FastAPI 同源托管。

**技术栈：** Python 3.12+、FastAPI、SQLAlchemy 2、Alembic、mutagen、httpx、Pillow、pytest；Vue 3 + Vite + TypeScript、TailwindCSS、Headless UI、Heroicons、Pinia、Vue Router。

**规格：** `docs/superpowers/specs/2026-11-16-music-scrap-design.md`
**原型：** `prototype/index.html`

## 全局约束

- 单用户、同源部署，不实现登录与 CSRF；所有接口前缀 `/api`。
- 错误体固定 `{code, message, details, trace_id}`。
- 并发上限：扫描 1、远程检索 3、写入 1（`asyncio.Semaphore`）。
- 标签写入默认**原地写入 + 强制快照**；安全模式默认关闭。
- 字段写入默认策略 `fill_only`（仅补空），可切 `overwrite` / `all`。
- 扫描仅手动触发；`.cue` 只用于整轨识别与曲目展示，不分割、不写回。
- 前端不得引入 Element Plus；样式使用 Tailwind + Headless UI + Heroicons。
- 所有文件访问必须经 `core.paths.resolve_inside_roots()` 校验，禁止软链越界。
- 数据源：MusicBrainz + Cover Art Archive、AcoustID、Discogs、Spotify、网易云/QQ（默认关闭）。
- 宿主 Python 3.15、Node 26 可用；`ffmpeg` 与 `fpcalc` 已安装。
- 执行期间不自动 `git commit`（工作区规则），除非用户明确要求。

## 审查重点（Review Focus）

1. **整轨误判**：目录含 `.cue` 但只有一个短音频，或单文件时长恰好 15 分钟 —— 必须按 `.cue` 优先判定为 `whole`。
2. **写中断**：写入第 N 个文件时异常 —— 已写文件可回滚，未写文件保持原样，计划状态与备份记录一致。
3. **路径越界**：请求或目录软链指向库根之外 —— 必须拒绝且不产生任何读写。
4. **Provider 不可用**：缺凭据、超时、429 —— 任务整体不失败，其他来源结果仍可匹配，并标记来源不完整。
5. **特殊字符**：中文、日文、emoji、多值艺术家 —— 读写与回读校验不得损坏文件，封面仍可嵌入。

---

## 文件结构

```
backend/
  pyproject.toml
  alembic.ini
  alembic/env.py
  alembic/versions/0001_initial.py
  app/
    main.py                 # FastAPI 装配、生命周期、静态托管
    core/config.py          # pydantic-settings
    core/paths.py           # 根目录解析与越界校验
    core/security.py        # Fernet 加密、掩码
    core/logging.py         # JSON 日志 + trace_id
    db/base.py              # DeclarativeBase
    db/models.py            # 全部表
    db/session.py           # engine/session factory/WAL
    api/deps.py             # session、runner、错误处理
    api/health.py roots.py jobs.py albums.py plans.py covers.py backups.py settings.py audit.py
    schemas.py              # 请求/响应 Pydantic 模型
    tagio/mapping.py        # 统一字段 ↔ 各格式原生字段
    tagio/service.py        # read/write/snapshot/restore 分派
    providers/base.py registry.py musicbrainz.py acoustid.py discogs.py spotify.py netease.py
    services/scan.py match.py plan.py write.py backup.py cover.py settings.py
    jobs/runner.py events.py
    static/                 # 构建后的前端（Docker 阶段拷贝）
  tests/
    conftest.py test_paths.py test_security.py test_tagio.py test_scan.py
    test_scoring.py test_plan.py test_write_rollback.py test_api_smoke.py
frontend/
  package.json vite.config.ts tailwind.config.js postcss.config.js index.html
  src/main.ts App.vue router.ts style.css
  src/api/client.ts types.ts
  src/stores/{roots,albums,jobs,plans,settings}.ts
  src/components/{AppShell,StatusStamp,ConfidenceMeter,CoverArt,AlbumCard,CandidateTable,DiffTable,CoverPicker,JobProgress,ConfirmDialog,ToastHost}.vue
  src/views/{OverviewView,AlbumsView,AlbumDetailView,ReviewView,TasksView,HistoryView,SettingsView}.vue
Dockerfile docker-compose.yml README.md
```

---

### 任务 1：工程骨架与健康检查

**文件：**
- 创建：`backend/pyproject.toml`、`backend/app/main.py`、`backend/app/core/config.py`、`backend/app/core/logging.py`、`backend/app/api/health.py`、`backend/tests/test_api_smoke.py`
- 创建：`frontend/package.json`、`vite.config.ts`、`tailwind.config.js`、`postcss.config.js`、`index.html`、`src/main.ts`、`src/App.vue`、`src/style.css`

- [ ] **步骤 1：编写失败的测试** `backend/tests/test_api_smoke.py::test_health_ok`：用 `TestClient(app)` 请求 `/api/health`，断言 200 且 `{"status":"ok","db":true,"fpcalc":true,"roots_readable":true}`。
- [ ] **步骤 2：运行** `cd backend && pytest tests/test_api_smoke.py::test_health_ok -v`，预期 FAIL（应用不存在）。
- [ ] **步骤 3：实现** `Settings`（`music_roots`、`db_path`、`backup_dir`、`secret_key`、`max_fetch_concurrency=3`、`enable_unofficial_providers=False`、`musicbrainz_user_agent`、`log_level`、`tz`），`create_app()` 挂载 `/api/health`，检查 SQLite 可写、根目录可读、`shutil.which("fpcalc")`。
- [ ] **步骤 4：验证** 测试 PASS；`uvicorn app.main:app` 后 `curl /api/health` 返回同上。
- [ ] **步骤 5：前端脚手架** Vite Vue-TS + Tailwind，`style.css` 定义原型色板（ink `#14150f`、paper `#f3eee4`、copper `#b8622d`、line `#d8cfbe`）与字体（Fraunces / IBM Plex Sans / Mono）。

### 任务 2：数据库模型与会话

**文件：**
- 创建：`backend/app/db/base.py`、`db/models.py`、`db/session.py`、`backend/alembic.ini`、`alembic/env.py`、`alembic/versions/0001_initial.py`
- 测试：`backend/tests/test_db_models.py`

- [ ] **步骤 1：测试** `test_schema_creates_all_tables`：在 `tmp_path` 建库后，断言表名集合包含 `library_roots, albums, tracks, match_candidates, change_plans, change_items, backups, jobs, provider_cache, settings, audit_logs`。
- [ ] **步骤 2：运行** `pytest tests/test_db_models.py -v`，预期 FAIL。
- [ ] **步骤 3：实现** SQLAlchemy 2 类型化模型，字段严格按规格 §5；`albums.file_sig`、`albums.status`（`unmatched/pending/matched`）、`jobs.status`（`queued/running/succeeded/failed/cancelled`）、`change_plans.status`（`draft/approved/applied/reverted`）；建索引；`create_engine(..., connect_args={"check_same_thread": False})` 并执行 `PRAGMA journal_mode=WAL`。
- [ ] **步骤 4：验证** 测试 PASS；`alembic upgrade head` 在空库成功。
- [ ] **步骤 5：迁移** 初始迁移覆盖全部表与索引；`alembic downgrade base` 可回退。

### 任务 3：路径安全与凭据加密

**文件：**
- 创建：`backend/app/core/paths.py`、`backend/app/core/security.py`
- 测试：`backend/tests/test_paths.py`、`test_security.py`

- [ ] **步骤 1：测试** `test_reject_path_traversal`：根为 `tmp_path/library`，传入 `../etc/passwd` 抛 `PathViolation`；`test_reject_symlink_escape`：库内软链指向外部目录同样拒绝；`test_secret_roundtrip_and_mask`：`encrypt("abc")` 后 `decrypt` 还原，`mask("sk_123456789") == "sk_••••6789"`。
- [ ] **步骤 2：运行** 预期 FAIL。
- [ ] **步骤 3：实现** `resolve_inside_roots(path, roots) -> Path` 用 `Path.resolve(strict=True)` 后做 `os.path.commonpath` 校验；`encrypt/decrypt` 用 Fernet（`SECRET_KEY` 经 SHA-256 派生 32 字节 urlsafe key）。
- [ ] **步骤 4：验证** 两个测试文件 PASS。

### 任务 4：标签读写、封面嵌入与快照恢复

**文件：**
- 创建：`backend/app/tagio/mapping.py`、`tagio/service.py`
- 创建：`backend/tests/conftest.py`（用 ffmpeg 生成 2 秒 FLAC/MP3/M4A/WAV 夹具）、`test_tagio.py`

- [ ] **步骤 1：测试**
  - `test_flac_roundtrip_chinese`：写入 `{"ALBUMARTIST":"甜梅号","TITLE":"城市天气","DATE":"2010"}`，回读相等。
  - `test_mp3_roundtrip_multivalue`：`ARTIST=["A","B"]` 写入后回读包含两项。
  - `test_cover_embed_flac`：写 600×600 JPEG 后 `FLAC(path).pictures` 长度为 1 且 mime 为 `image/jpeg`。
  - `test_snapshot_restore`：改标签后 `restore(snapshot)`，回读等于快照前。
  - `test_unsupported_format_raises`：`.txt` 抛 `UnsupportedFormat`。
- [ ] **步骤 2：运行** 预期 FAIL。
- [ ] **步骤 3：实现** `read(path) -> dict[str, list[str]]`、`write(path, fields, cover=None)`、`snapshot(path) -> FileSnapshot`、`restore(path, snapshot)`；按扩展名分派。映射见规格 §6.6：FLAC Vorbis Comment；MP3/ID3v2.4（TXXX 承载 CATALOGNUMBER/BARCODE/MBID）；M4A `©nam/©ART/aART/©alb/©day/trkn/disk/©gen/covr`；APE APEv2；WAV 走 ID3 chunk。写入前保留文件 mtime 语义（不改音频流）。
- [ ] **步骤 4：验证** 全部 `test_tagio.py` PASS；手工 `ffprobe` 确认音频流时长未变。

### 任务 5：扫描、解析与专辑分组

**文件：**
- 创建：`backend/app/services/scan.py`
- 测试：`backend/tests/test_scan.py`

- [ ] **步骤 1：测试**
  - `test_parse_artist_album_year`：`甜梅号/城市天气 (2010)` → `("甜梅号","城市天气",2010)`。
  - `test_whole_when_cue_present`：目录含 `album.cue` + 1 个 3 分钟 FLAC → `kind="whole"`。
  - `test_single_file_over_15min_is_whole`：无 CUE、单文件 16 分钟 → `whole`。
  - `test_split_for_multiple_tracks`：3 个 FLAC → `split`，`track_count=3`。
  - `test_incremental_scan_skips_unchanged`：二次扫描 `scanned_files == 0`。
  - `test_scan_ignores_non_audio`：`.jpg/.cue/.nfo` 不计入音频。
- [ ] **步骤 2：运行** 预期 FAIL。
- [ ] **步骤 3：实现** `scan_root(session, root, progress) -> ScanResult`：`os.scandir` 流式遍历；扩展名集合 `.flac .mp3 .m4a .mp4 .ape .wav .ogg`；同父目录聚合；读取基本标签与时长（mutagen）；`.cue` 优先整轨；`file_sig = sha256("\n".join(sorted(f"{rel}|{size}|{mtime_ns}")))`；按 `rel_path` 幂等 upsert，删除已消失的专辑/曲目。
- [ ] **步骤 4：验证** `test_scan.py` 全 PASS。

### 任务 6：Provider 基座（限流、缓存、统一模型）

**文件：**
- 创建：`backend/app/providers/base.py`、`providers/registry.py`
- 测试：`backend/tests/test_provider_base.py`

- [ ] **步骤 1：测试**
  - `test_token_bucket_spacing`：rate=10/s，连续 3 次 `acquire` 总耗时 ≥ 0.2s。
  - `test_cache_hit_avoids_loader`：同一 key 调用两次，loader 只执行一次。
  - `test_provider_timeout_does_not_raise`：查询单个 Provider 超时返回 `[]` 并记录 `degraded=True`。
- [ ] **步骤 2：运行** 预期 FAIL。
- [ ] **步骤 3：实现** `CanonicalRelease`、`CanonicalTrack`、`CoverCandidate`、`ReleaseQuery`；`Provider` 抽象基类（`name`、`capabilities`、`search_release`、`get_release`、`get_covers`、`is_enabled`）；`TokenBucket`；`cached(db, provider, key, ttl, loader)` 读写 `provider_cache`；`ProviderError` 与熔断计数。
- [ ] **步骤 4：验证** 测试 PASS。

### 任务 7：五个数据源适配器

**文件：**
- 创建：`backend/app/providers/musicbrainz.py`、`acoustid.py`、`discogs.py`、`spotify.py`、`netease.py`
- 测试：`backend/tests/test_providers.py`（`respx` 固定响应）

- [ ] **步骤 1：测试**
  - `test_musicbrainz_parses_release`：固定 JSON → `CanonicalRelease(title, artist, year, tracks, release_mbid)`。
  - `test_musicbrainz_sends_user_agent`：断言请求头含 `music-scrap/`。
  - `test_acoustid_without_key_is_disabled`：`is_enabled() is False`。
  - `test_discogs_without_token_is_disabled`。
  - `test_spotify_token_refresh_and_429`：首次取 token，429 后按 `Retry-After` 重试一次。
  - `test_netease_disabled_by_default`：`ENABLE_UNOFFICIAL_PROVIDERS=false` 时 `is_enabled() is False`。
- [ ] **步骤 2：运行** 预期 FAIL。
- [ ] **步骤 3：实现**
  - MB：`/ws/2/release?query=&fmt=json&limit=10`，`inc=recordings+artist-credits+labels+release-groups`，1 req/s，UA 必带。
  - CAA：`/release/{mbid}` 取 `images[].image/thumbnails.large`，过滤 `front` 优先。
  - AcoustID：`pyacoustid` + `fpcalc`，3 req/s，仅分轨调用，投票命中数写入 `raw_score`。
  - Discogs：`/database/search?type=release` + `/releases/{id}`，60 req/min。
  - Spotify：Client Credentials，`/v1/search?type=album` + `/v1/albums/{id}/tracks`，429 退避。
  - NetEase：默认关闭，启用时调用 `https://music.163.com/api/search/get`，0.5 req/s；失败仅降级。
- [ ] **步骤 4：验证** 测试 PASS；真实环境下 `curl` 触发一次 MB 搜索成功（限流 1 req/s）。

### 任务 8：匹配与打分

**文件：**
- 创建：`backend/app/services/match.py`
- 测试：`backend/tests/test_scoring.py`

- [ ] **步骤 1：测试**
  - `test_score_exact_match_above_085`：标题/艺术家/曲目数/时长全一致 → `score ≥ 0.85`。
  - `test_score_weights_sum_to_one`：返回的分项权重和为 1.0。
  - `test_sidecar_duration_penalty`：时长差 120s → `duration` 分项 < 0.5。
  - `test_threshold_buckets`：0.9→`matched`，0.7→`pending`，0.4→`unmatched`。
  - `test_dedupe_prefers_musicbrainz`：同 MBID 多源结果只保留 MB。
- [ ] **步骤 2：运行** 预期 FAIL。
- [ ] **步骤 3：实现** `score_release(release, album, tracks) -> (score, parts)` 按规格 §6.2 权重；`RapidFuzz.token_set_ratio`，中文回退 `fuzz.ratio`；`match_album(session, album_id) -> list[MatchCandidate]` 并发调用已启用 Provider，写 `match_candidates` 并更新专辑 `status/confidence`。
- [ ] **步骤 4：验证** 测试 PASS；离线 mock 下 `match_album` 产生 ≥ 1 个候选。

### 任务 9：任务系统与 SSE

**文件：**
- 创建：`backend/app/jobs/runner.py`、`jobs/events.py`
- 测试：`backend/tests/test_jobs.py`

- [ ] **步骤 1：测试**
  - `test_enqueue_and_run`：入队 `noop` 任务后状态变 `succeeded`。
  - `test_cancel_marks_cancelled`。
  - `test_resume_requeues_running_on_startup`：启动前手工置 `running`，启动后变 `queued/succeeded`。
  - `test_sse_emits_progress`：订阅者收到至少一条 `progress` 事件。
- [ ] **步骤 2：运行** 预期 FAIL。
- [ ] **步骤 3：实现** `EventBus`（每 job 多订阅者 `asyncio.Queue`）；`JobRunner.start()/stop()/enqueue(kind,payload)/cancel(id)`；启动时将 `running` 重置为 `queued`；任务注册表 `scan/match/apply/rollback`；每步骤 `job.progress` 持久化并发布；`asyncio.Semaphore(1/3/1)` 分别约束扫描、检索、写入。
- [ ] **步骤 4：验证** 测试 PASS。

### 任务 10：变更计划

**文件：**
- 创建：`backend/app/services/plan.py`
- 测试：`backend/tests/test_plan.py`

- [ ] **步骤 1：测试**
  - `test_fill_only_skips_non_empty`：旧值存在 → item `selected=False`。
  - `test_overwrite_includes_changes`。
  - `test_whole_album_only_writes_album_fields`：整轨计划中 `target` 只含专辑级字段。
  - `test_split_album_writes_album_and_track_fields`。
  - `test_plan_status_transitions`：`draft → approved → applied`。
- [ ] **步骤 2：运行** 预期 FAIL。
- [ ] **步骤 3：实现** `build_plan(session, album_id, candidate_id, policy) -> ChangePlan`；专辑级字段分发到每个文件，曲目级字段按 `track.position` 对齐；`patch_items(session, plan_id, items)` 支持 `selected/new_value`；`approve_plan`。
- [ ] **步骤 4：验证** 测试 PASS。

### 任务 11：封面处理、写入、备份与回滚

**文件：**
- 创建：`backend/app/services/cover.py`、`services/write.py`、`services/backup.py`
- 测试：`backend/tests/test_write_rollback.py`

- [ ] **步骤 1：测试**
  - `test_apply_writes_tags_and_cover`：临时 FLAC 专辑 → 应用计划 → 回读标签正确、`cover.jpg` 存在、FLAC 内嵌图存在。
  - `test_apply_creates_backup_before_write`：`backups` 行数与文件数一致，快照可反序列化。
  - `test_rollback_restores_tags`：回滚后标签等于原值，新增 `cover.jpg` 被删除。
  - `test_partial_failure_keeps_written_and_marks_plan_failed`：第 2 个文件写入抛错 → 第 1 个已写且可回滚，计划 `status="failed"`。
  - `test_cover_policy_if_missing`：已有 `cover.jpg` 且策略 `if_missing` → 不覆盖。
- [ ] **步骤 2：运行** 预期 FAIL。
- [ ] **步骤 3：实现** `fetch_cover(url) -> bytes`（httpx，Pillow 转 JPEG，边长 ≥ 500 校验）；`apply_plan(session, plan_id, progress)` 串行：快照 → 写标签 → 嵌封面 → 回读校验 → 记 `backups`；`rollback_backup(session, batch_id, progress)` 还原并记录审计；失败明细写入 `audit_logs` 与计划结果。
- [ ] **步骤 4：验证** 测试 PASS。

### 任务 12：REST API

**文件：**
- 创建：`backend/app/api/{deps,roots,jobs,albums,plans,covers,backups,settings,audit}.py`、`backend/app/schemas.py`
- 修改：`backend/app/main.py` 装配路由
- 测试：`backend/tests/test_api_smoke.py` 增补

- [ ] **步骤 1：测试** `test_roots_crud`、`test_scan_creates_albums`、`test_job_sse_stream`、`test_album_detail_and_candidates`、`test_plan_patch_and_apply`、`test_settings_masks_secrets`、`test_path_outside_root_rejected`。
- [ ] **步骤 2：运行** 预期 FAIL。
- [ ] **步骤 3：实现** 所有路由与请求/响应模型，严格对应规格 §8；统一异常处理器输出 `{code,message,details,trace_id}`；SSE `text/event-stream`；封面缩略图 `GET /api/albums/{id}/cover`（存在 `cover.jpg` 则返回，否则 404）。
- [ ] **步骤 4：验证** `pytest tests/test_api_smoke.py -v` 全 PASS；`/docs` 可访问。

### 任务 13：前端骨架与设计系统

**文件：**
- 创建：`frontend/src/router.ts`、`api/client.ts`、`api/types.ts`、`stores/*.ts`
- 创建：`components/AppShell.vue`、`StatusStamp.vue`、`ConfidenceMeter.vue`、`CoverArt.vue`、`ToastHost.vue`、`ConfirmDialog.vue`
- 修改：`App.vue`、`style.css`

- [ ] **步骤 1：验证失败** 运行 `npm run build`，预期因路由/组件缺失失败。
- [ ] **步骤 2：实现** 复用原型视觉：侧栏 + 顶栏 + 内容区；字体与色板写入 Tailwind 配置；`CoverArt.vue` 在无封面时按专辑 id 生成稳定的 SVG 封面（沿用原型构图）；`client.ts` 统一错误解析与 `ToastHost`；Pinia 模块封装 API。
- [ ] **步骤 3：验证** `npm run build` PASS。

### 任务 14：七个业务页面与 SSE

**文件：**
- 创建：`frontend/src/views/{Overview,Albums,AlbumDetail,Review,Tasks,History,Settings}View.vue`
- 创建：`components/{AlbumCard,CandidateTable,DiffTable,CoverPicker,JobProgress}.vue`

- [ ] **步骤 1：实现**
  - 概览：统计、待处理列表、运行任务。
  - 专辑库：状态/类型/根目录筛选、搜索、封面网格、批量条。
  - 详情：标签字段、候选表（得分）、曲目表、封面候选。
  - 变更预览：字段 diff、勾选/编辑、封面、确认写入弹窗。
  - 任务中心：SSE 进度 + 轮询降级、取消。
  - 历史：批次列表、回滚确认。
  - 设置：根目录、字段/封面策略、Provider 开关与掩码凭据。
- [ ] **步骤 2：验证** `npm run build` PASS；`npm run dev` 下逐页检查无控制台错误，移动端 390px 无横向溢出。

### 任务 15：部署与验收

**文件：**
- 创建：`Dockerfile`、`docker-compose.yml`、`README.md`
- 修改：`backend/app/main.py` 静态资源托管

- [ ] **步骤 1：实现** 多阶段构建（node 构建 → python:3.12-slim + `chromaprint-tools` + `ffmpeg`），非 root 运行；compose 挂载媒体只读、`data` 与 `backups` 可写；`MUSIC_ROOTS`/`SECRET_KEY` 等环境变量。
- [ ] **步骤 2：验证** `docker build` 成功；容器启动后 `/api/health` 200；浏览器加载前端。
- [ ] **步骤 3：端到端** 造 1 个整轨 + 1 个分轨目录 → 扫描 → 匹配（真实 MB，限流内）→ 生成计划 → 写入 → 回滚；断言标签与封面恢复。
- [ ] **步骤 4：README** 运行方式、目录挂载、Provider 配置、回滚说明、已知限制（网易云/QQ 默认关闭）。

---

## 覆盖对照

| 规格章节 | 对应任务 |
|---|---|
| §3 需求 FR-1~14 | 5, 7, 8, 9, 10, 11, 12, 14 |
| §4 架构 / 技术栈 | 1, 2, 12, 15 |
| §5 数据模型 | 2 |
| §6.1 扫描分组 | 5 |
| §6.2 匹配打分 | 8 |
| §6.3 变更计划 | 10 |
| §6.4 写入 | 11 |
| §6.5 备份回滚 | 11 |
| §6.6 封面 | 4, 11 |
| §7 Provider | 6, 7 |
| §8 API | 12 |
| §9 前端 | 13, 14 |
| §10 任务系统 | 9 |
| §11 部署 | 15 |
| §12 安全 | 3, 11, 12 |
| §13 性能 | 5, 9 |
| §14 测试 | 各任务测试步骤 |
| §16 决策基线 | 全局约束 |

## 自检结论

- 占位符：无「待定/TODO」；所有任务含可执行测试名与断言。
- 类型一致性：`CanonicalRelease`/`FileSnapshot`/`ChangePlan` 在任务 4/6/10 定义，后续任务只引用。
- 范围：15 个任务均在单一实施计划内，可独立测试。
- 风险覆盖：审查重点 5 条均已分配到任务 5/4/3/6/11 的测试。
