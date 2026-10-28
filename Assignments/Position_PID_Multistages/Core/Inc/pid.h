#ifndef PID_H
#define PID_H

#include <stdint.h>

typedef struct {
    float Kp;
    float Ki;
    float Kd;

    float previous_error;
    float integral;

    float output_max;
    float output_min;
} PID_t;


void Arrival_Reset(void);
uint8_t Motor_IsArrived(float error, float speed);
void PID_Reset(volatile PID_t *pid);
float PID_Update(volatile PID_t *pid, float target, float feedback, float dt);



#endif