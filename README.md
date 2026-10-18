# 桃園機場現在從哪邊降落？

https://kafutw.github.io/tpe-landing/

去桃園看飛機前先查：機場現在用哪一頭起降，該去西南側（華興池、第三航廈機場咖啡）還是東北側（復興航棧）。

- 由 Cloudflare Worker（tpe-landing.mrkafkalin.workers.dev）在資料超過 10 分鐘時用 workflow_dispatch 觸發 `scripts/update.py`：抓 adsb.lol（備援 adsb.fi）桃園機場附近的即時航機位置，找跑道延長線上低空、正在下降或爬升的飛機，看牠往東北（05）還是往西南（23）。
- 這一輪沒有低空飛機時沿用 60 分鐘內最近一次的判斷，再沒有才用 METAR 風向推估。
- 結果寫進 `public/status.json`，`public/index.html` 讀它顯示。

卡夫卡愛旅行 kafu.tw
