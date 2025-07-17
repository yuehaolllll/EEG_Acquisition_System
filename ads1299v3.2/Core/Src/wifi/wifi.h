#ifndef __WIFI_H
#define __WIFI_H

#include "main.h"
#include "stdbool.h"

//----------------- 用户配置区 -----------------
#define WIFI_SSID           "Yue"
#define WIFI_PASSWORD       "12345678"
#define SERVER_IP           "192.168.242.47"
#define SERVER_PORT         8080            

#define WIFI_UART_HANDLE    huart3
#define WIFI_EN_GPIO_PORT   WIFI_EN_GPIO_Port
#define WIFI_EN_PIN         WIFI_EN_Pin



//----------------- 驱动内部定义 -----------------
#define WIFI_RX_BUFFER_SIZE 256  // 可以适当减小，因为是非DMA方式
#define WIFI_CMD_TIMEOUT    5000
#define WIFI_CONNECT_TIMEOUT 20000

// 外部声明
extern UART_HandleTypeDef huart3;

// 函数声明
void Wifi_Rx_Callback(void);
bool Wifi_Init(void);

// 网络操作
bool Wifi_Connect_TCP_Server(const char* ip, uint16_t port, uint8_t* con_id);
bool Wifi_Send_Data(uint8_t con_id, const uint8_t* data, uint16_t len);
bool Wifi_Enter_Transparent_Mode(uint8_t con_id);
void Wifi_Send_Raw_Data(const uint8_t* data, uint16_t len);


#endif /* __WIFI_H */

