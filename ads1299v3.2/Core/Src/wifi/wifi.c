#include "wifi.h"
#include "usart.h"
#include "cmsis_os.h"
#include "string.h"
#include "stdio.h"

// --- ȫ�ֱ��� ---
static volatile uint8_t g_wifi_rx_buffer[WIFI_RX_BUFFER_SIZE];
static volatile uint16_t g_wifi_rx_index = 0;
static uint8_t g_rx_byte; // ����HAL_UART_Receive_IT�ĵ��ֽڻ�����

/**
  * @brief  ��ս��ջ�����
  */
static void wifi_rx_buffer_clear(void)
{
    memset((void*)g_wifi_rx_buffer, 0, WIFI_RX_BUFFER_SIZE);
    g_wifi_rx_index = 0;
}

/**
  * @brief  �ڴ����ж��б����ã����ڽ�������
  *         ���������Ҫ�� stm32f4xx_it.c �� HAL_UART_RxCpltCallback �е���
  */
void Wifi_Rx_Callback(void)
{
    if (g_wifi_rx_index < WIFI_RX_BUFFER_SIZE)
    {
        g_wifi_rx_buffer[g_wifi_rx_index++] = g_rx_byte;
    }
    // �������¿�����һ�ε��ֽڽ����ж�
    HAL_UART_Receive_IT(&WIFI_UART_HANDLE, &g_rx_byte, 1);
}

/**
  * @brief  ����ATָ��ȴ���Ӧ (��ѯ��ʽ)
  */
static bool wifi_send_command(const char* cmd, const char* expected_response, uint32_t timeout)
{
    wifi_rx_buffer_clear();
    printf("WIFI TX: %s", cmd);
    HAL_UART_Transmit(&WIFI_UART_HANDLE, (uint8_t*)cmd, strlen(cmd), 1000);

    uint32_t start_time = osKernelSysTick();
    while (osKernelSysTick() - start_time < timeout)
    {
        // ��ѯ����Ƿ��յ�������
        if (g_wifi_rx_index > 0)
        {
            // ��黺�������Ƿ������������Ӧ
            if (strstr((const char*)g_wifi_rx_buffer, expected_response) != NULL)
            {
                printf("WIFI RX: %s\r\n", (char*)g_wifi_rx_buffer);
                printf("WIFI: Found response \"%s\"\r\n", expected_response);
                return true;
            }
             // ����Ƿ��д�����Ӧ
            if (strstr((const char*)g_wifi_rx_buffer, "ERROR") != NULL)
            {
                printf("WIFI RX: %s\r\n", (char*)g_wifi_rx_buffer);
                printf("WIFI: Module returned ERROR!\r\n");
                return false;
            }
        }
        osDelay(10); // ������ʱ���ͷ�CPU
    }

    printf("WIFI: Timeout waiting for \"%s\".\r\n", expected_response);
    printf("WIFI Final Buffer: %s\r\n", (char*)g_wifi_rx_buffer); // ��ӡ��ʱǰ����������
    return false;
}


/**
  * @brief  ��ʼ��WiFiģ�� (��DMA��ʽ)
  */
bool Wifi_Init(void)
{
    // --- Ӳ����λ ---
    printf("WIFI: Performing a hard reset...\r\n");
    HAL_GPIO_WritePin(WIFI_EN_GPIO_PORT, WIFI_EN_PIN, GPIO_PIN_RESET);
    osDelay(300);
    HAL_GPIO_WritePin(WIFI_EN_GPIO_PORT, WIFI_EN_PIN, GPIO_PIN_SET);
    osDelay(1500);

    // --- ���������жϽ��� ---
    printf("WIFI: Starting UART IT receive...\r\n");
    wifi_rx_buffer_clear();
    // �ؼ���������һ�δ��ڽ����ж�
    HAL_UART_Receive_IT(&WIFI_UART_HANDLE, &g_rx_byte, 1);

    // --- ��ʼATָ������ ---
    // 1. ����ATָ�ȷ��ͨ�Ž���
    if (!wifi_send_command("AT\r\n", "OK", 2000)) {
        printf("WIFI Error: No response to AT command.\r\n");
        return false;
    }
    printf("WIFI: Communication established.\r\n");
    osDelay(200);

    // 2. �رջ��� ATE0
    if (!wifi_send_command("ATE0\r\n", "OK", 2000)) {
        printf("WIFI Warn: Failed to disable echo (ATE0).\r\n");
    } else {
        printf("WIFI: Echo disabled.\r\n");
    }
    osDelay(200);

    // 3. ����WiFiΪStationģʽ (AT+WMODE=1,1)
    if (!wifi_send_command("AT+WMODE=1,1\r\n", "OK", 5000)) {
        printf("WIFI Error: Failed to set STA mode (AT+WMODE=1,1).\r\n");
        return false;
    }
    printf("WIFI: Mode set to Station and saved.\r\n");
    osDelay(500);

    // 4. ���ӵ�ָ����WiFi AP (AT+WJAP)
    char cmd_buffer[128];
    sprintf(cmd_buffer, "AT+WJAP=\"%s\",\"%s\"\r\n", WIFI_SSID, WIFI_PASSWORD);
    
    // ��������ָ���ģ����ȷ���OK��Ȼ���첽�ϱ��¼�
    if (!wifi_send_command(cmd_buffer, "OK", 5000)) {
        printf("WIFI Error: AT+WJAP command failed to execute.\r\n");
        return false;
    }
    printf("WIFI: Connecting to AP...\r\n");
    
    // 5. �ȴ���ȡIP�� URC �¼� "+EVENT:WIFI_GOT_IP"
    // ����������ͬһ���������ȴ��첽�ϱ�
    if (!wifi_send_command("", "+EVENT:WIFI_GOT_IP", WIFI_CONNECT_TIMEOUT)) {
        printf("WIFI Error: Timed out waiting for IP address (+EVENT:WIFI_GOT_IP).\r\n");
        return false;
    }

    printf("WIFI: Initialization successful!\r\n");
    return true;
}

