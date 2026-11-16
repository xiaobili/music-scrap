# music-scrap

常驻 NAS / 服务器的音乐元数据刮削工具：扫描整轨与分轨音乐文件，聚合 MusicBrainz、Cover Art Archive、AcoustID、Discogs、Spotify（以及默认关闭的网易云/QQ）候选，生成字段级差异预览，确认后写入标签与封面，全程可回滚。

- 前端：Vue 3 + Vite + TypeScript + TailwindCSS + Headless UI + Heroicons
- 后端：FastAPI + SQLAlchemy + SQLite（WAL）+ mutagen + Pillow
- 部署：单容器，FastAPI 同源托管前端静态资源

## 功能

- 扫描库根目录，识别 `whole`（整轨）与 `split`（分轨），支持增量扫描
- 多源并行检索与加权置信度打分（标题 / 艺术家 / 曲目数 / 时长 / 年份）
- 字段级变更计划：勾选、行内编辑，默认仅补空字段
- 写入前强制快照；写后回读校验；按批次回滚标签与内嵌封面
- 封面：多候选预览、选定后转 JPEG、内嵌 FLAC/MP3/M4A/WAV，并写 `cover.jpg`
- 任务队列 + SSE 进度，支持取消与重启续跑
- 路径越界与软链逃逸防护，Provider 凭据 Fernet 加密存储

## 本地开发

要求：Python 3.12+、Node 20+、`ffmpeg`、`fpcalc`（chromaprint）。

```bash
# 后端
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env        # 修改 MUSIC_ROOTS / SECRET_KEY
uvicorn app.main:app --reload --port 8000

# 前端（另一个终端）
cd frontend
npm install
npm run dev                 # http://localhost:5173，/api 代理到 8000
```

生产预览（FastAPI 托管构建产物）：

```bash
cd frontend && npm run build
cd ../backend && uvicorn app.main:app --port 8000
# 打开 http://127.0.0.1:8000
```

## Docker

```bash
cp .env.example .env        # 或手动创建
cat > .env <<'EOF'
SECRET_KEY=replace-with-a-long-random-string
MUSIC_DIR=/volume1/music
TZ=Asia/Shanghai
EOF

mkdir -p data backups
docker compose up -d --build
```

访问 `http://<nas>:8080`。媒体目录需要**可写**（写入标签），`data/` 与 `backups/` 需要容器用户（默认 uid 1000）可写：

```bash
sudo chown -R 1000:1000 data backups
```

## 使用流程

1. 设置 → 添加媒体库根目录（路径必须已存在）
2. 点击「扫描曲库」，等待任务完成
3. 专辑库 → 选择专辑 → 查看候选；必要时手动关键词重搜
4. 选择候选 → 变更预览 → 勾选/编辑字段 → 确认写入
5. 历史与回滚 → 需要时还原批次（标签与内嵌封面）

## 数据源配置

| 数据源 | 说明 |
|---|---|
| MusicBrainz + Cover Art Archive | 无需凭据；按 1 req/s 限流，User-Agent 需可联系 |
| AcoustID | 设置 API Key 后启用；仅分轨做逐轨指纹投票 |
| Discogs | 设置 Personal Access Token；60 req/min |
| Spotify | 设置 Client ID / Secret（Client Credentials） |
| 网易云音乐 | 非官方接口，默认关闭；需 `ENABLE_UNOFFICIAL_PROVIDERS=true`，Cookie 可选 |
| QQ 音乐 | 非官方接口，默认关闭；需 `ENABLE_UNOFFICIAL_PROVIDERS=true`，Cookie 可选 |

凭据通过设置页写入，使用 `SECRET_KEY` 派生的 Fernet 密钥加密，API 只返回掩码。

## 安全与回滚

- 所有文件访问都校验在库根目录内，拒绝软链越界
- 写入默认「原地写入 + 强制快照」；可在设置中开启安全模式（复制后写）
- 每次写入按 `plan-<id>` 批次记录备份，回滚可还原标签与内嵌图片，并恢复/删除 `cover.jpg`
- 单文件失败不阻塞整批，计划会标记为 `failed`，应检查后再决定是否回滚

## 测试

```bash
cd backend
pytest -q                   # 43 个测试：解析、标签、扫描、打分、计划、写入/回滚、API
```

测试使用 `ffmpeg` 生成临时音频夹具，不依赖外部网络。

## API

FastAPI 自动文档：`/docs`。主要路由前缀 `/api`：

- `GET /health`、`GET /stats`
- `GET/POST /roots`、`POST /roots/{id}/scan`
- `GET /albums`、`GET /albums/{id}`、`GET /albums/{id}/candidates`
- `POST /albums/{id}/select`、`/albums/{id}/search`、`/albums/{id}/cover`
- `GET/PATCH /plans/{id}`、`POST /plans/{id}/apply`
- `GET /backups`、`POST /backups/{batch}/restore`
- `GET/PUT /settings`、`GET /audit-logs`
- `GET /jobs`、`GET /jobs/{id}/events`（SSE）

## 已知限制

- `.cue` 只用于整轨识别与展示，不分割、不写回
- 不做文件重命名/目录重组
- 不提供登录与多用户权限（单用户部署）
- 网易云/QQ 适配器依赖非官方接口，可能失效
- SQLite 适合 < 5 万文件；更大规模建议迁移 PostgreSQL 并拆分任务队列
