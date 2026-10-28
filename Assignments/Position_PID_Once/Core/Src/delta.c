#include "stdint.h"
#include "delta.h"

int32_t Encoder_Delta(uint16_t current, uint16_t previous)
{
    int32_t delta = (int32_t)current - (int32_t)previous;
    if(delta > 32767)
    {
        delta -= 65536;
    }
    else if(delta < - 32768)
    {
        delta += 65536;
    }
    return delta;
}