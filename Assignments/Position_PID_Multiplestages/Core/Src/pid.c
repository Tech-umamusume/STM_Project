#include "pid.h"
#include "stdint.h"
#include "gpio.h"

static uint32_t arrival_start_ms = 0;
static uint8_t arrival_timing = 0;

/*PID重置模块*/
void PID_Reset(volatile PID_t *pid)
{
    pid->previous_error = 0;
    pid->integral = 0;
}

/*PID算法模块*/
float PID_Update(volatile PID_t *pid, float target, float feedback, float dt)
{
    float error = target - feedback;
    float delta_error = error - pid->previous_error;

    float P = pid->Kp * error;
    float I_try = pid->Ki * (pid->integral + error * dt);
    float D = pid->Kd * delta_error / dt;

    float output_try = P + I_try + D;

    // 判断输出，进行保护——关于I的更新 与 结果的保护
    if (output_try > pid->output_max)
    {
        if(error > 0)
        {
            //输出超过最大值，同时error>0，即此时正在向上接近，应当减缓曲线（即减小加速度），所以不更新I
            pid->integral = pid->integral;
        }
        else
        {
            pid->integral += error * dt;
        }

        float I = pid-> Ki * pid->integral;
        output_try = P + I + D;
    }

    else if (output_try < pid->output_min)
    {
        if(error < 0)
        {
            //输出超过最小值，同时error<0，即此时正在向下接近，应当减缓曲线（即减小加速度），所以不更新I
            pid->integral = pid->integral;
        }
        else
        {
            pid->integral += error * dt;
        }

        float I = pid-> Ki * pid->integral;
        output_try = P + I + D;

        if(output_try < pid->output_min)
        {
            output_try = pid->output_min;
        }
    }
    
    else
    {
        //正常范围内，更新I
        pid->integral += error * dt;
    }

    
    if(output_try > pid->output_max)
    {
        output_try = pid->output_max;
    }
    else if(output_try < pid->output_min)
    {
        output_try = pid->output_min;
    }
    
    pid->previous_error = error;

    return output_try;
}

/*判断重置模块*/
void Arrival_Reset(void)
{
    arrival_timing = 0; //此为状态机参数
}

/*判断函数模块*/
uint8_t Motor_IsArrived(float error, float speed)
{
    //核心思想：当error稳定处于一定误差内，当速度降低到一定水平内，当这种稳定状态持续到一定时间阈值后，判断为已经达到target
    //暂时设定error阈值为5，速度阈值为5，时间阈值为100ms——应依据实际情况而定
    
    /*合规性检测，不合规就重置*/
    if((error < -5.0f || error > 5.0f) || (speed < -5.0f || speed > 5.0f))
    {
        arrival_timing = 0;
        arrival_start_ms = 0;
        return 0;
    }

    /*第一次合规*/
    if(arrival_timing == 0)
    {
        arrival_start_ms = HAL_GetTick();
        arrival_timing = 1;
    }

    /*检测是否达到时间阈值*/
    if(((uint32_t)HAL_GetTick() - arrival_start_ms) >= 100U)
    {
        arrival_timing = 0;
        return 1;
    }

    return 0;
}