/**
  * @brief  ���ӵ�TCP������
  * @param  ip: ������IP��ַ�ַ���
  * @param  port: �������˿ں�
  * @param  con_id: ���ڷ�������ID��ָ��
  * @retval bool: true��ʾ�ɹ�, false��ʾʧ��
  */
bool Wifi_Connect_TCP_Server(const char* ip, uint16_t port, uint8_t* con_id)
{
    char cmd_buffer[128];
    char response_buffer[32];

    // AT+SOCKET=<type>,<remote host>,<port>
    // type=4 ��ʾ TCP Client
    sprintf(cmd_buffer, "AT+SOCKET=4,%s,%d\r\n", ip, port);
    
    // �ɹ���Ӧ�ĸ�ʽ�� "connect success ConID=<id>"
    if (wifi_send_command(cmd_buffer, "connect success ConID=", 10000))
    {
        // ����Ӧ�н����� Connection ID
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
  * @brief  ͨ��ATָ������� (������ģʽ)
  * @param  con_id: ����ID
  * @param  data: Ҫ���͵�����ָ��
  * @param  len: Ҫ���͵����ݳ���
  * @retval bool: true��ʾ�ɹ�, false��ʾʧ��
  */
bool Wifi_Send_Data(uint8_t con_id, const uint8_t* data, uint16_t len)
{
    char cmd_buffer[64];
    
    // AT+SOCKETSEND=<ConID>,<length>
    sprintf(cmd_buffer, "AT+SOCKETSEND=%d,%d\r\n", con_id, len);
    
    // ����"׼����������"��ָ����ȴ�">"����
    if (!wifi_send_command(cmd_buffer, ">", 2000))
    {
        printf("WIFI Error: AT+SOCKETSEND command failed.\r\n");
        return false;
    }
    
    // �յ�">"��ֱ�ӷ���ԭʼ����
    HAL_UART_Transmit(&WIFI_UART_HANDLE, (uint8_t*)data, len, 2000);
    
    // ���������ݺ󣬵ȴ�ģ�鷵�� "OK"
    // ע�⣺������Ҫһ���µĵȴ���������Ϊwifi_send_command����ջ�����
    // Ϊ�򻯣�����ֱ�ӵȴ�OK
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
  * @brief  ����͸��ģʽ
  */
bool Wifi_Enter_Transparent_Mode(uint8_t con_id) // con_id ������Ȼ���ã��������ӿ�һ����
{
    // �����ֲᣬAT+SOCKETTT ָ����κβ���
    const char* cmd = "AT+SOCKETTT\r\n";
    
    // ���������ĳɹ���Ӧ��һ�� ">" ����
    if (wifi_send_command(cmd, ">", 2000)) {
        printf("WIFI: Entered transparent mode.\r\n");
        return true;
    }

    printf("WIFI Error: Failed to enter transparent mode.\r\n");
    return false;
}


/**
  * @brief  ��͸��ģʽ��ֱ�ӷ���������
  */
void Wifi_Send_Raw_Data(const uint8_t* data, uint16_t len)
{
    HAL_UART_Transmit(&WIFI_UART_HANDLE, (uint8_t*)data, len, 1000);
}
