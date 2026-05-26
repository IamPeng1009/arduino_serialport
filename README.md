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

## 最小用法

```cpp
#include "MultiSensorParser.h"

MultiSensorParser sensors;

void setup() {
    sensors.begin(Serial, 1000000);
}

void loop() {
    sensors.update();

    float values[MultiSensorParser::SENSOR_COUNT];
    if (sensors.readValues(values)) {
        // values[0] .. values[7] 就是 8 路通道值
    }
}
```

## API

| 方法 | 说明 |
| --- | --- |
| `begin(Serial, baud)` | 绑定串口并设置波特率，默认 1000000 |
| `update()` | 在 `loop()` 里反复调用，处理输入字节 |
| `readValues(values[8])` | 一次性读出 8 路值，读取后清新数据标志 |
| `getLatestValue(i)` | 获取第 i 路（0..7）最近值 |
