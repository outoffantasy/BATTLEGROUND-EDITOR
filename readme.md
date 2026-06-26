## 一、docker 环境构建

环境 / 构建命令：

项目开发环境使用 Docker。镜像内部是 Debian 13（`python:3.12-trixie`），Python 虚拟环境在容器内的 `/opt/venv`，Playwright Chromium 在 `/ms-playwright`。源码通过 bind mount 挂载到容器的 `/workspace`。

构建开发镜像：
```bash
docker compose -f docker-compose.yml build dev
```

进入开发容器：
```bash
docker compose -f docker-compose.yml run --rm dev
```

退出当前的 docker container：
```
exit 或者 CTRL + D
```


另：
如果你 增加 或 修改 了项目的依赖，修改了
```
 dockerfile, docker-compose.yml
 uv.lock, pyproject.toml, .python-version
 package-lock.json, package.json, .nvmrc
```
等依赖文件，你需要重新 build 镜像：

```bash
docker compose -f docker-compose.yml build dev
```



## 二、容器内确认环境

容器内确认环境：

```bash
cat /etc/os-release
which python
python --version
python -m playwright --version
node --version
```

容器内运行 backend 检查：

```bash
cd backend
python -m compileall data_process tests
pytest
```

容器内运行 frontend 检查：

```bash
npm --prefix frontend run check
```

如果要清理旧的本机环境，可以手动执行：

```bash
rm -rf backend/.venv backend/.pytest_cache frontend/node_modules
```


## 三、清理 docker
清理没用的旧 image：用来清理 dangling images，比如 `<none>:<none>`。
```
docker image prune
```

清理 build cache：这个会清理构建缓存。
```
docker builder prune
```

清理停止的 container、没用的 network、dangling image、build cache：
```
docker system prune
```


## 四、
从暴雪炉石战棋官网爬数据：https://hearthstone.blizzard.com/en-us/battlegrounds
进去 docker 后，运行
```
python backend/data_process/sources/crawl_blizzard_bg.py
```
如果之前爬过一次，要在之前的基础上再爬，运行：
```
python backend/data_process/sources/crawl_blizzard_bg.py --resume-from data/raw/crawl/blizzard_bg/en-us/<run_id>
```


## 五、

data_process的流程：
sources/sync_raw_hearthstonejson.py
transforms/process_hearthstonejson.py
validators/processed.py
exporters/frontend.py

完整流程入口：
run_pipeline.py
