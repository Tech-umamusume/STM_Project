#include "pid.h"
#include "stdint.h"
#include "gpio.h"

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
