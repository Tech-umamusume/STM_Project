/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2026 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"
#include "tim.h"
#include "gpio.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include "pid.h"
#include "delta.h"
/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/

/* USER CODE BEGIN PV */
volatile PID_t speed_pid = {
    .Kp = 1.0f,
    .Ki = 0.5f,
    .Kd = 0.1f,
    .previous_error = 0.0f,
    .integral = 0.0f,
    .output_max = 999.0f,
    .output_min = -999.0f
};
volatile PID_t position_pid = {
    .Kp = 1.0f,
    .Ki = 0.5f,
    .Kd = 0.1f,
    .previous_error = 0.0f,
    .integral = 0.0f,
    .output_max = 999.0f,
    .output_min = -999.0f
};  //这两个pid的Kp, Ki, Kd值需要根据实际情况来调，这里只是假设
volatile uint16_t previous_count = 0;
volatile uint16_t current_count = 0;
volatile int32_t delta_count = 0;
volatile int32_t total_count = 0;
int32_t target_position = 13 * 30 * 2 * 1; //一圈
volatile float current_speed = 0.0f; //单位为CNT/s
volatile float target_CCR = 0.0f; //目标占空比
float dt = 0.01f; //定时器中断周期，单位为秒
volatile uint8_t check_point = 0U;
uint32_t start_ms = 0U; //用于延时的计时器
/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
/* USER CODE BEGIN PFP */

/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */

/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{

  /* USER CODE BEGIN 1 */

  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
  HAL_Init();

  /* USER CODE BEGIN Init */

  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_TIM1_Init();
  MX_TIM2_Init();
  MX_TIM3_Init();
  /* USER CODE BEGIN 2 */
  //初始化参数
  PID_Reset(&speed_pid);
  PID_Reset(&position_pid);
  Arrival_Reset();

  __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_1, 0); //设置初始占空比为0

  HAL_GPIO_WritePin(AIN1_GPIO_Port, AIN1_Pin, GPIO_PIN_RESET);
  HAL_GPIO_WritePin(AIN2_GPIO_Port, AIN2_Pin, GPIO_PIN_SET);  //初始定义为顺时针

  //逐次启动TIM1——编码器采集，TIM3——PWM输出，TIM2——定时器中断
  __HAL_TIM_SET_COUNTER(&htim1, 0);
  HAL_TIM_Base_Start(&htim1);
  if(HAL_TIM_Encoder_Start(&htim1, TIM_CHANNEL_ALL) != HAL_OK)
  {
      Error_Handler();
  }

  HAL_TIM_Base_Start(&htim3);
  if(HAL_TIM_PWM_Start(&htim3, TIM_CHANNEL_1) != HAL_OK)
  {
      Error_Handler();
  }

  __HAL_TIM_SET_COUNTER(&htim2, 0);
  __HAL_TIM_CLEAR_FLAG(&htim2, TIM_FLAG_UPDATE);
  if(HAL_TIM_Base_Start_IT(&htim2) != HAL_OK)
  {
      Error_Handler();
  }
  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
  }
  /* USER CODE END 3 */
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
  RCC_OscInitStruct.HSEState = RCC_HSE_ON;
  RCC_OscInitStruct.HSEPredivValue = RCC_HSE_PREDIV_DIV1;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  RCC_OscInitStruct.PLL.PLLMUL = RCC_PLL_MUL9;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2) != HAL_OK)
  {
    Error_Handler();
  }
}

/* USER CODE BEGIN 4 */
void HAL_TIM_PeriodElapsedCallback(TIM_HandleTypeDef *htim)
{
    if (htim->Instance == TIM2) //检查是否是TIM2的中断
    {
      /*PID控制工厂，不断运行*/
      //读取编码器计数，并进行基本计算
      current_count = __HAL_TIM_GET_COUNTER(&htim1);
      delta_count = Encoder_Delta(current_count, previous_count);
      total_count += delta_count;
      previous_count = current_count;

      current_speed = (float)delta_count / dt; 

      //进行PID双环串联
      float needed_speed = PID_Update(&position_pid, (float)target_position, (float)total_count, dt);
      target_CCR = PID_Update(&speed_pid, needed_speed, current_speed, dt);

      //判断方向，写入CCR寄存器
      if(target_CCR >= 0)
      {
          HAL_GPIO_WritePin(AIN1_GPIO_Port, AIN1_Pin, GPIO_PIN_RESET);
          HAL_GPIO_WritePin(AIN2_GPIO_Port, AIN2_Pin, GPIO_PIN_SET);
          int32_t ccr_value = (int32_t)target_CCR;
          __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_1, ccr_value);
      }
      else
      {
          HAL_GPIO_WritePin(AIN1_GPIO_Port, AIN1_Pin, GPIO_PIN_SET);
          HAL_GPIO_WritePin(AIN2_GPIO_Port, AIN2_Pin, GPIO_PIN_RESET);
          int32_t ccr_value = (int32_t)(-target_CCR);
          __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_1, ccr_value);
      }

      /*状态机与运动阶段更迭*/
      switch(check_point) //先顺转1圈，再延时500ms，再反转2圈，再延时500ms，以此反复
      {
          case 0: //初始检查点，承顺转1圈，继500ms延迟
              if(Motor_IsArrived((float)(target_position - total_count), current_speed))
              {
                  check_point = 1U;
                  start_ms = HAL_GetTick();
              }
              break;
          case 1: //检查点，承500ms延迟，继反转2圈
              if((HAL_GetTick() - start_ms) >= 500U)
              {
                  check_point = 2U;
                  total_count = 0; //重置计数器，方便计算
                  target_position =- 13 * 30 * 2 * 2; //反转两圈
              }
              break;
          case 2: //检查点，承反转2圈，继500ms延迟
              if(Motor_IsArrived((float)(target_position - total_count), current_speed))
              {
                  check_point = 3U;
                  start_ms = HAL_GetTick();
              }
              break;
          case 3: //检查点，承500ms延迟，继顺转1圈
              if((HAL_GetTick() - start_ms) >= 500U)
              {
                  check_point = 0U;
                  total_count = 0; //重置计数器，方便计算
                  target_position =13 * 30 * 2 * 1; //顺转一圈
              }
              break;
      }
    }
}
/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  /* User can add his own implementation to report the HAL error return state */
  __disable_irq();
  while (1)
  {
  }
  /* USER CODE END Error_Handler_Debug */
}
#ifdef USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
