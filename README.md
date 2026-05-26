# 采集模组串口库

只需 `#include` 即可读到 8 路传感器的 float 数值。

## 安装

将整个 `multi_point_arduino_lib` 目录复制到：

```
C:\Users\<你的用户名>\Documents\Arduino\libraries\
```

重启 Arduino IDE，"文件 → 示例" 里会出现 `SYCMultiSensorLib`。

也可以直接把 `src/MultiSensorParser.h` 和 `src/MultiSensorParser.cpp` 复制到自己的项目目录。

## 协议

每一帧：`0xAA 0xAA` + 48 字节数据 + `0xBB 0xBB`

48 字节数据 = 8 个传感器 × 6 字节，每个传感器：

- 前 3 字节：整数部分（big-endian uint24）
- 后 3 字节：小数部分（big-endian uint24，除以 1000000）

## 最小用法（适配 `huda_serial.py` 上位机）

下面的 sketch 一边用本库解析采集模组发来的二进制帧，一边以 **上位机 `huda_serial.py` 期望的文本格式** 打印到串口，可直接烧录到 Arduino。

```cpp
#include "MultiSensorParser.h"

MultiSensorParser sensors;

void setup() {
    // 与采集模组、Python 脚本默认波特率保持一致：1000000
    sensors.begin(Serial, 1000000);
}

void loop() {
    sensors.update();

    float values[MultiSensorParser::SENSOR_COUNT];
    if (sensors.readValues(values)) {
        // 帧头：huda_serial.py 用这一行作为新帧标记
        Serial.print(F("=== Frame #"));
        Serial.print(sensors.getFrameCount());
        Serial.println(F(" ==="));

        // 每行格式必须是 "Sxx: 数值"，其中 xx 两位补零，否则正则匹配不到
        for (uint8_t i = 0; i < MultiSensorParser::SENSOR_COUNT; i++) {
            Serial.print(F("S"));
            if (i + 1 < 10) Serial.print('0');
            Serial.print(i + 1);
            Serial.print(F(": "));
            Serial.println(values[i], 6);  // 保留 6 位小数
        }
    }
}
```

> 输出格式必须严格匹配以下两条 —— 上位机正则 `S(\d+):\s*(-?\d+(?:\.\d+)?)` 才认得：
> - 帧头行：`=== Frame #123 ===`
> - 数据行：`S01: 0.404050`（S 大写、两位编号、冒号 + 空格、6 位小数）

这段代码也直接做成了示例：`examples/BASIC/BASIC.ino`，在 Arduino IDE "文件 → 示例 → SYCMultiSensorLib → BASIC" 里可以直接打开。

## 用 Python 脚本测试

烧录完上面的 sketch 后，按下面步骤验证整条链路通不通。

### 1. 安装 Python 依赖

要求 Python 3.9+。在仓库目录下执行：

```bash
pip install pyserial PyQt6 pyqtgraph
```

### 2. 接线确认

- 采集模组 TX → Arduino RX（D0）
- 采集模组 GND → Arduino GND
- 采集模组供电按手册接好
- Arduino USB 连电脑

参考仓库根目录的 `接线示意图.jpg` 和 `接线实物图.jpg`。

### 3. 启动上位机

```bash
python huda_serial.py
```

GUI 打开后：

1. **Port** 下拉框选你 Arduino 所在的串口（Windows 下形如 `COM3`，macOS/Linux 下形如 `/dev/ttyUSB0`、`/dev/cu.usbmodem*`）。若没有，点 **Refresh**。
2. **Baud** 选择 `1000000`（必须与 sketch 里 `sensors.begin(Serial, 1000000)` 一致）。
3. 点 **Connect**。状态变绿、右上角 **FPS** 开始跳数即说明数据已通。
4. 中间曲线区会实时画出 8 路通道；右侧 `CURRENT VALUES` 显示当前数值。点单行可隐藏/显示对应曲线。

## API

| 方法 | 说明 |
| --- | --- |
| `begin(Serial, baud)` | 绑定串口并设置波特率，默认 1000000 |
| `update()` | 在 `loop()` 里反复调用，处理输入字节 |
| `readValues(values[8])` | 一次性读出 8 路值，读取后清新数据标志 |
| `getLatestValue(i)` | 获取第 i 路（0..7）最近值 |
| `getFrameCount()` | 累计已解析帧数 |
