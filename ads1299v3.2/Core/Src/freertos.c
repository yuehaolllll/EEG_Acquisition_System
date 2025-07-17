/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * File Name          : freertos.c
  * Description        : Code for freertos applications
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

/* Includes ------------------------------------------------------------------*/
#include "FreeRTOS.h"
#include "task.h"
#include "main.h"
#include "cmsis_os.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include "stdio.h"
#include "ads1299.h"
#include "string.h"
#include "stdbool.h"
#include "wifi.h"
/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */
// Vref is external ±2.5V
#define V_REF_SPAN 5.0f      // VREFP - VREFN = 2.5 - (-2.5) = 5.0V
#define GAIN 24.0f           // From CHnSET = 0x65
#define LSB_UV ( (V_REF_SPAN / GAIN / 8388607.0f) * 1000000.0f ) / 2 

// Vref is internal 4.5V
//#define V_REF_SPAN 4.5f      
//#define GAIN 24.0f           // From CHnSET = 0x65
//#define LSB_UV ( (V_REF_SPAN / GAIN / 8388607.0f) * 1000000.0f ) / 2 


#define BATCH_SIZE 10 // 每积累10个数据点(帧)发送一次
#define FRAME_SIZE 27 

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
/* USER CODE BEGIN Variables */
osMailQId ads1299DataQueueHandle;
osSemaphoreId ads1299Semaphore;
osSemaphoreId networkReadySemaphore; 

uint8_t g_tcp_con_id = 0;     
bool g_is_transparent_mode = false; 

/* USER CODE END Variables */
osThreadId defaultTaskHandle;
osThreadId wifiHandle;
osThreadId ads1299Handle;
osThreadId processTaskHandle;
osThreadId ledHandle;

/* Private function prototypes -----------------------------------------------*/
/* USER CODE BEGIN FunctionPrototypes */
/* USER CODE END FunctionPrototypes */

void StartDefaultTask(void const * argument);
void wifiTask(void const * argument);
void ads1299Task(void const * argument);
void processDataTask(void const * argument);
void ledTask(void const * argument);

void MX_FREERTOS_Init(void); /* (MISRA C 2004 rule 8.1) */

/* GetIdleTaskMemory prototype (linked to static allocation support) */
void vApplicationGetIdleTaskMemory( StaticTask_t **ppxIdleTaskTCBBuffer, StackType_t **ppxIdleTaskStackBuffer, uint32_t *pulIdleTaskStackSize );

/* USER CODE BEGIN GET_IDLE_TASK_MEMORY */


void vApplicationGetIdleTaskMemory( StaticTask_t **ppxIdleTaskTCBBuffer, StackType_t **ppxIdleTaskStackBuffer, uint32_t *pulIdleTaskStackSize )
{
	static StaticTask_t xIdleTaskTCBBuffer;
	static StackType_t xIdleStack[configMINIMAL_STACK_SIZE];
  *ppxIdleTaskTCBBuffer = &xIdleTaskTCBBuffer;
  *ppxIdleTaskStackBuffer = &xIdleStack[0];
  *pulIdleTaskStackSize = configMINIMAL_STACK_SIZE;
  /* place for user code */
}
/* USER CODE END GET_IDLE_TASK_MEMORY */

/**
  * @brief  FreeRTOS initialization
  * @param  None
  * @retval None
*/
void MX_FREERTOS_Init(void) {
  /* USER CODE BEGIN Init */

  /* USER CODE END Init */

  /* USER CODE BEGIN RTOS_MUTEX */
  /* add mutexes, ... */
  /* USER CODE END RTOS_MUTEX */

  /* USER CODE BEGIN RTOS_SEMAPHORES */
	
	osSemaphoreDef(DataReadySem);
  ads1299Semaphore = osSemaphoreCreate(osSemaphore(DataReadySem), 1);
	osSemaphoreWait(ads1299Semaphore, 0);
	

  /* add semaphores, ... */
  /* USER CODE END RTOS_SEMAPHORES */
	
    osSemaphoreDef(NetworkReadySem);
    networkReadySemaphore = osSemaphoreCreate(osSemaphore(NetworkReadySem), 1);
    osSemaphoreWait(networkReadySemaphore, 0);

  /* USER CODE BEGIN RTOS_TIMERS */
  /* start timers, add new ones, ... */
  /* USER CODE END RTOS_TIMERS */

  /* USER CODE BEGIN RTOS_QUEUES */
  /* add queues, ... */
	
	// Use osMailQDef to define a mail queue
	osMailQDef(ads1299DataQueue, 32, ADS1299_Data_t); 
	// Use osMailCreate to create the mail queue and get its handle
	ads1299DataQueueHandle = osMailCreate(osMailQ(ads1299DataQueue), NULL);
  /* USER CODE END RTOS_QUEUES */

  /* Create the thread(s) */
  /* definition and creation of defaultTask */
  osThreadDef(defaultTask, StartDefaultTask, osPriorityNormal, 0, 128);
  defaultTaskHandle = osThreadCreate(osThread(defaultTask), NULL);

  /* definition and creation of wifi */
  osThreadDef(wifi, wifiTask, osPriorityNormal, 0, 1024);
  wifiHandle = osThreadCreate(osThread(wifi), NULL);

  /* definition and creation of ads1299 */
  osThreadDef(ads1299, ads1299Task, osPriorityHigh, 0, 1024);
  ads1299Handle = osThreadCreate(osThread(ads1299), NULL);

  /* definition and creation of processTask */
  osThreadDef(processTask, processDataTask, osPriorityNormal, 0, 1024);
  processTaskHandle = osThreadCreate(osThread(processTask), NULL);

  /* definition and creation of led */
//  osThreadDef(led, ledTask, osPriorityIdle, 0, 128);
//  ledHandle = osThreadCreate(osThread(led), NULL);

  /* USER CODE BEGIN RTOS_THREADS */
  /* USER CODE END RTOS_THREADS */

}

