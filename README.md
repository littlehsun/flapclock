# flapclock

Ubuntu 22.04 以上的翻頁時鐘。同一支程式可以當桌面小工具，也可以當全螢幕螢幕保護程式。

## 執行

```bash
./bin/flapclock
./bin/flapclock --screensaver
```

需要 `python3-gi`、`python3-cairo`、`gir1.2-gtk-3.0`、`gir1.2-pango-1.0`。

登入後自動啟動小工具：

```bash
./install.sh
```

小工具可以拖曳，滾輪改變大小。右鍵開啟選單。中鍵立刻進入螢幕保護程式。
