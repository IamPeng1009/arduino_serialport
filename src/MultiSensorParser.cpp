#include "MultiSensorParser.h"

static const uint8_t HEADER_BYTE = 0xAA;
static const uint8_t TAIL_BYTE   = 0xBB;

// 状态机
enum : uint8_t {
    WAIT_HEADER_1 = 0,
    WAIT_HEADER_2 = 1,
    READ_DATA     = 2,
    WAIT_TAIL_1   = 3,
    WAIT_TAIL_2   = 4
};

MultiSensorParser::MultiSensorParser()
{
    _serial = nullptr;
    _state = WAIT_HEADER_1;
    _index = 0;
    _hasValue = false;
    _newData = false;
    _frameCount = 0;
    _historyIndex = 0;

    memset(_frameData, 0, sizeof(_frameData));
    memset(_latestValues, 0, sizeof(_latestValues));
    memset(_valueHistory, 0, sizeof(_valueHistory));
}

void MultiSensorParser::begin(HardwareSerial &serialPort, unsigned long baudrate)
{
    _serial = &serialPort;
    _serial->begin(baudrate);
}

void MultiSensorParser::update()
{
    if (_serial == nullptr) return;

    while (_serial->available() > 0)
    {
        uint8_t value = static_cast<uint8_t>(_serial->read());

        switch (_state)
        {
        case WAIT_HEADER_1:
            if (value == HEADER_BYTE) _state = WAIT_HEADER_2;
            break;

        case WAIT_HEADER_2:
            if (value == HEADER_BYTE) {
                _state = READ_DATA;
                _index = 0;
            } else {
                _state = WAIT_HEADER_1;
            }
            break;

        case READ_DATA:
            _frameData[_index++] = value;
            if (_index >= FRAME_DATA_SIZE) _state = WAIT_TAIL_1;
            break;

        case WAIT_TAIL_1:
            if (value == TAIL_BYTE) {
                _state = WAIT_TAIL_2;
            } else {
                _state = (value == HEADER_BYTE) ? WAIT_HEADER_2 : WAIT_HEADER_1;
            }
            break;

        case WAIT_TAIL_2:
            if (value == TAIL_BYTE) parseFrame();
            _state = (value == HEADER_BYTE) ? WAIT_HEADER_2 : WAIT_HEADER_1;
            break;

        default:
            _state = WAIT_HEADER_1;
            _index = 0;
            break;
        }
    }
}

void MultiSensorParser::parseFrame()
{
    for (uint8_t i = 0; i < SENSOR_COUNT; i++)
    {
        uint8_t *p = &_frameData[i * SENSOR_SIZE];
        uint32_t intPart  = ((uint32_t)p[0] << 16) | ((uint32_t)p[1] << 8) | p[2];
        uint32_t fracPart = ((uint32_t)p[3] << 16) | ((uint32_t)p[4] << 8) | p[5];

        float v = (float)intPart + (float)fracPart / 1000000.0f;
        _latestValues[i] = v;
        _valueHistory[i][_historyIndex] = v;
    }

    _historyIndex = (_historyIndex + 1) % 200;
    _hasValue = true;
    _newData = true;
    _frameCount++;
}

bool MultiSensorParser::hasValue() const { return _hasValue; }
bool MultiSensorParser::available() const { return _newData; }

bool MultiSensorParser::readValues(float values[SENSOR_COUNT])
{
    if (!_newData) return false;
    for (uint8_t i = 0; i < SENSOR_COUNT; i++) values[i] = _latestValues[i];
    _newData = false;
    return true;
}

float MultiSensorParser::getLatestValue(uint8_t index) const
{
    if (index >= SENSOR_COUNT) return 0.0f;
    return _latestValues[index];
}

float MultiSensorParser::getAverageValue(uint8_t index) const
{
    if (index >= SENSOR_COUNT) return 0.0f;
    float sum = 0.0f;
    for (int i = 0; i < 200; i++) sum += _valueHistory[index][i];
    return sum / 200.0f;
}

unsigned long MultiSensorParser::getFrameCount() const { return _frameCount; }