/* USER CODE BEGIN Header_StartDefaultTask */
/**
  * @brief  Function implementing the defaultTask thread.
  * @param  argument: Not used
  * @retval None
  */
/* USER CODE END Header_StartDefaultTask */
void StartDefaultTask(void const * argument)
{
  /* USER CODE BEGIN StartDefaultTask */
  /* Infinite loop */
  for(;;)
  {
    osDelay(1);
  }
  /* USER CODE END StartDefaultTask */
}

/* USER CODE BEGIN Header_wifiTask */
/**
* @brief Function implementing the wifiTask thread.
* @param argument: Not used
* @retval None
*/
/* USER CODE END Header_wifiTask */
void wifiTask(void const * argument)
{
  /* USER CODE BEGIN wifiTask */
    osDelay(1000); 

    // 1. 初始化WiFi并连接到AP
    while (Wifi_Init() != true)
    {
        printf("WiFi Initialization failed, retrying...\r\n");
        osDelay(5000);
    }
    printf("WiFi AP connected.\r\n");
    
    // 2. 连接到TCP服务器
    while(Wifi_Connect_TCP_Server(SERVER_IP, SERVER_PORT, &g_tcp_con_id) != true)
    {
        printf("TCP Connection failed, retrying...\r\n");
        osDelay(5000);
    }
    printf("TCP Server connected.\r\n");

    // 3. 进入透传模式 (推荐)
    if (Wifi_Enter_Transparent_Mode(g_tcp_con_id)) {
        g_is_transparent_mode = true;
    }
		
    if (g_is_transparent_mode) {
        printf("Network is ready. Releasing semaphore.\r\n");
        // 释放网络就绪信号量，通知ads1299Task可以开始工作了
        osSemaphoreRelease(networkReadySemaphore);
    }
    
    // 任务完成使命，挂起
    vTaskSuspend(NULL); 
  /* USER CODE END wifiTask */
}

/* USER CODE BEGIN Header_ads1299Task */
/**
* @brief Function implementing the ADS1299 thread.
* @param argument: Not used
* @retval None
*/
/* USER CODE END Header_ads1299Task */
void ads1299Task(void const * argument)
{
  /* USER CODE BEGIN ads1299Task */

    adsHandle.hspi = &hspi2;
    adsHandle.dataReadySemaphore = ads1299Semaphore;

		// wait for TCP connection
	  osSemaphoreWait(networkReadySemaphore, osWaitForever);
    printf("ADS1299 Task: Network is ready. Initializing ADS1299...\r\n");
		 
    osDelay(1000); 

    ADS1299_Init(&adsHandle);

		/* Infinite loop */
		for(;;)
		{
				// wait for DRDY interrupt
				osSemaphoreWait(ads1299Semaphore, osWaitForever);
				// allocate memory for mail
        ADS1299_Data_t *mail = (ADS1299_Data_t*) osMailAlloc(ads1299DataQueueHandle, osWaitForever);
		
        if (mail != NULL) {
						// read data from SPI, and put data in mail
            ADS1299_ReadData(&adsHandle, mail);
						// put mail in queue
            osMailPut(ads1299DataQueueHandle, mail);
					
						
        }
		}
		/* USER CODE END ads1299Task */
}

