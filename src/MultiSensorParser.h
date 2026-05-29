#ifndef MULTI_SENSOR_PARSER_H
#define MULTI_SENSOR_PARSER_H

#include <Arduino.h>

class MultiSensorParser
{
public:
    static const uint8_t SENSOR_COUNT = 8;
    static const uint8_t SENSOR_SIZE = 6;
    static const uint16_t FRAME_DATA_SIZE = SENSOR_COUNT * SENSOR_SIZE;

    // 平均值的历史窗口长度。
    // 注意：8 通道 × N × 4 字节 = 总 SRAM。UNO 只有 2048 字节，
    // 这里取 32（共 1024 字节）以确保 UNO 装得下。如果是 Mega/ESP32
    // 可以放心改成 200 之类的更大值。
    static const uint8_t HISTORY_DEPTH = 32;

    MultiSensorParser();

    // 初始化串口；默认波特率 1000000，与采集模组保持一致
    void begin(HardwareSerial &serialPort, unsigned long baudrate = 1000000);

    // 在 loop() 里反复调用，处理串口流
    void update();

    // 是否收到过任何一帧有效数据
    bool hasValue() const;

    // 是否有新帧到达（读取后会自动清除）
    bool available() const;

    // 一次性读出全部 8 个通道，读取后清除 newData 标志
    bool readValues(float values[SENSOR_COUNT]);

    // 获取单个通道最近一次值，index = 0..7；越界返回 0
    float getLatestValue(uint8_t index) const;

    // 获取单个通道最近 HISTORY_DEPTH 帧的平均值
    float getAverageValue(uint8_t index) const;

    // 累计帧计数（调试用）
    unsigned long getFrameCount() const;

private:
    HardwareSerial *_serial;

    uint8_t _state;
    uint16_t _index;
    uint8_t _frameData[FRAME_DATA_SIZE];

    float _latestValues[SENSOR_COUNT];
    float _valueHistory[SENSOR_COUNT][HISTORY_DEPTH];
    uint8_t _historyIndex;

    bool _hasValue;
    bool _newData;
    unsigned long _frameCount;

    void parseFrame();
};

#endif
