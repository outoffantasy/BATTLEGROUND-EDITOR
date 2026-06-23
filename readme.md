环境 / 构建命令：

Python backend:

```bash
cd backend
uv sync --dev
uv run python -m compileall data_process
uv run pytest
```

Frontend:

```bash
cd frontend
nvm use 22
npm install
npm run build
```

1.
神圣火花机器人 和 暗潮战略专家 这两张卡，现在的版本里没有。但是在爬下来的json数据里有。
应该清除掉。

TOTEM 和 DRAENEI 这两个 tribe 也不存在，应该清除掉。


2.
最好能有个自动校验机制吧！
比如每张卡去hsbg校验下？或者去官网校验下？校验下看看这张卡在现在的版本还有没有了。（避免出现 1. 中的问题）

可以再加个字段，如果校验没通过，就说明这张卡的数据有问题。要标注下。


3.
单人酒馆模式 和 双人模式的牌，没有分清楚。
要加一个字段。


4.
这个process_hearthstonejson.py不行，要全删了重写。
data/temp 里的数据也都不行。现在放在这里只是暂时看看罢了。



另：
5.
比如，At the start of combat...、At the end of your turn...、等这种。
现在好像没有这些tag、分类方法。后面可以尝试这加上。
（raw data 里好像有 START_OF_COMBAT 和 END_OF_TURN_TRIGGER 这两个字段）


6.
text的文本没有清洗。
textPlain 应该清洗成text。

7.
catagory 和 kind 的区别，
之所有设置这两个，是因为要处理timewarp的问题。



data_process的流程：
sources/sync_raw_hearthstonejson.py
transforms/process_hearthstonejson.py
validators/processed.py
exporters/frontend.py

完整流程入口：
run_pipeline.py
