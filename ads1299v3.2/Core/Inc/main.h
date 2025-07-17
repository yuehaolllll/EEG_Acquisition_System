/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.h
  * @brief          : Header for main.c file.
  *                   This file contains the common defines of the application.
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2025 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */

/* Define to prevent recursive inclusion -------------------------------------*/
#ifndef __MAIN_H
#define __MAIN_H

#ifdef __cplusplus
extern "C" {
#endif

/* Includes ------------------------------------------------------------------*/
#include "stm32f4xx_hal.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */

/* USER CODE END Includes */

/* Exported types ------------------------------------------------------------*/
/* USER CODE BEGIN ET */

/* USER CODE END ET */

/* Exported constants --------------------------------------------------------*/
/* USER CODE BEGIN EC */

/* USER CODE END EC */

/* Exported macro ------------------------------------------------------------*/
/* USER CODE BEGIN EM */

/* USER CODE END EM */

/* Exported functions prototypes ---------------------------------------------*/
void Error_Handler(void);

/* USER CODE BEGIN EFP */

/* USER CODE END EFP */

/* Private defines -----------------------------------------------------------*/
#define WIFI_EN_Pin GPIO_PIN_1
#define WIFI_EN_GPIO_Port GPIOB
#define CS_Pin GPIO_PIN_12
#define CS_GPIO_Port GPIOB
#define START_Pin GPIO_PIN_7
#define START_GPIO_Port GPIOC
#define RESET_Pin GPIO_PIN_8
#define RESET_GPIO_Port GPIOC
#define SPI3_CS2_Pin GPIO_PIN_11
#define SPI3_CS2_GPIO_Port GPIOA
#define SPI3_CS3_Pin GPIO_PIN_12
#define SPI3_CS3_GPIO_Port GPIOA
#define KEY1_Pin GPIO_PIN_10
#define KEY1_GPIO_Port GPIOC
#define KEY2_Pin GPIO_PIN_11
#define KEY2_GPIO_Port GPIOC
#define KEY3_Pin GPIO_PIN_12
#define KEY3_GPIO_Port GPIOC
#define KEY4_Pin GPIO_PIN_2
#define KEY4_GPIO_Port GPIOD
#define LED1_Pin GPIO_PIN_3
#define LED1_GPIO_Port GPIOB
#define LED2_Pin GPIO_PIN_4
#define LED2_GPIO_Port GPIOB

/* USER CODE BEGIN Private defines */

/* USER CODE END Private defines */

#ifdef __cplusplus
}
#endif

#endif /* __MAIN_H */