/* USER CODE BEGIN Header_processDataTask */
/**
* @brief Function implementing the processTask thread.
* @param argument: Not used
* @retval None
*/
/* USER CODE END Header_processDataTask */
void processDataTask(void const * argument){
  /* USER CODE BEGIN processDataTask */
		static uint32_t count = 0;
    printf("Process Data Task: Ready to receive and transmit data.\r\n");
	
    uint8_t data_batch_buffer[FRAME_SIZE * BATCH_SIZE];
    uint16_t frame_count = 0; 
	
//		typedef struct __attribute__((packed)) {
//    uint8_t header[2]; // 帧头, e.g., 0xA5, 0x5A
//    uint8_t status[3]; // ADS1299 状态字节
//    uint8_t ch_data[8][3]; // 8个通道的数据
//    uint8_t tail[2];   // 帧尾, e.g., 0x0D, 0x0A
//    } EEG_Frame_t;
//		
//		EEG_Frame_t eeg_frame;
//    eeg_frame.header[0] = 0xA5;
//    eeg_frame.header[1] = 0x5A;
//    eeg_frame.tail[0] = 0x0D;
//    eeg_frame.tail[1] = 0x0A;
		
		/* Infinite loop */
    for(;;)
    {
        // 3. 从邮件队列等待并获取采集到的数据
        osEvent evt = osMailGet(ads1299DataQueueHandle, osWaitForever);
			
        if (evt.status == osEventMail) {
            ADS1299_Data_t *raw_data = (ADS1299_Data_t*)evt.value.p;
						memcpy(data_batch_buffer + (frame_count * FRAME_SIZE), (uint8_t*)raw_data, FRAME_SIZE);
						
						frame_count++;
					
						osMailFree(ads1299DataQueueHandle, raw_data);
					
						if (frame_count >= BATCH_SIZE)
            {
                // --- 触发一次批量发送 ---
                // 我们可以在数据包前后加上自定义的帧头帧尾，来标识一个大的数据批次
                uint8_t batch_header[] = {0xAA, 0xBB, 0xCC, 0xDD};
                
                // 1. 发送批次头
                Wifi_Send_Raw_Data(batch_header, sizeof(batch_header));
                
                // 2. 发送整个数据批次缓冲区
                Wifi_Send_Raw_Data(data_batch_buffer, BATCH_SIZE * FRAME_SIZE);

                // 3. (可选) 发送校验和或其他信息

                // 4. 重置帧计数器，为下一批次做准备
                frame_count = 0;
                
                // 打印一个心跳，表示一个大包已发送
                printf("Batch Sent.\r\n");
            }
         }


//            // 4. 将原始数据打包到我们的发送帧中
//            memcpy(eeg_frame.status, raw_data->status, 3);
//            memcpy(eeg_frame.ch_data, raw_data->channel_data, 24);

//            // 5. 通过WiFi发送完整的数据帧
//            // 我们之前已经进入了透传模式，所以直接发送裸数据
//            Wifi_Send_Raw_Data((uint8_t*)&eeg_frame, sizeof(EEG_Frame_t));

            // 6. 释放邮件内存块，这非常重要！
//            osMailFree(ads1299DataQueueHandle, raw_data);

        
    }
  /* USER CODE END processDataTask */		
	
}
//void processDataTask(void const * argument)
//{
//  /* USER CODE BEGIN processDataTask */
//	static uint32_t count = 0;
//	
//  /* Infinite loop */
//  for(;;)
//  {
//		    osEvent evt = osMailGet(ads1299DataQueueHandle, osWaitForever);
//        if (evt.status == osEventMail) {
//            ADS1299_Data_t *data = (ADS1299_Data_t*)evt.value.p;

//            if (count % 10 == 0) { 
//                printf("ADS1299 Data:\r\n");
//                for (uint8_t i = 0; i < 8; i++) {
//                    int32_t raw = (int32_t)((data->channel_data[i][0] << 16) | (data->channel_data[i][1] << 8) | data->channel_data[i][2]);
//                    if (raw & 0x00800000) {
//                        raw |= 0xFF000000;
//                    }
//                    float voltage = raw * LSB_UV;
//										//float voltage = raw;
//                    printf("CH%d: %8.3f uV\r\n", i + 1, voltage);
//                }
//                printf("\r\n");
//            }
//            count++;

//            osMailFree(ads1299DataQueueHandle, data);
//        }
//  }
//  /* USER CODE END processDataTask */
//}

/* USER CODE BEGIN Header_ledTask */
/**
* @brief Function implementing the led thread.
* @param argument: Not used
* @retval None
*/
/* USER CODE END Header_ledTask */
//void ledTask(void const * argument)
//{
//  /* USER CODE BEGIN ledTask */
//  /* Infinite loop */
//  for(;;)
//  {
//		HAL_GPIO_TogglePin(LED1_GPIO_Port,LED1_Pin);
//    osDelay(500);
//  }
//  /* USER CODE END ledTask */
//}

/* Private application code --------------------------------------------------*/
/* USER CODE BEGIN Application */
void HAL_GPIO_EXTI_Callback(uint16_t GPIO_Pin)
{
    if (GPIO_Pin == ADS1299_DRDY_Pin) {
			HAL_GPIO_TogglePin(LED2_GPIO_Port,LED2_Pin);
			osSemaphoreRelease(ads1299Semaphore);
    }
}
/* USER CODE END Application */
