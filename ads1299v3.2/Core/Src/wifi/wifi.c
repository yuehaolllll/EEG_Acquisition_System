#include "wifi.h"
#include "usart.h"
#include "cmsis_os.h"
#include "string.h"
#include "stdio.h"

// --- 全局变量 ---
static volatile uint8_t g_wifi_rx_buffer[WIFI_RX_BUFFER_SIZE];
static volatile uint16_t g_wifi_rx_index = 0;
static uint8_t g_rx_byte; // 用于HAL_UART_Receive_IT的单字节缓冲区

/**
  * @brief  清空接收缓冲区
  */
static void wifi_rx_buffer_clear(void)
{
    memset((void*)g_wifi_rx_buffer, 0, WIFI_RX_BUFFER_SIZE);
    g_wifi_rx_index = 0;
}

/**
  * @brief  在串口中断中被调用，用于接收数据
  *         这个函数需要在 stm32f4xx_it.c 的 HAL_UART_RxCpltCallback 中调用
  */
void Wifi_Rx_Callback(void)
{
    if (g_wifi_rx_index < WIFI_RX_BUFFER_SIZE)
    {
        g_wifi_rx_buffer[g_wifi_rx_index++] = g_rx_byte;
    }
    // 立即重新开启下一次单字节接收中断
    HAL_UART_Receive_IT(&WIFI_UART_HANDLE, &g_rx_byte, 1);
}

/**
  * @brief  发送AT指令并等待响应 (轮询方式)
  */
static bool wifi_send_command(const char* cmd, const char* expected_response, uint32_t timeout)
{
    wifi_rx_buffer_clear();
    printf("WIFI TX: %s", cmd);
    HAL_UART_Transmit(&WIFI_UART_HANDLE, (uint8_t*)cmd, strlen(cmd), 1000);

    uint32_t start_time = osKernelSysTick();
    while (osKernelSysTick() - start_time < timeout)
    {
        // 轮询检查是否收到了数据
        if (g_wifi_rx_index > 0)
        {
            // 检查缓冲区中是否包含期望的响应
            if (strstr((const char*)g_wifi_rx_buffer, expected_response) != NULL)
            {
                printf("WIFI RX: %s\r\n", (char*)g_wifi_rx_buffer);
                printf("WIFI: Found response \"%s\"\r\n", expected_response);
                return true;
            }
             // 检查是否有错误响应
            if (strstr((const char*)g_wifi_rx_buffer, "ERROR") != NULL)
            {
                printf("WIFI RX: %s\r\n", (char*)g_wifi_rx_buffer);
                printf("WIFI: Module returned ERROR!\r\n");
                return false;
            }
        }
        osDelay(10); // 短暂延时，释放CPU
    }

    printf("WIFI: Timeout waiting for \"%s\".\r\n", expected_response);
    printf("WIFI Final Buffer: %s\r\n", (char*)g_wifi_rx_buffer); // 打印超时前的最终内容
    return false;
}


/**
  * @brief  初始化WiFi模块 (非DMA方式)
  */
bool Wifi_Init(void)
{
    // --- 硬件复位 ---
    printf("WIFI: Performing a hard reset...\r\n");
    HAL_GPIO_WritePin(WIFI_EN_GPIO_PORT, WIFI_EN_PIN, GPIO_PIN_RESET);
    osDelay(300);
    HAL_GPIO_WritePin(WIFI_EN_GPIO_PORT, WIFI_EN_PIN, GPIO_PIN_SET);
    osDelay(1500);

    // --- 启动串口中断接收 ---
    printf("WIFI: Starting UART IT receive...\r\n");
    wifi_rx_buffer_clear();
    // 关键：启动第一次串口接收中断
    HAL_UART_Receive_IT(&WIFI_UART_HANDLE, &g_rx_byte, 1);

    // --- 开始AT指令流程 ---
    // 1. 测试AT指令，确保通信建立
    if (!wifi_send_command("AT\r\n", "OK", 2000)) {
        printf("WIFI Error: No response to AT command.\r\n");
        return false;
    }
    printf("WIFI: Communication established.\r\n");
    osDelay(200);

    // 2. 关闭回显 ATE0
    if (!wifi_send_command("ATE0\r\n", "OK", 2000)) {
        printf("WIFI Warn: Failed to disable echo (ATE0).\r\n");
    } else {
        printf("WIFI: Echo disabled.\r\n");
    }
    osDelay(200);

    // 3. 设置WiFi为Station模式 (AT+WMODE=1,1)
    if (!wifi_send_command("AT+WMODE=1,1\r\n", "OK", 5000)) {
        printf("WIFI Error: Failed to set STA mode (AT+WMODE=1,1).\r\n");
        return false;
    }
    printf("WIFI: Mode set to Station and saved.\r\n");
    osDelay(500);

    // 4. 连接到指定的WiFi AP (AT+WJAP)
    char cmd_buffer[128];
    sprintf(cmd_buffer, "AT+WJAP=\"%s\",\"%s\"\r\n", WIFI_SSID, WIFI_PASSWORD);
    
    // 发送连接指令后，模块会先返回OK，然后异步上报事件
    if (!wifi_send_command(cmd_buffer, "OK", 5000)) {
        printf("WIFI Error: AT+WJAP command failed to execute.\r\n");
        return false;
    }
    printf("WIFI: Connecting to AP...\r\n");
    
    // 5. 等待获取IP的 URC 事件 "+EVENT:WIFI_GOT_IP"
    // 这里我们用同一个函数来等待异步上报
    if (!wifi_send_command("", "+EVENT:WIFI_GOT_IP", WIFI_CONNECT_TIMEOUT)) {
        printf("WIFI Error: Timed out waiting for IP address (+EVENT:WIFI_GOT_IP).\r\n");
        return false;
    }

    printf("WIFI: Initialization successful!\r\n");
    return true;
}

/**
  * @brief  连接到TCP服务器
  * @param  ip: 服务器IP地址字符串
  * @param  port: 服务器端口号
  * @param  con_id: 用于返回连接ID的指针
  * @retval bool: true表示成功, false表示失败
  */
bool Wifi_Connect_TCP_Server(const char* ip, uint16_t port, uint8_t* con_id)
{
    char cmd_buffer[128];
    char response_buffer[32];

    // AT+SOCKET=<type>,<remote host>,<port>
    // type=4 表示 TCP Client
    sprintf(cmd_buffer, "AT+SOCKET=4,%s,%d\r\n", ip, port);
    
    // 成功响应的格式是 "connect success ConID=<id>"
    if (wifi_send_command(cmd_buffer, "connect success ConID=", 10000))
    {
        // 从响应中解析出 Connection ID
        char* p = strstr((const char*)g_wifi_rx_buffer, "ConID=");
        if (p) {
            *con_id = atoi(p + strlen("ConID="));
            printf("WIFI: TCP connection successful, ConID = %d\r\n", *con_id);
            return true;
        }
    }
    
    printf("WIFI Error: Failed to connect to TCP server.\r\n");
    return false;
}

/**
  * @brief  通过AT指令发送数据 (长数据模式)
  * @param  con_id: 连接ID
  * @param  data: 要发送的数据指针
  * @param  len: 要发送的数据长度
  * @retval bool: true表示成功, false表示失败
  */
bool Wifi_Send_Data(uint8_t con_id, const uint8_t* data, uint16_t len)
{
    char cmd_buffer[64];
    
    // AT+SOCKETSEND=<ConID>,<length>
    sprintf(cmd_buffer, "AT+SOCKETSEND=%d,%d\r\n", con_id, len);
    
    // 发送"准备发送数据"的指令，并等待">"符号
    if (!wifi_send_command(cmd_buffer, ">", 2000))
    {
        printf("WIFI Error: AT+SOCKETSEND command failed.\r\n");
        return false;
    }
    
    // 收到">"后，直接发送原始数据
    HAL_UART_Transmit(&WIFI_UART_HANDLE, (uint8_t*)data, len, 2000);
    
    // 发送完数据后，等待模块返回 "OK"
    // 注意：这里需要一个新的等待函数，因为wifi_send_command会清空缓冲区
    // 为简化，我们直接等待OK
    uint32_t start_time = osKernelSysTick();
    while (osKernelSysTick() - start_time < 2000)
    {
        if (strstr((const char*)g_wifi_rx_buffer, "OK") != NULL)
        {
             printf("WIFI: Data sent successfully.\r\n");
             return true;
        }
        osDelay(10);
    }
    
    printf("WIFI Error: No OK after sending data.\r\n");
    return false;
}

/**
  * @brief  进入透传模式
  */
bool Wifi_Enter_Transparent_Mode(uint8_t con_id) // con_id 参数虽然不用，但保留接口一致性
{
    // 根据手册，AT+SOCKETTT 指令不带任何参数
    const char* cmd = "AT+SOCKETTT\r\n";
    
    // 我们期望的成功响应是一个 ">" 符号
    if (wifi_send_command(cmd, ">", 2000)) {
        printf("WIFI: Entered transparent mode.\r\n");
        return true;
    }

    printf("WIFI Error: Failed to enter transparent mode.\r\n");
    return false;
}


/**
  * @brief  在透传模式下直接发送裸数据
  */
void Wifi_Send_Raw_Data(const uint8_t* data, uint16_t len)
{
    HAL_UART_Transmit(&WIFI_UART_HANDLE, (uint8_t*)data, len, 1000);
}
